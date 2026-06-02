"""DataModels 插件 - 模型发现与导出

封装 IEC 61850 服务端模型的发现、浏览和导出功能。

v3.0+: discover_model() 统一委托给 Iec61850Client 缓存的 IedModel，
不再独立遍历 IED。所有模型发现由 ModelDiscoveryService 统一管理。
"""

from typing import Any

from ...core.linked_list import get_list_from_linked_list
from ...defs.address import (
    extract_ln_class,
    parse_ref,
)
from ...defs.constants import (
    HAS_IEC61850,
    IEC_TYPE_UNKNOWN,
)
from ...defs.da_patterns import (
    BDA_TYPE_MAP,
    DA_PATTERNS,
    EXTRA_DA_INFO,
    KNOWN_BDA_FALLBACK_ONLINE,
    SKIP_DA_NAMES,
    STRUCT_DA_EXPAND_ONLINE,
)
from ...defs.ln_classes import (
    SIGNAL_DOS,
    SKIP_SYSTEM_DOS,
    YC_LN_CLASSES,
    YK_LN_CLASSES,
    YT_LN_CLASSES,
    YX_LN_CLASSES,
)
from ...log import log
from ...model.registry_bridge import build_registry_from_model

if HAS_IEC61850:
    from pyiec61850 import pyiec61850 as iec61850


