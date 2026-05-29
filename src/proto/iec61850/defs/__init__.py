"""IEC 61850 公共定义包

统一导出所有共享常量、枚举、数据类和工具函数，
供 Client/Server/ModelExporter/GOOSE 等模块共用。
"""

from .constants import (
    HAS_IEC61850,
    FC_MX, FC_ST, FC_CO, FC_CF, FC_DC,
    FunctionalConstraint,
    IecType,
    FrameType,
    AcsiClass,
    FRAME_TYPE_DESC,
    FC_TO_FRAME_TYPE,
    FRAME_TYPE_TO_FC,
    # IecType 枚举值重导出 (旧常量名, 统一由 defs 层导出)
    IEC_TYPE_FLOAT,
    IEC_TYPE_BOOLEAN,
    IEC_TYPE_INTEGER,
    IEC_TYPE_STRING,
    IEC_TYPE_TIMESTAMP,
    IEC_TYPE_UNKNOWN,
)

from .ln_classes import (
    YC_LN_CLASSES,
    YX_LN_CLASSES,
    YK_LN_CLASSES,
    YT_LN_CLASSES,
    ALL_LN_CLASSES,
    SKIP_SYSTEM_DOS,
    SIGNAL_DOS,
)

from .da_patterns import (
    DA_PATTERNS,
    DA_PATH_TO_FRAME_TYPE,
    EXTRA_DA_INFO,
    ENC_DO_DA_TYPE_OVERRIDE,
    SKIP_DA_NAMES,
    BDA_TYPE_MAP,
    STRUCT_DA_EXPAND_ONLINE,
    KNOWN_BDA_FALLBACK_ONLINE,
)

from .address import (
    ParsedRef,
    is_full_ref,
    parse_ref,
    infer_fc_from_address,
    infer_iec_type_from_address,
    extract_ln_class,
    split_ln_name,
)

from .types import (
    PointRef,
    DAInfo,
    DOInfo,
    DataSetInfo,
    GoCBInfo,
    RCBInfo,
    LNInfo,
    LDInfo,
    ServerModel,
)

__all__ = [
    # constants
    "HAS_IEC61850", "FC_MX", "FC_ST", "FC_CO", "FC_CF", "FC_DC",
    "FunctionalConstraint", "IecType", "FrameType", "AcsiClass",
    "FRAME_TYPE_DESC", "FC_TO_FRAME_TYPE", "FRAME_TYPE_TO_FC",
    "IEC_TYPE_FLOAT", "IEC_TYPE_BOOLEAN", "IEC_TYPE_INTEGER",
    "IEC_TYPE_STRING", "IEC_TYPE_TIMESTAMP", "IEC_TYPE_UNKNOWN",
    # ln_classes
    "YC_LN_CLASSES", "YX_LN_CLASSES", "YK_LN_CLASSES", "YT_LN_CLASSES",
    "ALL_LN_CLASSES", "SKIP_SYSTEM_DOS", "SIGNAL_DOS",
    # da_patterns
    "DA_PATTERNS", "DA_PATH_TO_FRAME_TYPE", "EXTRA_DA_INFO",
    "ENC_DO_DA_TYPE_OVERRIDE", "SKIP_DA_NAMES", "BDA_TYPE_MAP",
    "STRUCT_DA_EXPAND_ONLINE", "KNOWN_BDA_FALLBACK_ONLINE",
    # address
    "ParsedRef", "is_full_ref", "parse_ref",
    "infer_fc_from_address", "infer_iec_type_from_address",
    "extract_ln_class", "split_ln_name",
    # types
    "PointRef", "DAInfo", "DOInfo", "DataSetInfo", "GoCBInfo",
    "RCBInfo", "LNInfo", "LDInfo", "ServerModel",
]
