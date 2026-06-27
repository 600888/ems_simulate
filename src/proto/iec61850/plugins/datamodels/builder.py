"""IEC 61850 服务端模型构建器

动态创建 IedModel，管理 LD/LN/DO/DA 节点。
从 iec61850_server.py 的模型构建逻辑提取。
"""

from typing import Any

from ...defs.address import is_full_ref, parse_ref, split_ln_name
from ...defs.constants import FC_CO, FC_MX, FC_ST, HAS_IEC61850
from ...defs.ln_classes import YC_LN_CLASSES, YK_LN_CLASSES, YT_LN_CLASSES, YX_LN_CLASSES
from ...log import log

if HAS_IEC61850:
    from pyiec61850 import pyiec61850 as iec61850


class IedModelBuilder:
    """服务端 IedModel 动态构建器

    职责:
    - 动态创建 IedModel
    - 管理测点注册 (add_point)
    - 管理 LD/LN/DO/DA 节点创建与去重
    - 自动补充标准 DA (q, t, dU)
    """

    def __init__(self, model_name: str = "EMS", ied_name: str = "EMSDevice", ld_name: str = "GenericLD"):
        if not HAS_IEC61850:
            raise RuntimeError("pyiec61850 未安装，无法创建 IedModelBuilder")

        self.model_name = model_name
        self.ied_name = ied_name
        self.ld_name = ld_name

        # IedModel
        ied_model_name = self.ied_name if self.ied_name else self.model_name
        self._model = iec61850.IedModel_create(ied_model_name)
        self.model_name = ied_model_name

        # 简单地址模式: 固定逻辑节点引用
        self._ld = None
        self._lln0 = None
        self._mmxu = None
        self._ggio1 = None
        self._ggio2 = None

        # 动态模型: LD/LN 缓存
        self._ld_map: dict[str, Any] = {}
        self._ln_map: dict[str, Any] = {}
        self._do_map: dict[str, Any] = {}
        self._da_map: dict[str, Any] = {}

        # 测点映射
        self._point_refs: dict[str, str] = {}
        self._point_attrs: dict[str, Any] = {}
        self._point_fc: dict[str, str] = {}
        self._point_iec_type: dict[str, str] = {}

        # 标准 DA 列表 (用于服务器启动后初始化默认值)
        self._standard_bda_list: list[tuple] = []

        # 保持底层 C 对象的 Python 引用
        self._keep_alive: list[Any] = []

    @property
    def model(self):
        """获取 IedModel"""
        return self._model

    @property
    def point_refs(self) -> dict[str, str]:
        return self._point_refs

    @property
    def point_attrs(self) -> dict[str, Any]:
        return self._point_attrs

    @property
    def point_fc(self) -> dict[str, str]:
        return self._point_fc

    @property
    def point_iec_type(self) -> dict[str, str]:
        return self._point_iec_type

    @property
    def ld_map(self) -> dict[str, Any]:
        return self._ld_map

    @property
    def ln_map(self) -> dict[str, Any]:
        return self._ln_map

    @property
    def standard_bda_list(self) -> list[tuple]:
        return self._standard_bda_list

    @property
    def keep_alive(self) -> list[Any]:
        return self._keep_alive

    # ===== LD/LN 管理 =====

    def ensure_base_ld(self):
        """懒创建默认 LD 及其逻辑节点"""
        if self._ld is not None:
            return
        self._ld = iec61850.LogicalDevice_create(self.ld_name, self._model)
        self._lln0 = iec61850.LogicalNode_create("LLN0", self._ld)
        self._mmxu = iec61850.LogicalNode_create("MMXU1", self._ld)
        self._ggio1 = iec61850.LogicalNode_create("GGIO1", self._ld)
        self._ggio2 = iec61850.LogicalNode_create("GGIO2", self._ld)
        self._ld_map[self.ld_name] = self._ld
        self._ln_map[f"{self.ld_name}/LLN0"] = self._lln0
        self._ln_map[f"{self.ld_name}/MMXU1"] = self._mmxu
        self._ln_map[f"{self.ld_name}/GGIO1"] = self._ggio1
        self._ln_map[f"{self.ld_name}/GGIO2"] = self._ggio2

    def get_or_create_ld(self, ld_inst: str):
        """获取或创建逻辑设备"""
        if ld_inst in self._ld_map:
            return self._ld_map[ld_inst]
        ld = iec61850.LogicalDevice_create(ld_inst, self._model)
        lln0 = iec61850.LogicalNode_create("LLN0", ld)
        self._ld_map[ld_inst] = ld
        self._ln_map[f"{ld_inst}/LLN0"] = lln0
        log.info(f"IEC61850 动态创建逻辑设备: {ld_inst}")
        return ld

    def get_or_create_ln(self, ld_inst: str, ln_name: str):
        """获取或创建逻辑节点"""
        key = f"{ld_inst}/{ln_name}"
        if key in self._ln_map:
            return self._ln_map[key]
        ld = self.get_or_create_ld(ld_inst)

        # get_or_create_ld 会为新 LD 自动创建 LLN0。若本次请求本身
        # 就是该 LD 的首个 LLN0，请直接复用它，避免创建两个同名节点。
        if key in self._ln_map:
            return self._ln_map[key]

        ln = iec61850.LogicalNode_create(ln_name, ld)
        self._ln_map[key] = ln
        log.info(f"IEC61850 动态创建逻辑节点: {key}")
        return ln

    # ===== 测点添加 =====

    def add_point(self, address, frame_type: int = 0, fc: str = "") -> str | None:
        """添加测点到数据模型"""
        addr_str = str(address)
        if addr_str in self._point_refs:
            return self._point_refs[addr_str]
        if is_full_ref(address):
            return self._add_point_from_ref(address, frame_type, fc)
        else:
            return self._add_point_simple(address, frame_type)

    def _add_point_simple(self, address, frame_type: int) -> str | None:
        """简单地址模式: 使用固定结构添加测点"""
        self.ensure_base_ld()
        addr_str = str(address)
        safe_addr = str(address).replace(".", "_").replace("/", "_").replace("\\", "_").replace("-", "_")
        ref = None

        if frame_type == 0:  # 遥测
            do_name = f"MV_{safe_addr}"
            do_key = f"{self.ld_name}/MMXU1.{do_name}"
            do = self._do_map.get(do_key)
            if do is None:
                do = iec61850.DataObject_create(do_name, iec61850.toModelNode(self._mmxu), 0)
                self._do_map[do_key] = do
                self._keep_alive.append(do)
                self._add_standard_das(do, do_key, "MX", 0, ["mag", "f"])
            mag_key = f"{do_key}.mag"
            mag = self._do_map.get(mag_key)
            if mag is None:
                mag = iec61850.DataObject_create("mag", iec61850.toModelNode(do), 0)
                self._do_map[mag_key] = mag
                self._keep_alive.append(mag)
            da = iec61850.DataAttribute_create(
                "f", iec61850.toModelNode(mag), iec61850.IEC61850_FLOAT32, FC_MX, 0, 0, 0
            )
            ref = f"{self.model_name}{self.ld_name}/MMXU1.{do_name}.mag.f"
            self._point_attrs[addr_str] = da
            self._point_fc[addr_str] = "MX"
            self._point_iec_type[addr_str] = "float"
            self._keep_alive.extend([do_name, da])

        elif frame_type == 1:  # 遥信
            do_name = f"SPS_{safe_addr}"
            do_key = f"{self.ld_name}/GGIO1.{do_name}"
            do = self._do_map.get(do_key)
            if do is None:
                do = iec61850.DataObject_create(do_name, iec61850.toModelNode(self._ggio1), 0)
                self._do_map[do_key] = do
                self._keep_alive.append(do)
                self._add_standard_das(do, do_key, "ST", 1, ["stVal"])
            da = iec61850.DataAttribute_create(
                "stVal", iec61850.toModelNode(do), iec61850.IEC61850_BOOLEAN, FC_ST, 0, 0, 0
            )
            ref = f"{self.model_name}{self.ld_name}/GGIO1.{do_name}.stVal"
            self._point_attrs[addr_str] = da
            self._point_fc[addr_str] = "ST"
            self._point_iec_type[addr_str] = "boolean"
            self._keep_alive.extend([do_name, da])

        elif frame_type == 2:  # 遥控
            do_name = f"SPC_{safe_addr}"
            do_key = f"{self.ld_name}/GGIO1.{do_name}"
            do = self._do_map.get(do_key)
            if do is None:
                do = iec61850.DataObject_create(do_name, iec61850.toModelNode(self._ggio1), 0)
                self._do_map[do_key] = do
                self._keep_alive.append(do)
            da = iec61850.DataAttribute_create(
                "ctlVal", iec61850.toModelNode(do), iec61850.IEC61850_BOOLEAN, FC_CO, 0, 0, 0
            )
            ref = f"{self.model_name}{self.ld_name}/GGIO1.{do_name}.ctlVal"
            self._point_attrs[addr_str] = da
            self._point_fc[addr_str] = "CO"
            self._point_iec_type[addr_str] = "boolean"
            self._keep_alive.extend([do_name, da])

        elif frame_type == 3:  # 遥调
            do_name = f"APC_{safe_addr}"
            do_key = f"{self.ld_name}/GGIO2.{do_name}"
            do = self._do_map.get(do_key)
            if do is None:
                do = iec61850.DataObject_create(do_name, iec61850.toModelNode(self._ggio2), 0)
                self._do_map[do_key] = do
                self._keep_alive.append(do)
            da = iec61850.DataAttribute_create(
                "ctlVal", iec61850.toModelNode(do), iec61850.IEC61850_FLOAT32, FC_CO, 0, 0, 0
            )
            ref = f"{self.model_name}{self.ld_name}/GGIO2.{do_name}.ctlVal"
            self._point_attrs[addr_str] = da
            self._point_fc[addr_str] = "CO"
            self._point_iec_type[addr_str] = "float"
            self._keep_alive.extend([do_name, da])

        if ref:
            self._point_refs[addr_str] = ref
            log.info(f"IEC61850 已成功添加测点(简单模式): address={address}, frame_type={frame_type}, ref={ref}")
        else:
            log.error(f"IEC61850 添加测点失败: address={address}, frame_type={frame_type}")
        return ref

    def _add_point_from_ref(self, address: str, frame_type: int, fc: str = "") -> str | None:
        """完整引用路径模式: 按 ICD 结构动态创建 LD/LN/DO/DA"""
        parsed = parse_ref(address)
        if not parsed:
            log.error(f"IEC61850 无法解析引用路径: {address}")
            return None

        ld_inst, ln_name, do_name, da_path = parsed
        if not da_path:
            ln_class, _ = split_ln_name(ln_name)
            if ln_class in YK_LN_CLASSES:
                da_path = "ctlVal"
            elif ln_class in YT_LN_CLASSES:
                da_path = "Oper.ctlVal"
            elif ln_class in YC_LN_CLASSES:
                da_path = "mag.f"
            elif ln_class in YX_LN_CLASSES:
                da_path = "stVal"
            else:
                log.warning(f"IEC61850 引用路径缺少 DA 路径且无法推断 LN 类别: {address}")
                return None
            log.info(f"IEC61850 引用路径缺少 DA, 根据 LN 类别 '{ln_class}' 推断为: {da_path}")

        addr_str = str(address)
        ln = self.get_or_create_ln(ld_inst, ln_name)
        da_parts = da_path.split(".") if da_path else []

        # 获取或创建 DO
        do_key = f"{ld_inst}/{ln_name}.{do_name}"
        do_obj = self._do_map.get(do_key)
        if do_obj is None:
            do_obj = iec61850.DataObject_create(do_name, iec61850.toModelNode(ln), 0)
            self._do_map[do_key] = do_obj
            self._keep_alive.append(do_obj)
            self._add_standard_das(do_obj, do_key, fc, frame_type, da_parts)

        # 推断 FC
        if not fc:
            fc = self._infer_fc(frame_type, da_parts[0] if da_parts else "")
        fc_const = self._resolve_fc_const(fc)
        if fc_const is None:
            fc_const = FC_MX

        iec_type = self._infer_iec_type(frame_type, da_parts)

        # 沿 da_path 逐级创建
        parent = do_obj
        for i, part in enumerate(da_parts):
            is_leaf = i == len(da_parts) - 1
            part_key = f"{ld_inst}/{ln_name}.{do_name}.{'.'.join(da_parts[: i + 1])}"

            if is_leaf:
                existing_da = self._da_map.get(part_key)
                if existing_da is not None:
                    da = existing_da
                else:
                    da = iec61850.DataAttribute_create(part, iec61850.toModelNode(parent), iec_type, fc_const, 0, 0, 0)
                    self._da_map[part_key] = da
                    self._keep_alive.append(da)
            else:
                existing_obj = self._do_map.get(part_key)
                if existing_obj is not None:
                    parent = existing_obj
                else:
                    sub_obj = iec61850.DataObject_create(part, iec61850.toModelNode(parent), 0)
                    self._do_map[part_key] = sub_obj
                    self._keep_alive.append(sub_obj)
                    parent = sub_obj

        ref = f"{self.model_name}{ld_inst}/{ln_name}.{do_name}.{da_path}"
        self._point_refs[addr_str] = ref
        self._point_fc[addr_str] = fc
        iec_type_str = self._infer_iec_type_str(da_parts)
        self._point_iec_type[addr_str] = iec_type_str

        leaf_key = f"{ld_inst}/{ln_name}.{do_name}.{da_path}"
        leaf_da = self._da_map.get(leaf_key)
        if leaf_da is not None:
            self._point_attrs[addr_str] = leaf_da

        return ref

    # ===== FC/IEC type 推断 =====

    @staticmethod
    def _infer_fc(frame_type: int, top_da: str) -> str:
        DA_FC_MAP = {
            "mag": "MX",
            "instMag": "MX",
            "cVal": "MX",
            "mxVal": "MX",
            "fCVal": "MX",
            "stVal": "ST",
            "ctlVal": "CO",
            "setVal": "CO",
            "q": "MX",
            "t": "MX",
            "dU": "DC",
            "origin": "OR",
            "subVal": "SV",
            "blkEna": "BL",
            "Oper": "CO",
            "SBOw": "CO",
            "Cancel": "CO",
            "SBO": "CO",
        }
        fc = DA_FC_MAP.get(top_da)
        if fc:
            return fc
        return {0: "MX", 1: "ST", 2: "CO", 3: "CO"}.get(frame_type, "MX")

    @staticmethod
    def _resolve_fc_const(fc: str):
        if not HAS_IEC61850:
            return None
        FC_CONST_MAP = {
            "MX": iec61850.IEC61850_FC_MX,
            "ST": iec61850.IEC61850_FC_ST,
            "CO": iec61850.IEC61850_FC_CO,
            "CF": iec61850.IEC61850_FC_CF,
            "DC": iec61850.IEC61850_FC_DC,
            "EX": iec61850.IEC61850_FC_EX,
            "SG": iec61850.IEC61850_FC_SG,
            "SR": iec61850.IEC61850_FC_SR,
            "OR": iec61850.IEC61850_FC_OR,
            "BL": iec61850.IEC61850_FC_BL,
            "SV": iec61850.IEC61850_FC_SV,
            "SP": iec61850.IEC61850_FC_SP,
            "SE": iec61850.IEC61850_FC_SE,
            "US": iec61850.IEC61850_FC_US,
            "MS": iec61850.IEC61850_FC_MS,
            "RP": iec61850.IEC61850_FC_RP,
        }
        return FC_CONST_MAP.get(fc)

    @staticmethod
    def _infer_iec_type(frame_type: int, da_parts: list) -> int:
        if not HAS_IEC61850:
            return 0
        leaf = da_parts[-1] if da_parts else ""
        if leaf == "f":
            return iec61850.IEC61850_FLOAT32
        if frame_type == 3 and leaf in ("ctlVal", "setVal", "wVal"):
            return iec61850.IEC61850_FLOAT32
        if frame_type == 0 and leaf in ("ctlVal", "setVal"):
            return iec61850.IEC61850_FLOAT32
        if leaf in ("stVal", "ctlVal") and frame_type in (1, 2):
            return iec61850.IEC61850_BOOLEAN
        if leaf in ("stVal",) and frame_type == 1:
            return iec61850.IEC61850_INT32
        if leaf in ("validity", "source", "orCat", "ctlNum", "TimeAccuracy"):
            return iec61850.IEC61850_INT32
        if leaf in ("seconds", "detailQuality"):
            return iec61850.IEC61850_INT32
        if leaf == "fraction":
            return iec61850.IEC61850_INT32U
        if leaf in ("dU", "d", "du"):
            return iec61850.IEC61850_VISIBLE_STRING_255
        if leaf in ("orIdent",):
            return iec61850.IEC61850_OCTET_STRING_64
        if frame_type == 0 or frame_type == 3:
            return iec61850.IEC61850_FLOAT32
        return iec61850.IEC61850_BOOLEAN

    @staticmethod
    def _infer_iec_type_str(da_parts: list) -> str:
        leaf = da_parts[-1] if da_parts else ""
        parent = da_parts[-2] if len(da_parts) > 1 else ""
        if leaf == "f":
            return "float"
        if leaf in ("ctlVal", "setVal", "wVal") and parent in ("APC", "setMag"):
            return "float"
        if leaf == "q":
            return "quality"
        if leaf == "t":
            return "timestamp"
        if leaf in (
            "stVal",
            "ctlVal",
            "subEna",
            "blkEna",
            "LeapSecondsKnown",
            "ClockedFailure",
            "ClockNotSynchronized",
        ):
            return "boolean"
        if leaf in (
            "validity",
            "source",
            "orCat",
            "ctlNum",
            "frVal",
            "actVal",
            "frValSec",
            "TimeAccuracy",
            "seconds",
            "fraction",
            "detailQuality",
        ):
            return "integer"
        if leaf in ("dU", "d", "du"):
            return "string"
        return "unknown"

    # libIEC61850 各版本暴露的类型常量可能不同，使用 hasattr 做安全访问
    _IEC_TYPE_CONST_MAP: dict[str, int | None] = {}
    _IEC_TYPE_FALLBACK = None  # int，由 _iec_fallback() 延迟求值

    @classmethod
    def _iec_fallback(cls) -> int:
        """返回 iec_type 回退常量（延迟初始化，避免 import 时 HAS_IEC61850=False）"""
        if cls._IEC_TYPE_FALLBACK is None and HAS_IEC61850:
            cls._IEC_TYPE_FALLBACK = iec61850.IEC61850_INT32
        return cls._IEC_TYPE_FALLBACK or 0

    @classmethod
    def _get_iec_type_const(cls, iec_type: str) -> int:
        """安全获取 IEC61850 类型常量，部分版本未暴露 BITSTRING 等"""
        if not HAS_IEC61850:
            return 0
        const_name = {
            "boolean": "IEC61850_BOOLEAN",
            "float": "IEC61850_FLOAT32",
            "integer": "IEC61850_INT32",
            "string": "IEC61850_VISIBLE_STRING_255",
            "bitstring": "IEC61850_BITSTRING",
            "timestamp": "IEC61850_TIMESTAMP",
        }.get(iec_type, "")
        if const_name:
            const_val = getattr(iec61850, const_name, None)
            if const_val is not None:
                return const_val
            log.debug(f"IEC61850 类型常量 {const_name} 在当前 libIEC61850 中不可用，iec_type={iec_type}")
        return cls._iec_fallback()

    @staticmethod
    def _infer_iec_type_from_str(iec_type: str, da_parts: list) -> int:
        if not HAS_IEC61850:
            return 0
        leaf = da_parts[-1] if da_parts else ""
        if leaf == "f":
            return iec61850.IEC61850_FLOAT32
        if leaf in ("stVal", "ctlVal") and iec_type == "boolean":
            return iec61850.IEC61850_BOOLEAN
        if leaf in ("stVal",) and iec_type == "integer":
            return iec61850.IEC61850_INT32
        if leaf in ("dU", "d", "du"):
            return iec61850.IEC61850_VISIBLE_STRING_255
        if leaf in ("validity", "source", "orCat"):
            return iec61850.IEC61850_INT32
        if leaf == "q":
            return iec61850.IEC61850_QUALITY
        if leaf == "t":
            return iec61850.IEC61850_TIMESTAMP
        return IedModelBuilder._get_iec_type_const(iec_type)

    # ===== 标准 DA =====

    def _add_standard_das(self, do_obj, do_key: str, fc: str, frame_type: int, da_parts: list) -> None:
        """为 DO 自动补充标准 DA 结构 (q, t, dU)"""
        if not fc:
            fc = self._infer_fc(frame_type, da_parts[0] if da_parts else "")
        if not fc:
            fc = "MX"
        if fc in ("CO",):
            return
        qt_fc = "ST" if fc == "ST" else "MX"
        qt_fc_const = self._resolve_fc_const(qt_fc)
        dc_fc_const = self._resolve_fc_const("DC")

        q_key = f"{do_key}.q"
        if q_key not in self._da_map and qt_fc_const:
            q_da = iec61850.DataAttribute_create(
                "q", iec61850.toModelNode(do_obj), iec61850.IEC61850_QUALITY, qt_fc_const, 0, 0, 0
            )
            self._da_map[q_key] = q_da
            self._keep_alive.append(q_da)
            self._standard_bda_list.append((q_da, "q", "quality"))

        t_key = f"{do_key}.t"
        if t_key not in self._da_map and qt_fc_const:
            t_da = iec61850.DataAttribute_create(
                "t", iec61850.toModelNode(do_obj), iec61850.IEC61850_TIMESTAMP, qt_fc_const, 0, 0, 0
            )
            self._da_map[t_key] = t_da
            self._keep_alive.append(t_da)
            self._standard_bda_list.append((t_da, "t", "timestamp"))

        du_key = f"{do_key}.dU"
        if du_key not in self._da_map and dc_fc_const:
            du_da = iec61850.DataAttribute_create(
                "dU", iec61850.toModelNode(do_obj), iec61850.IEC61850_VISIBLE_STRING_255, dc_fc_const, 0, 0, 0
            )
            self._da_map[du_key] = du_da
            self._keep_alive.append(du_da)
            self._standard_bda_list.append((du_da, "dU", "string"))

    # ===== FCDA 模型节点确保 =====

    def ensure_fcda_model_nodes(self, ld_inst: str, ln_name: str, do_da_path: str, fc: str, iec_type: str) -> None:
        """确保 FCDA 引用的 LN/DO/DA 节点存在于数据模型中"""
        ln = self.get_or_create_ln(ld_inst, ln_name)
        parts = do_da_path.split(".")
        if not parts:
            return
        do_name = parts[0]
        da_path_parts = parts[1:]

        do_key = f"{ld_inst}/{ln_name}.{do_name}"
        do_obj = self._do_map.get(do_key)
        if do_obj is None:
            frame_type = {"MX": 0, "ST": 1, "CO": 2, "SP": 3}.get(fc, 0)
            do_obj = iec61850.DataObject_create(do_name, iec61850.toModelNode(ln), 0)
            self._do_map[do_key] = do_obj
            self._keep_alive.append(do_obj)
            self._add_standard_das(do_obj, do_key, fc, frame_type, da_path_parts)

        fc_const = self._resolve_fc_const(fc)
        if fc_const is None:
            fc_const = FC_MX
        iec_type_const = self._infer_iec_type_from_str(iec_type, da_path_parts)

        parent = do_obj
        for i, part in enumerate(da_path_parts):
            is_leaf = i == len(da_path_parts) - 1
            part_key = f"{ld_inst}/{ln_name}.{do_name}.{'.'.join(da_path_parts[: i + 1])}"
            if is_leaf:
                if part_key not in self._da_map:
                    da = iec61850.DataAttribute_create(
                        part, iec61850.toModelNode(parent), iec_type_const, fc_const, 0, 0, 0
                    )
                    self._da_map[part_key] = da
                    self._keep_alive.append(da)
            else:
                existing_obj = self._do_map.get(part_key)
                if existing_obj is not None:
                    parent = existing_obj
                else:
                    sub_obj = iec61850.DataObject_create(part, iec61850.toModelNode(parent), 0)
                    self._do_map[part_key] = sub_obj
                    self._keep_alive.append(sub_obj)
                    parent = sub_obj

    # ===== DA 解析 =====

    def resolve_da(self, address: str):
        """根据地址解析 DataAttribute 对象"""
        addr_str = str(address)
        da = self._point_attrs.get(addr_str)
        if da is not None:
            return da, addr_str
        if is_full_ref(addr_str):
            parsed = parse_ref(addr_str)
            if parsed:
                ld_inst, ln_name, do_name, da_path = parsed
                if not da_path:
                    ln_class, _ = split_ln_name(ln_name)
                    if ln_class in YK_LN_CLASSES:
                        fallback = f"{addr_str}.ctlVal"
                    elif ln_class in YT_LN_CLASSES:
                        fallback = f"{addr_str}.Oper.ctlVal"
                    elif ln_class in YC_LN_CLASSES:
                        fallback = f"{addr_str}.mag.f"
                    elif ln_class in YX_LN_CLASSES:
                        fallback = f"{addr_str}.stVal"
                    else:
                        return None, addr_str
                    da = self._point_attrs.get(fallback)
                    if da is not None:
                        return da, fallback
        return None, addr_str

    # ===== 浏览方法 =====

    def browse_logical_devices(self) -> list[str]:
        ld_list = []
        for ld_inst in self._ld_map:
            prefix = f"{ld_inst}/"
            if any(key.startswith(prefix) for key in self._ln_map):
                ld_list.append(ld_inst)
        return ld_list

    def browse_logical_nodes(self, ld_inst: str) -> list[str]:
        ln_names = []
        prefix = f"{ld_inst}/"
        for key in self._ln_map:
            if key.startswith(prefix):
                ln_names.append(key[len(prefix) :])
        return ln_names

    def browse_data_objects(self, ld_inst: str, ln_name: str) -> list[dict]:
        do_map: dict[str, int | None] = {}
        for address, _ref in self._point_refs.items():
            if not isinstance(address, str) or "/" not in address:
                continue
            parsed = parse_ref(address)
            if parsed and parsed[0] == ld_inst and parsed[1] == ln_name:
                do_name = parsed[2]
                if do_name not in do_map:
                    do_map[do_name] = None
        return [{"name": name, "frame_type": ft} for name, ft in sorted(do_map.items())]

    def browse_data_attributes(self, ld_inst: str, ln_name: str, do_name: str) -> list[dict]:
        da_map: dict[str, dict] = {}
        for address, _ref in self._point_refs.items():
            if not isinstance(address, str) or "/" not in address:
                continue
            parsed = parse_ref(address)
            if parsed and parsed[0] == ld_inst and parsed[1] == ln_name and parsed[2] == do_name:
                da_path = parsed[3]
                if da_path and da_path not in da_map:
                    first_da = da_path.split(".")[0]
                    da_map[da_path] = {"name": first_da, "path": da_path, "fc": "", "type": ""}
        return sorted(da_map.values(), key=lambda x: x["path"])
