"""IEC 61850 地址解析与推断工具

统一地址解析、FC 推断、iec_type 推断逻辑，
供 Client/Server/ModelExporter 共用。

消除了原来在 client.py 和 server.py 中重复定义的
_is_full_ref, _parse_ref, _extract_ln_class, _split_ln_name 等函数。
"""

from dataclasses import dataclass

from .constants import IEC_TYPE_BOOLEAN, IEC_TYPE_FLOAT, IEC_TYPE_UNKNOWN
from .da_patterns import (
    BDA_TYPE_MAP,
    DA_PATH_TO_FRAME_TYPE,
    DA_PATTERNS,
    EXTRA_DA_INFO,
)
from .ln_classes import ALL_LN_CLASSES


@dataclass(frozen=True, slots=True)
class ParsedRef:
    """解析后的 IEC 61850 引用路径"""

    ld_inst: str
    ln_name: str
    do_name: str
    da_path: str


def is_full_ref(address) -> bool:
    """判断地址是否为完整引用路径 (包含 '/')

    原 client.py:38 和 server.py:37 的 _is_full_ref() 统一。
    """
    return isinstance(address, str) and "/" in address


def parse_ref(address: str) -> tuple[str, str, str, str] | None:
    """解析完整 IEC 61850 引用路径

    格式: {ld_inst}/{ln_name}.{do_name}.{da_path}
    例: "MEAS/M0GGIO1.AnIn1.mag.f" -> ("MEAS", "M0GGIO1", "AnIn1", "mag.f")

    原 client.py:43 和 server.py:42 的 _parse_ref() 统一。

    Returns:
        (ld_inst, ln_name, do_name, da_path) 或 None (解析失败)
    """
    try:
        parts = address.split("/", 1)
        if len(parts) != 2:
            return None
        ld_inst = parts[0]
        rest = parts[1]
        rest_parts = rest.split(".", 2)
        if len(rest_parts) < 2:
            return None
        ln_name = rest_parts[0]
        do_name = rest_parts[1]
        da_path = rest_parts[2] if len(rest_parts) > 2 else ""
        return (ld_inst, ln_name, do_name, da_path)
    except Exception:
        return None


def infer_fc_from_address(address: str) -> str:
    """根据 IEC61850 地址推断功能约束 (FC)

    从地址中提取 DA 路径的第一层, 然后查表获取 FC。

    原 client.py:200 和 server.py 中的 FC 推断逻辑统一。

    Args:
        address: IEC61850 引用地址, 如 "LD0/LLN0.Mod.stVal"

    Returns:
        FC 字符串, 如 "MX", "ST", "CO", "DC" 等; 无法推断时返回空字符串
    """
    if not address or "/" not in address:
        return ""

    try:
        slash_idx = address.index("/")
        rest = address[slash_idx + 1 :]
        dot_idx = rest.index(".")
        da_part = rest[dot_idx + 1 :]
        first_dot = da_part.index(".")
        da_path = da_part[first_dot + 1 :] if first_dot >= 0 else ""
    except (ValueError, IndexError):
        return ""

    if not da_path:
        return ""

    top_da = da_path.split(".")[0]

    # 先查附加 DA 表
    if top_da in EXTRA_DA_INFO:
        return EXTRA_DA_INFO[top_da][1]  # (path, FC, iec_type) 的第二项

    # 再查主值 DA 表
    if top_da in DA_PATTERNS:
        frame_type = DA_PATTERNS[top_da][1]
        fc_map = {0: "MX", 1: "ST", 2: "CO", 3: "SP"}
        return fc_map.get(frame_type, "")

    return ""


