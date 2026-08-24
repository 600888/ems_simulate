"""IEC 61850 公共定义包

统一导出所有共享常量、枚举、数据类和工具函数，
供 Client/Server/Reports/GOOSE 等模块共用。
"""

from .address import (
    ParsedRef,
    extract_ln_class,
    infer_fc_from_address,
    infer_iec_type_from_address,
    is_full_ref,
    parse_ref,
    split_ln_name,
)
from .constants import (
    FC_BR,
    FC_CF,
    FC_CO,
    FC_DC,
    FC_MX,
    FC_RP,
    FC_ST,
    FC_TO_FRAME_TYPE,
    FRAME_TYPE_DESC,
    FRAME_TYPE_TO_FC,
    HAS_IEC61850,
    IEC_TYPE_BOOLEAN,
    # IecType 枚举值重导出 (旧常量名, 统一由 defs 层导出)
    IEC_TYPE_FLOAT,
    IEC_TYPE_INTEGER,
    IEC_TYPE_STRING,
    IEC_TYPE_TIMESTAMP,
    IEC_TYPE_UNKNOWN,
    AcsiClass,
    FrameType,
    FunctionalConstraint,
    IecType,
)
from .da_patterns import (
    BDA_TYPE_MAP,
    DA_PATH_TO_FRAME_TYPE,
    DA_PATTERNS,
    ENC_DO_DA_TYPE_OVERRIDE,
    EXTRA_DA_INFO,
    KNOWN_BDA_FALLBACK_ONLINE,
    SKIP_DA_NAMES,
    STRUCT_DA_EXPAND_ONLINE,
)
from .error_codes import IedClientErrorCode, describe_ied_error, format_ied_error
from .ln_classes import (
    ALL_LN_CLASSES,
    SIGNAL_DOS,
    SKIP_SYSTEM_DOS,
    YC_LN_CLASSES,
    YK_LN_CLASSES,
    YT_LN_CLASSES,
    YX_LN_CLASSES,
)
from .mms_types import (
    BTYPE_TO_MMS_TYPE,
    MmsType,
    iec_type_from_mms_type,
    infer_mms_type_from_path,
    mms_type_from_btype,
    mms_type_from_iec_type,
    mms_type_from_native,
)
from .types import (
    OptFields,
    PointRef,
    RCBInfo,
    ReportDataEntry,
    TrgOps,
)

__all__ = [
    # constants
    "HAS_IEC61850",
    "FC_MX",
    "FC_ST",
    "FC_CO",
    "FC_CF",
    "FC_DC",
    "FC_RP",
    "FC_BR",
    "FunctionalConstraint",
    "IecType",
    "FrameType",
    "AcsiClass",
    "FRAME_TYPE_DESC",
    "FC_TO_FRAME_TYPE",
    "FRAME_TYPE_TO_FC",
    "IEC_TYPE_FLOAT",
    "IEC_TYPE_BOOLEAN",
    "IEC_TYPE_INTEGER",
    "IEC_TYPE_STRING",
    "IEC_TYPE_TIMESTAMP",
    "IEC_TYPE_UNKNOWN",
    "MmsType",
    "BTYPE_TO_MMS_TYPE",
    "mms_type_from_native",
    "mms_type_from_btype",
    "mms_type_from_iec_type",
    "iec_type_from_mms_type",
    "infer_mms_type_from_path",
    "IedClientErrorCode",
    "describe_ied_error",
    "format_ied_error",
    # ln_classes
    "YC_LN_CLASSES",
    "YX_LN_CLASSES",
    "YK_LN_CLASSES",
    "YT_LN_CLASSES",
    "ALL_LN_CLASSES",
    "SKIP_SYSTEM_DOS",
    "SIGNAL_DOS",
    # da_patterns
    "DA_PATTERNS",
    "DA_PATH_TO_FRAME_TYPE",
    "EXTRA_DA_INFO",
    "ENC_DO_DA_TYPE_OVERRIDE",
    "SKIP_DA_NAMES",
    "BDA_TYPE_MAP",
    "STRUCT_DA_EXPAND_ONLINE",
    "KNOWN_BDA_FALLBACK_ONLINE",
    # address
    "ParsedRef",
    "is_full_ref",
    "parse_ref",
    "infer_fc_from_address",
    "infer_iec_type_from_address",
    "extract_ln_class",
    "split_ln_name",
    # types
    "PointRef",
    "RCBInfo",
    "TrgOps",
    "OptFields",
    "ReportDataEntry",
]
