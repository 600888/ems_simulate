"""
IEC 61850 MMS 客户端封装
基于 pyiec61850 (libiec61850 Python bindings) 实现 MMS 客户端

支持两种地址格式:
  1. 简单地址 (如 "1", "2"): 使用固定的 MMXU1/GGIO1/GGIO2 逻辑节点结构构建引用
  2. 完整引用路径 (如 "MEAS/M0GGIO1.AnIn1.mag.f"): 直接使用原始引用路径
"""

import time
from ctypes import byref, c_bool
from typing import Any, Dict, List, Optional, Tuple, Union
from .log import log
from .iec61850_defs import (
    YC_LN_CLASSES, YX_LN_CLASSES, YK_LN_CLASSES, YT_LN_CLASSES,
    ALL_LN_CLASSES, SKIP_SYSTEM_DOS, SIGNAL_DOS,
)

try:
    from pyiec61850 import pyiec61850 as iec61850
    HAS_IEC61850 = True
except ImportError:
    HAS_IEC61850 = False
    log.warning("pyiec61850 未安装，IEC 61850 功能不可用。请执行: pip install pyiec61850-ng==1.6.1.1")


# IEC 61850 功能约束 (Functional Constraint)
FC_MX = None
FC_ST = None
FC_CO = None

if HAS_IEC61850:
    FC_MX = iec61850.IEC61850_FC_MX
    FC_ST = iec61850.IEC61850_FC_ST
    FC_CO = iec61850.IEC61850_FC_CO


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
        rest_parts = rest.split('.', 2)
        if len(rest_parts) < 2:
            return None
        ln_name = rest_parts[0]
        do_name = rest_parts[1]
        da_path = rest_parts[2] if len(rest_parts) > 2 else ""
        return (ld_inst, ln_name, do_name, da_path)
    except Exception:
        return None


# IEC 61850 数据类型枚举（用于确定读写方法，替代 frame_type）
IEC_TYPE_FLOAT = "float"        # 浮点数 (MMS float)
IEC_TYPE_BOOLEAN = "boolean"    # 布尔值 (MMS boolean)
IEC_TYPE_INTEGER = "integer"    # 整数 (MMS integer, 如枚举值、计数器)
IEC_TYPE_STRING = "string"      # 字符串 (MMS visible-string, 如 dU)
IEC_TYPE_TIMESTAMP = "timestamp"  # 时标 (MMS timestamp, 如 t)
IEC_TYPE_UNKNOWN = "unknown"    # 未知类型，读取时自动探测

# DA 路径 -> (frame_type, iec_type) 映射 (用于模型发现时推断测点类型)
# frame_type 仍保留用于数据库分类（遥测/遥信/遥控/遥调），但读写不再依赖它
_DA_PATH_TO_FRAME_TYPE = {
    "mag.f": (0, IEC_TYPE_FLOAT),       # 遥测
    "cVal.mag.f": (0, IEC_TYPE_FLOAT),  # 遥测 (CMV)
    "instMag.f": (0, IEC_TYPE_FLOAT),   # 遥测 (SAV)
    "stVal": (1, IEC_TYPE_BOOLEAN),     # 遥信
    "ctlVal": (2, IEC_TYPE_BOOLEAN),    # 遥控 (布尔型)
    "Oper.ctlVal": (2, IEC_TYPE_BOOLEAN),  # 遥控
    "setVal": (3, IEC_TYPE_FLOAT),      # 遥调
}

# DA 第一层名称 -> (完整 DA 路径, frame_type, iec_type) 映射
# 用于从服务器模型发现 DA 结构时，根据 getDataDirectory 返回的 DA 名称
# 推断测点类型和完整 DA 路径，避免猜测导致的测点遗漏
_DA_PATTERNS = {
    # 遥测 (YC) - 测量值类 DA
    "mag": ("mag.f", 0, IEC_TYPE_FLOAT),          # MV/SAV CDC: 浮点测量值
    "cVal": ("cVal.mag.f", 0, IEC_TYPE_FLOAT),    # CMV CDC: 复数测量值
    "instMag": ("instMag.f", 0, IEC_TYPE_FLOAT),  # SAV CDC: 瞬时测量值
    "mxVal": ("mxVal.f", 0, IEC_TYPE_FLOAT),      # 某些实现的测量值
    "fCVal": ("fCVal.mag.f", 0, IEC_TYPE_FLOAT),  # 复数浮点测量值
    # 遥信 (YX) - 状态值类 DA
    "stVal": ("stVal", 1, IEC_TYPE_BOOLEAN),      # SPS/ACT/ACD/SEC CDC: 状态值
    # 遥控 (YK) - 控制值类 DA
    "ctlVal": ("ctlVal", 2, IEC_TYPE_BOOLEAN),    # SPC/DPC CDC: 控制值
    "Oper": ("Oper.ctlVal", 2, IEC_TYPE_BOOLEAN), # SPC/DPC CDC: 安全操作控制
    # 遥调 (YT) - 设定值类 DA
    "setVal": ("setVal", 3, IEC_TYPE_FLOAT),      # APC/BSC/ISC CDC: 设定值
    "wVal": ("wVal.f", 3, IEC_TYPE_FLOAT),        # 某些实现的设定值
}

# ENC 类型 DO 的 stVal 类型覆盖
# Mod/Beh/Health 的 stVal 是枚举整型, 而非布尔; NamPlt 无 stVal
# 格式: DO名 -> {DA名: iec_type}
_ENC_DO_DA_TYPE_OVERRIDE = {
    "Mod": {"stVal": IEC_TYPE_INTEGER, "ctlVal": IEC_TYPE_INTEGER},
    "Beh": {"stVal": IEC_TYPE_INTEGER},
    "Health": {"stVal": IEC_TYPE_INTEGER},
}

# 附加 DA (元数据类) - 这些不是主值, 但需要在树形表格中显示
# 映射格式: DA名 -> (完整DA路径, FC, iec_type)
_EXTRA_DA_INFO = {
    "q": ("q", "MX", IEC_TYPE_INTEGER),       # 品质 (Quality struct - Pack32 / BitString)
    "t": ("t", "MX", IEC_TYPE_TIMESTAMP),     # 时标 (Timestamp struct)
    "du": ("du", "DC", IEC_TYPE_STRING),      # 描述 (Description string) - 小写兼容
    "dU": ("dU", "DC", IEC_TYPE_STRING),      # 描述 (Description string) - IEC 61850 标准名
    "subVal": ("subVal", "SV", IEC_TYPE_UNKNOWN),  # 替代值
    "subEna": ("subEna", "SV", IEC_TYPE_BOOLEAN),  # 替代使能
    "blkEna": ("blkEna", "BL", IEC_TYPE_BOOLEAN),  # 闭锁使能
    "origin": ("origin", "OR", IEC_TYPE_INTEGER),  # 来源 (Origin struct - orCat=INT, orIdent=Octet)
    "ctlNum": ("ctlNum", "CO", IEC_TYPE_INTEGER),  # 控制序号
    "SBO": ("SBO", "CO", IEC_TYPE_UNKNOWN),      # SBO 参考
    "SBOw": ("SBOw.ctlVal", "CO", IEC_TYPE_BOOLEAN),  # SBO 写入
    "Cancel": ("Cancel.ctlVal", "CO", IEC_TYPE_BOOLEAN),  # 取消
    "Oper": ("Oper.ctlVal", "CO", IEC_TYPE_BOOLEAN),  # 操作 (已在 _DA_PATTERNS 中, 但这里补充 FC)
    "frVal": ("frVal", "ST", IEC_TYPE_INTEGER),  # 冻结值
    "frTm": ("frTm", "ST", IEC_TYPE_TIMESTAMP),  # 冻结时间
    "actVal": ("actVal", "ST", IEC_TYPE_INTEGER),  # BCR 实际值
    "frValSec": ("frValSec", "ST", IEC_TYPE_INTEGER),  # BCR 冻结秒值
    "valWTr": ("valWTr", "CO", IEC_TYPE_BOOLEAN),  # 值带瞬变
    # NamPlt (铭牌) 相关 DA - LPL CDC, FC=DC
    "vendor": ("vendor", "DC", IEC_TYPE_STRING),       # 厂商
    "swRev": ("swRev", "DC", IEC_TYPE_STRING),         # 软件版本
    "configRev": ("configRev", "DC", IEC_TYPE_STRING), # 配置版本
    "d": ("d", "DC", IEC_TYPE_STRING),                 # 描述 (短名称, 某些 NamPlt 实现)
    "lnNs": ("lnNs", "DC", IEC_TYPE_STRING),           # LN 命名空间
    "AddCause": ("AddCause", "CO", IEC_TYPE_INTEGER),  # 附加原因
}

# BDA 子节点 -> iec_type 映射（用于推断 struct 内部 BDA 的数据类型）
_BDA_TYPE_MAP = {
    # Quality (q) 的 BDA
    "validity": IEC_TYPE_INTEGER,
    "detailQuality": IEC_TYPE_INTEGER,
    "source": IEC_TYPE_INTEGER,
    "operatorBlocked": IEC_TYPE_BOOLEAN,
    "test": IEC_TYPE_BOOLEAN,
    # Timestamp (t) 的 BDA
    "seconds": IEC_TYPE_INTEGER,
    "fraction": IEC_TYPE_INTEGER,
    "LeapSecondsKnown": IEC_TYPE_BOOLEAN,
    "ClockedFailure": IEC_TYPE_BOOLEAN,
    "ClockNotSynchronized": IEC_TYPE_BOOLEAN,
    "TimeAccuracy": IEC_TYPE_INTEGER,
    # Origin 的 BDA
    "orCat": IEC_TYPE_INTEGER,
    "orIdent": IEC_TYPE_UNKNOWN,  # Octet string
}


# 需要递归展开子 BDA 的 struct DA 名称
# q 和 t 是 IEC61850 固有属性, 不作为测点也不展开; origin 展开为测点
_STRUCT_DA_EXPAND_ONLINE = {"origin"}

# 已知 struct DA 的硬编码 BDA 子节点 (当在线发现子 DA 失败时使用)
# q 和 t 是固有属性, 不需要回退
_KNOWN_BDA_FALLBACK_ONLINE = {
    "origin": ["orCat", "orIdent"],
}


