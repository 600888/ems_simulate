"""
IEC 61850 MMS 服务端封装
基于 pyiec61850 (libiec61850 Python bindings) 实现动态数据模型的 IED Server

支持两种地址格式:
  1. 简单地址 (如 "1", "2"): 使用固定的 MMXU1/GGIO1/GGIO2 逻辑节点结构
  2. 完整引用路径 (如 "MEAS/M0GGIO1.AnIn1.mag.f"): 按 ICD 文件结构动态创建 LD/LN/DO/DA
"""

import threading
import time
from typing import Any, Dict, List, Optional, Tuple, Union
from .log import log
from .iec61850_defs import ALL_LN_CLASSES, YK_LN_CLASSES, YT_LN_CLASSES, YC_LN_CLASSES, YX_LN_CLASSES

try:
    from pyiec61850 import pyiec61850 as iec61850
    HAS_IEC61850 = True
except ImportError:
    HAS_IEC61850 = False
    log.warning("pyiec61850 未安装，IEC 61850 功能不可用。请执行: pip install pyiec61850")


# IEC 61850 功能约束 (Functional Constraint)
FC_MX = None  # 测量值 (Measured Value)
FC_ST = None  # 状态 (Status)
FC_CO = None  # 控制 (Control)
FC_CF = None  # 配置 (Configuration)

if HAS_IEC61850:
    FC_MX = iec61850.IEC61850_FC_MX
    FC_ST = iec61850.IEC61850_FC_ST
    FC_CO = iec61850.IEC61850_FC_CO
    FC_CF = iec61850.IEC61850_FC_CF


def _is_full_ref(address) -> bool:
    """判断地址是否为完整的 IEC 61850 引用路径 (包含 '/')"""
    return isinstance(address, str) and '/' in address


def _parse_ref(address: str):
    """解析完整 IEC 61850 引用路径

    格式: {ld_inst}/{ln_name}.{do_name}.{da_path}
    例: "MEAS/M0GGIO1.AnIn1.mag.f" -> ("MEAS", "M0GGIO1", "AnIn1", "mag.f")

    Returns:
        (ld_inst, ln_name, do_name, da_path) 或 None (解析失败)
    """
    try:
        parts = address.split('/', 1)
        if len(parts) != 2:
            return None
        ld_inst = parts[0]
        rest = parts[1]
        # 至少要有 LN.DO 两部分
        rest_parts = rest.split('.', 2)
        if len(rest_parts) < 2:
            return None
        ln_name = rest_parts[0]
        do_name = rest_parts[1]
        da_path = rest_parts[2] if len(rest_parts) > 2 else ""
        return (ld_inst, ln_name, do_name, da_path)
    except Exception:
        return None


def _split_ln_name(ln_name: str) -> Tuple[str, str]:
    """将完整 LN 名称拆分为 (ln_class, ln_inst)

    IEC 61850 LN 命名格式: [prefix]{lnClass}[inst]
    例如: "MMCL4" → ("MMCL", "4")
          "M0GGIO1" → ("GGIO", "1")    # prefix=M0, class=GGIO, inst=1
          "LLN0" → ("LLN0", "")
          "MMXU1" → ("MMXU", "1")

    Args:
        ln_name: 完整 LN 名称

    Returns:
        (ln_class, ln_inst) 元组
    """
    if not ln_name:
        return ("", "")
    if ln_name == "LLN0":
        return ("LLN0", "")

    # 方法1: 从字母部分提取已知 LN class（处理含前缀的情况如 "M0GGIO1"）
    alpha = ''.join(c for c in ln_name if c.isalpha())
    known_class = None
    if alpha in ALL_LN_CLASSES:
        known_class = alpha
    else:
        for i in range(1, len(alpha)):
            suffix = alpha[i:]
            if suffix in ALL_LN_CLASSES:
                known_class = suffix
                break

    if known_class:
        idx = ln_name.find(known_class)
        if idx >= 0:
            inst_part = ln_name[idx + len(known_class):]
            return (known_class, inst_part)

    # 方法2: 回退 - 按最后一个字母/数字边界拆分
    import re
    match = re.match(r'^(\D+)(\d*)$', ln_name)
    if match:
        return (match.group(1), match.group(2))

    return (ln_name, "")