class DataModelsPlugin:
    """DataModels 插件

    管理模型发现、浏览、导出等功能。
    """

    def __init__(self):
        self._connection = None
        self._registry = None
        self._client = None
        self._initialized = False

    @property
    def name(self) -> str:
        return "datamodels"

    @property
    def available(self) -> bool:
        return HAS_IEC61850

    def initialize(self, connection: Any, **kwargs) -> None:
        self._connection = connection
        self._registry = kwargs.get("registry")
        self._client = kwargs.get("client")
        self._initialized = True
        log.info("DataModels 插件已初始化")

    def shutdown(self) -> None:
        self._connection = None
        self._registry = None
        self._client = None
        self._initialized = False

    # ===== 模型发现 =====

    def discover_model(self) -> list[dict[str, Any]]:
        """从缓存的 IedModel 派生 PointRegistry

        模型发现由 ModelDiscoveryService 统一管理（连接时自动执行），
        本方法仅从已缓存的 IedModel 派生测点注册表。
        """
        if self._client and hasattr(self._client, 'model') and self._client.model is not None:
            log.info("从缓存的 IedModel 派生 PointRegistry...")
            return build_registry_from_model(self._client.model, self._registry)
        log.warning("IedModel 未缓存，无法派生 PointRegistry")
        return []

    # ===== 浏览方法 =====

    def browse_logical_devices(self) -> list[str]:
        """浏览远端 IED 的逻辑设备列表"""
        if not self._connection or not self._connection.is_connected:
            return []
        return self._connection.browse_logical_devices()

    def browse_logical_nodes(self, ld: str) -> list[str]:
        """浏览指定逻辑设备下的逻辑节点列表"""
        if not self._connection or not self._connection.is_connected:
            return []
        try:
            result = iec61850.IedConnection_getLogicalDeviceDirectory(self._connection.connection, ld)
            ln_list = result[0] if isinstance(result, (list, tuple)) else result
            error = result[1] if isinstance(result, (list, tuple)) else 0
            if error != iec61850.IED_ERROR_OK:
                return []
            lns = get_list_from_linked_list(ln_list)
            return sorted(lns)
        except Exception as e:
            log.error(f"浏览逻辑节点失败: {e}")
            return []

    def browse_data_objects(self, ld: str, ln: str) -> list[dict[str, Any]]:
        """浏览指定逻辑节点下的数据对象列表"""
        if not self._connection or not self._connection.is_connected:
            return []
        ln_ref = f"{ld}/{ln}"
        try:
            result = iec61850.IedConnection_getLogicalNodeDirectory(self._connection.connection, ln_ref, 0)
            do_list = result[0] if isinstance(result, (list, tuple)) else result
            error = result[1] if isinstance(result, (list, tuple)) else 0
            if error != iec61850.IED_ERROR_OK or do_list is None:
                return []
            dos = get_list_from_linked_list(do_list)
            do_items = []
            for do_name in dos:
                frame_type = self._infer_frame_type_from_do(ln, do_name)
                do_items.append({"name": do_name, "frame_type": frame_type})
            return do_items
        except Exception as e:
            log.error(f"浏览数据对象失败: {e}")
            return []

    def browse_data_attributes(self, ld: str, ln: str, do_name: str) -> list[dict[str, Any]]:
        """浏览指定数据对象下的数据属性列表"""
        if not self._connection or not self._connection.is_connected:
            return []
        do_ref = f"{ld}/{ln}.{do_name}"
        try:
            result = iec61850.IedConnection_getDataDirectory(self._connection.connection, do_ref)
            da_list = result[0] if isinstance(result, (list, tuple)) else result
            error = result[1] if isinstance(result, (list, tuple)) else 0
            if error != iec61850.IED_ERROR_OK or da_list is None:
                return []
            das = get_list_from_linked_list(da_list)
            da_items = []
            for da_name in das:
                da_info = {"name": da_name, "path": da_name, "fc": "", "type": ""}
                if da_name in DA_PATTERNS:
                    full_path, frame_type, _ = DA_PATTERNS[da_name]
                    da_info["path"] = full_path
                    type_names = {0: "Float32", 1: "Boolean", 2: "Boolean", 3: "Float32"}
                    fc_names = {0: "MX", 1: "ST", 2: "CO", 3: "CO"}
                    da_info["type"] = type_names.get(frame_type, "")
                    da_info["fc"] = fc_names.get(frame_type, "")
                elif da_name in EXTRA_DA_INFO:
                    full_path, fc, type_desc = EXTRA_DA_INFO[da_name]
                    da_info["path"] = full_path
                    da_info["fc"] = fc
                    da_info["type"] = type_desc
                else:
                    da_info["type"] = "Unknown"
                da_items.append(da_info)
            return da_items
        except Exception as e:
            log.debug(f"浏览数据属性失败: {do_ref}, 错误: {e}")
            return []

    def get_discovered_points(self) -> list[dict[str, Any]]:
        """获取当前已映射的测点列表（含 GOOSE 控制块）"""
        result = []
        for addr, ref in self._registry.point_refs.items():
            code = self._extract_code_from_address(addr)
            fc = self._registry.get_fc(addr)
            iec_type = self._registry.get_iec_type(addr) or IEC_TYPE_UNKNOWN
            parsed = parse_ref(addr)
            name = self._registry.get_name(addr) or (parsed[2] if parsed else code)
            da_path = parsed[3] if parsed else ""
            frame_type = 0
            if da_path:
                top_da = da_path.split(".")[0]
                if top_da in DA_PATTERNS:
                    frame_type = DA_PATTERNS[top_da][1]
                elif top_da in EXTRA_DA_INFO:
                    frame_type = 1
            result.append(
                {
                    "address": addr,
                    "frame_type": frame_type,
                    "ref": ref,
                    "code": code,
                    "name": name,
                    "fc": fc,
                    "iec_type": iec_type,
                }
            )
        result.extend(self._registry.discovered_goose_items)
        return result

    # ===== 辅助方法 =====

    def _infer_frame_type_from_do(self, ln_name: str, do_name: str) -> int | None:
        """根据逻辑节点名和数据对象名推断 frame_type"""
        if do_name.startswith("MV_"):
            return 0
        elif do_name.startswith("SPS_"):
            return 1
        elif do_name.startswith("SPC_"):
            return 2
        elif do_name.startswith("APC_"):
            return 3
        if do_name in SKIP_SYSTEM_DOS:
            return 1
        if do_name in SIGNAL_DOS:
            return 1
        ln_class = extract_ln_class(ln_name)
        if ln_class:
            if ln_class in YC_LN_CLASSES:
                return 0
            elif ln_class in YX_LN_CLASSES:
                return 1
            elif ln_class in YK_LN_CLASSES:
                return 2
            elif ln_class in YT_LN_CLASSES:
                return 3
        if do_name.startswith(("TotW", "TotV", "TotA", "TotF", "TotPF", "TotQ")):
            return 0
        if do_name.startswith(("A", "V", "W", "Hz", "PF", "PhV", "PPV", "Amp", "Vol")):
            return 0
        if do_name.startswith(("St", "Ind", "Blk", "Sw")):
            return 1
        if do_name.startswith(("Ctl", "Pos")):
            return 2
        if do_name.startswith(("Spt", "ValW", "Csx")):
            return 3
        return None

    def _infer_da_path(self, frame_type: int) -> str:
        """根据 frame_type 推断数据属性路径"""
        if frame_type == 0:
            return "mag.f"
        elif frame_type == 1:
            return "stVal"
        elif frame_type == 2 or frame_type == 3:
            return "ctlVal"
        return ""

    def _discover_da_paths(self, do_ref: str) -> list[tuple[str, int, str, str]]:
        """通过查询服务器模型发现 DO 下的 DA 路径"""
        try:
            result = iec61850.IedConnection_getDataDirectory(self._connection.connection, do_ref)
            da_list = result[0] if isinstance(result, (list, tuple)) else result
            error = result[1] if isinstance(result, (list, tuple)) else 0
            if error != iec61850.IED_ERROR_OK or da_list is None:
                return []
            das = get_list_from_linked_list(da_list)
            found = []
            for da_name in das:
                if da_name in DA_PATTERNS:
                    da_path, frame_type, iec_type = DA_PATTERNS[da_name]
                    fc_map = {0: "MX", 1: "ST", 2: "CO", 3: "CO"}
                    fc = fc_map.get(frame_type, "")
                    found.append((da_path, frame_type, fc, iec_type))
                elif da_name in EXTRA_DA_INFO:
                    da_path, fc, iec_type = EXTRA_DA_INFO[da_name]
                    if da_name in SKIP_DA_NAMES:
                        continue
                    found.append((da_path, 1, fc, iec_type))
                    if da_name in STRUCT_DA_EXPAND_ONLINE:
                        sub_ref = f"{do_ref}.{da_name}"
                        sub_found = self._discover_sub_da_paths(sub_ref, fc, da_name)
                        found.extend(sub_found)
                else:
                    if da_name in SKIP_DA_NAMES:
                        continue
                    found.append((da_name, 1, "", IEC_TYPE_UNKNOWN))
            return found
        except Exception as e:
            log.debug(f"查询 DA 目录失败: {do_ref}, 错误: {e}")
            return []

    def _discover_sub_da_paths(
        self, parent_ref: str, parent_fc: str, parent_path_prefix: str = ""
    ) -> list[tuple[str, int, str, str]]:
        """递归发现结构体 DA 的子 BDA 路径"""
        try:
            result = iec61850.IedConnection_getDataDirectory(self._connection.connection, parent_ref)
            da_list = result[0] if isinstance(result, (list, tuple)) else result
            error = result[1] if isinstance(result, (list, tuple)) else 0
            if error == iec61850.IED_ERROR_OK and da_list is not None:
                das = get_list_from_linked_list(da_list)
                found = []
                for bda_name in das:
                    full_path = f"{parent_path_prefix}.{bda_name}"
                    iec_type = BDA_TYPE_MAP.get(bda_name, IEC_TYPE_UNKNOWN)
                    found.append((full_path, 1, parent_fc, iec_type))
                if found:
                    return found
            else:
                log.debug(f"查询子 DA 目录失败: {parent_ref}, 使用硬编码回退")
        except Exception as e:
            log.debug(f"查询子 DA 目录异常: {parent_ref}, 错误: {e}, 使用硬编码回退")
        # 回退: 使用硬编码的 BDA 列表
        if parent_path_prefix in KNOWN_BDA_FALLBACK_ONLINE:
            found = []
            for bda_name in KNOWN_BDA_FALLBACK_ONLINE[parent_path_prefix]:
                full_path = f"{parent_path_prefix}.{bda_name}"
                iec_type = BDA_TYPE_MAP.get(bda_name, IEC_TYPE_UNKNOWN)
                found.append((full_path, 1, parent_fc, iec_type))
            return found
        return []

    def _read_du_description(self, do_ref: str) -> str:
        """读取 DO 的描述数据属性值

        不同 IED 的描述属性名/FC 不一致, 依次尝试: dU(DC)、d(DC)、dU(CF)、d(CF)。
        被 _fill_du_names() 调用（iec61850_client.py），system DO 已在调用方过滤。
        """
        if not self._connection or not self._connection.is_connected:
            return ""
        if not hasattr(iec61850, "IedConnection_readStringValue"):
            return ""
        for da_name, fc in (
            ("dU", iec61850.IEC61850_FC_DC),
            ("d", iec61850.IEC61850_FC_DC),
            ("dU", iec61850.IEC61850_FC_CF),
            ("d", iec61850.IEC61850_FC_CF),
        ):
            try:
                [value, error] = iec61850.IedConnection_readStringValue(
                    self._connection.connection, f"{do_ref}.{da_name}", fc
                )
                if error == iec61850.IED_ERROR_OK and value:
                    return str(value).strip()
            except Exception:
                continue
        log.debug(f"读取描述失败 (尝试 dU/d, DC/CF 均无): {do_ref}")
        return ""

    def _extract_code_from_address(self, address: str) -> str:
        """从 address 中提取短编码"""
        parsed = parse_ref(address)
        if parsed:
            ld_inst, ln_name, do_name, da_path = parsed
            if do_name.startswith(("MV_", "SPS_", "SPC_", "APC_")):
                for prefix in ("MV_", "SPS_", "SPC_", "APC_"):
                    if do_name.startswith(prefix):
                        return do_name[len(prefix) :]
                    return f"{ln_name}.{do_name}"
        return address