def infer_fc_from_address(address: str) -> str:
    """根据 IEC61850 地址推断功能约束 (FC)

    从地址中提取 DA 路径的第一层, 然后查表获取 FC。

    Args:
        address: IEC61850 引用地址, 如 "LD0/LLN0.Mod.stVal"

    Returns:
        FC 字符串, 如 "MX", "ST", "CO", "DC" 等; 无法推断时返回空字符串
    """
    if not address or '/' not in address:
        return ''

    try:
        slash_idx = address.index('/')
        rest = address[slash_idx + 1:]
        dot_idx = rest.index('.')
        da_part = rest[dot_idx + 1:]
        first_dot = da_part.index('.')
        da_path = da_part[first_dot + 1:] if first_dot >= 0 else ''
    except (ValueError, IndexError):
        return ''

    if not da_path:
        return ''

    top_da = da_path.split('.')[0]

    # 先查附加 DA 表
    if top_da in _EXTRA_DA_INFO:
        return _EXTRA_DA_INFO[top_da][1]  # (path, FC, iec_type) 的第二项

    # 再查主值 DA 表
    if top_da in _DA_PATTERNS:
        frame_type = _DA_PATTERNS[top_da][1]
        fc_map = {0: 'MX', 1: 'ST', 2: 'CO', 3: 'CO'}
        return fc_map.get(frame_type, '')

    return ''


def infer_iec_type_from_address(address: str) -> str:
    """根据 IEC61850 地址推断数据类型 (iec_type)

    从地址中的 DA/BDA 路径推断数据类型，用于选择正确的读写方法。

    Args:
        address: IEC61850 引用地址, 如 "LD0/LLN0.Mod.stVal" 或 "LD0/LLN0.Mod.t.fraction"

    Returns:
        iec_type 字符串, 如 "float", "boolean", "integer", "string", "timestamp"
    """
    if not address or '/' not in address:
        return IEC_TYPE_UNKNOWN

    try:
        slash_idx = address.index('/')
        rest = address[slash_idx + 1:]
        dot_idx = rest.index('.')
        da_part = rest[dot_idx + 1:]
        first_dot = da_part.index('.')
        da_path = da_part[first_dot + 1:] if first_dot >= 0 else ''
    except (ValueError, IndexError):
        return IEC_TYPE_UNKNOWN

    if not da_path:
        return IEC_TYPE_UNKNOWN

    parts = da_path.split('.')
    top_da = parts[0]

    # 查完整 DA 路径表
    if da_path in _DA_PATH_TO_FRAME_TYPE:
        return _DA_PATH_TO_FRAME_TYPE[da_path][1]

    # 查主值 DA 表
    if top_da in _DA_PATTERNS:
        return _DA_PATTERNS[top_da][2]

    # 查附加 DA 表
    if top_da in _EXTRA_DA_INFO:
        return _EXTRA_DA_INFO[top_da][2]

    # BDA 子节点推断：如 "t.fraction", "q.validity", "origin.orCat"
    if len(parts) >= 2:
        bda_name = parts[-1]  # 取最后一段作为 BDA 名
        if bda_name in _BDA_TYPE_MAP:
            return _BDA_TYPE_MAP[bda_name]

    # DA 叶子节点特征推断
    leaf = parts[-1]
    if leaf in ("f", "db", "sg", "stepSize"):
        return IEC_TYPE_FLOAT
    if leaf in ("stVal", "ctlVal", "subEna", "blkEna"):
        return IEC_TYPE_BOOLEAN

    return IEC_TYPE_UNKNOWN




