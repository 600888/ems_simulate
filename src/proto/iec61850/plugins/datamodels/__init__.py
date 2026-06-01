"""DataModels 插件 - 模型发现与导出

封装 IEC 61850 服务端模型的发现、浏览和导出功能。
从 IEC61850Client 的 discover_model/browse_* 方法迁移而来。
"""

import contextlib
import time
from typing import Any, Dict, List, Optional, Tuple

from ...core.linked_list import get_list_from_linked_list
from ...core.mms_value import mms_value_to_python
from ...defs.address import (
    extract_ln_class,
    infer_fc_from_address,
    infer_iec_type_from_address,
    is_full_ref,
    parse_ref,
)
from ...defs.constants import (
    HAS_IEC61850,
    IEC_TYPE_BOOLEAN,
    IEC_TYPE_FLOAT,
    IEC_TYPE_INTEGER,
    IEC_TYPE_STRING,
    IEC_TYPE_TIMESTAMP,
    IEC_TYPE_UNKNOWN,
)
from ...defs.da_patterns import (
    BDA_TYPE_MAP,
    DA_PATH_TO_FRAME_TYPE,
    DA_PATTERNS,
    ENC_DO_DA_TYPE_OVERRIDE,
    EXTRA_DA_INFO,
    KNOWN_BDA_FALLBACK_ONLINE,
    SKIP_DA_NAMES,
    STRUCT_DA_EXPAND_ONLINE,
)
from ...defs.ln_classes import (
    ALL_LN_CLASSES,
    SIGNAL_DOS,
    SKIP_SYSTEM_DOS,
    YC_LN_CLASSES,
    YK_LN_CLASSES,
    YT_LN_CLASSES,
    YX_LN_CLASSES,
)
from ...log import log
from ..base import Iec61850Plugin

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
        """动态发现并映射服务端的数据模型

        支持两种模型结构:
        1. 简单地址模式: 识别 MV_/SPS_/SPC_/APC_ 前缀的 DO
        2. 动态模型模式 (ICD 导入): 识别没有前缀的 DO，根据 LN 推断 frame_type

        Returns:
            发现的测点列表
        """
        if not self._connection or not self._connection.is_connected:
            return []

        log.info("开始 IEC 61850 动态模型发现...")
        start_time = time.time()
        discovered_points: list[dict[str, Any]] = []
        self._registry.discovered_goose_items.clear()

        # 1. 获取逻辑设备列表
        result = iec61850.IedConnection_getLogicalDeviceList(self._connection.connection)
        ld_list = result[0] if isinstance(result, (list, tuple)) else result
        error = result[1] if isinstance(result, (list, tuple)) else 0

        if error != iec61850.IED_ERROR_OK:
            log.error(f"发现模型失败: 无法获取逻辑设备列表 (错误码: {error})")
            return []

        lds = get_list_from_linked_list(ld_list)
        log.info(f"发现逻辑设备: {lds}")

        for ld in lds:
            # 2. 获取逻辑节点列表
            result = iec61850.IedConnection_getLogicalDeviceDirectory(self._connection.connection, ld)
            ln_list = result[0] if isinstance(result, (list, tuple)) else result
            error = result[1] if isinstance(result, (list, tuple)) else 0

            if error != iec61850.IED_ERROR_OK:
                log.debug(f"跳过逻辑设备 {ld}: 无法获取目录 (错误码: {error})")
                continue

            lns = get_list_from_linked_list(ln_list)
            log.info(f"逻辑设备 {ld} 下发现逻辑节点: {lns}")

            for ln in lns:
                ln_ref = f"{ld}/{ln}"

                # 3. 获取数据对象列表
                dos = []
                for acsi_val in [0, 2, 3, 1]:
                    try:
                        result = iec61850.IedConnection_getLogicalNodeDirectory(
                            self._connection.connection, ln_ref, acsi_val
                        )
                        do_list = result[0] if isinstance(result, (list, tuple)) else result
                        error = result[1] if isinstance(result, (list, tuple)) else 0
                        if error == iec61850.IED_ERROR_OK and do_list is not None:
                            dos = get_list_from_linked_list(do_list)
                            if dos:
                                break
                    except Exception:
                        continue
                log.info(f"逻辑节点 {ln_ref} 下发现数据对象: {dos}")
                if not dos:
                    log.warning(f"跳过逻辑节点 {ln_ref}: 无法获取数据对象目录")
                    continue

                for do in dos:
                    full_do_ref = f"{ln_ref}.{do}"

                    try:
                        # 简单地址模式: DO 名带前缀
                        if do.startswith("MV_"):
                            addr = do[3:]
                            da_path = "mag.f"
                            frame_type = 0
                            fc = "MX"
                            iec_type = IEC_TYPE_FLOAT
                            ref = f"{full_do_ref}.{da_path}"
                            address = f"{ld}/{ln}.{do}.{da_path}"
                            self._registry.set_ref(address, ref)
                            self._registry.set_fc(address, fc)
                            self._registry.set_iec_type(address, iec_type)
                            discovered_points.append(
                                {
                                    "address": address,
                                    "frame_type": frame_type,
                                    "ref": ref,
                                    "code": addr,
                                    "fc": fc,
                                    "iec_type": iec_type,
                                }
                            )
                        elif do.startswith("SPS_"):
                            addr = do[4:]
                            da_path = "stVal"
                            frame_type = 1
                            fc = "ST"
                            iec_type = IEC_TYPE_BOOLEAN
                            ref = f"{full_do_ref}.{da_path}"
                            address = f"{ld}/{ln}.{do}.{da_path}"
                            self._registry.set_ref(address, ref)
                            self._registry.set_fc(address, fc)
                            self._registry.set_iec_type(address, iec_type)
                            discovered_points.append(
                                {
                                    "address": address,
                                    "frame_type": frame_type,
                                    "ref": ref,
                                    "code": addr,
                                    "fc": fc,
                                    "iec_type": iec_type,
                                }
                            )
                        elif do.startswith("SPC_"):
                            addr = do[4:]
                            da_path = "ctlVal"
                            frame_type = 2
                            fc = "CO"
                            iec_type = IEC_TYPE_BOOLEAN
                            ref = f"{full_do_ref}.{da_path}"
                            address = f"{ld}/{ln}.{do}.{da_path}"
                            self._registry.set_ref(address, ref)
                            self._registry.set_fc(address, fc)
                            self._registry.set_iec_type(address, iec_type)
                            discovered_points.append(
                                {
                                    "address": address,
                                    "frame_type": frame_type,
                                    "ref": ref,
                                    "code": addr,
                                    "fc": fc,
                                    "iec_type": iec_type,
                                }
                            )
                        elif do.startswith("APC_"):
                            addr = do[4:]
                            da_path = "ctlVal"
                            frame_type = 3
                            fc = "CO"
                            iec_type = IEC_TYPE_FLOAT
                            ref = f"{full_do_ref}.{da_path}"
                            address = f"{ld}/{ln}.{do}.{da_path}"
                            self._registry.set_ref(address, ref)
                            self._registry.set_fc(address, fc)
                            self._registry.set_iec_type(address, iec_type)
                            discovered_points.append(
                                {
                                    "address": address,
                                    "frame_type": frame_type,
                                    "ref": ref,
                                    "code": addr,
                                    "fc": fc,
                                    "iec_type": iec_type,
                                }
                            )
                        else:
                            # 动态模型模式 (ICD 导入)
                            da_paths = self._discover_da_paths(full_do_ref)
                            du_desc = self._read_du_description(full_do_ref)

                            if da_paths:
                                for da_path, frame_type, fc, iec_type in da_paths:
                                    # ENC 类型 DO 的 stVal/ctlVal 是整型而非布尔
                                    if do in ENC_DO_DA_TYPE_OVERRIDE:
                                        da_top = da_path.split(".")[0]
                                        override_type = ENC_DO_DA_TYPE_OVERRIDE[do].get(da_top)
                                        if override_type:
                                            iec_type = override_type
                                    ref = f"{full_do_ref}.{da_path}"
                                    address = f"{ld}/{ln}.{do}.{da_path}"
                                    code = f"{ln}.{do}.{da_path}"
                                    name = du_desc if du_desc else do
                                    self._registry.set_ref(address, ref)
                                    self._registry.set_fc(address, fc)
                                    self._registry.set_iec_type(address, iec_type)
                                    self._registry.set_name(address, name)
                                    discovered_points.append(
                                        {
                                            "address": address,
                                            "frame_type": frame_type,
                                            "ref": ref,
                                            "code": code,
                                            "name": name,
                                            "fc": fc,
                                            "iec_type": iec_type,
                                        }
                                    )
                            else:
                                # 回退到推断模式
                                frame_type = self._infer_frame_type_from_do(ln, do)
                                if frame_type is None:
                                    log.debug(f"跳过数据对象 {full_do_ref}: 无法推断测点类型")
                                    continue

                                da_path = self._infer_da_path(frame_type)
                                ref = f"{full_do_ref}.{da_path}"
                                address = f"{ld}/{ln}.{do}.{da_path}"
                                code = f"{ln}.{do}.{da_path}"
                                name = du_desc if du_desc else do
                                fc_map = {0: "MX", 1: "ST", 2: "CO", 3: "CO"}
                                fc = fc_map.get(frame_type, "")
                                iec_type = IEC_TYPE_FLOAT if frame_type in (0, 3) else IEC_TYPE_BOOLEAN
                                if do in ENC_DO_DA_TYPE_OVERRIDE:
                                    override_type = ENC_DO_DA_TYPE_OVERRIDE[do].get(da_path)
                                    if override_type:
                                        iec_type = override_type
                                self._registry.set_ref(address, ref)
                                self._registry.set_fc(address, fc)
                                self._registry.set_iec_type(address, iec_type)
                                self._registry.set_name(address, name)
                                discovered_points.append(
                                    {
                                        "address": address,
                                        "frame_type": frame_type,
                                        "ref": ref,
                                        "code": code,
                                        "name": name,
                                        "fc": fc,
                                        "iec_type": iec_type,
                                    }
                                )
                    except Exception as e:
                        log.error(f"解析测点地址失败: {do}, 错误: {e}")
                        continue

                # 4. 对于 LLN0, 发现 GOOSE 控制块
                go_cb_names: list[str] = []
                if ln == "LLN0" and hasattr(iec61850, "ACSI_CLASS_GoCB"):
                    go_cb_names = self._discover_goose_control_blocks(ld, ln_ref)

                    for cb_name in go_cb_names:
                        goose_item = self._read_goose_control_block_info(ld, cb_name)
                        discovered_points.append(goose_item)
                        self._registry.discovered_goose_items.append(goose_item)
                        log.info(
                            f"发现 GOOSE 控制块: {goose_item['go_cb_ref']}, "
                            f"appID=0x{(goose_item.get('app_id') or 0):04X}, "
                            f"ds={goose_item.get('data_set_ref', '')}"
                        )

                if not go_cb_names and ln == "LLN0":
                    log.warning(f"LLN0({ln_ref}) 下未发现任何 GoCB (可能服务器不支持 GoCB 浏览)")

        # 5. 发现 DataSet
        try:
            if self._client:
                self._registry.discovered_datasets = self._client.discover_datasets()
            log.info(f"动态发现完成, 发现 {len(self._registry.discovered_datasets)} 个 DataSet")
        except Exception as e:
            log.debug(f"自动发现 DataSet 失败: {e}")
            self._registry.discovered_datasets = []

        log.info(
            f"IEC 61850 动态发现完成, 耗时: {time.time() - start_time:.2f}s, "
            f"发现并映射了 {len(discovered_points)} 个测点"
        )
        return discovered_points

    def _discover_goose_control_blocks(self, ld: str, ln_ref: str) -> list[str]:
        """发现 LLN0 下的 GOOSE 控制块名称列表"""
        go_cb_names = []
        try:
            gse_result = iec61850.IedConnection_getLogicalNodeDirectory(
                self._connection.connection, ln_ref, int(iec61850.ACSI_CLASS_GoCB)
            )
            gse_list = gse_result[0] if isinstance(gse_result, (list, tuple)) else gse_result
            gse_error = gse_result[1] if isinstance(gse_result, (list, tuple)) else 0
            if gse_error == iec61850.IED_ERROR_OK and gse_list is not None:
                names = get_list_from_linked_list(gse_list)
                for name in names or []:
                    if name and name not in go_cb_names:
                        try:
                            goena_ref = f"{ln_ref}.{name}.GoEna"
                            [_, goena_err] = iec61850.IedConnection_readBooleanValue(
                                self._connection.connection, goena_ref, iec61850.IEC61850_FC_GO
                            )
                            if goena_err == iec61850.IED_ERROR_OK:
                                go_cb_names.append(name)
                        except Exception:
                            pass
        except Exception:
            pass
        return go_cb_names

    def _read_goose_control_block_info(self, ld: str, cb_name: str) -> dict[str, Any]:
        """读取 GOOSE 控制块详细信息

        优先使用 libiec61850 的 GoCB 专用 API (IedConnection_getGoCBValues)，
        它能正确读取 appID（位于目标地址子结构）、datSet、confRev、goID；
        逐属性读取 .appID 叶子节点在多数 IED 上不可用，会导致 APPID/DataSet 为空。
        """
        app_id = None
        dat_set = ""
        conf_rev = 0
        go_id = ""

        # libiec61850 的 getGoCBValues/create 要求引用含 FC 段 .GO.，
        # 形如 LD/LLN0.GO.gcbName；缺少则返回 OBJECT_NOT_FOUND，导致属性全空
        gocb_ref = f"{ld}/LLN0.GO.{cb_name}"
        gocb = None
        try:
            gocb = iec61850.ClientGooseControlBlock_create(gocb_ref)
            if gocb is not None:
                result = iec61850.IedConnection_getGoCBValues(self._connection.connection, gocb_ref, gocb)
                err = (result[1] if len(result) > 1 else 0) if isinstance(result, (list, tuple)) else result
                if err != iec61850.IED_ERROR_OK:
                    log.warning(f"getGoCBValues 失败: ref={gocb_ref}, err={err}")
                    with contextlib.suppress(Exception):
                        iec61850.ClientGooseControlBlock_destroy(gocb)
                    gocb = None
            else:
                log.warning(f"ClientGooseControlBlock_create 失败: ref={gocb_ref}")
        except Exception as e:
            log.warning(f"getGoCBValues 异常: ref={gocb_ref}, {type(e).__name__}: {e}")
            gocb = None

        if gocb is not None:
            try:
                appid_val = iec61850.ClientGooseControlBlock_getDstAddress_appid(gocb)
                if appid_val is not None:
                    app_id = int(appid_val)
            except Exception as e:
                log.debug(f"读取 GoCB appID 失败: {e}")
            try:
                dat_set = str(iec61850.ClientGooseControlBlock_getDatSet(gocb) or "")
            except Exception as e:
                log.debug(f"读取 GoCB datSet 失败: {e}")
            try:
                conf_rev = int(iec61850.ClientGooseControlBlock_getConfRev(gocb) or 0)
            except Exception as e:
                log.debug(f"读取 GoCB confRev 失败: {e}")
            try:
                go_id = str(iec61850.ClientGooseControlBlock_getGoID(gocb) or "")
            except Exception as e:
                log.debug(f"读取 GoCB goID 失败: {e}")
            with contextlib.suppress(Exception):
                iec61850.ClientGooseControlBlock_destroy(gocb)

        go_cb_ref = f"{ld}/LLN0$GO${cb_name}"
        return {
            "_type": "goose",
            "go_cb_ref": go_cb_ref,
            "go_id": go_id,
            "app_id": app_id,
            "data_set_ref": dat_set,
            "conf_rev": conf_rev,
            "name": cb_name,
            "ld_inst": ld,
        }

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
                    full_path, frame_type = DA_PATTERNS[da_name]
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

    def _infer_frame_type_from_do(self, ln_name: str, do_name: str) -> Optional[int]:
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