class IEC61850Server:
    """IEC 61850 MMS 服务端

    使用 pyiec61850 动态创建 IedModel 和 IedServer，
    将测点映射到 IEC 61850 数据模型。

    支持两种地址格式:
    1. 简单地址 (int/str 不含 '/'): 使用固定结构
        IedModel (model_name)
          └── LogicalDevice (ld_name)
                ├── LLN0
                ├── MMXU1 (遥测) → MV_{address}.mag.f
                ├── GGIO1 (遥信/遥控) → SPS_{address}.stVal / SPC_{address}.ctlVal
                └── GGIO2 (遥调) → APC_{address}.ctlVal

    2. 完整引用路径 (含 '/'): 按 ICD 结构动态创建
        IedModel (model_name)
          └── LogicalDevice ({ld_inst})   ← 动态创建
                ├── LLN0
                └── {ln_name}             ← 动态创建
                      └── {do_name}       ← 使用原始 DO 名
                            └── {da_path} ← 按 frame_type 创建
    """

    def __init__(
        self,
        ip: str = "0.0.0.0",
        port: int = 102,
        model_name: str = "EMS",
        ied_name: str = "EMSDevice",
        ld_name: str = "GenericLD",
    ):
        if not HAS_IEC61850:
            raise RuntimeError("pyiec61850 未安装，无法创建 IEC 61850 服务器")

        self.ip = ip
        self.port = port
        self.model_name = model_name
        self.ied_name = ied_name
        self.ld_name = ld_name

        self._server = None
        self._model = None
        self._ld = None
        self._is_running = False

        # 简单地址模式: 固定逻辑节点引用
        self._lln0 = None
        self._mmxu = None   # 遥测逻辑节点
        self._ggio1 = None  # 遥信/遥控逻辑节点
        self._ggio2 = None  # 遥调逻辑节点

        # 动态模型: LD/LN 缓存 (用于完整引用路径)
        self._ld_map: Dict[str, Any] = {}   # ld_inst -> LD 对象
        self._ln_map: Dict[str, Any] = {}   # "ld_inst/ln_name" -> LN 对象
        # DO/DA 去重缓存: 防止同一 LN 下重复创建同名 DO/DA
        self._do_map: Dict[str, Any] = {}   # "ld_inst/ln_name.do_name[.sub_do]" -> DO 对象
        self._da_map: Dict[str, Any] = {}   # "ld_inst/ln_name.do_name.da_path" -> DA 对象

        # 地址 -> MMS 引用路径 的映射
        self._point_refs: Dict[str, str] = {}  # address -> ref
        # 地址 -> DataAttribute 对象的映射
        self._point_attrs: Dict[str, Any] = {}
        # 地址 -> FC 的映射
        self._point_fc: Dict[str, str] = {}
        # 地址 -> iec_type 的映射
        self._point_iec_type: Dict[str, str] = {}

        # 集成 GOOSE 发布配置
        self._goose_interface: str = "eth0"          # GOOSE 网络接口
        self._goose_publishing_enabled: bool = False  # GOOSE 以太网发布是否启用
        self._goose_cb_list: List[Dict[str, Any]] = []  # 跟踪已注册的 GoCB 条目
        # DataSet 信息目录（用于前端结构树展示）
        # 每个元素: {ref, name, ld, member_count, members: [{ref, fc, iec_type}]}
        self._dataset_catalog: List[Dict[str, Any]] = []

        # 模型变更标记：当 GSEControlBlock/DataSet 在 IedServer_create 之后添加时，
        # MMS 命名空间不会自动更新，需要销毁并重建 IedServer 才能让客户端发现新节点。
        # 此标记在 add_goose_control_block / register_dataset 中设置，
        # 在 apply_model_changes() 中消费。
        self._model_changed: bool = False

        # 待注册 GoCB/DataSet 队列：当 server_map 中找不到对应 server 时，
        # 将 GoCB 配置暂存于此队列，待 server 启动前统一注册到模型。
        # 每个元素: {"type": "gocb"|"dataset", **kwargs}
        self._pending_goose_registrations: List[Dict[str, Any]] = []

        # 标准 DA (q, t, dU) 引用列表，
        # 用于服务器启动后初始化默认值，避免 IED Scout 因值为空显示红色感叹号
        # 每个元素: (da_object, da_name, iec_type_str)
        # iec_type_str: "quality", "timestamp", "string"
        self._standard_bda_list: List[tuple] = []

        # 保持底层 C 对象的 Python 引用，防止被垃圾回收导致崩溃
        self._keep_alive: List[Any] = []

        self._build_base_model()

    def _build_base_model(self):
        """构建基础 IED 模型（只含 IedModel，LD/LN 在添加测点时懒创建）

        使用 ied_name 作为 IED 模型名称 (与 ICD 文件的 iedName 保持一致)。
        model_name 同时作为 MMS 引用路径前缀，应与 ied_name 一致。

        注意：不再预创建默认 LD (GenericLD) 和逻辑节点 (MMXU1/GGIO1/GGIO2)，
        避免 ICD 导入模式下服务器模型出现多余的 Logical Device，
        导致 IEDScout 等客户端加载 CID 文件连接时报 LIB0406 结构不匹配错误。
        """
        ied_model_name = self.ied_name if self.ied_name else self.model_name
        self._model = iec61850.IedModel_create(ied_model_name)
        # 同步 model_name 确保 MMS 引用路径前缀与 IED 名称一致
        self.model_name = ied_model_name

    def _ensure_base_ld(self):
        """懒创建默认 LD (simple address mode) 及其逻辑节点

        仅在添加简单地址测点时调用，避免 ICD 导入模式下产生多余的 GenericLD。
        """
        if self._ld is not None:
            return
        self._ld = iec61850.LogicalDevice_create(self.ld_name, self._model)
        self._lln0 = iec61850.LogicalNode_create("LLN0", self._ld)

        # 预创建简单地址模式的逻辑节点
        self._mmxu = iec61850.LogicalNode_create("MMXU1", self._ld)
        self._ggio1 = iec61850.LogicalNode_create("GGIO1", self._ld)
        self._ggio2 = iec61850.LogicalNode_create("GGIO2", self._ld)

        # 注册默认 LD 和其 LN (用于去重, 避免 _get_or_create_ln 重复创建)
        self._ld_map[self.ld_name] = self._ld
        self._ln_map[f"{self.ld_name}/LLN0"] = self._lln0
        self._ln_map[f"{self.ld_name}/MMXU1"] = self._mmxu
        self._ln_map[f"{self.ld_name}/GGIO1"] = self._ggio1
        self._ln_map[f"{self.ld_name}/GGIO2"] = self._ggio2

    def _get_or_create_ld(self, ld_inst: str):
        """获取或创建逻辑设备"""
        if ld_inst in self._ld_map:
            return self._ld_map[ld_inst]
        ld = iec61850.LogicalDevice_create(ld_inst, self._model)
        lln0 = iec61850.LogicalNode_create("LLN0", ld)
        self._ld_map[ld_inst] = ld
        # 将自动创建的 LLN0 也注册到 _ln_map, 避免 _get_or_create_ln 重复创建
        self._ln_map[f"{ld_inst}/LLN0"] = lln0
        log.info(f"IEC61850 动态创建逻辑设备: {ld_inst}")
        return ld

    def _get_or_create_ln(self, ld_inst: str, ln_name: str):
        """获取或创建逻辑节点"""
        key = f"{ld_inst}/{ln_name}"
        if key in self._ln_map:
            return self._ln_map[key]
        ld = self._get_or_create_ld(ld_inst)
        ln = iec61850.LogicalNode_create(ln_name, ld)
        self._ln_map[key] = ln
        log.info(f"IEC61850 动态创建逻辑节点: {key}")
        return ln

    def add_point(self, address, frame_type: int = 0, fc: str = "") -> Optional[str]:
        """添加测点到数据模型

        Args:
            address: 测点地址，支持两种格式:
                     - 简单地址 (int/str 不含 '/'): 使用 MMXU1/GGIO1/GGIO2 固定结构
                     - 完整引用路径 (str 含 '/'): 按 ICD 结构动态创建 LD/LN/DO/DA
            frame_type: 帧类型 (0=遥测, 1=遥信, 2=遥控, 3=遥调)，仅简单地址模式使用
            fc: IEC 61850 功能约束 (如 "MX", "ST", "CO", "DC")，仅完整引用路径模式使用

        Returns:
            MMS 引用路径，用于后续读写
        """
        addr_str = str(address)
        if addr_str in self._point_refs:
            return self._point_refs[addr_str]  # 已存在

        if _is_full_ref(address):
            return self._add_point_from_ref(address, frame_type, fc)
        else:
            return self._add_point_simple(address, frame_type)

    def _add_point_simple(self, address, frame_type: int) -> Optional[str]:
        """简单地址模式: 使用固定的 MMXU1/GGIO1/GGIO2 结构添加测点"""
        # 确保默认 LD 已创建（懒初始化）
        self._ensure_base_ld()
        addr_str = str(address)

        # 确保 address 是合法的 IEC 61850 节点名称 (不能包含 . / \ 等)
        safe_addr = str(address).replace('.', '_').replace('/', '_').replace('\\', '_').replace('-', '_')

        ref = None
        if frame_type == 0:  # 遥测 - MV (Measured Value)
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
                "f", iec61850.toModelNode(mag),
                iec61850.IEC61850_FLOAT32,
                FC_MX, 0, 0, 0
            )
            ref = f"{self.model_name}{self.ld_name}/MMXU1.{do_name}.mag.f"
            self._point_attrs[addr_str] = da
            self._point_fc[addr_str] = "MX"
            self._point_iec_type[addr_str] = "float"
            self._keep_alive.extend([do_name, da])

        elif frame_type == 1:  # 遥信 - SPS (Single Point Status)
            do_name = f"SPS_{safe_addr}"
            do_key = f"{self.ld_name}/GGIO1.{do_name}"
            do = self._do_map.get(do_key)
            if do is None:
                do = iec61850.DataObject_create(do_name, iec61850.toModelNode(self._ggio1), 0)
                self._do_map[do_key] = do
                self._keep_alive.append(do)
                self._add_standard_das(do, do_key, "ST", 1, ["stVal"])
            da = iec61850.DataAttribute_create(
                "stVal", iec61850.toModelNode(do),
                iec61850.IEC61850_BOOLEAN,
                FC_ST, 0, 0, 0
            )
            ref = f"{self.model_name}{self.ld_name}/GGIO1.{do_name}.stVal"
            self._point_attrs[addr_str] = da
            self._point_fc[addr_str] = "ST"
            self._point_iec_type[addr_str] = "boolean"
            self._keep_alive.extend([do_name, da])

        elif frame_type == 2:  # 遥控 - SPC (Single Point Control)
            do_name = f"SPC_{safe_addr}"
            do_key = f"{self.ld_name}/GGIO1.{do_name}"
            do = self._do_map.get(do_key)
            if do is None:
                do = iec61850.DataObject_create(do_name, iec61850.toModelNode(self._ggio1), 0)
                self._do_map[do_key] = do
                self._keep_alive.append(do)
            da = iec61850.DataAttribute_create(
                "ctlVal", iec61850.toModelNode(do),
                iec61850.IEC61850_BOOLEAN,
                FC_CO, 0, 0, 0
            )
            ref = f"{self.model_name}{self.ld_name}/GGIO1.{do_name}.ctlVal"
            self._point_attrs[addr_str] = da
            self._point_fc[addr_str] = "CO"
            self._point_iec_type[addr_str] = "boolean"
            self._keep_alive.extend([do_name, da])

        elif frame_type == 3:  # 遥调 - APC (Analog Point Control)
            do_name = f"APC_{safe_addr}"
            do_key = f"{self.ld_name}/GGIO2.{do_name}"
            do = self._do_map.get(do_key)
            if do is None:
                do = iec61850.DataObject_create(do_name, iec61850.toModelNode(self._ggio2), 0)
                self._do_map[do_key] = do
                self._keep_alive.append(do)
            da = iec61850.DataAttribute_create(
                "ctlVal", iec61850.toModelNode(do),
                iec61850.IEC61850_FLOAT32,
                FC_CO, 0, 0, 0
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

    def _add_point_from_ref(self, address: str, frame_type: int, fc: str = "") -> Optional[str]:
        """完整引用路径模式: 按 ICD 文件结构动态创建 LD/LN/DO/DA

        address 格式: {ld_inst}/{ln_name}.{do_name}.{da_path}
        例如: "MEAS/M0GGIO1.AnIn1.mag.f"

        关键: 同一 LN 下的同名 DO 只创建一次, 同一 DO 下的同名 DA 也只创建一次,
        避免客户端连接时因重复 key 崩溃 (如 Key: Health)。
        """
        parsed = _parse_ref(address)
        if not parsed:
            log.error(f"IEC61850 无法解析引用路径: {address}")
            return None

        ld_inst, ln_name, do_name, da_path = parsed
        if not da_path:
            # 引用路径缺少 DA 路径 (如 "C1/CSWI1.StrVal")，
            # 根据 LN 类别推断默认 DA 路径
            ln_class, _ = _split_ln_name(ln_name)
            if ln_class in YK_LN_CLASSES:
                da_path = "ctlVal"
            elif ln_class in YT_LN_CLASSES:
                da_path = "Oper.ctlVal"
            elif ln_class in YC_LN_CLASSES:
                da_path = "mag.f"
            elif ln_class in YX_LN_CLASSES:
                da_path = "stVal"
            else:
                log.warning(f"IEC61850 引用路径缺少 DA 路径且无法推断 LN 类别: {address}, ln={ln_name}")
                return None
            log.info(f"IEC61850 引用路径缺少 DA, 根据 LN 类别 '{ln_class}' 推断为: {address} -> {da_path}")

        addr_str = str(address)

        # 获取或创建逻辑节点
        ln = self._get_or_create_ln(ld_inst, ln_name)

        # 预拆分 da_path 以便在 DO 创建时用于 FC 推断
        da_parts = da_path.split('.') if da_path else []

        # === 1. 获取或创建 DO (去重) ===
        do_key = f"{ld_inst}/{ln_name}.{do_name}"
        do_obj = self._do_map.get(do_key)
        if do_obj is None:
            do_obj = iec61850.DataObject_create(do_name, iec61850.toModelNode(ln), 0)
            self._do_map[do_key] = do_obj
            self._keep_alive.append(do_obj)
            # 为新 DO 自动补充标准 DAs (q, t, dU)，确保 MMS 模型完整
            # 避免 .NET 客户端因缺少预期 DA 而 IndexOutOfRange
            self._add_standard_das(do_obj, do_key, fc, frame_type, da_parts)

        # === 2. 根据 da_path 创建 DA 层级结构 (去重) ===
        # da_path 示例: "mag.f", "stVal", "q.validity", "Oper.ctlVal", "cVal.mag.f"

        # 推断 FC: 优先用传入值, 否则从 DA 路径推断
        if not fc:
            fc = self._infer_fc(frame_type, da_parts[0])

        fc_const = self._resolve_fc_const(fc)
        if fc_const is None:
            log.warning(f"IEC61850 无法解析 FC: {fc}, 使用 MX 作为默认值")
            fc_const = FC_MX

        # 推断 DA 的 IEC 61850 数据类型
        iec_type = self._infer_iec_type(frame_type, da_parts)

        # 沿 da_path 逐级创建, 中间级用 DataObject (结构体), 叶子级用 DataAttribute
        parent = do_obj
        for i, part in enumerate(da_parts):
            is_leaf = (i == len(da_parts) - 1)
            part_key = f"{ld_inst}/{ln_name}.{do_name}.{'.'.join(da_parts[:i+1])}"

            if is_leaf:
                # 叶子节点: 创建 DataAttribute
                existing_da = self._da_map.get(part_key)
                if existing_da is not None:
                    # DA 已存在, 复用
                    da = existing_da
                    # log.debug(f"IEC61850 DA 已存在, 复用: {part_key}")
                else:
                    da = iec61850.DataAttribute_create(
                        part, iec61850.toModelNode(parent),
                        iec_type, fc_const, 0, 0, 0
                    )
                    self._da_map[part_key] = da
                    self._keep_alive.append(da)
            else:
                # 中间节点: 创建 DataObject (结构体容器)
                existing_obj = self._do_map.get(part_key)
                if existing_obj is not None:
                    parent = existing_obj
                else:
                    sub_obj = iec61850.DataObject_create(part, iec61850.toModelNode(parent), 0)
                    self._do_map[part_key] = sub_obj
                    self._keep_alive.append(sub_obj)
                    parent = sub_obj

        # === 3. 构建完整 MMS 引用路径 ===
        ref = f"{self.model_name}{ld_inst}/{ln_name}.{do_name}.{da_path}"
        self._point_refs[addr_str] = ref
        self._point_fc[addr_str] = fc

        # 推断 iec_type 字符串
        iec_type_str = self._infer_iec_type_str(da_parts)
        self._point_iec_type[addr_str] = iec_type_str

        # 记录叶子 DA 用于后续读写
        leaf_key = f"{ld_inst}/{ln_name}.{do_name}.{da_path}"
        leaf_da = self._da_map.get(leaf_key)
        if leaf_da is not None:
            self._point_attrs[addr_str] = leaf_da

        return ref

    @staticmethod
    def _infer_fc(frame_type: int, top_da: str) -> str:
        """根据帧类型和顶级 DA 名称推断 FC"""
        DA_FC_MAP = {
            "mag": "MX", "instMag": "MX", "cVal": "MX", "mxVal": "MX", "fCVal": "MX",
            "stVal": "ST", "ctlVal": "CO", "setVal": "CO",
            "q": "MX", "t": "MX", "dU": "DC",
            "origin": "OR", "subVal": "SV", "blkEna": "BL",
            "Oper": "CO", "SBOw": "CO", "Cancel": "CO", "SBO": "CO",
        }
        fc = DA_FC_MAP.get(top_da)
        if fc:
            return fc
        # 回退: 根据帧类型推断
        return {0: "MX", 1: "ST", 2: "CO", 3: "CO"}.get(frame_type, "MX")

    @staticmethod
    def _resolve_fc_const(fc: str):
        """将 FC 字符串解析为 pyiec61850 常量"""
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
        """根据帧类型和 DA 路径推断 IEC 61850 数据类型"""
        if not HAS_IEC61850:
            return 0

        leaf = da_parts[-1] if da_parts else ""
        parent = da_parts[-2] if len(da_parts) > 1 else ""

        # 浮点数: mag.f, cVal.mag.f, instMag.f, ctlVal (遥调), setVal, wVal
        if leaf == "f":
            return iec61850.IEC61850_FLOAT32
        if frame_type == 3 and leaf in ("ctlVal", "setVal", "wVal"):
            return iec61850.IEC61850_FLOAT32
        if frame_type == 0 and leaf in ("ctlVal", "setVal"):
            return iec61850.IEC61850_FLOAT32

        # 布尔值: stVal (遥信/遥控), ctlVal (遥控)
        if leaf in ("stVal", "ctlVal") and frame_type in (1, 2):
            return iec61850.IEC61850_BOOLEAN

        # 整数/枚举: stVal (ENS/ENC), validity, source, orCat
        if leaf in ("stVal",) and frame_type == 1:
            return iec61850.IEC61850_INT32
        if leaf in ("validity", "source", "orCat", "ctlNum", "TimeAccuracy"):
            return iec61850.IEC61850_INT32
        if leaf in ("seconds", "detailQuality"):
            return iec61850.IEC61850_INT32
        if leaf == "fraction":
            return iec61850.IEC61850_INT32U

        # 可见字符串: dU, d
        if leaf in ("dU", "d", "du"):
            return iec61850.IEC61850_VISIBLE_STRING_255

        # 八位字节串: orIdent
        if leaf in ("orIdent",):
            return iec61850.IEC61850_OCTET_STRING_64

        # 默认: 根据帧类型
        if frame_type == 0 or frame_type == 3:
            return iec61850.IEC61850_FLOAT32
        return iec61850.IEC61850_BOOLEAN

    def _add_standard_das(
        self,
        do_obj,
        do_key: str,
        fc: str,
        frame_type: int,
        da_parts: list,
    ) -> None:
        """为 DO 自动补充标准 DA 结构 (q, t, dU)

        许多 IEC 61850 客户端（如 .NET IEC61850Lib）在创建 FcDataNodeModel 时
        期望每个 DO 下都有 q (品质), t (时标), dU (描述) 等标准 DA。
        如果服务端模型缺少这些 DA，客户端在 GetDataValues 时集合索引会不匹配，
        导致 IndexOutOfRangeException。

        Args:
            do_obj: DO 的 pyiec61850 对象
            do_key: DO 的缓存键 (如 "MEAS/M0GGIO1.AnIn1")
            fc: 主 DO 的 FC（可能为空，为空时需要推断）
            frame_type: 帧类型
            da_parts: DA 路径分段列表
        """
        # 推断 FC: 优先用传入值, 否则从 DA 路径推断
        if not fc:
            fc = self._infer_fc(frame_type, da_parts[0] if da_parts else "")
        if not fc:
            fc = "MX"

        # 控制类型不需要 q/t/dU
        if fc in ("CO",):
            return

        # q/t 的 FC: 遥信=ST, 其他=MX
        qt_fc = "ST" if fc == "ST" else "MX"
        qt_fc_const = self._resolve_fc_const(qt_fc)
        dc_fc_const = self._resolve_fc_const("DC")

        # --- 1. q (品质) - 单值 DataAttribute ---
        # IEC 61850 MMS 映射: Quality 映射为单个 BitString (13位),
        # 而非结构体。.NET IEC61850Lib 客户端期望 q 是单个值，
        # 若服务端返回结构体则 SetValueFromMmsDataObj 会 NullReferenceException。
        q_key = f"{do_key}.q"
        if q_key not in self._da_map and qt_fc_const:
            q_da = iec61850.DataAttribute_create(
                "q", iec61850.toModelNode(do_obj),
                iec61850.IEC61850_QUALITY, qt_fc_const, 0, 0, 0
            )
            self._da_map[q_key] = q_da
            self._keep_alive.append(q_da)
            self._standard_bda_list.append((q_da, "q", "quality"))

        # --- 2. t (时标) - 单值 DataAttribute ---
        # IEC 61850 MMS 映射: Timestamp 映射为单个 UTC_Time,
        # 而非包含 seconds/fraction 等子 BDA 的结构体。
        t_key = f"{do_key}.t"
        if t_key not in self._da_map and qt_fc_const:
            t_da = iec61850.DataAttribute_create(
                "t", iec61850.toModelNode(do_obj),
                iec61850.IEC61850_TIMESTAMP, qt_fc_const, 0, 0, 0
            )
            self._da_map[t_key] = t_da
            self._keep_alive.append(t_da)
            self._standard_bda_list.append((t_da, "t", "timestamp"))

        # --- 3. dU (描述) - 可见字符串 ---
        du_key = f"{do_key}.dU"
        if du_key not in self._da_map and dc_fc_const:
            du_da = iec61850.DataAttribute_create(
                "dU", iec61850.toModelNode(do_obj),
                iec61850.IEC61850_VISIBLE_STRING_255,
                dc_fc_const, 0, 0, 0
            )
            self._da_map[du_key] = du_da
            self._keep_alive.append(du_da)

    def _init_standard_bda_defaults(self):
        """初始化标准 DA 的默认值

        在服务器启动后调用，为所有 q(品质) 和 t(时标) 设置默认初始值，
        避免 IED Scout 等客户端读取时因值为空显示红色感叹号。

        q 使用 IedServer_updateQuality 设置品质位 (0 = GOOD)
        t 使用 IedServer_updateUTCTimeAttributeValue 设置当前时间
        """
        if not self._server or not self._is_running:
            return

        import time as time_module
        now_ms = int(time_module.time() * 1000)

        for da, name, iec_type in self._standard_bda_list:
            try:
                if iec_type == "quality":
                    # 品质: 0 表示 validity=GOOD, 无标志位
                    iec61850.IedServer_updateQuality(
                        self._server, da, 0
                    )
                elif iec_type == "timestamp":
                    # 时标: 当前 UTC 时间 (毫秒)
                    iec61850.IedServer_updateUTCTimeAttributeValue(
                        self._server, da, now_ms
                    )
                elif iec_type == "string":
                    if hasattr(iec61850, 'IedServer_updateStringAttributeValue'):
                        iec61850.IedServer_updateStringAttributeValue(
                            self._server, da, ""
                        )
            except Exception as e:
                log.warning(
                    f"初始化标准 DA 默认值失败: {name}({iec_type}), error={e}"
                )

    def _apply_pending_registrations(self):
        """处理待注册的 GoCB/DataSet 队列

        在 IedServer_create 之前调用，将暂存的 GoCB 和 DataSet 配置
        批量注册到 IedModel 中。这样 IedServer_create 构建命名空间时
        就能包含这些节点，客户端可以发现它们。

        典型场景：应用启动时 load_from_db 因 server_map 找不到 server
        而将 GoCB 配置暂存，随后设备启动时此方法统一注册到模型。
        """
        if not self._pending_goose_registrations:
            return

        applied = 0
        for item in self._pending_goose_registrations:
            reg_type = item.get("_type", "")
            try:
                if reg_type == "gocb":
                    self.add_goose_control_block(
                        name=item.get("name", ""),
                        app_id=item.get("app_id", 0x0001),
                        data_set_ref=item.get("data_set_ref", ""),
                        conf_rev=item.get("conf_rev", 1),
                        go_id=item.get("go_id", ""),
                        min_time=item.get("min_time", 10),
                        max_time=item.get("max_time", 1000),
                        ld_inst=item.get("ld_inst"),
                        entries=item.get("entries"),
                        dst_mac=item.get("dst_mac"),
                        vlan_id=item.get("vlan_id", 0),
                        vlan_prio=item.get("vlan_prio", 4),
                    )
                    applied += 1
                elif reg_type == "dataset":
                    self.register_dataset(
                        ld_inst=item.get("ld_inst", ""),
                        ds_name=item.get("ds_name", ""),
                        data_set_ref=item.get("data_set_ref", ""),
                        entries=item.get("entries"),
                    )
                    applied += 1
            except Exception as e:
                log.warning(f"处理待注册 {reg_type} 失败: {e}")

        self._pending_goose_registrations.clear()
        if applied > 0:
            log.info(f"已处理 {applied} 个待注册 GoCB/DataSet 配置")

    def apply_model_changes(self) -> bool:
        """应用模型变更：若 IedServer 已运行且有变更，重建 IedServer 以更新 MMS 命名空间

        libIEC61850 的 MMS 命名空间在 IedServer_create 时一次性构建。
        若 GSEControlBlock、DataSet 等在 IedServer_create 之后被添加到 IedModel，
        客户端无法发现这些新节点。必须销毁并重建 IedServer 才能更新 MMS 命名空间。

        本方法检查 _model_changed 标志，若有变更则重建 IedServer。
        应在所有批量模型操作（如 load_from_db）完成后调用。

        Returns:
            是否执行了重建
        """
        if not self._model_changed or not self._is_running:
            return False

        log.info("检测到 IedModel 变更，重建 IedServer 以更新 MMS 命名空间...")
        self._model_changed = False

        try:
            # 1. 停止并销毁当前 IedServer
            if self._server:
                try:
                    iec61850.IedServer_stop(self._server)
                    iec61850.IedServer_destroy(self._server)
                except Exception as e:
                    log.warning(f"停止旧 IedServer 时出错: {e}")
                self._server = None

            # 1.5 等待端口释放（避免 Windows 上 TCP TIME_WAIT 导致端口冲突）
            import time as _time
            _time.sleep(0.5)

            # 2. 基于（已更新的）IedModel 重新创建 IedServer
            self._server = iec61850.IedServer_create(self._model)
            if not self._server:
                self._is_running = False
                log.error("重建 IedServer 失败: IedServer_create 返回空")
                return False

            # 3. 恢复 IedServer 配置
            iec61850.IedServer_setServerIdentity(self._server, "EMS", self.model_name, "1.0")

            # 4. 启动新的 IedServer（先启动 MMS，再尝试 GOOSE 发布）
            iec61850.IedServer_start(self._server, self.port)

            if iec61850.IedServer_isRunning(self._server):
                log.info("IedServer 重建成功，MMS 命名空间已更新")
                self._init_standard_bda_defaults()
                self._try_enable_goose_publishing()
                import time as _time
                import platform
                _time.sleep(0.3)
                if platform.system() != "Windows":
                    self._enable_all_goose_cbs()
                return True
            else:
                self._is_running = False
                log.error("IedServer 重建后启动失败")
                return False

        except Exception as e:
            log.error(f"重建 IedServer 失败: {e}", exc_info=True)
            self._is_running = False
            return False

    def start(self):
        """启动 IEC 61850 MMS 服务器"""
        if self._is_running:
            # 如果服务器已在运行且模型有变更，执行热重建
            if self._model_changed:
                log.info("IEC61850Server.start(): 服务器已在运行，检测到模型变更，执行热重建")
                self.apply_model_changes()
            return

        # 在 IedServer_create 之前，处理待注册的 GoCB/DataSet 队列
        # 这些可能是在 load_from_db 时因 server_map 找不到 server 而暂存的配置
        self._apply_pending_registrations()

        # 诊断：检查 IedModel 中的 GoCB 和 DataSet
        log.info(
            f"IedServer_create 前模型诊断: "
            f"GoCB={len(self._goose_cb_list)}, "
            f"DataSet={len(self._dataset_catalog)}, "
            f"pending={len(self._pending_goose_registrations)}, "
            f"LD={list(self._ld_map.keys()) or [self.ld_name]}, "
            f"LN={list(self._ln_map.keys())}"
        )

        self._server = iec61850.IedServer_create(self._model)

        # 设置 MMS TCP 端口
        iec61850.IedServer_setServerIdentity(self._server, "EMS", self.model_name, "1.0")

        # 重要：先启动 MMS 服务器，再尝试启用 GOOSE 发布
        # IedServer_enableGoosePublishing 在某些平台（如 Windows）或无效网络接口上
        # 可能导致 C 层 segfault 崩溃，Python try/except 无法捕获。
        # 必须确保 MMS 服务先启动，GoCB 通过 MMS 浏览发现不依赖 GOOSE 发布。
        self._is_running = True
        iec61850.IedServer_start(self._server, self.port)

        if iec61850.IedServer_isRunning(self._server):
            log.info(f"IEC 61850 MMS 服务器已启动, 端口: {self.port}")

            # 服务器启动后初始化 q/t 子 DA 的默认值，避免 IED Scout 读取时显示红色感叹号
            try:
                self._init_standard_bda_defaults()
                log.info("标准 DA 默认值初始化完成")
            except Exception as e:
                log.warning(f"初始化标准 DA 默认值异常 (非致命): {e}")

            # 尝试启用 GOOSE 以太网发布（非致命，失败不影响 MMS 服务）
            # GoCB 通过 MMS 协议发现不依赖此功能，仅影响实际 GOOSE 报文发送
            self._try_enable_goose_publishing()

            # 短暂等待 MMS 服务完全就绪后再设置 GoEna=TRUE
            # 避免 IedConnection_connect 因 MMS 监听线程未就绪而失败
            import time as _time
            _time.sleep(0.3)
            # 启动后设置所有已注册 GoCB 的 GoEna=TRUE
            # 注意: IedConnection_writeBooleanValue 在某些平台上可能导致 C 层崩溃，
            # 在 Windows 上跳过此步骤 (GoCB 仍可通过 MMS 浏览发现)
            import platform
            if platform.system() != "Windows":
                try:
                    self._enable_all_goose_cbs()
                    log.info("所有 GoCB GoEna 设置完成")
                except Exception as e:
                    log.warning(f"设置 GoCB GoEna 异常 (非致命): {e}")
            else:
                log.info("Windows 平台跳过 GoEna 设置 (GoCB 仍可通过 MMS 浏览发现)")
        else:
            self._is_running = False
            log.error(f"IEC 61850 服务器启动失败, 端口: {self.port}")

    def _try_enable_goose_publishing(self):
        """尝试启用 GOOSE 以太网发布（非致命）

        IedServer_enableGoosePublishing 在以下情况下可能导致 C 层崩溃:
        - Windows 平台（原始以太网套接字不支持）
        - 指定的网络接口不存在
        - 接口名格式不正确

        GoCB 通过 MMS 协议被 IEDScout 发现不依赖此功能。
        此功能仅影响实际 GOOSE 报文的以太网发送。
        如果启用失败，MMS 浏览仍可发现 GoCB，但不会发送 GOOSE 报文。

        使用子进程检测是否可安全调用，避免主进程崩溃。
        """
        import platform
        import subprocess
        import sys

        # Windows 平台: 原始以太网套接字不支持，直接跳过
        if platform.system() == "Windows":
            log.info("GOOSE 以太网发布: Windows 平台不支持原始套接字，已跳过 (MMS 发现不受影响)")
            self._goose_publishing_enabled = False
            return

        # Linux 平台: 检查网络接口是否存在
        interface = self._goose_interface
        if interface and interface != "eth0":
            # 用户指定了非默认接口，先检查是否存在
            try:
                result = subprocess.run(
                    ["ip", "link", "show", interface],
                    capture_output=True, timeout=3
                )
                if result.returncode != 0:
                    log.warning(f"GOOSE 网络接口 '{interface}' 不存在，跳过 GOOSE 发布")
                    self._goose_publishing_enabled = False
                    return
            except Exception:
                pass  # 检查失败，继续尝试

        # 尝试启用 GOOSE 发布
        try:
            iec61850.IedServer_setGooseInterfaceId(self._server, interface)
            log.info(f"GOOSE 网络接口已设置: {interface}")
        except Exception as e:
            log.warning(f"设置 GOOSE 网络接口失败 ({interface}): {e}")

        try:
            iec61850.IedServer_enableGoosePublishing(self._server)
            log.info("GOOSE 发布服务已启用")
            self._goose_publishing_enabled = True
        except Exception as e:
            log.warning(f"启用 GOOSE 发布服务失败: {e}")
            self._goose_publishing_enabled = False

    def stop(self):
        """停止 IEC 61850 MMS 服务器"""
        if self._server and self._is_running:
            iec61850.IedServer_stop(self._server)
            iec61850.IedServer_destroy(self._server)
            self._server = None
            self._is_running = False
            log.info("IEC 61850 服务器已停止")

    def restart(self) -> bool:
        """重启 MMS 服务器，保留 IedModel"""
        if self._server:
            try:
                iec61850.IedServer_stop(self._server)
                iec61850.IedServer_destroy(self._server)
            except Exception:
                pass
        self._server = None
        self._is_running = False
        import time as _time
        _time.sleep(1)
        self._server = iec61850.IedServer_create(self._model)
        if not self._server:
            log.error("重启失败: IedServer_create 返回空")
            return False
        iec61850.IedServer_setServerIdentity(self._server, "EMS", self.model_name, "1.0")
        # 先启动 MMS 服务，再尝试 GOOSE 发布（同 start() 逻辑）
        self._is_running = True
        iec61850.IedServer_start(self._server, self.port)
        if iec61850.IedServer_isRunning(self._server):
            log.info(f"IEC 61850 服务器重启成功, 端口: {self.port}")
            self._init_standard_bda_defaults()
            self._try_enable_goose_publishing()
            # 短暂等待 MMS 服务完全就绪后再设置 GoEna=TRUE
            import time as _time
            import platform
            _time.sleep(0.3)
            # Windows 上跳过 GoEna 设置 (IedConnection_writeBooleanValue 可能导致 C 层崩溃)
            if platform.system() != "Windows":
                self._enable_all_goose_cbs()
            return True
        else:
            self._is_running = False
            log.error(f"IEC 61850 服务器重启失败, 端口: {self.port}")
            return False

    @property
    def is_running(self) -> bool:
        if self._server:
            return iec61850.IedServer_isRunning(self._server)
        return False

    @staticmethod
    def _infer_iec_type_str(da_parts: list) -> str:
        """从 DA 路径推断 iec_type 字符串（用于 get/set_point_value）"""
        leaf = da_parts[-1] if da_parts else ""
        parent = da_parts[-2] if len(da_parts) > 1 else ""

        if leaf == "f":
            return "float"
        if leaf in ("ctlVal", "setVal", "wVal") and parent in ("APC", "setMag"):
            return "float"
        # q 和 t 作为单值 DataAttribute
        if leaf == "q":
            return "quality"
        if leaf == "t":
            return "timestamp"
        if leaf in ("stVal", "ctlVal", "subEna", "blkEna",
                     "LeapSecondsKnown", "ClockedFailure", "ClockNotSynchronized"):
            return "boolean"
        if leaf in ("validity", "source", "orCat", "ctlNum", "frVal", "actVal", "frValSec",
                     "TimeAccuracy", "seconds", "fraction", "detailQuality"):
            return "integer"
        if leaf in ("dU", "d", "du"):
            return "string"
        return "unknown"

    def _resolve_da(self, address: str):
        """根据地址解析 DataAttribute 对象

        先直接查找，若失败则尝试根据 LN 类别推断默认 DA 后再查找。
        例如: "C1/CSWI1.StrVal" 未注册 -> 尝试 "C1/CSWI1.StrVal.ctlVal"

        Returns:
            (da, resolved_addr) 元组，未找到时 da 为 None
        """
        addr_str = str(address)
        da = self._point_attrs.get(addr_str)
        if da is not None:
            return da, addr_str

        # 回退: 尝试根据 LN 类别推断默认 DA 后查找
        if _is_full_ref(addr_str):
            parsed = _parse_ref(addr_str)
            if parsed:
                ld_inst, ln_name, do_name, da_path = parsed
                if not da_path:
                    ln_class, _ = _split_ln_name(ln_name)
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

    def get_point_value(self, address, fc: str = "") -> Any:
        """获取测点值

        Args:
            address: 测点地址 (简单地址或完整引用路径)
            fc: 功能约束 (为空时使用注册时的 FC)

        Returns:
            测点值 (float/int/bool/str)
        """
        if not self._server or not self._is_running:
            return 0

        addr_str = str(address)
        da, resolved_addr = self._resolve_da(address)
        if not da:
            log.warning(f"IEC61850 读取测点值时未找到 DataAttribute: address={address}")
            return 0

        # 类型安全检查：确保 da 是 SWIG 包装的 DataAttribute 对象
        if not hasattr(da, 'this'):
            log.error(f"IEC61850 数据属性对象类型错误: address={address}, type={type(da)}")
            return 0

        # 获取 iec_type (优先用解析后的地址)
        iec_type = self._point_iec_type.get(resolved_addr, self._point_iec_type.get(addr_str, "unknown"))

        try:
            if iec_type == "float":
                value = iec61850.IedServer_getFloatAttributeValue(self._server, da)
                return float(value) if value is not None else 0.0
            elif iec_type == "boolean":
                value = iec61850.IedServer_getBooleanAttributeValue(self._server, da)
                return bool(value) if value is not None else False
            elif iec_type == "integer":
                if hasattr(iec61850, 'IedServer_getIntegerAttributeValue'):
                    value = iec61850.IedServer_getIntegerAttributeValue(self._server, da)
                    return int(value) if value is not None else 0
                # 回退到布尔
                value = iec61850.IedServer_getBooleanAttributeValue(self._server, da)
                return bool(value) if value is not None else False
            elif iec_type == "string":
                if hasattr(iec61850, 'IedServer_getStringAttributeValue'):
                    value = iec61850.IedServer_getStringAttributeValue(self._server, da)
                    return str(value).strip() if value else ""
                return ""
            elif iec_type == "quality":
                # 品质值: 返回整数位串
                if hasattr(iec61850, 'IedServer_getUnsignedAttributeValue'):
                    value = iec61850.IedServer_getUnsignedAttributeValue(self._server, da)
                    return int(value) if value is not None else 0
                return 0
            elif iec_type == "timestamp":
                # 时标值: 返回毫秒级 UTC 时间戳
                if hasattr(iec61850, 'IedServer_getUTCTimeAttributeValue'):
                    value = iec61850.IedServer_getUTCTimeAttributeValue(self._server, da)
                    return int(value) if value is not None else 0
                return 0
            else:
                # unknown: 自动探测 - 先尝试浮点, 再布尔, 再整数
                try:
                    value = iec61850.IedServer_getFloatAttributeValue(self._server, da)
                    return float(value) if value is not None else 0.0
                except Exception:
                    pass
                try:
                    value = iec61850.IedServer_getBooleanAttributeValue(self._server, da)
                    return bool(value) if value is not None else False
                except Exception:
                    pass
                if hasattr(iec61850, 'IedServer_getIntegerAttributeValue'):
                    try:
                        value = iec61850.IedServer_getIntegerAttributeValue(self._server, da)
                        return int(value) if value is not None else 0
                    except Exception:
                        pass
                return 0
        except Exception as e:
            log.error(f"IEC61850 调用底层获取值函数失败: address={address}, error={e}")
            return 0

    def set_point_value(self, address, value: Any, fc: str = "") -> None:
        """设置测点值

        Args:
            address: 测点地址 (简单地址或完整引用路径)
            value: 要设置的值
            fc: 功能约束 (为空时使用注册时的 FC)
        """
        if not self._server or not self._is_running:
            return

        addr_str = str(address)
        da, resolved_addr = self._resolve_da(address)
        if not da:
            log.warning(f"IEC61850 设置测点值时未找到 DataAttribute: address={address}")
            return

        if not hasattr(da, 'this'):
            log.error(f"IEC61850 数据属性对象类型错误(设置值): address={address}, type={type(da)}")
            return

        # 获取 iec_type (优先用解析后的地址)
        iec_type = self._point_iec_type.get(resolved_addr, self._point_iec_type.get(addr_str, "unknown"))

        try:
            if isinstance(value, str) or iec_type == "string":
                # 字符串类型 (如 dU 描述)
                if hasattr(iec61850, 'IedServer_updateStringAttributeValue'):
                    iec61850.IedServer_updateStringAttributeValue(
                        self._server, da, str(value)
                    )
                else:
                    log.warning(f"IEC61850 不支持字符串写入: address={address}")
            elif iec_type == "float":
                iec61850.IedServer_updateFloatAttributeValue(
                    self._server, da, float(value)
                )
            elif iec_type == "integer":
                if isinstance(value, int) and not isinstance(value, bool):
                    if hasattr(iec61850, 'IedServer_updateIntegerAttributeValue'):
                        iec61850.IedServer_updateIntegerAttributeValue(
                            self._server, da, int(value)
                        )
                    else:
                        iec61850.IedServer_updateBooleanAttributeValue(
                            self._server, da, bool(value)
                        )
                else:
                    iec61850.IedServer_updateBooleanAttributeValue(
                        self._server, da, bool(value)
                    )
            elif iec_type == "boolean":
                iec61850.IedServer_updateBooleanAttributeValue(
                    self._server, da, bool(value)
                )
            elif iec_type == "quality":
                # 品质值: 整数位串
                iec61850.IedServer_updateQuality(
                    self._server, da, int(value)
                )
            elif iec_type == "timestamp":
                # 时标值: 毫秒级 UTC 时间戳
                iec61850.IedServer_updateUTCTimeAttributeValue(
                    self._server, da, int(value)
                )
            else:
                # unknown: 根据 value 类型选择
                if isinstance(value, float):
                    iec61850.IedServer_updateFloatAttributeValue(
                        self._server, da, float(value)
                    )
                elif isinstance(value, bool):
                    iec61850.IedServer_updateBooleanAttributeValue(
                        self._server, da, bool(value)
                    )
                elif isinstance(value, int):
                    if hasattr(iec61850, 'IedServer_updateIntegerAttributeValue'):
                        iec61850.IedServer_updateIntegerAttributeValue(
                            self._server, da, int(value)
                        )
                    else:
                        iec61850.IedServer_updateBooleanAttributeValue(
                            self._server, da, bool(value)
                        )
        except Exception as e:
            log.error(f"IEC61850 调用底层设置值函数失败: address={address}, value={value}, error={e}")

    def browse_logical_devices(self) -> list[str]:
        """浏览服务端数据模型的逻辑设备列表

        返回所有已创建的逻辑设备名称。
        默认 GenericLD 仅在添加了简单地址测点后才存在，
        ICD 导入模式的 LD 则动态创建。

        Returns:
            逻辑设备名称列表，如 ["MEAS", "CTRL"] 或 ["GenericLD"]
        """
        ld_list = []
        for ld_inst in self._ld_map:
            prefix = f"{ld_inst}/"
            if any(key.startswith(prefix) for key in self._ln_map):
                ld_list.append(ld_inst)
        return ld_list

    def browse_logical_nodes(self, ld_inst: str) -> list[str]:
        """浏览指定逻辑设备下的逻辑节点列表

        对于动态 LD (ICD 导入), 返回所有 LN (包括 LLN0);
        对于简单地址模式的默认 LD, 返回所有 LN (不含内部固定节点过滤)。

        Args:
            ld_inst: 逻辑设备实例名，如 "MEAS"

        Returns:
            逻辑节点名称列表，如 ["LLN0", "M0GGIO1", "METMMXU1"]
        """
        ln_names = []
        prefix = f"{ld_inst}/"
        for key in self._ln_map:
            if key.startswith(prefix):
                ln_name = key[len(prefix):]
                ln_names.append(ln_name)
        return sorted(ln_names)

    def browse_data_objects(self, ld_inst: str, ln_name: str) -> list[dict]:
        """浏览指定逻辑节点下的数据对象列表

        从 _point_refs 中提取指定 LN 下的 DO 名称和类型。

        Args:
            ld_inst: 逻辑设备实例名, 如 "MEAS"
            ln_name: 逻辑节点名称, 如 "M0GGIO1"

        Returns:
            DO 信息列表, 如 [{"name": "AnIn1", "frame_type": 0}, ...]
        """
        # 从 _point_refs 中提取匹配的 DO
        do_map: Dict[str, Optional[int]] = {}  # do_name -> frame_type
        prefix = f"{ld_inst}/{ln_name}."

        for (address, frame_type), ref in self._point_refs.items():
            if not isinstance(address, str) or '/' not in address:
                continue
            parsed = _parse_ref(address)
            if parsed and parsed[0] == ld_inst and parsed[1] == ln_name:
                do_name = parsed[2]
                if do_name not in do_map:
                    do_map[do_name] = frame_type

        return [{"name": name, "frame_type": ft} for name, ft in sorted(do_map.items())]

    def browse_data_attributes(self, ld_inst: str, ln_name: str, do_name: str) -> list[dict]:
        """浏览指定数据对象下的数据属性列表

        从 _point_refs 中提取指定 DO 下的 DA 路径信息。

        Args:
            ld_inst: 逻辑设备实例名
            ln_name: 逻辑节点名称
            do_name: 数据对象名称

        Returns:
            DA 信息列表, 如 [{"name": "mag", "path": "mag.f", "fc": "MX", "type": "Float32"}, ...]
        """
        fc_map = {0: "MX", 1: "ST", 2: "CO", 3: "CO"}
        type_map = {0: "Float32", 1: "Boolean", 2: "Boolean", 3: "Float32"}

        da_map: Dict[str, dict] = {}  # da_path -> info
        for (address, frame_type), ref in self._point_refs.items():
            if not isinstance(address, str) or '/' not in address:
                continue
            parsed = _parse_ref(address)
            if parsed and parsed[0] == ld_inst and parsed[1] == ln_name and parsed[2] == do_name:
                da_path = parsed[3]
                if da_path and da_path not in da_map:
                    # 提取第一层 DA 名称
                    first_da = da_path.split('.')[0]
                    da_map[da_path] = {
                        "name": first_da,
                        "path": da_path,
                        "fc": fc_map.get(frame_type, ""),
                        "type": type_map.get(frame_type, ""),
                    }

        return sorted(da_map.values(), key=lambda x: x["path"])

    def add_goose_control_block(
        self,
        name: str,
        app_id: int,
        data_set_ref: str,
        conf_rev: int,
        go_id: str = "",
        min_time: int = 10,
        max_time: int = 1000,
        ld_inst: str = None,
        entries: Optional[List[Dict[str, Any]]] = None,
        dst_mac: Optional[List[int]] = None,
        vlan_id: int = 0,
        vlan_prio: int = 4,
    ) -> bool:
        """在 LLN0 下创建 GSEControlBlock，使 MMS 客户端可发现 GOOSE

        使用 libIEC61850 的 GSEControlBlock_create 创建标准 GoCB 结构，
        同时将 FCDA 条目添加到 DataSet 中，确保客户端能发现完整的数据集结构。

        Args:
            name: GSEControlBlock 名称 (如 "gcb1")
            app_id: APPID
            data_set_ref: DataSet 引用路径 (如 "LD0/LLN0$dsGOOSE1")
            conf_rev: 配置修订号
            go_id: GOOSE 标识符
            min_time: 最小重发时间 (ms)
            max_time: 最大重发时间 (ms)
            ld_inst: 逻辑设备实例名，默认使用 self.ld_name
            entries: 数据集条目列表，每个条目包含 name (fcda_ref), value, iec_type

        Returns:
            是否成功
        """
        if not self._model:
            log.warning("无法添加 GSEControlBlock: 模型未初始化")
            return False

        ld_inst = ld_inst or self.ld_name
        lln0_key = f"{ld_inst}/LLN0"
        lln0 = self._ln_map.get(lln0_key)
        if lln0 is None:
            if ld_inst == self.ld_name:
                self._ensure_base_ld()
                lln0 = self._lln0
            else:
                # 非默认 LD: 自动创建 LD 和 LLN0
                # 当 ICD 文件中某个 LD 下只有 GOOSE DataSet 而没有 MMS 测点时，
                # point import 不会创建该 LD，需要在此处自动创建
                ld = self._get_or_create_ld(ld_inst)
                lln0 = self._ln_map.get(lln0_key)
                log.info(f"为 GSEControlBlock 自动创建 LD/LLN0: {ld_inst}")
        if not lln0:
            log.warning(f"无法添加 GSEControlBlock: LLN0 未找到 (ld_inst={ld_inst})")
            return False

        try:
            # 1. 创建 DataSet (数据集)
            # IEC 61850 标准创建顺序：数据模型 → DataSet → GSEControlBlock
            # DataSet 必须先于 GSEControlBlock 存在，否则 GoCB 无法引用
            ds_name = data_set_ref.split("$")[-1] if "$" in data_set_ref else f"ds{name}"
            data_set = iec61850.DataSet_create(ds_name, lln0)
            if not data_set:
                log.warning(f"创建 DataSet {ds_name} 失败，无法创建 GSEControlBlock")
                return False
            self._keep_alive.append(data_set)
            # 为 DataSet 添加 FCDA 条目
            added_entries = self._add_fcda_entries_to_dataset(data_set, entries, ld_inst)

            # 记录 DataSet 到目录（供前端结构树展示）
            # 无论 FCDA 是否实际写入 MMS 模型，都记录条目信息供前端展示
            ds_members = []
            if entries:
                entry_to_fc_map = {
                    "stVal": "ST", "ctlVal": "CO", "mag.f": "MX",
                    "mag": "MX", "f": "MX", "q": "MX", "t": "MX",
                    "dU": "DC", "setVal": "CO",
                }
                type_to_fc_map = {
                    "boolean": "ST", "float": "MX",
                    "integer": "ST", "string": "DC",
                }
                for entry in entries:
                    entry_ref = entry.get("name", "")
                    entry_iec_type = entry.get("iec_type", "")
                    entry_fc = type_to_fc_map.get(entry_iec_type, "")
                    if not entry_fc and "/" in entry_ref:
                        da_part = entry_ref.rsplit(".", 1)[-1] if "." in entry_ref else ""
                        entry_fc = entry_to_fc_map.get(da_part, "MX")
                    ds_members.append({
                        "ref": entry_ref,
                        "fc": entry_fc or "MX",
                        "iec_type": entry_iec_type,
                    })
            # 从 data_set_ref 中提取 LN: "LD0/LLN0$dsGOOSE1" -> "LLN0"
            ds_ln = ""
            if "$" in data_set_ref:
                ref_ln_part = data_set_ref.split("/")[-1] if "/" in data_set_ref else data_set_ref
                ds_ln = ref_ln_part.split("$")[0]
            self._dataset_catalog.append({
                "ref": data_set_ref,
                "name": ds_name,
                "ld": ld_inst,
                "ln": ds_ln,
                "member_count": len(ds_members),
                "members": ds_members,
            })

            # 2. 创建 GSEControlBlock (标准 libIEC61850 GoCB)
            # 重要: dataSet 参数必须是 DataSet 名称 (如 "dsGOOSE1")，不能是完整引用路径 (如 "CTMP01/LLN0$dsGOOSE1")
            # 因为 libIEC61850 内部会以此名称在 LLN0 的 DataSet 列表中查找对应的 DataSet 对象
            # 若传完整路径，查找时名称不匹配 → GOOSE Publisher 创建失败 → 不会发送 GOOSE 报文
            app_id_str = f"{app_id:04X}" if isinstance(app_id, int) else str(app_id)
            gse_cb = iec61850.GSEControlBlock_create(
                name, lln0, app_id_str,
                ds_name, conf_rev,
                False, min_time, max_time,
            )
            log.info(f"GSEControlBlock_create: {name}, {lln0}, {app_id_str}, {ds_name}, {conf_rev}, {False}, {min_time}, {max_time}")
            if not gse_cb:
                log.warning(f"创建 GSEControlBlock {name} 失败")
                return False
            self._keep_alive.append(gse_cb)
            log.info(
                f"GSEControlBlock 创建成功: name={name}, "
                f"parent={lln0 is not None}, dataSet={ds_name}, "
                f"app_id=0x{app_id:04X}, conf_rev={conf_rev}"
            )

            # 验证 GSEControlBlock 是否已挂载到 IedModel
            # 通过 LLN0 的 GSE 控制块列表验证
            try:
                gse_count = 0
                if hasattr(iec61850, 'LogicalNode_getGSEControlBlockCount'):
                    gse_count = iec61850.LogicalNode_getGSEControlBlockCount(lln0)
                log.info(
                    f"GSEControlBlock 模型验证: name={name}, ld={ld_inst}, "
                    f"lln0_gse_count={gse_count}, "
                    f"goose_cb_list_total={len(self._goose_cb_list) + 1}, "
                    f"dataset_catalog_total={len(self._dataset_catalog)}"
                )
            except Exception as verify_err:
                log.debug(f"GSEControlBlock 模型验证跳过: {verify_err}")

            # 3. 添加物理通信地址 (MAC/APPID/VLAN)
            # 若不设置 PhyComAddress，GOOSE 发布器将使用默认组播地址，
            # 但某些客户端可能无法正确识别。ICD 文件中通常包含 GSE 通信地址。
            try:
                if dst_mac and len(dst_mac) == 6:
                    phy_addr = iec61850.PhyComAddress_create(
                        vlan_prio, vlan_id, app_id, dst_mac
                    )
                    if phy_addr:
                        iec61850.GSEControlBlock_addPhyComAddress(gse_cb, phy_addr)
                        self._keep_alive.append(phy_addr)
                        log.info(f"GoCB {name} PhyComAddress 已设置: MAC={':'.join(f'{b:02X}' for b in dst_mac)}, VLAN={vlan_id}, APPID=0x{app_id:04X}")
                    else:
                        log.warning(f"GoCB {name}: PhyComAddress_create 返回空，使用默认地址")
                else:
                    log.debug(f"GoCB {name}: 未提供 dst_mac，GOOSE 将使用默认组播地址")
            except Exception as phy_err:
                log.debug(f"添加 PhyComAddress 不可用 (非致命): {phy_err}")

            # 4. 记录 GoCB 信息并设置 GoEna=TRUE（如果服务器已在运行）
            self._goose_cb_list.append({
                "ld_inst": ld_inst,
                "name": name,
                "app_id": app_id,
            })
            # 关键：libIEC61850 的 MMS 命名空间在 IedServer_create 时一次性构建。
            # 如果 GSEControlBlock 是在 IedServer_create 之后添加到 IedModel 的，
            # MMS 层不会自动更新，客户端无法发现新的 GoCB/DataSet。
            # 必须标记模型变更，等待 apply_model_changes() 重建 IedServer。
            if self._server and self._is_running:
                self._model_changed = True
                log.info(f"GoCB {name} 在 IedServer 运行时添加，需要重建 IedServer 以更新 MMS 命名空间")

            log.info(
                f"GSEControlBlock 已添加到 MMS 数据模型: "
                f"name={name}, app_id=0x{app_id:04X}, "
                f"dataSet={data_set_ref}, entries={len(entries or [])}"
            )
            return True
        except Exception as e:
            log.error(f"添加 GSEControlBlock 失败: {e}", exc_info=True)
            return False

    def register_dataset(
        self,
        ld_inst: str,
        ds_name: str,
        data_set_ref: str,
        entries: Optional[List[Dict[str, Any]]] = None,
        dataset_catalog: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        """注册 DataSet 并在 MMS 模型中创建真实数据集

        用于 ICD 导入时注册不带 GSEControlBlock 的 DataSet。
        在 LLN0 下创建 DataSet 对象并添加 FCDA 条目，
        使 MMS 客户端可以发现和浏览数据集。

        Args:
            ld_inst: 逻辑设备实例名
            ds_name: DataSet 名称
            data_set_ref: DataSet 引用路径 (如 "CTMP01/LLN0$dsRack1CellTemp")
            entries: 条目列表，每个条目含 name(fcda_ref), iec_type
            dataset_catalog: 外部 catalog 列表（如 import 流程中传入），
                            为 None 时使用 self._dataset_catalog

        Returns:
            是否成功
        """
        if not self._model:
            log.warning(f"register_dataset [{ds_name}]: 模型未初始化")
            return False

        lln0_key = f"{ld_inst}/LLN0"
        lln0 = self._ln_map.get(lln0_key)
        log.info(f"register_dataset [{ds_name}]: 查找 LLN0 key={lln0_key}, found={lln0 is not None}, ld_inst={ld_inst}, self.ld_name={self.ld_name}")
        if lln0 is None:
            if ld_inst == self.ld_name:
                self._ensure_base_ld()
                lln0 = self._lln0
            else:
                # 非默认 LD: 自动创建 LD 和 LLN0
                # 当 ICD 文件中某个 LD 下只有纯 DataSet 而没有 MMS 测点时，
                # 需要在此处自动创建 LD/LLN0 以便注册 DataSet
                ld = self._get_or_create_ld(ld_inst)
                lln0 = self._ln_map.get(lln0_key)
                log.info(f"为 register_dataset 自动创建 LD/LLN0: {ld_inst}")
        if not lln0:
            log.warning(f"无法注册 DataSet: LLN0 未找到 (ld_inst={ld_inst})")
            return False

        try:
            # 在 MMS 模型中创建真实的 DataSet
            data_set = iec61850.DataSet_create(ds_name, lln0)
            if not data_set:
                log.warning(f"register_dataset [{ds_name}]: DataSet_create 失败")
                return False

            self._keep_alive.append(data_set)

            # 为 DataSet 添加 FCDA 条目
            added_entries = self._add_fcda_entries_to_dataset(data_set, entries, ld_inst)

            # 记录 DataSet 到目录（供前端结构树展示）
            ds_members = []
            if entries:
                entry_to_fc_map = {
                    "stVal": "ST", "ctlVal": "CO", "mag.f": "MX",
                    "mag": "MX", "f": "MX", "q": "MX", "t": "MX",
                    "dU": "DC", "setVal": "CO",
                }
                type_to_fc_map = {
                    "boolean": "ST", "float": "MX",
                    "integer": "ST", "string": "DC",
                }
                for entry in entries:
                    entry_ref = entry.get("name", "")
                    entry_iec_type = entry.get("iec_type", "")
                    entry_fc = type_to_fc_map.get(entry_iec_type, "")
                    if not entry_fc and "/" in entry_ref:
                        da_part = entry_ref.rsplit(".", 1)[-1] if "." in entry_ref else ""
                        entry_fc = entry_to_fc_map.get(da_part, "MX")
                    ds_members.append({
                        "ref": entry_ref,
                        "fc": entry_fc or "MX",
                        "iec_type": entry_iec_type,
                    })

            # 从 data_set_ref 中提取 LN
            ds_ln = ""
            if "$" in data_set_ref:
                ref_ln_part = data_set_ref.split("/")[-1] if "/" in data_set_ref else data_set_ref
                ds_ln = ref_ln_part.split("$")[0]

            catalog_item = {
                "ref": data_set_ref,
                "name": ds_name,
                "ld": ld_inst,
                "ln": ds_ln,
                "member_count": len(ds_members),
                "members": ds_members,
            }

            # 写入 catalog
            catalog = dataset_catalog if dataset_catalog is not None else self._dataset_catalog
            catalog.append(catalog_item)

            log.info(
                f"DataSet 已注册到 MMS 模型: "
                f"name={ds_name}, ld={ld_inst}, "
                f"ref={data_set_ref}, members={len(ds_members)}, "
                f"fcda_added={added_entries}"
            )
            # 同 add_goose_control_block，标记模型变更
            if self._server and self._is_running:
                self._model_changed = True
                log.info(f"DataSet {ds_name} 在 IedServer 运行时添加，需要重建 IedServer 以更新 MMS 命名空间")
            return True
        except Exception as e:
            log.error(f"注册 DataSet 失败: {e}", exc_info=True)
            return False

    def _add_fcda_entries_to_dataset(
        self,
        data_set,
        entries: Optional[List[Dict[str, Any]]],
        default_ld_inst: str,
    ) -> int:
        """向 DataSet 添加 FCDA 条目，使客户端可发现数据集中的成员

        使用 DataSetEntry_create 为每个 FCDA 引用创建条目。
        DataSetEntry_create(dataSet, variable, index, component) 参数:
          - dataSet: DataSet 对象
          - variable: MMS 变量名格式引用 (使用 $ 分隔符)
          - index: 在数据集中的索引位置
          - component: 组件名 (None 表示无子组件)

        重要:
        1. variable 参数必须使用 MMS 变量名格式，而非 IEC 61850 对象引用格式！
           - IEC 61850 对象引用: "CTMP01/GGIO1.Ind1.stVal" (用 . 分隔)
           - MMS 变量名:         "CTMP01/GGIO1$ST$Ind1$stVal" (用 $ 分隔)
        2. FCDA 引用的 LN/DO/DA 节点必须已存在于数据模型中。
        3. variable 中 "/" 前面必须是 LD 实例名 (不含 IED 前缀！)，
           因为 libIEC61850 的 createDataSets() 会自动拼接
           iedModel->name + logicalDeviceName 来查找 MMS 域名。
           若误用完整 MMS 域名 (如 "EMSDeviceCTMP01")，拼接后
           变为 "EMSDeviceEMSDeviceCTMP01"，导致域名查找失败，
           accessSpecifier.domain=NULL，客户端请求时崩溃。

        variable 格式:
          - 含 LD:  "{LD_inst}/{LN_name}${FC}${DO_name}${DA_path}"
          - 不含 LD: "{LN_name}${FC}${DO_name}${DA_path}"

        Args:
            data_set: pyiec61850 DataSet 对象
            entries: 条目列表，每个条目含 name(fcda_ref), iec_type, fc(可选)
            default_ld_inst: 默认 LD 实例名（当 FCDA 引用不包含 LD 时使用）

        Returns:
            成功添加的 FCDA 数量
        """
        if not entries:
            return 0

        # DA 名称到 FC 的映射表
        da_to_fc = {
            "stVal": "ST", "ctlVal": "CO", "Oper": "CO", "SBOw": "CO",
            "Cancel": "CO", "origin": "CO", "setVal": "CO",
            "dU": "DC", "cmdQual": "CO",
        }
        # iec_type 到 FC 的映射表
        type_to_fc = {
            "boolean": "ST", "float": "MX", "integer": "ST",
            "string": "DC", "bitstring": "ST", "timestamp": "ST",
        }
        # iec_type 到 frame_type 的映射 (用于 _add_point_from_ref)
        type_to_frame = {
            "float": 0, "boolean": 1, "integer": 1,
            "string": 1, "bitstring": 1, "timestamp": 1,
        }

        added_count = 0

        for idx, entry in enumerate(entries):
            try:
                fcda_ref = entry.get("name", "")
                if not fcda_ref:
                    continue

                # 解析 FCDA 引用，提取 LD 和 LN.DO.DA 部分
                # FCDA 引用格式: "LD0/GGIO1.Ind1.stVal" 或 "GGIO1.Ind1.stVal"
                if "/" in fcda_ref:
                    slash_idx = fcda_ref.index("/")
                    ld_part = fcda_ref[:slash_idx]
                    rest_part = fcda_ref[slash_idx + 1:]
                else:
                    ld_part = default_ld_inst
                    rest_part = fcda_ref

                # 解析 rest_part: "LN.DO.DA[.DA...]" → 构建为 MMS 变量名格式
                dot_idx = rest_part.find(".")
                if dot_idx > 0:
                    ln_name = rest_part[:dot_idx]
                    do_da_part = rest_part[dot_idx + 1:]  # "DO.DA[.DA...]"

                    # 确定 FC: 优先使用 entry 中显式指定的 FC
                    fc = entry.get("fc", "")
                    if not fc:
                        # 从 DA 名称推断 FC
                        da_name = do_da_part.rsplit(".", 1)[-1] if "." in do_da_part else do_da_part
                        fc = da_to_fc.get(da_name, "")
                    if not fc:
                        # 从 iec_type 推断 FC
                        fc = type_to_fc.get(entry.get("iec_type", ""), "")
                    if not fc:
                        # 默认使用 MX
                        fc = "MX"

                    # === 确保 LN/DO/DA 节点存在于数据模型中 ===
                    # IedServer_create 构建命名空间时会验证 DataSetEntry 引用，
                    # 若引用的 MMS 变量不存在则静默丢弃该条目。
                    # 因此必须先创建模型节点，再创建 DataSetEntry。
                    self._ensure_fcda_model_nodes(
                        ld_part, ln_name, do_da_part, fc, entry.get("iec_type", "")
                    )

                    # 构建 MMS 变量名格式引用 (使用 $ 分隔符)
                    # DataSetEntry_create 的 variable 参数中，"/" 前面是 LD 实例名
                    # (不含 IED 前缀)，libIEC61850 的 createDataSets() 会自动拼接
                    # iedModel->name + logicalDeviceName 来查找 MMS 域名。
                    # 例如: variable="CTMP01/GGIO1$ST$Ind1$stVal"
                    #   → logicalDeviceName="CTMP01"
                    #   → createDataSets 查找域名: "EMSDevice"+"CTMP01"="EMSDeviceCTMP01"
                    # 注意: 若 logicalDeviceName 已含 IED 前缀 (如 "EMSDeviceCTMP01")，
                    # 则拼接后变为 "EMSDeviceEMSDeviceCTMP01"，域名查找失败，
                    # accessSpecifier.domain=NULL，客户端请求时导致空指针崩溃！
                    do_da_mms = do_da_part.replace(".", "$")
                    variable_ref = f"{ld_part}/{ln_name}${fc}${do_da_mms}"
                else:
                    # 只有 LN 名，没有 DO/DA（异常情况，跳过）
                    log.debug(f"FCDA 引用缺少 DO/DA: {fcda_ref}")
                    continue

                log.debug(f"DataSetEntry variable_ref: {variable_ref} (fcda_ref={fcda_ref}, fc={fc})")

                try:
                    ds_entry = iec61850.DataSetEntry_create(
                        data_set, variable_ref, idx, None
                    )
                    if ds_entry:
                        self._keep_alive.append(ds_entry)
                        added_count += 1
                    else:
                        log.debug(f"DataSetEntry_create 返回空: {variable_ref}")
                except Exception as create_err:
                    log.debug(f"DataSetEntry_create 失败: {variable_ref}, error={create_err}")

            except Exception as e:
                log.debug(f"添加 FCDA 条目异常: {e}")

        if added_count > 0:
            log.info(f"DataSet 已添加 {added_count}/{len(entries)} 个 FCDA 条目")
        elif entries:
            log.info(
                f"DataSet FCDA 条目添加失败 ({len(entries)} 个), "
                f"但 GoCB 本身已被创建, 不影响 MMS 浏览发现 "
                f"(GoCB 节点已存在于 LLN0 下)"
            )

        return added_count

    def _ensure_fcda_model_nodes(
        self,
        ld_inst: str,
        ln_name: str,
        do_da_path: str,
        fc: str,
        iec_type: str,
    ) -> None:
        """确保 FCDA 引用的 LN/DO/DA 节点存在于数据模型中

        当 IedServer_create 构建命名空间时，会验证每个 DataSetEntry 引用的
        MMS 变量是否存在。如果不存在，该条目会被静默丢弃。
        因此必须在创建 DataSetEntry 之前先创建对应的模型节点。

        本方法使用与 _add_point_from_ref 相同的去重机制 (_do_map, _da_map)，
        因此不会重复创建已存在的节点。

        Args:
            ld_inst: 逻辑设备实例名 (如 "CTMP01")
            ln_name: 逻辑节点名 (如 "GGIO1")
            do_da_path: DO.DA[.DA...] 路径 (如 "Ind1.stVal" 或 "AnIn1.mag.f")
            fc: 功能约束 (如 "ST", "MX", "CO")
            iec_type: IEC 数据类型字符串 (如 "boolean", "float")
        """
        # 获取或创建 LN
        ln = self._get_or_create_ln(ld_inst, ln_name)

        # 解析 do_da_path: "DO.DA[.DA...]"
        parts = do_da_path.split(".")
        if not parts:
            return

        do_name = parts[0]
        da_path_parts = parts[1:]  # DA 层级路径

        # === 1. 获取或创建 DO ===
        do_key = f"{ld_inst}/{ln_name}.{do_name}"
        do_obj = self._do_map.get(do_key)
        if do_obj is None:
            # 确定 frame_type 用于 _add_standard_das
            frame_type = {"MX": 0, "ST": 1, "CO": 2, "SP": 3}.get(fc, 0)
            do_obj = iec61850.DataObject_create(do_name, iec61850.toModelNode(ln), 0)
            self._do_map[do_key] = do_obj
            self._keep_alive.append(do_obj)
            # 为新 DO 自动补充标准 DAs (q, t, dU)
            self._add_standard_das(do_obj, do_key, fc, frame_type, da_path_parts)

        # === 2. 沿 da_path 逐级创建 DA 层级 ===
        fc_const = self._resolve_fc_const(fc)
        if fc_const is None:
            fc_const = FC_MX

        # 推断 DA 的 IEC 61850 数据类型
        iec_type_const = self._infer_iec_type_from_str(iec_type, da_path_parts)

        parent = do_obj
        for i, part in enumerate(da_path_parts):
            is_leaf = (i == len(da_path_parts) - 1)
            part_key = f"{ld_inst}/{ln_name}.{do_name}.{'.'.join(da_path_parts[:i+1])}"

            if is_leaf:
                # 叶子节点: 创建 DataAttribute
                if part_key not in self._da_map:
                    da = iec61850.DataAttribute_create(
                        part, iec61850.toModelNode(parent),
                        iec_type_const, fc_const, 0, 0, 0
                    )
                    self._da_map[part_key] = da
                    self._keep_alive.append(da)
            else:
                # 中间节点: 创建 DataObject (结构体容器)
                existing_obj = self._do_map.get(part_key)
                if existing_obj is not None:
                    parent = existing_obj
                else:
                    sub_obj = iec61850.DataObject_create(part, iec61850.toModelNode(parent), 0)
                    self._do_map[part_key] = sub_obj
                    self._keep_alive.append(sub_obj)
                    parent = sub_obj

    @staticmethod
    def _infer_iec_type_from_str(iec_type: str, da_parts: list) -> int:
        """从 iec_type 字符串推断 IEC 61850 数据类型常量

        Args:
            iec_type: 类型字符串 ("boolean", "float", "integer", "string" 等)
            da_parts: DA 路径分段列表

        Returns:
            pyiec61850 数据类型常量
        """
        if not HAS_IEC61850:
            return 0

        leaf = da_parts[-1] if da_parts else ""

        # 优先根据叶子 DA 名推断
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

        # 回退: 根据 iec_type 字符串
        type_map = {
            "boolean": iec61850.IEC61850_BOOLEAN,
            "float": iec61850.IEC61850_FLOAT32,
            "integer": iec61850.IEC61850_INT32,
            "string": iec61850.IEC61850_VISIBLE_STRING_255,
            "bitstring": iec61850.IEC61850_BITSTRING,
            "timestamp": iec61850.IEC61850_TIMESTAMP,
        }
        return type_map.get(iec_type, iec61850.IEC61850_FLOAT32)

    def browse_datasets(self) -> List[Dict[str, Any]]:
        """返回服务器上所有已注册的数据集目录

        数据集在调用 add_goose_control_block 时被记录到 _dataset_catalog 中。
        返回结构与客户端 discover_datasets() 兼容，供前端结构树展示。

        Returns:
            DataSet 信息列表:
            [{ref, name, ld, member_count, members: [{ref, fc, iec_type}]}]
        """
        return list(self._dataset_catalog)

    def _enable_single_goose_cb(self, ld_inst: str, cb_name: str, max_retries: int = 3, retry_delay: float = 0.5):
        """设置单个 GoCB 的 GoEna=TRUE

        带重试逻辑：服务器启动后 MMS 服务可能需要短暂时间才能接受连接，
        因此在连接失败时自动重试。

        Args:
            ld_inst: 逻辑设备实例名
            cb_name: GSEControlBlock 名称
            max_retries: 最大重试次数 (默认 3)
            retry_delay: 重试间隔秒数 (默认 0.5)
        """
        if not self._server or not self._is_running:
            return

        ref = f"{self.model_name}{ld_inst}/LLN0.{cb_name}.GoEna"
        for attempt in range(1, max_retries + 1):
            conn = None
            try:
                conn = iec61850.IedConnection_create()
                result = iec61850.IedConnection_connect(conn, "127.0.0.1", self.port)
                error = result if not isinstance(result, (list, tuple)) else result[1]
                if error != 0:
                    if attempt < max_retries:
                        log.debug(f"设置 GoCB GoEna 连接失败 (第{attempt}次), {retry_delay}s 后重试: 127.0.0.1:{self.port}")
                        import time as _time
                        _time.sleep(retry_delay)
                        continue
                    log.warning(f"设置 GoCB GoEna 时无法连接到自身 (已重试{max_retries}次): 127.0.0.1:{self.port}, error={error}")
                    return
                iec61850.IedConnection_writeBooleanValue(
                    conn, ref, iec61850.IEC61850_FC_GO, True
                )
                log.info(f"GoCB GoEna 已设为 TRUE: ld={ld_inst}, cb={cb_name}")
                return
            except Exception as e:
                if attempt < max_retries:
                    log.debug(f"设置 GoCB GoEna 异常 (第{attempt}次), {retry_delay}s 后重试: {e}")
                    import time as _time
                    _time.sleep(retry_delay)
                    continue
                log.warning(f"设置 GoCB GoEna 失败 (已重试{max_retries}次, ld={ld_inst}, cb={cb_name}): {e}")
            finally:
                if conn:
                    try:
                        iec61850.IedConnection_destroy(conn)
                    except Exception as destroy_err:
                        log.debug(f"销毁 IedConnection 失败: {destroy_err}")

    def _enable_all_goose_cbs(self):
        """服务器启动后，设置所有已注册 GoCB 的 GoEna=TRUE"""
        if not self._server or not self._is_running:
            return
        for cb_info in self._goose_cb_list:
            self._enable_single_goose_cb(
                cb_info["ld_inst"], cb_info["name"]
            )

    def set_goose_interface(self, interface: str):
        """设置 GOOSE 网络接口"""
        self._goose_interface = interface
        if self._server:
            try:
                iec61850.IedServer_setGooseInterfaceId(self._server, interface)
            except Exception:
                pass

    def destroy(self):
        """销毁服务器和模型"""
        self.stop()
        if self._model:
            iec61850.IedModel_destroy(self._model)
            self._model = None