def infer_iec_type_from_address(address: str) -> str:
    """根据 IEC61850 地址推断数据类型 (iec_type)

    从地址中的 DA/BDA 路径推断数据类型，用于选择正确的读写方法。

    原 client.py:242 的 infer_iec_type_from_address 统一。

    Args:
        address: IEC61850 引用地址, 如 "LD0/LLN0.Mod.stVal" 或 "LD0/LLN0.Mod.t.fraction"

    Returns:
        iec_type 字符串, 如 "float", "boolean", "integer", "string", "timestamp"
    """
    if not address or "/" not in address:
        return IEC_TYPE_UNKNOWN

    try:
        slash_idx = address.index("/")
        rest = address[slash_idx + 1 :]
        dot_idx = rest.index(".")
        da_part = rest[dot_idx + 1 :]
        first_dot = da_part.index(".")
        da_path = da_part[first_dot + 1 :] if first_dot >= 0 else ""
    except (ValueError, IndexError):
        return IEC_TYPE_UNKNOWN

    if not da_path:
        return IEC_TYPE_UNKNOWN

    parts = da_path.split(".")
    top_da = parts[0]
    leaf = parts[-1]

    # stVal/ctlVal 可能为布尔或整型，取决于 CDC 类型 (SPS/ACT→BOOLEAN, INS/ENC/DPC→INTEGER)
    # 无法从地址字符串推断，返回 UNKNOWN 让 AutoDetectReader 运行时自动探测类型
    if leaf in ("stVal", "ctlVal"):
        return IEC_TYPE_UNKNOWN

    # 查完整 DA 路径表
    if da_path in DA_PATH_TO_FRAME_TYPE:
        return DA_PATH_TO_FRAME_TYPE[da_path][1]

    # 查附加 DA 表 (优先于 DA_PATTERNS, 如 origin, t)
    if top_da in EXTRA_DA_INFO:
        return EXTRA_DA_INFO[top_da][2]

    # BDA 子节点推断：如 "mag.i", "t.fraction", "q.validity", "origin.orCat"
    # 必须在 DA_PATTERNS 之前检查，否则 "mag" 的粗粒度映射会覆盖 "mag.i" 的正确类型
    if len(parts) >= 2:
        bda_name = parts[-1]
        if bda_name in BDA_TYPE_MAP:
            return BDA_TYPE_MAP[bda_name]

    # 查主值 DA 表 (粗粒度匹配, 如 "mag"→"mag.f", "stVal"→"stVal")
    if top_da in DA_PATTERNS:
        return DA_PATTERNS[top_da][2]

    # DA 叶子节点特征推断
    if leaf in ("f", "db", "sg", "stepSize"):
        return IEC_TYPE_FLOAT
    if leaf in ("subEna", "blkEna"):
        return IEC_TYPE_BOOLEAN

    return IEC_TYPE_UNKNOWN


def extract_ln_class(ln_name: str) -> str | None:
    """从可能带前缀的逻辑节点名中提取 lnClass

    原 client.py:1143 的 _extract_ln_class 统一。

    IEC 61850 LN 名称格式: {prefix}{lnClass}{inst}
    例如: METMMXU1 → prefix=MET, lnClass=MMXU, inst=1
          TRIPPTRC1 → prefix=TRIP, lnClass=PTRC, inst=1
    """
    alpha = "".join(c for c in ln_name if c.isalpha())
    # 直接匹配
    if alpha in ALL_LN_CLASSES:
        return alpha
    # 从后往前尝试匹配, 去除前缀部分
    for i in range(1, len(alpha)):
        suffix = alpha[i:]
        if suffix in ALL_LN_CLASSES:
            return suffix
    return None


def split_ln_name(ln_name: str) -> tuple[str, str]:
    """将完整 LN 名称拆分为 (ln_class, ln_inst)

    原 server.py:69 的 _split_ln_name 统一。

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
    known_class = extract_ln_class(ln_name)

    if known_class:
        idx = ln_name.find(known_class)
        if idx >= 0:
            inst_part = ln_name[idx + len(known_class) :]
            return (known_class, inst_part)

    # 方法2: 回退 - 按最后一个字母/数字边界拆分
    import re

    match = re.match(r"^(\D+)(\d*)$", ln_name)
    if match:
        return (match.group(1), match.group(2))

    return (ln_name, "")