class IEC61850Client:
    """IEC 61850 MMS 客户端

    使用 pyiec61850 通过 MMS 协议连接到 IEC 61850 服务器，
    读写远端 IED 的数据属性。

    支持两种地址格式:
    1. 简单地址 (int/str 不含 '/'): 使用固定结构构建 MMS 引用
    2. 完整引用路径 (str 含 '/'): 直接使用原始引用路径构建 MMS 引用

    数据类型由地址中的 DA/BDA 路径和 FC 自动推断，不依赖 frame_type。
    """

    def __init__(
        self,
        ip: str = "127.0.0.1",
        port: int = 102,
        model_name: str = "EMS",
        ld_name: str = "GenericLD",
    ):
        if not HAS_IEC61850:
            raise RuntimeError("pyiec61850 未安装，无法创建 IEC 61850 客户端")

        self.ip = ip
        self.port = port
        self.model_name = model_name
        self.ld_name = ld_name

        self._connection = None
        self._is_connected = False

        # 地址 -> MMS 引用路径的映射
        self._point_refs: Dict[str, str] = {}
        # 地址 -> FC 的映射
        self._point_fc: Dict[str, str] = {}
        # 地址 -> iec_type 的映射
        self._point_iec_type: Dict[str, str] = {}
        # 发现的 GOOSE 控制块列表（与普通测点分开存储）
        self._discovered_goose_items: List[Dict[str, Any]] = []
        # 发现的 DataSet 列表
        self._discovered_datasets: List[Dict[str, Any]] = []

    def _build_ref(self, address) -> str:
        """根据地址构建 MMS 引用路径

        对于完整引用路径 (含 '/'): 拼接 model_name 前缀构建完整 MMS 引用
        对于简单地址: 使用 MMXU1/GGIO1/GGIO2 固定结构
        """
        if _is_full_ref(address):
            # 完整引用路径: "MEAS/M0GGIO1.AnIn1.mag.f"
            # MMS 引用: "EMSMEAS/M0GGIO1.AnIn1.mag.f"
            parsed = _parse_ref(address)
            if parsed:
                ld_inst = parsed[0]
                rest = address.split('/', 1)[1]
                return f"{self.model_name}{ld_inst}/{rest}"
            # 解析失败，回退到简单模式
            log.warning(f"IEC61850 客户端无法解析引用路径 {address}，回退到简单模式")

        # 简单地址模式: 使用固定结构
        safe_addr = str(address).replace('.', '_').replace('/', '_').replace('\\', '_').replace('-', '_')

        # 简单地址模式需要 frame_type 来确定结构，从 _point_iec_type 反推
        iec_type = self._point_iec_type.get(str(address), "")
        if iec_type == IEC_TYPE_FLOAT:
            # 遥测或遥调 - 先按遥测处理
            return f"{self.model_name}{self.ld_name}/MMXU1.MV_{safe_addr}.mag.f"
        elif iec_type == IEC_TYPE_BOOLEAN:
            # 遥信或遥控 - 先按遥信处理
            return f"{self.model_name}{self.ld_name}/GGIO1.SPS_{safe_addr}.stVal"
        else:
            # 未知类型，回退到遥测
            return f"{self.model_name}{self.ld_name}/MMXU1.MV_{safe_addr}.mag.f"

    def add_point(self, address, frame_type: int = 0, fc: str = "") -> str:
        """注册测点引用路径

        Args:
            address: 测点地址 (简单地址或完整引用路径)
            frame_type: 帧类型（仅用于数据库分类，不影响读写方式）
            fc: 功能约束（如 "MX", "ST", "CO"），为空时自动推断

        Returns:
            MMS 引用路径
        """
        addr_str = str(address)
        if addr_str not in self._point_refs:
            # 推断 FC
            if not fc:
                fc = infer_fc_from_address(addr_str)
                # 简单地址模式：按 frame_type 推断
                if not fc and not _is_full_ref(addr_str):
                    fc_map = {0: "MX", 1: "ST", 2: "CO", 3: "CO"}
                    fc = fc_map.get(frame_type, "MX")
            self._point_fc[addr_str] = fc

            # 推断 iec_type
            iec_type = infer_iec_type_from_address(addr_str)
            if iec_type == IEC_TYPE_UNKNOWN and not _is_full_ref(addr_str):
                # 简单地址模式：按 frame_type 推断
                if frame_type == 0 or frame_type == 3:
                    iec_type = IEC_TYPE_FLOAT
                else:
                    iec_type = IEC_TYPE_BOOLEAN
            self._point_iec_type[addr_str] = iec_type

            self._point_refs[addr_str] = self._build_ref(addr_str)
        return self._point_refs[addr_str]

    def connect(self, auto_discover: bool = True) -> bool:
        """连接到 IEC 61850 服务器（同步阻塞方法，应在线程中调用）

        注意: IedConnection_connect 是 C 扩展同步阻塞调用，会持有 GIL，
        因此不能在事件循环中直接调用，也不能用 run_in_executor（同样受 GIL 阻塞）。
        应通过 threading.Thread(daemon=True) 在独立线程中调用。

        Args:
            auto_discover: 是否在连接成功后自动发现模型（默认 True，保持向后兼容）
        """
        try:
            self._connection = iec61850.IedConnection_create()
            result = iec61850.IedConnection_connect(
                self._connection, self.ip, self.port
            )
            
            # 处理返回值，可能是 int 或 (None, int)
            error = result
            if isinstance(result, (list, tuple)):
                error = result[1]
                
            if error == iec61850.IED_ERROR_OK:
                self._is_connected = True
                log.info(f"IEC 61850 客户端已连接: {self.ip}:{self.port}")
                
                # 自动发现模型（可由调用方控制）
                if auto_discover:
                    self.discover_model()
                
                return True
            else:
                log.error(f"IEC 61850 连接失败, 错误码: {error}")
                self._is_connected = False
                # 连接失败时清理资源
                self._cleanup_connection()
                return False
        except Exception as e:
            log.error(f"IEC 61850 连接异常: {e}")
            self._is_connected = False
            self._cleanup_connection()
            return False

    def _cleanup_connection(self):
        """清理连接资源"""
        if self._connection:
            try:
                iec61850.IedConnection_destroy(self._connection)
            except Exception:
                pass
            self._connection = None

    def disconnect(self):
        """断开连接"""
        if self._connection:
            try:
                iec61850.IedConnection_close(self._connection)
            except Exception:
                pass
            try:
                iec61850.IedConnection_destroy(self._connection)
            except Exception:
                pass
            self._connection = None
            self._is_connected = False
            log.info("IEC 61850 客户端已断开")

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    def _get_fc_value(self, fc: str):
        """将 FC 字符串转换为 pyiec61850 常量值"""
        if not fc or not HAS_IEC61850:
            return FC_MX  # 默认 MX
        fc_map = {
            "MX": FC_MX,
            "ST": FC_ST,
            "CO": FC_CO,
        }
        return fc_map.get(fc, FC_MX)

    def read_points_batch(self, addresses: List[str], fc_map: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """批量读取多个测点值

        按 iec_type 分组批量读取，同一类型使用相同的 MMS 读取方法，
        减少类型判断和 FC 解析开销，同时支持连接断开时快速失败。

        Args:
            addresses: 测点地址列表 (简单地址或完整引用路径)
            fc_map: 地址 -> FC 的映射 (可选, 为空时使用注册时的 FC 或自动推断)

        Returns:
            {address: value} 字典, 读取失败的地址不包含在结果中
        """
        if not self._connection or not self._is_connected:
            return {}

        if not addresses:
            return {}

        fc_map = fc_map or {}

        # 1. 按 iec_type 分组, 预解析所有元数据 (ref, fc_val, iec_type)
        type_groups: Dict[str, List[Tuple[str, str, Any, str]]] = {}
        # type_groups: {iec_type: [(addr_str, ref, fc_val, iec_type), ...]}

        for addr in addresses:
            addr_str = str(addr)
            ref = self._point_refs.get(addr_str)
            if not ref:
                ref = self._build_ref(addr_str)

            # 获取 FC
            fc = fc_map.get(addr_str, "")
            if not fc:
                fc = self._point_fc.get(addr_str, "")
            if not fc:
                fc = infer_fc_from_address(addr_str)
            fc_val = self._get_fc_value(fc)

            # 获取 iec_type
            iec_type = self._point_iec_type.get(addr_str, "")
            if iec_type == IEC_TYPE_UNKNOWN:
                iec_type = infer_iec_type_from_address(addr_str)
            if not iec_type:
                iec_type = IEC_TYPE_UNKNOWN

            if iec_type not in type_groups:
                type_groups[iec_type] = []
            type_groups[iec_type].append((addr_str, ref, fc_val, iec_type))

        # 2. 按 iec_type 分组批量读取
        results: Dict[str, Any] = {}

        for iec_type, items in type_groups.items():
            try:
                if iec_type == IEC_TYPE_FLOAT:
                    self._read_floats_batch(items, results)
                elif iec_type == IEC_TYPE_BOOLEAN:
                    self._read_booleans_batch(items, results)
                elif iec_type == IEC_TYPE_INTEGER:
                    self._read_integers_batch(items, results)
                elif iec_type == IEC_TYPE_STRING:
                    self._read_strings_batch(items, results)
                elif iec_type == IEC_TYPE_TIMESTAMP:
                    self._read_timestamps_batch(items, results)
                else:
                    # UNKNOWN: 逐个自动探测
                    self._read_unknowns_batch(items, results)
            except Exception as e:
                log.error(f"IEC61850 批量读取异常 (type={iec_type}): {e}")
                self._is_connected = False
                break  # 连接异常, 停止后续读取

        return results

    def _read_floats_batch(self, items: List[Tuple[str, str, Any, str]], results: Dict[str, Any]) -> None:
        """批量读取浮点值"""
        for addr_str, ref, fc_val, _ in items:
            try:
                [value, error] = iec61850.IedConnection_readFloatValue(
                    self._connection, ref, fc_val
                )
                if error == iec61850.IED_ERROR_OK:
                    results[addr_str] = float(value)
                else:
                    log.debug(f"批量读取浮点值失败: ref={ref}, error={error}")
            except Exception as e:
                log.debug(f"批量读取浮点值异常: ref={ref}, error={e}")

    def _read_booleans_batch(self, items: List[Tuple[str, str, Any, str]], results: Dict[str, Any]) -> None:
        """批量读取布尔值 (失败时回退整数读取)"""
        for addr_str, ref, fc_val, _ in items:
            try:
                [value, error] = iec61850.IedConnection_readBooleanValue(
                    self._connection, ref, fc_val
                )
                if error == iec61850.IED_ERROR_OK:
                    results[addr_str] = bool(value)
                    continue
                # 布尔读取失败, 尝试整数读取
                if hasattr(iec61850, 'IedConnection_readIntegerValue'):
                    try:
                        [int_value, int_error] = iec61850.IedConnection_readIntegerValue(
                            self._connection, ref, fc_val
                        )
                        if int_error == iec61850.IED_ERROR_OK:
                            results[addr_str] = int(int_value)
                            continue
                    except Exception:
                        pass
                log.debug(f"批量读取布尔值失败: ref={ref}, error={error}")
            except Exception as e:
                log.debug(f"批量读取布尔值异常: ref={ref}, error={e}")

    def _read_integers_batch(self, items: List[Tuple[str, str, Any, str]], results: Dict[str, Any]) -> None:
        """批量读取整数值"""
        if not hasattr(iec61850, 'IedConnection_readIntegerValue'):
            log.debug("pyiec61850 不支持 readIntegerValue, 跳过整批量读取")
            return
        for addr_str, ref, fc_val, _ in items:
            try:
                [value, error] = iec61850.IedConnection_readIntegerValue(
                    self._connection, ref, fc_val
                )
                if error == iec61850.IED_ERROR_OK:
                    results[addr_str] = int(value)
                else:
                    log.debug(f"批量读取整数值失败: ref={ref}, error={error}")
            except Exception as e:
                log.debug(f"批量读取整数值异常: ref={ref}, error={e}")

    def _read_strings_batch(self, items: List[Tuple[str, str, Any, str]], results: Dict[str, Any]) -> None:
        """批量读取字符串值"""
        if not hasattr(iec61850, 'IedConnection_readStringValue'):
            log.debug("pyiec61850 不支持 readStringValue, 跳过字符串批量读取")
            return
        for addr_str, ref, fc_val, _ in items:
            try:
                [value, error] = iec61850.IedConnection_readStringValue(
                    self._connection, ref, fc_val
                )
                if error == iec61850.IED_ERROR_OK:
                    results[addr_str] = str(value).strip() if value else ""
                else:
                    log.debug(f"批量读取字符串值失败: ref={ref}, error={error}")
            except Exception as e:
                log.debug(f"批量读取字符串值异常: ref={ref}, error={e}")

    def _read_timestamps_batch(self, items: List[Tuple[str, str, Any, str]], results: Dict[str, Any]) -> None:
        """批量读取时标值"""
        for addr_str, ref, fc_val, _ in items:
            try:
                if hasattr(iec61850, 'IedConnection_readIntegerValue'):
                    [value, error] = iec61850.IedConnection_readIntegerValue(
                        self._connection, ref, fc_val
                    )
                    if error == iec61850.IED_ERROR_OK:
                        results[addr_str] = int(value)
                        continue
                [value, error] = iec61850.IedConnection_readFloatValue(
                    self._connection, ref, fc_val
                )
                if error == iec61850.IED_ERROR_OK:
                    results[addr_str] = float(value)
                else:
                    log.debug(f"批量读取时标值失败: ref={ref}, error={error}")
            except Exception as e:
                log.debug(f"批量读取时标值异常: ref={ref}, error={e}")

    def _read_unknowns_batch(self, items: List[Tuple[str, str, Any, str]], results: Dict[str, Any]) -> None:
        """批量自动探测读取"""
        for addr_str, ref, fc_val, _ in items:
            value = self._read_point_auto_detect(ref, fc_val)
            if value is not None:
                results[addr_str] = value

    def read_point(self, address, fc: str = "") -> Any:
        """读取测点值

        根据地址中的 DA/BDA 路径自动推断数据类型和 FC，
        选择正确的 IEC 61850 读取方法。

        Args:
            address: 测点地址 (简单地址或完整引用路径)
            fc: 功能约束 (为空时使用注册时的 FC 或自动推断)

        Returns:
            测点值 (float/int/bool/str)，失败返回 None
        """
        if not self._connection or not self._is_connected:
            return None

        addr_str = str(address)
        ref = self._point_refs.get(addr_str)
        if not ref:
            ref = self._build_ref(addr_str)

        # 获取 FC
        if not fc:
            fc = self._point_fc.get(addr_str, "")
        if not fc:
            fc = infer_fc_from_address(addr_str)
        fc_val = self._get_fc_value(fc)

        # 获取 iec_type
        iec_type = self._point_iec_type.get(addr_str, "")
        if iec_type == IEC_TYPE_UNKNOWN:
            iec_type = infer_iec_type_from_address(addr_str)

        try:
            if iec_type == IEC_TYPE_FLOAT:
                [value, error] = iec61850.IedConnection_readFloatValue(
                    self._connection, ref, fc_val
                )
                if error == iec61850.IED_ERROR_OK:
                    return float(value)
                else:
                    log.error(f"读取浮点值失败: ref={ref}, fc={fc}, error={error}")
                    return None

            elif iec_type == IEC_TYPE_BOOLEAN:
                [value, error] = iec61850.IedConnection_readBooleanValue(
                    self._connection, ref, fc_val
                )
                if error == iec61850.IED_ERROR_OK:
                    return bool(value)
                # 布尔读取失败时, 尝试整数读取 (ENC/ENS 等 CDC 的 stVal 为整型枚举值)
                if hasattr(iec61850, 'IedConnection_readIntegerValue'):
                    try:
                        [int_value, int_error] = iec61850.IedConnection_readIntegerValue(
                            self._connection, ref, fc_val
                        )
                        if int_error == iec61850.IED_ERROR_OK:
                            return int(int_value)
                    except Exception:
                        pass
                log.error(f"读取布尔值失败: ref={ref}, fc={fc}, error={error}")
                return None

            elif iec_type == IEC_TYPE_INTEGER:
                if hasattr(iec61850, 'IedConnection_readIntegerValue'):
                    [value, error] = iec61850.IedConnection_readIntegerValue(
                        self._connection, ref, fc_val
                    )
                    if error == iec61850.IED_ERROR_OK:
                        return int(value)
                    log.error(f"读取整数值失败: ref={ref}, fc={fc}, error={error}")
                    return None
                else:
                    log.error(f"pyiec61850 不支持 readIntegerValue: ref={ref}")
                    return None

            elif iec_type == IEC_TYPE_STRING:
                if hasattr(iec61850, 'IedConnection_readStringValue'):
                    [value, error] = iec61850.IedConnection_readStringValue(
                        self._connection, ref, fc_val
                    )
                    if error == iec61850.IED_ERROR_OK:
                        return str(value).strip() if value else ""
                    log.error(f"读取字符串值失败: ref={ref}, fc={fc}, error={error}")
                    return None
                else:
                    log.error(f"pyiec61850 不支持 readStringValue: ref={ref}")
                    return None

            elif iec_type == IEC_TYPE_TIMESTAMP:
                # Timestamp: 读取 seconds (整数) 和 fraction (整数)
                # 尝试读取为整数，Timestamp 的底层存储为两段整数
                if hasattr(iec61850, 'IedConnection_readIntegerValue'):
                    [value, error] = iec61850.IedConnection_readIntegerValue(
                        self._connection, ref, fc_val
                    )
                    if error == iec61850.IED_ERROR_OK:
                        return int(value)
                # 整数读取失败，尝试浮点 (某些实现)
                [value, error] = iec61850.IedConnection_readFloatValue(
                    self._connection, ref, fc_val
                )
                if error == iec61850.IED_ERROR_OK:
                    return float(value)
                log.error(f"读取时标值失败: ref={ref}, fc={fc}, error={error}")
                return None

            else:
                # IEC_TYPE_UNKNOWN: 自动探测 - 依次尝试浮点、布尔、整数、字符串
                return self._read_point_auto_detect(ref, fc_val)

        except Exception as e:
            log.error(f"IEC61850 客户端读取异常: address={address}, error={e}")
            self._is_connected = False
            return None

    def _read_point_auto_detect(self, ref: str, fc_val) -> Any:
        """自动探测数据类型并读取值（当 iec_type 为 unknown 时使用）"""
        # 尝试浮点
        try:
            [value, error] = iec61850.IedConnection_readFloatValue(
                self._connection, ref, fc_val
            )
            if error == iec61850.IED_ERROR_OK:
                return float(value)
        except Exception:
            pass

        # 尝试布尔
        try:
            [value, error] = iec61850.IedConnection_readBooleanValue(
                self._connection, ref, fc_val
            )
            if error == iec61850.IED_ERROR_OK:
                return bool(value)
        except Exception:
            pass

        # 尝试整数
        if hasattr(iec61850, 'IedConnection_readIntegerValue'):
            try:
                [value, error] = iec61850.IedConnection_readIntegerValue(
                    self._connection, ref, fc_val
                )
                if error == iec61850.IED_ERROR_OK:
                    return int(value)
            except Exception:
                pass

        # 尝试字符串
        if hasattr(iec61850, 'IedConnection_readStringValue'):
            try:
                [value, error] = iec61850.IedConnection_readStringValue(
                    self._connection, ref, fc_val
                )
                if error == iec61850.IED_ERROR_OK:
                    return str(value).strip() if value else ""
            except Exception:
                pass

        log.error(f"自动探测读取失败: ref={ref}")
        return None

    def write_point(self, address, value: Any, fc: str = "") -> bool:
        """写入测点值

        根据地址中的 DA/BDA 路径自动推断数据类型和 FC，
        选择正确的 IEC 61850 写入方法。

        Args:
            address: 测点地址 (简单地址或完整引用路径)
            value: 要写入的值
            fc: 功能约束 (为空时使用注册时的 FC 或自动推断)

        Returns:
            是否写入成功
        """
        if not self._connection or not self._is_connected:
            return False

        addr_str = str(address)
        ref = self._point_refs.get(addr_str)
        if not ref:
            ref = self._build_ref(addr_str)

        # 获取 FC
        if not fc:
            fc = self._point_fc.get(addr_str, "")
        if not fc:
            fc = infer_fc_from_address(addr_str)
        fc_val = self._get_fc_value(fc)

        # 获取 iec_type
        iec_type = self._point_iec_type.get(addr_str, "")
        if iec_type == IEC_TYPE_UNKNOWN:
            iec_type = infer_iec_type_from_address(addr_str)

        try:
            if iec_type == IEC_TYPE_FLOAT:
                error = iec61850.IedConnection_writeFloatValue(
                    self._connection, ref, fc_val, float(value)
                )
                return error == iec61850.IED_ERROR_OK

            elif iec_type == IEC_TYPE_BOOLEAN:
                error = iec61850.IedConnection_writeBooleanValue(
                    self._connection, ref, fc_val, bool(value)
                )
                return error == iec61850.IED_ERROR_OK

            elif iec_type == IEC_TYPE_INTEGER:
                if hasattr(iec61850, 'IedConnection_writeIntegerValue'):
                    error = iec61850.IedConnection_writeIntegerValue(
                        self._connection, ref, fc_val, int(value)
                    )
                    return error == iec61850.IED_ERROR_OK
                else:
                    log.error(f"pyiec61850 不支持 writeIntegerValue: ref={ref}")
                    return False

            elif iec_type == IEC_TYPE_STRING:
                if hasattr(iec61850, 'IedConnection_writeStringValue'):
                    error = iec61850.IedConnection_writeStringValue(
                        self._connection, ref, fc_val, str(value)
                    )
                    return error == iec61850.IED_ERROR_OK
                else:
                    log.error(f"pyiec61850 不支持 writeStringValue: ref={ref}")
                    return False

            else:
                # UNKNOWN: 根据 value 类型选择
                if isinstance(value, float):
                    error = iec61850.IedConnection_writeFloatValue(
                        self._connection, ref, fc_val, float(value)
                    )
                    return error == iec61850.IED_ERROR_OK
                elif isinstance(value, bool):
                    error = iec61850.IedConnection_writeBooleanValue(
                        self._connection, ref, fc_val, bool(value)
                    )
                    return error == iec61850.IED_ERROR_OK
                elif isinstance(value, int):
                    if hasattr(iec61850, 'IedConnection_writeIntegerValue'):
                        error = iec61850.IedConnection_writeIntegerValue(
                            self._connection, ref, fc_val, int(value)
                        )
                        return error == iec61850.IED_ERROR_OK
                    return False
                else:
                    log.error(f"不支持写入的数据类型: ref={ref}, value_type={type(value)}")
                    return False

        except Exception as e:
            log.error(f"IEC61850 客户端写入异常: address={address}, error={e}")
            self._is_connected = False
            return False

    def _mms_value_to_python(self, mms_value, iec_type: str = IEC_TYPE_UNKNOWN) -> Any:
        """将 MmsValue 转换为 Python 原生类型

        根据 iec_type 或 MmsValue 的 MmsType 自动选择合适的读取方法。

        Args:
            mms_value: pyiec61850 MmsValue 对象
            iec_type: 期望的数据类型 (float/boolean/integer/string/timestamp/unknown)

        Returns:
            Python 原生值 (float/bool/int/str)，None 表示转换失败
        """
        if mms_value is None:
            return None

        if not hasattr(iec61850, 'MmsValue_getType'):
            return None

        # 优先按已知 iec_type 读取
        if iec_type == IEC_TYPE_FLOAT or iec_type == IEC_TYPE_INTEGER:
            try:
                return float(iec61850.MmsValue_toFloat(mms_value))
            except Exception:
                try:
                    return int(str(mms_value))
                except Exception:
                    return None
        elif iec_type == IEC_TYPE_BOOLEAN:
            try:
                return bool(iec61850.MmsValue_getBoolean(mms_value))
            except Exception:
                return None
        elif iec_type == IEC_TYPE_STRING:
            try:
                return str(iec61850.MmsValue_toString(mms_value))
            except Exception:
                return None
        elif iec_type == IEC_TYPE_TIMESTAMP:
            try:
                return iec61850.MmsValue_getUtcTimeInMs(mms_value)
            except Exception:
                return None

        # 未知类型: 根据 MmsType 自动探测
        try:
            mms_type = iec61850.MmsValue_getType(mms_value)
            type_str = iec61850.MmsValue_getTypeString(mms_value)

            # FLOAT 类型
            if mms_type in (iec61850.MMS_FLOAT,) or 'float' in type_str.lower():
                return float(iec61850.MmsValue_toFloat(mms_value))
            # BOOLEAN 类型
            elif mms_type == iec61850.MMS_BOOLEAN:
                return bool(iec61850.MmsValue_getBoolean(mms_value))
            # INTEGER 类型
            elif mms_type in (iec61850.MMS_INTEGER, iec61850.MMS_UNSIGNED):
                return int(iec61850.MmsValue_toFloat(mms_value))
            # BITSTRING 类型
            elif hasattr(iec61850, 'MMS_BITSTRING') and mms_type == iec61850.MMS_BITSTRING:
                return iec61850.MmsValue_getBitStringAsInteger(mms_value)
            # STRING/VISIBLE_STRING 类型
            elif mms_type in (iec61850.MMS_VISIBLE_STRING, iec61850.MMS_STRING):
                return str(iec61850.MmsValue_toString(mms_value))
            # UTC TIME 类型
            elif mms_type == iec61850.MMS_UTC_TIME:
                return iec61850.MmsValue_getUtcTimeInMs(mms_value)
            # ARRAY/STRUCTURE: 返回子元素列表
            elif mms_type in (iec61850.MMS_ARRAY, iec61850.MMS_STRUCTURE):
                arr_size = iec61850.MmsValue_getArraySize(mms_value)
                elements = []
                for j in range(arr_size):
                    el = iec61850.MmsValue_getElement(mms_value, j)
                    if el:
                        el_val = self._mms_value_to_python(el, IEC_TYPE_UNKNOWN)
                        if el_val is not None:
                            elements.append(el_val)
                return elements if elements else None
            else:
                # 回退: 尝试 float 和 str
                try:
                    return float(iec61850.MmsValue_toFloat(mms_value))
                except Exception:
                    return str(mms_value)
        except Exception:
            # 最后回退
            try:
                return float(iec61850.MmsValue_toFloat(mms_value))
            except Exception:
                try:
                    return str(mms_value)
                except Exception:
                    return None

    def _get_list_from_linked_list(self, linked_list) -> List[str]:
        """从 LinkedList 中提取字符串列表

        LinkedList 结构: linked_list 本身是头节点, LinkedList_getNext 返回下一个节点。
        之前的实现从 getNext 开始遍历, 导致遗漏了链表的第一个元素。
        正确做法: 先读取头节点数据, 再遍历后续节点。
        """
        if linked_list is None:
            return []
        items = []
        # 先读取头节点的数据
        try:
            head_data = iec61850.toCharP(linked_list.data)
            if head_data:
                items.append(head_data)
        except Exception:
            pass
        # 再遍历后续节点
        item = iec61850.LinkedList_getNext(linked_list)
        while item:
            try:
                items.append(iec61850.toCharP(item.data))
            except Exception:
                pass
            item = iec61850.LinkedList_getNext(item)
        iec61850.LinkedList_destroy(linked_list)
        return items

    def _extract_ln_class(self, ln_name: str) -> Optional[str]:
        """从可能带前缀的逻辑节点名中提取 lnClass

        IEC 61850 LN 名称格式: {prefix}{lnClass}{inst}
        例如: METMMXU1 → prefix=MET, lnClass=MMXU, inst=1
              TRIPPTRC1 → prefix=TRIP, lnClass=PTRC, inst=1
        """
        alpha = ''.join(c for c in ln_name if c.isalpha())
        # 直接匹配
        if alpha in ALL_LN_CLASSES:
            return alpha
        # 从后往前尝试匹配, 去除前缀部分
        for i in range(1, len(alpha)):
            suffix = alpha[i:]
            if suffix in ALL_LN_CLASSES:
                return suffix
        return None

    def _infer_frame_type_from_do(self, ln_name: str, do_name: str) -> Optional[int]:
        """根据逻辑节点名和数据对象名推断 frame_type

        优先级:
        1. DO 名称前缀约定 (MV_, SPS_, SPC_, APC_) — 简单地址模式
        2. 跳过 ENC 类型系统 DO (Mod, Beh, Health, NamPlt) — 不可布尔读取
        3. LN class 推断 — 支持带前缀的 LN 名 (如 METMMXU1→MMXU)
        4. 信号 DO 名称 (Op, Tr, Str 等) — 映射为遥信
        5. DO 名称模式推断 — 根据常见 DO 命名规则
        """
        # 1. 前缀约定 (简单地址模式创建的 DO)
        if do_name.startswith("MV_"):
            return 0
        elif do_name.startswith("SPS_"):
            return 1
        elif do_name.startswith("SPC_"):
            return 2
        elif do_name.startswith("APC_"):
            return 3

        # 2. LLN0 系统 DO (CDC 类型为 ENC/LPL)
        # Mod/Beh/Health 的 stVal 是 ENC 整型, NamPlt 是 LPL 结构体 (字符串 DA)
        # 均映射为遥信 (frame_type=1), 但 iec_type 不是布尔
        if do_name in SKIP_SYSTEM_DOS:
            return 1  # 遥信/状态类

        # 3. 信号 DO (CDC 类型为 ACT/SPS, stVal 是布尔值)
        if do_name in SIGNAL_DOS:
            return 1  # 遥信

        # 4. LN class 推断 (支持带前缀的 LN 名)
        ln_class = self._extract_ln_class(ln_name)
        if ln_class:
            if ln_class in YC_LN_CLASSES:
                return 0  # 遥测
            elif ln_class in YX_LN_CLASSES:
                return 1  # 遥信
            elif ln_class in YK_LN_CLASSES:
                return 2  # 遥控
            elif ln_class in YT_LN_CLASSES:
                return 3  # 遥调

        # 5. DO 名称模式推断 (基于 IEC 61850 CDC 命名约定)
        if do_name.startswith(("TotW", "TotV", "TotA", "TotF", "TotPF", "TotQ")):
            return 0  # 遥测
        if do_name.startswith(("A", "V", "W", "Hz", "PF", "PhV", "PPV", "Amp", "Vol")):
            return 0  # 遥测
        # 状态类 DO (CDC: SPS, ACT, ACD, SEC, BCR)
        if do_name.startswith(("St", "Ind", "Blk", "Sw")):
            return 1  # 遥信
        # 控制类 DO (CDC: SPC, DPC, ENC)
        if do_name.startswith(("Ctl", "Pos")):
            return 2  # 遥控
        # 设点类 DO (CDC: APC, BSC, ISC)
        if do_name.startswith(("Spt", "ValW", "Csx")):
            return 3  # 遥调

        return None

    def _infer_da_path(self, frame_type: int) -> str:
        """根据 frame_type 推断数据属性路径"""
        if frame_type == 0:
            return "mag.f"
        elif frame_type == 1:
            return "stVal"
        elif frame_type == 2:
            return "ctlVal"
        elif frame_type == 3:
            return "ctlVal"
        return ""

    def _read_du_description(self, do_ref: str) -> str:
        """读取 DO 的 du (描述) 数据属性值

        du 是 IEC 61850 的描述属性 (FC=DC, bType=VisString),
        包含 DO 的人类可读描述, 用于作为测点名称.

        Args:
            do_ref: 数据对象的完整 MMS 引用 (如 "EMSGenericLD/MMXU1.TotW")

        Returns:
            du 值字符串, 失败返回空字符串
        """
        if not self._connection or not self._is_connected:
            return ""

        du_ref = f"{do_ref}.dU"
        try:
            if hasattr(iec61850, 'IedConnection_readStringValue'):
                [value, error] = iec61850.IedConnection_readStringValue(
                    self._connection, du_ref, iec61850.IEC61850_FC_DC
                )
                if error == iec61850.IED_ERROR_OK and value:
                    return str(value).strip()
        except Exception:
            pass
        return ""

    def _discover_da_paths(self, do_ref: str) -> List[Tuple[str, int, str, str]]:
        """通过查询服务器模型发现 DO 下的 DA 路径

        使用 IedConnection_getDataDirectory 获取 DO 的直接子 DA 列表,
        返回所有 DA (包括主值 DA 和元数据 DA 如 q/t/du),
        每个元组为 (da_path, frame_type, fc, iec_type)。

        Args:
            do_ref: 数据对象的完整 MMS 引用 (如 "EMSGenericLD/MMXU1.TotW")

        Returns:
            (da_path, frame_type, fc, iec_type) 元组列表, 空列表表示发现失败
        """
        try:
            result = iec61850.IedConnection_getDataDirectory(self._connection, do_ref)
            da_list = result[0] if isinstance(result, (list, tuple)) else result
            error = result[1] if isinstance(result, (list, tuple)) else 0

            if error != iec61850.IED_ERROR_OK or da_list is None:
                return []

            das = self._get_list_from_linked_list(da_list)

            found = []
            for da_name in das:
                if da_name in _DA_PATTERNS:
                    da_path, frame_type, iec_type = _DA_PATTERNS[da_name]
                    # 根据 frame_type 推断 FC
                    fc_map = {0: "MX", 1: "ST", 2: "CO", 3: "CO"}
                    fc = fc_map.get(frame_type, "")
                    found.append((da_path, frame_type, fc, iec_type))
                elif da_name in _EXTRA_DA_INFO:
                    da_path, fc, iec_type = _EXTRA_DA_INFO[da_name]
                    # q 和 t 是 IEC61850 固有属性, 不作为测点
                    if da_name in ("q", "t"):
                        continue
                    # 元数据 DA 的 frame_type 统一为 1 (遥信/状态类)
                    found.append((da_path, 1, fc, iec_type))
                    # 对 origin 等结构体 DA, 递归获取子 BDA
                    if da_name in _STRUCT_DA_EXPAND_ONLINE:
                        sub_ref = f"{do_ref}.{da_name}"
                        sub_found = self._discover_sub_da_paths(sub_ref, fc, da_name)
                        found.extend(sub_found)
                else:
                    # 未知 DA, 直接使用名称作为路径, 默认 frame_type=1
                    found.append((da_name, 1, "", IEC_TYPE_UNKNOWN))

            return found
        except Exception as e:
            log.debug(f"查询 DA 目录失败: {do_ref}, 错误: {e}")
            return []

    def _discover_sub_da_paths(self, parent_ref: str, parent_fc: str, parent_path_prefix: str = "") -> List[Tuple[str, int, str, str]]:
        """递归发现结构体 DA 的子 BDA 路径

        优先从服务器查询子 DA 目录; 若查询失败, 则使用硬编码的 BDA 回退。

        Args:
            parent_ref: 父 DA 的完整 MMS 引用 (如 "EMSGenericLD/MMXU1.TotW.q")
            parent_fc: 父 DA 的 FC
            parent_path_prefix: 父 DA 的路径前缀 (如 "q", "mag", "cVal")

        Returns:
            (da_path, frame_type, fc, iec_type) 元组列表
        """
        try:
            result = iec61850.IedConnection_getDataDirectory(self._connection, parent_ref)
            da_list = result[0] if isinstance(result, (list, tuple)) else result
            error = result[1] if isinstance(result, (list, tuple)) else 0

            if error == iec61850.IED_ERROR_OK and da_list is not None:
                das = self._get_list_from_linked_list(da_list)
                found = []
                for bda_name in das:
                    full_path = f"{parent_path_prefix}.{bda_name}"
                    iec_type = _BDA_TYPE_MAP.get(bda_name, IEC_TYPE_UNKNOWN)
                    found.append((full_path, 1, parent_fc, iec_type))
                if found:
                    return found
                # 服务器返回空列表, 使用硬编码回退
                log.debug(f"服务器返回空的子 DA 目录: {parent_ref}, 使用硬编码回退")
            else:
                log.debug(f"查询子 DA 目录失败: {parent_ref}, 使用硬编码回退")
        except Exception as e:
            log.debug(f"查询子 DA 目录异常: {parent_ref}, 错误: {e}, 使用硬编码回退")

        # 回退: 使用硬编码的 BDA 列表
        if parent_path_prefix in _KNOWN_BDA_FALLBACK_ONLINE:
            found = []
            for bda_name in _KNOWN_BDA_FALLBACK_ONLINE[parent_path_prefix]:
                full_path = f"{parent_path_prefix}.{bda_name}"
                iec_type = _BDA_TYPE_MAP.get(bda_name, IEC_TYPE_UNKNOWN)
                found.append((full_path, 1, parent_fc, iec_type))
            return found

        return []

    def _extract_code_from_address(self, address: str) -> str:
        """从 address 中提取短编码

        简单地址模式 (MV_/SPS_/SPC_/APC_ 前缀):
            "GenericLD/MMXU1.MV_1.mag.f" -> "1"
        ICD 动态模型模式:
            "MEAS/M0GGIO1.AnIn1.mag.f" -> "M0GGIO1.AnIn1"
        """
        parsed = _parse_ref(address)
        if parsed:
            ld_inst, ln_name, do_name, da_path = parsed
            # 简单地址模式: DO 名带前缀
            if do_name.startswith(("MV_", "SPS_", "SPC_", "APC_")):
                # 提取前缀后的部分
                for prefix in ("MV_", "SPS_", "SPC_", "APC_"):
                    if do_name.startswith(prefix):
                        return do_name[len(prefix):]
            # ICD 模式: LN.DO
            return f"{ln_name}.{do_name}"
        return address

    def discover_model(self) -> List[Dict[str, Any]]:
        """动态发现并映射服务端的数据模型

        支持两种模型结构:
        1. 简单地址模式: 识别 MV_/SPS_/SPC_/APC_ 前缀的 DO
        2. 动态模型模式 (ICD 导入): 识别没有前缀的 DO，根据 LN 推断 frame_type

        Returns:
            发现的测点列表，每个元素为 {"address": str, "frame_type": int, "ref": str, "code": str}
            address 使用 MMS 引用格式 (包含 model_name 前缀)，如 "EMSGenericLD/MMXU1.MV_1.mag.f"
            code 为短编码: 简单地址模式为原始地址(如 "1")，ICD 模式为 "LN.DO"(如 "M0GGIO1.AnIn1")
        """
        if not self._connection or not self._is_connected:
            return []

        log.info("开始 IEC 61850 动态模型发现...")
        start_time = time.time()
        discovered_points: List[Dict[str, Any]] = []
        self._discovered_goose_items.clear()

        # 1. 获取逻辑设备列表
        result = iec61850.IedConnection_getLogicalDeviceList(self._connection)
        ld_list = result[0] if isinstance(result, (list, tuple)) else result
        error = result[1] if isinstance(result, (list, tuple)) else 0
        
        if error != iec61850.IED_ERROR_OK:
            log.error(f"发现模型失败: 无法获取逻辑设备列表 (错误码: {error})")
            return []
        
        lds = self._get_list_from_linked_list(ld_list)
        log.info(f"发现逻辑设备: {lds}")
        
        for ld in lds:
            # 2. 获取逻辑节点列表 (使用 getLogicalDeviceDirectory)
            result = iec61850.IedConnection_getLogicalDeviceDirectory(self._connection, ld)
            ln_list = result[0] if isinstance(result, (list, tuple)) else result
            error = result[1] if isinstance(result, (list, tuple)) else 0
            
            if error != iec61850.IED_ERROR_OK:
                log.debug(f"跳过逻辑设备 {ld}: 无法获取目录 (错误码: {error})")
                continue
            
            lns = self._get_list_from_linked_list(ln_list)
            log.info(f"逻辑设备 {ld} 下发现逻辑节点: {lns}")

            for ln in lns:
                ln_ref = f"{ld}/{ln}"
                
                # 3. 获取数据对象列表 (使用 getLogicalNodeDirectory)
                result = iec61850.IedConnection_getLogicalNodeDirectory(self._connection, ln_ref, 0) # 0 = ACSI_CLASS_DATA_OBJECT
                do_list = result[0] if isinstance(result, (list, tuple)) else result
                error = result[1] if isinstance(result, (list, tuple)) else 0
                
                if error != iec61850.IED_ERROR_OK:
                    log.info(f"跳过逻辑节点 {ln_ref}: 无法获取目录 (错误码: {error})")
                    continue
                
                dos = self._get_list_from_linked_list(do_list)
                log.info(f"逻辑节点 {ln_ref} 下发现数据对象: {dos}")
                
                if not dos:
                    log.warning(f"逻辑节点 {ln_ref} 下没有发现数据对象 (DO 列表为空)")

                for do in dos:
                    # 注意: 不再跳过 Mod/Beh/Health/NamPlt 等 LLN0 系统 DO
                    # 这些 DO 的 stVal 是 ENC (整型) 而非布尔, 但 read 方法已有整数回退逻辑
                    # NamPlt 的 DA 是字符串类型, _discover_da_paths 会正确发现

                    full_do_ref = f"{ln_ref}.{do}"
                    
                    try:
                        # 简单地址模式: DO 名带前缀 (MV_, SPS_, SPC_, APC_)
                        # 前缀已经明确了测点类型和 DA 路径, 无需查询服务端
                        if do.startswith("MV_"):
                            addr = do[3:]
                            da_path = "mag.f"
                            frame_type = 0
                            fc = "MX"
                            iec_type = IEC_TYPE_FLOAT
                            ref = f"{full_do_ref}.{da_path}"
                            address = f"{ld}/{ln}.{do}.{da_path}"
                            code = addr
                            self._point_refs[address] = ref
                            self._point_fc[address] = fc
                            self._point_iec_type[address] = iec_type
                            discovered_points.append({"address": address, "frame_type": frame_type, "ref": ref, "code": code, "fc": fc, "iec_type": iec_type})
                        elif do.startswith("SPS_"):
                            addr = do[4:]
                            da_path = "stVal"
                            frame_type = 1
                            fc = "ST"
                            iec_type = IEC_TYPE_BOOLEAN
                            ref = f"{full_do_ref}.{da_path}"
                            address = f"{ld}/{ln}.{do}.{da_path}"
                            code = addr
                            self._point_refs[address] = ref
                            self._point_fc[address] = fc
                            self._point_iec_type[address] = iec_type
                            discovered_points.append({"address": address, "frame_type": frame_type, "ref": ref, "code": code, "fc": fc, "iec_type": iec_type})
                        elif do.startswith("SPC_"):
                            addr = do[4:]
                            da_path = "ctlVal"
                            frame_type = 2
                            fc = "CO"
                            iec_type = IEC_TYPE_BOOLEAN
                            ref = f"{full_do_ref}.{da_path}"
                            address = f"{ld}/{ln}.{do}.{da_path}"
                            code = addr
                            self._point_refs[address] = ref
                            self._point_fc[address] = fc
                            self._point_iec_type[address] = iec_type
                            discovered_points.append({"address": address, "frame_type": frame_type, "ref": ref, "code": code, "fc": fc, "iec_type": iec_type})
                        elif do.startswith("APC_"):
                            addr = do[4:]
                            da_path = "ctlVal"
                            frame_type = 3
                            fc = "CO"
                            iec_type = IEC_TYPE_FLOAT
                            ref = f"{full_do_ref}.{da_path}"
                            address = f"{ld}/{ln}.{do}.{da_path}"
                            code = addr
                            self._point_refs[address] = ref
                            self._point_fc[address] = fc
                            self._point_iec_type[address] = iec_type
                            discovered_points.append({"address": address, "frame_type": frame_type, "ref": ref, "code": code, "fc": fc, "iec_type": iec_type})
                        else:
                            # 动态模型模式 (ICD 导入): DO 没有前缀
                            # 优先通过查询服务端实际数据模型发现 DA 结构,
                            # 返回所有 DA (包括主值 DA 和元数据 DA 如 q/t/du)
                            da_paths = self._discover_da_paths(full_do_ref)

                            # 尝试读取 du (描述) 作为测点名称
                            du_desc = self._read_du_description(full_do_ref)

                            if da_paths:
                                # 从服务端模型发现了具体的 DA 路径
                                for da_path, frame_type, fc, iec_type in da_paths:
                                    # ENC 类型 DO 的 stVal/ctlVal 是整型而非布尔
                                    if do in _ENC_DO_DA_TYPE_OVERRIDE:
                                        da_top = da_path.split('.')[0]
                                        override_type = _ENC_DO_DA_TYPE_OVERRIDE[do].get(da_top)
                                        if override_type:
                                            iec_type = override_type
                                    ref = f"{full_do_ref}.{da_path}"
                                    address = f"{ld}/{ln}.{do}.{da_path}"
                                    # code 使用 LN.DO.DA路径格式, 确保唯一
                                    code = f"{ln}.{do}.{da_path}"
                                    # 测点名称: 优先使用 du 描述, 否则用 DO 名
                                    name = du_desc if du_desc else do
                                    self._point_refs[address] = ref
                                    self._point_fc[address] = fc
                                    self._point_iec_type[address] = iec_type
                                    discovered_points.append({
                                        "address": address, "frame_type": frame_type,
                                        "ref": ref, "code": code, "name": name, "fc": fc,
                                        "iec_type": iec_type,
                                    })
                            else:
                                # getDataDirectory 不可用或失败, 回退到推断模式
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
                                # 推断 iec_type
                                iec_type = IEC_TYPE_FLOAT if frame_type in (0, 3) else IEC_TYPE_BOOLEAN
                                # ENC 类型 DO 的 stVal 是整型
                                if do in _ENC_DO_DA_TYPE_OVERRIDE:
                                    override_type = _ENC_DO_DA_TYPE_OVERRIDE[do].get(da_path)
                                    if override_type:
                                        iec_type = override_type
                                self._point_refs[address] = ref
                                self._point_fc[address] = fc
                                self._point_iec_type[address] = iec_type
                                discovered_points.append({
                                    "address": address, "frame_type": frame_type,
                                    "ref": ref, "code": code, "name": name, "fc": fc,
                                    "iec_type": iec_type,
                                })
                    except Exception as e:
                        log.error(f"解析测点地址失败: {do}, 错误: {e}")
                        continue

                # 4. 对于 LLN0, 发现 GOOSE 控制块 (GoCB)
                go_cb_names: List[str] = []
                if ln == "LLN0" and hasattr(iec61850, 'ACSI_CLASS_GoCB'):
                    try:
                        gse_result = iec61850.IedConnection_getLogicalNodeDirectory(
                            self._connection, ln_ref, int(iec61850.ACSI_CLASS_GoCB)
                        )
                        gse_list = gse_result[0] if isinstance(gse_result, (list, tuple)) else gse_result
                        gse_error = gse_result[1] if isinstance(gse_result, (list, tuple)) else 0
                        if gse_error == iec61850.IED_ERROR_OK and gse_list is not None:
                            names = self._get_list_from_linked_list(gse_list)
                            for name in (names or []):
                                if name and name not in go_cb_names:
                                    try:
                                        goena_ref = f"{ln_ref}.{name}.GoEna"
                                        [_, goena_err] = iec61850.IedConnection_readBooleanValue(
                                            self._connection, goena_ref, iec61850.IEC61850_FC_GO
                                        )
                                        if goena_err == iec61850.IED_ERROR_OK:
                                            go_cb_names.append(name)
                                    except Exception:
                                        pass
                    except Exception:
                        pass

                    for cb_name in go_cb_names:
                        cb_ref = f"{ld}/LLN0.{cb_name}"
                        app_id = None
                        dat_set = ""
                        conf_rev = 0
                        go_id = ""
                        if hasattr(iec61850, 'IEC61850_FC_GO'):
                            try:
                                appid_ref = f"{cb_ref}.appID"
                                [value, err] = iec61850.IedConnection_readUnsigned32Value(
                                    self._connection, appid_ref, iec61850.IEC61850_FC_GO
                                )
                                if err == iec61850.IED_ERROR_OK:
                                    app_id = int(value)
                            except Exception:
                                pass
                            try:
                                ds_ref = f"{cb_ref}.datSet"
                                [value, err] = iec61850.IedConnection_readStringValue(
                                    self._connection, ds_ref, iec61850.IEC61850_FC_GO
                                )
                                if err == iec61850.IED_ERROR_OK:
                                    dat_set = str(value or "")
                            except Exception:
                                pass
                            try:
                                cr_ref = f"{cb_ref}.confRev"
                                [value, err] = iec61850.IedConnection_readUnsigned32Value(
                                    self._connection, cr_ref, iec61850.IEC61850_FC_GO
                                )
                                if err == iec61850.IED_ERROR_OK:
                                    conf_rev = int(value)
                            except Exception:
                                pass
                            try:
                                gid_ref = f"{cb_ref}.goID"
                                [value, err] = iec61850.IedConnection_readStringValue(
                                    self._connection, gid_ref, iec61850.IEC61850_FC_GO
                                )
                                if err == iec61850.IED_ERROR_OK:
                                    go_id = str(value or "")
                            except Exception:
                                pass

                        go_cb_ref = f"{ld}/LLN0$GO${cb_name}"
                        goose_item = {
                            "_type": "goose",
                            "go_cb_ref": go_cb_ref,
                            "go_id": go_id,
                            "app_id": app_id,
                            "data_set_ref": dat_set,
                            "conf_rev": conf_rev,
                            "name": cb_name,
                            "ld_inst": ld,
                        }
                        discovered_points.append(goose_item)
                        self._discovered_goose_items.append(goose_item)
                        log.info(f"发现 GOOSE 控制块: {go_cb_ref}, appID=0x{(app_id or 0):04X}, ds={dat_set}")

                if not go_cb_names:
                    log.warning(f"LLN0({ln_ref}) 下未发现任何 GoCB (可能服务器不支持 GoCB 浏览)")

        # 5. 发现 DataSet (数据集)
        try:
            self._discovered_datasets = self.discover_datasets()
            log.info(f"动态发现完成, 发现 {len(self._discovered_datasets)} 个 DataSet")
        except Exception as e:
            log.debug(f"自动发现 DataSet 失败: {e}")
            self._discovered_datasets = []

        log.info(f"IEC 61850 动态发现完成, 耗时: {time.time() - start_time:.2f}s, 发现并映射了 {len(discovered_points)} 个测点")
        return discovered_points

    def get_discovered_points(self) -> List[Dict[str, Any]]:
        """获取当前已映射的测点列表（含 GOOSE 控制块）

        Returns:
            测点列表，每个元素为 {"address": str, "frame_type": int, "ref": str, "code": str, "name": str, "fc": str}
            GOOSE 控制块带 _type="goose" 标记
        """
        result = []
        for addr, ref in self._point_refs.items():
            code = self._extract_code_from_address(addr)
            fc = self._point_fc.get(addr, "")
            iec_type = self._point_iec_type.get(addr, IEC_TYPE_UNKNOWN)
            parsed = _parse_ref(addr)
            name = parsed[2] if parsed else code
            da_path = parsed[3] if parsed else ""
            frame_type = 0
            if da_path:
                top_da = da_path.split('.')[0]
                if top_da in _DA_PATTERNS:
                    frame_type = _DA_PATTERNS[top_da][1]
                elif top_da in _EXTRA_DA_INFO:
                    frame_type = 1
            result.append({"address": addr, "frame_type": frame_type, "ref": ref, "code": code, "name": name, "fc": fc, "iec_type": iec_type})
        # 追加发现的 GOOSE 控制块
        result.extend(self._discovered_goose_items)
        return result

    def get_discovered_datasets(self) -> List[Dict[str, Any]]:
        """获取当前已发现的 DataSet 列表"""
        return list(self._discovered_datasets)

    def discover_datasets(self) -> List[Dict[str, Any]]:
        """发现所有逻辑设备下的 DataSet (数据集) 引用

        使用 IedConnection_getLogicalDeviceDataSets 获取每个 LD 下的 DataSet 列表，
        然后使用 IedConnection_getDataSetDirectory 获取每个 DataSet 的成员信息。

        Returns:
            DataSet 信息列表，每个元素包含:
            {
                "ref": "LD0/LLN0$dsGOOSE1",       # DataSet 完整引用
                "name": "dsGOOSE1",                  # DataSet 名称
                "ld": "LD0",                         # 所属逻辑设备
                "ln": "LLN0",                        # 所属逻辑节点
                "member_count": 5,                   # 成员数量
                "members": [                         # 成员列表
                    {"ref": "LD0/MMXU1.TotW.mag.f", "fc": "MX"},
                    ...
                ]
            }
        """
        if not self._connection or not self._is_connected:
            return []

        if not hasattr(iec61850, 'IedConnection_getLogicalDeviceDataSets'):
            log.warning("pyiec61850 不支持获取逻辑设备 DataSet 列表")
            return []

        # 1. 获取逻辑设备列表
        try:
            lds = self.browse_logical_devices()
        except Exception as e:
            log.error(f"发现 DataSet 时获取逻辑设备列表失败: {e}")
            return []

        datasets_result = []
        for ld in lds:
            try:
                # 2. 获取逻辑设备下的 DataSet 引用列表
                ds_refs_raw = iec61850.IedConnection_getLogicalDeviceDataSets(
                    self._connection, ld
                )
                if isinstance(ds_refs_raw, (list, tuple)):
                    ds_ref_list = ds_refs_raw[0] if ds_refs_raw[0] else None
                    ds_error = ds_refs_raw[1] if len(ds_refs_raw) > 1 else 0
                else:
                    ds_ref_list = ds_refs_raw
                    ds_error = 0

                if ds_error != iec61850.IED_ERROR_OK or ds_ref_list is None:
                    log.debug(f"逻辑设备 {ld} 下没有 DataSet (错误码: {ds_error})")
                    continue

                # 解析 DataSet 引用列表
                ds_refs = self._get_list_from_linked_list(ds_ref_list)

                for ds_ref in ds_refs:
                    ds_ref_str = str(ds_ref)
                    catalog_ref = ds_ref_str  # 用于 catalog 存储（可能比原始 ref 多 LD 前缀）
                    # 解析 DataSet 名称: "LD0/LLN0$dsGOOSE1" -> "dsGOOSE1"
                    ds_name = ds_ref_str.split("$")[-1] if "$" in ds_ref_str else ds_ref_str
                    # 解析所属 LD/LN
                    # 注意: 远程 IED 的 IedConnection_getLogicalDeviceDataSets 返回的 ref
                    # 可能不带 LD 前缀 (如 "LLN0$dsRack1CellTemp")，因为 LD 由 API 调用上下文隐含
                    try:
                        parts = ds_ref_str.split("/", 1)
                        if len(parts) >= 2:
                            ds_ld = parts[0]
                            ln_part = parts[1].split("$")[0] if "$" in parts[1] else ""
                        else:
                            ds_ld = ld  # 使用外层循环的 LD 名称
                            ln_part = parts[0].split("$")[0] if "$" in parts[0] else ""
                            # 补全 ref 为完整格式（前端树结构依赖 LD 前缀）
                            catalog_ref = f"{ds_ld}/{ds_ref_str}"
                    except Exception:
                        ds_ld = ld
                        ln_part = ""

                    # 3. 浏览 DataSet 目录 (获取成员列表)
                    # 注意: API 调用用原始 ds_ref_str (不带 LD 前缀)，远程 IED 可能不认识补全后的 ref
                    members = self.browse_dataset_directory(ds_ref_str)

                    datasets_result.append({
                        "ref": catalog_ref,  # 存储补全后的完整 ref
                        "name": ds_name,
                        "ld": ds_ld,
                        "ln": ln_part,
                        "member_count": len(members),
                        "members": members,
                    })
                    log.info(f"发现 DataSet: {catalog_ref}, 成员数: {len(members)}")

            except Exception as e:
                log.debug(f"发现逻辑设备 {ld} 的 DataSet 时出错: {e}")
                continue

        log.info(f"DataSet 发现完成, 共发现 {len(datasets_result)} 个 DataSet")
        return datasets_result

    def browse_dataset_directory(self, dataset_ref: str) -> List[Dict[str, Any]]:
        """浏览 DataSet 目录, 获取其成员列表 (FCDA 条目)

        使用 IedConnection_getDataSetDirectory 获取 DataSet 中所有 FCDA 引用，
        每个成员包含引用路径 (ref)、功能约束 (fc)、和推断的数据类型 (iec_type)。

        Args:
            dataset_ref: DataSet 引用路径，如 "LD0/LLN0$dsGOOSE1"

        Returns:
            成员信息列表:
            [{"ref": str, "fc": str, "iec_type": str}, ...]
        """
        if not self._connection or not self._is_connected:
            return []

        if not hasattr(iec61850, 'IedConnection_getDataSetDirectory'):
            log.warning("pyiec61850 不支持浏览 DataSet 目录")
            return []

        try:
            # 不同 pyiec61850 版本的 IedConnection_getDataSetDirectory 签名不同:
            #   方式1: getDataSetDirectory(conn, ref, byref(c_bool())) -> (sDataSet, error)
            #   方式2: getDataSetDirectory(conn, ref, False) -> (sDataSet, error)
            #   方式3: getDataSetDirectory(conn, ref) -> (sDataSet, error)
            is_deletable = c_bool()
            result = None
            try_methods = [
                lambda: iec61850.IedConnection_getDataSetDirectory(
                    self._connection, dataset_ref, byref(is_deletable)),
                lambda: iec61850.IedConnection_getDataSetDirectory(
                    self._connection, dataset_ref, False),
                lambda: iec61850.IedConnection_getDataSetDirectory(
                    self._connection, dataset_ref, is_deletable),
                lambda: iec61850.IedConnection_getDataSetDirectory(
                    self._connection, dataset_ref),
            ]
            for try_fn in try_methods:
                try:
                    result = try_fn()
                    if result is not None:
                        break
                except TypeError:
                    continue
                except Exception:
                    continue
            if result is None:
                return []
                s_data_set = result[0] if result[0] else None
                dir_error = result[1] if len(result) > 1 else 0
            else:
                s_data_set = result
                dir_error = 0

            if dir_error != iec61850.IED_ERROR_OK or s_data_set is None:
                log.debug(f"浏览 DataSet 目录失败: {dataset_ref} (错误码: {dir_error})")
                return []

            # sDataSet.fcdas 是一个 LinkedList，每个节点包含 DataSetEntry
            fcdas = getattr(s_data_set, 'fcdas', None)
            if fcdas is None:
                return []

            members = []
            it = iec61850.LinkedList_getNext(fcdas)
            while it:
                entry = iec61850.LinkedList_getData(it)
                if entry:
                    try:
                        # DataSetEntry 字段: logicalDeviceName, variableName, componentName
                        ld_name = getattr(entry, 'logicalDeviceName', '') or ''
                        var_name = getattr(entry, 'variableName', '') or ''
                        comp_name = getattr(entry, 'componentName', '') or ''
                        entry_index = getattr(entry, 'index', 0) or 0

                        # 构建 FCDA 引用: "LD0/MMXU1.TotW.mag.f"
                        if ld_name and var_name:
                            if comp_name:
                                ref_str = f"{ld_name}/{var_name}.{comp_name}"
                                # 处理有 index 的情况 (如数组元素)
                                if entry_index > 0:
                                    ref_str = f"{ld_name}/{var_name}[{entry_index}].{comp_name}"
                            else:
                                ref_str = f"{ld_name}/{var_name}"
                        else:
                            # 备用: 使用 DataSetEntry.value 或 str(entry)
                            ref_str = str(entry) if entry else ""

                        # 推断 FC
                        fc_str = infer_fc_from_address(ref_str) if ref_str else "MX"

                        # 推断 iec_type
                        iec_type = infer_iec_type_from_address(ref_str) if ref_str else IEC_TYPE_UNKNOWN

                        members.append({
                            "ref": ref_str,
                            "fc": fc_str,
                            "iec_type": iec_type,
                            "index": entry_index,
                        })
                    except Exception as e:
                        log.debug(f"解析 DataSet 条目时出错: {e}")

                it = iec61850.LinkedList_getNext(it)

            return members

        except Exception as e:
            log.error(f"浏览 DataSet 目录异常: {dataset_ref}, 错误: {e}")
            return []

    def read_dataset_values(self, dataset_ref: str, fc: str = "") -> Dict[str, Any]:
        """通过 DataSet 一次 MMS 调用读取所有成员的值

        使用 IedConnection_readDataSetValues 在单个 MMS 请求中读取 DataSet
        的所有成员值。这比逐点读取效率高得多。

        Args:
            dataset_ref: DataSet 引用路径，如 "LD0/LLN0$dsGOOSE1"
            fc: 功能约束 (如 "MX", "ST", "CO")，为空时自动使用 MX

        Returns:
            {fcda_ref: value} 字典，
            如 {"GenericEquipment/LLN0.dsGOOSE1.member1": 123.45, ...}
        """
        if not self._connection or not self._is_connected:
            return {}

        if not hasattr(iec61850, 'IedConnection_readDataSetValues'):
            log.warning("pyiec61850 不支持 IedConnection_readDataSetValues")
            return {}

        fc_val = self._get_fc_value(fc) if fc else FC_MX

        try:
            # 尝试 3 参数版本: readDataSetValues(conn, ref, fc) -> (ClientDataSet, error)
            result = iec61850.IedConnection_readDataSetValues(
                self._connection, dataset_ref, fc_val
            )
            if isinstance(result, (list, tuple)):
                client_data_set = result[0] if len(result) > 0 else None
                read_error = result[1] if len(result) > 1 else 0
            else:
                client_data_set = result
                read_error = 0

        except TypeError:
            # 4 参数版本: readDataSetValues(conn, ref, fc, clientDataSet) -> error
            client_data_set = None
            read_error = -1
            if hasattr(iec61850, 'ClientDataSet_create'):
                try:
                    client_data_set = iec61850.ClientDataSet_create()
                    err = iec61850.IedConnection_readDataSetValues(
                        self._connection, dataset_ref, fc_val, client_data_set
                    )
                    if isinstance(err, (list, tuple)):
                        read_error = err[1] if len(err) > 1 else err[0]
                    else:
                        read_error = int(err)
                except Exception as e2:
                    log.debug(f"读取 DataSet 值(4参数)失败: {dataset_ref}, {e2}")
                    return {}

        if read_error != 0 or client_data_set is None:
            log.debug(f"读取 DataSet 值失败: {dataset_ref} (错误码: {read_error})")
            return {}

        # 获取成员列表（用于映射返回值到 FCDA 引用）
        members = self.browse_dataset_directory(dataset_ref)

        # 使用 ClientDataSet_getValues 获取 MmsValue 数组
        if not hasattr(iec61850, 'ClientDataSet_getValues'):
            return {}

        mms_array = iec61850.ClientDataSet_getValues(client_data_set)
        if mms_array is None:
            return {}

        values = {}
        array_size = iec61850.MmsValue_getArraySize(mms_array) if hasattr(iec61850, 'MmsValue_getArraySize') else 0

        for i in range(min(array_size, len(members))):
            element = iec61850.MmsValue_getElement(mms_array, i) if hasattr(iec61850, 'MmsValue_getElement') else None
            if element is None:
                continue

            member = members[i] if i < len(members) else {}
            ref = member.get("ref", str(i))
            iec_type = member.get("iec_type", IEC_TYPE_UNKNOWN)

            try:
                val = self._mms_value_to_python(element, iec_type)
                if val is not None:
                    values[ref] = val
            except Exception:
                pass

        # 清理
        try:
            iec61850.MmsValue_delete(mms_array)
        except Exception:
            pass
        try:
            iec61850.ClientDataSet_destroy(client_data_set)
        except Exception:
            pass

        return values

    def browse_logical_devices(self) -> List[str]:
        """浏览远端 IED 的逻辑设备列表"""
        if not self._connection or not self._is_connected:
            return []

        try:
            [ld_list, error] = iec61850.IedConnection_getLogicalDeviceList(
                self._connection
            )
            if error != iec61850.IED_ERROR_OK:
                return []

            return self._get_list_from_linked_list(ld_list)
        except Exception as e:
            log.error(f"浏览逻辑设备失败: {e}")
            return []

    def browse_logical_nodes(self, ld: str) -> List[str]:
        """浏览指定逻辑设备下的逻辑节点列表

        Args:
            ld: 逻辑设备名称，如 "EMSGenericLD"

        Returns:
            逻辑节点名称列表，如 ["LLN0", "MMXU1", "GGIO1"]
        """
        if not self._connection or not self._is_connected:
            return []

        try:
            result = iec61850.IedConnection_getLogicalDeviceDirectory(self._connection, ld)
            ln_list = result[0] if isinstance(result, (list, tuple)) else result
            error = result[1] if isinstance(result, (list, tuple)) else 0

            if error != iec61850.IED_ERROR_OK:
                log.debug(f"获取逻辑设备 {ld} 的逻辑节点失败 (错误码: {error})")
                return []

            lns = self._get_list_from_linked_list(ln_list)
            return sorted(lns)
        except Exception as e:
            log.error(f"浏览逻辑节点失败: {e}")
            return []

    def browse_data_objects(self, ld: str, ln: str) -> List[Dict[str, Any]]:
        """浏览指定逻辑节点下的数据对象列表

        类似 IECSCOUT 的 DO 浏览, 返回每个 DO 的名称和推断的测点类型。

        Args:
            ld: 逻辑设备名称 (含 model_name 前缀), 如 "EMSGenericLD"
            ln: 逻辑节点名称, 如 "MMXU1"

        Returns:
            DO 信息列表, 如 [{"name": "TotW", "frame_type": 0}, ...]
        """
        if not self._connection or not self._is_connected:
            return []

        ln_ref = f"{ld}/{ln}"
        try:
            result = iec61850.IedConnection_getLogicalNodeDirectory(
                self._connection, ln_ref, 0  # 0 = ACSI_CLASS_DATA_OBJECT
            )
            do_list = result[0] if isinstance(result, (list, tuple)) else result
            error = result[1] if isinstance(result, (list, tuple)) else 0

            if error != iec61850.IED_ERROR_OK or do_list is None:
                return []

            dos = self._get_list_from_linked_list(do_list)
            do_items = []
            for do_name in dos:
                # 不再跳过 SKIP_SYSTEM_DOS, LLN0 的 Mod/Beh/Health/NamPlt 也应显示
                frame_type = self._infer_frame_type_from_do(ln, do_name)
                do_items.append({
                    "name": do_name,
                    "frame_type": frame_type,
                })
            return do_items
        except Exception as e:
            log.error(f"浏览数据对象失败: {e}")
            return []

    def browse_data_attributes(self, ld: str, ln: str, do_name: str) -> List[Dict[str, Any]]:
        """浏览指定数据对象下的数据属性列表 (类似 IECSCOUT)

        使用 getDataDirectory 获取 DO 的 DA 结构, 返回每个 DA 的
        名称、完整路径、功能约束 (FC) 和数据类型。
        包含所有 DA (主值和元数据如 q/t/du)。

        Args:
            ld: 逻辑设备名称 (含 model_name 前缀)
            ln: 逻辑节点名称
            do_name: 数据对象名称

        Returns:
            DA 信息列表, 如 [{"name": "mag", "path": "mag.f", "fc": "MX", "type": "Float32"}, ...]
        """
        if not self._connection or not self._is_connected:
            return []

        do_ref = f"{ld}/{ln}.{do_name}"
        try:
            result = iec61850.IedConnection_getDataDirectory(self._connection, do_ref)
            da_list = result[0] if isinstance(result, (list, tuple)) else result
            error = result[1] if isinstance(result, (list, tuple)) else 0

            if error != iec61850.IED_ERROR_OK or da_list is None:
                return []

            das = self._get_list_from_linked_list(da_list)

            da_items = []
            for da_name in das:
                da_info = {"name": da_name, "path": da_name, "fc": "", "type": ""}

                # 匹配已知 DA 模式, 推断完整路径和类型
                if da_name in _DA_PATTERNS:
                    full_path, frame_type = _DA_PATTERNS[da_name]
                    da_info["path"] = full_path
                    type_names = {0: "Float32", 1: "Boolean", 2: "Boolean", 3: "Float32"}
                    fc_names = {0: "MX", 1: "ST", 2: "CO", 3: "CO"}
                    da_info["type"] = type_names.get(frame_type, "")
                    da_info["fc"] = fc_names.get(frame_type, "")
                elif da_name in _EXTRA_DA_INFO:
                    full_path, fc, type_desc = _EXTRA_DA_INFO[da_name]
                    da_info["path"] = full_path
                    da_info["fc"] = fc
                    da_info["type"] = type_desc
                else:
                    # 未知 DA, 使用名称作为路径
                    da_info["type"] = "Unknown"

                da_items.append(da_info)
            return da_items
        except Exception as e:
            log.debug(f"浏览数据属性失败: {do_ref}, 错误: {e}")
            return []

    # ========== 模型导出插件 ==========

    @property
    def model_exporter(self):
        """获取模型导出工具实例 (懒加载)"""
        if not hasattr(self, '_model_exporter') or self._model_exporter is None:
            from .iec61850_model_exporter import IEC61850ModelExporter
            self._model_exporter = IEC61850ModelExporter(self)
        return self._model_exporter

    def discover_server_model(self):
        """动态发现服务端完整数据模型 (结构化)

        委托给 IEC61850ModelExporter，返回 ServerModel 对象。
        包含完整的 LD -> LN -> DO/DS/RCB/GoCB -> DA/BDA 树形层次。
        """
        return self.model_exporter.discover()

    def export_model_json(self, model, output_path, indent=2):
        """导出模型为 JSON - 委托给 model_exporter"""
        return self.model_exporter.export_json(model, output_path, indent)

    def export_model_csv(self, model, output_path):
        """导出模型为 CSV - 委托给 model_exporter"""
        return self.model_exporter.export_csv(model, output_path)

    def export_model_tree_text(self, model, output_path):
        """导出模型为树形文本 - 委托给 model_exporter"""
        return self.model_exporter.export_tree_text(model, output_path)

    def export_model_xml(self, model, output_path, pretty=True):
        """导出模型为 XML - 委托给 model_exporter"""
        return self.model_exporter.export_xml(model, output_path, pretty)

    def export_model_icd(self, model, output_path, ied_name="", pretty=True):
        """导出模型为 ICD (SCL标准格式) - 委托给 model_exporter"""
        return self.model_exporter.export_icd(model, output_path, ied_name=ied_name, pretty=pretty)

    def export_model_all(self, model, output_dir, ied_name=""):
        """导出所有格式 - 委托给 model_exporter"""
        return self.model_exporter.export_all(model, output_dir, ied_name=ied_name)
