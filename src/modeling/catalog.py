"""IEC 61850 建模节点目录、父子约束和属性表单定义。"""

from typing import Any

CHILD_RULES: dict[str, tuple[str, ...]] = {
    "ROOT": ("HEADER", "COMMUNICATION", "IED", "DATA_TYPE_TEMPLATES"),
    "IED": ("ACCESS_POINT",),
    "ACCESS_POINT": ("SERVER",),
    "SERVER": ("LDEVICE",),
    "LDEVICE": ("LN0", "LN"),
    "LN0": ("DOI", "DATASET", "REPORT_CONTROL", "GSE_CONTROL", "INPUTS"),
    "LN": ("DOI", "DATASET", "REPORT_CONTROL", "GSE_CONTROL", "INPUTS"),
    "DOI": ("DAI", "SDI"),
    "SDI": ("DAI", "SDI"),
    "DATASET": ("FCDA",),
    "INPUTS": ("EXT_REF",),
    "DATA_TYPE_TEMPLATES": ("LNODE_TYPE", "DO_TYPE", "DA_TYPE", "ENUM_TYPE"),
    "LNODE_TYPE": ("DO_DEF",),
    "DO_TYPE": ("DA_DEF", "SDO_DEF"),
    "DA_TYPE": ("BDA_DEF",),
    "ENUM_TYPE": ("ENUM_VALUE",),
}

KIND_LABELS = {
    "ROOT": "模型根节点",
    "HEADER": "SCL 头信息",
    "COMMUNICATION": "通信配置",
    "IED": "智能电子设备 (IED)",
    "ACCESS_POINT": "访问点",
    "SERVER": "服务实例",
    "LDEVICE": "逻辑设备",
    "LN0": "零逻辑节点 (LLN0)",
    "LN": "逻辑节点",
    "DOI": "数据对象实例",
    "DAI": "数据属性实例",
    "SDI": "子数据实例",
    "DATASET": "数据集",
    "FCDA": "功能约束数据属性",
    "REPORT_CONTROL": "报告控制块",
    "GSE_CONTROL": "GOOSE 控制块",
    "INPUTS": "外部引用集合",
    "EXT_REF": "外部引用",
    "DATA_TYPE_TEMPLATES": "数据类型模板",
    "LNODE_TYPE": "逻辑节点类型",
    "DO_TYPE": "数据对象类型",
    "DA_TYPE": "数据属性类型",
    "ENUM_TYPE": "枚举类型",
    "DO_DEF": "数据对象定义",
    "DA_DEF": "数据属性定义",
    "SDO_DEF": "子数据对象定义",
    "BDA_DEF": "基础数据属性定义",
    "ENUM_VALUE": "枚举值",
}

BASE_FIELDS = [
    {"key": "name", "label": "节点名称", "component": "input", "required": True},
    {"key": "desc", "label": "描述", "component": "textarea"},
]

PROPERTY_FIELDS: dict[str, list[dict[str, Any]]] = {
    "IED": [
        {"key": "manufacturer", "label": "制造商", "component": "input"},
        {"key": "type", "label": "设备类型", "component": "input"},
        {"key": "configVersion", "label": "配置版本", "component": "input"},
    ],
    "ACCESS_POINT": [{"key": "router", "label": "路由能力", "component": "switch"}],
    "LDEVICE": [{"key": "inst", "label": "实例标识 inst", "component": "input", "required": True}],
    "LN": [
        {"key": "prefix", "label": "前缀 prefix", "component": "input"},
        {"key": "lnClass", "label": "逻辑节点类", "component": "input", "required": True},
        {"key": "inst", "label": "实例号 inst", "component": "input", "required": True},
        {"key": "lnType", "label": "类型引用 lnType", "component": "input"},
    ],
    "LN0": [{"key": "lnType", "label": "类型引用 lnType", "component": "input"}],
    "DOI": [{"key": "accessControl", "label": "访问控制", "component": "input"}],
    "DAI": [
        {"key": "sAddr", "label": "短地址", "component": "input"},
        {"key": "value", "label": "初始值", "component": "input"},
    ],
    "DATASET": [{"key": "datSet", "label": "数据集标识", "component": "input"}],
    "REPORT_CONTROL": [
        {"key": "rptID", "label": "报告标识", "component": "input"},
        {"key": "datSet", "label": "数据集引用", "component": "input", "required": True},
        {"key": "buffered", "label": "缓冲报告", "component": "switch"},
        {"key": "bufTime", "label": "缓存时间 (ms)", "component": "number"},
        {"key": "intgPd", "label": "完整性周期 (ms)", "component": "number"},
    ],
    "GSE_CONTROL": [
        {"key": "appID", "label": "应用标识", "component": "input"},
        {"key": "datSet", "label": "数据集引用", "component": "input", "required": True},
        {"key": "confRev", "label": "配置版本", "component": "number"},
    ],
    "LNODE_TYPE": [
        {"key": "id", "label": "类型 ID", "component": "input", "required": True},
        {"key": "lnClass", "label": "逻辑节点类", "component": "input", "required": True},
    ],
    "DO_TYPE": [
        {"key": "id", "label": "类型 ID", "component": "input", "required": True},
        {"key": "cdc", "label": "公共数据类 CDC", "component": "input", "required": True},
    ],
    "DA_TYPE": [{"key": "id", "label": "类型 ID", "component": "input", "required": True}],
    "ENUM_TYPE": [{"key": "id", "label": "类型 ID", "component": "input", "required": True}],
    "ENUM_VALUE": [{"key": "ord", "label": "枚举序号", "component": "number", "required": True}],
}

PROTECTED_KINDS = {"ROOT", "HEADER", "DATA_TYPE_TEMPLATES", "LN0"}
SINGLETON_CHILD_KINDS = {"HEADER", "COMMUNICATION", "DATA_TYPE_TEMPLATES", "LN0", "SERVER", "INPUTS"}


def get_kind_schema(kind: str) -> dict[str, Any]:
    normalized = kind.upper()
    if normalized not in KIND_LABELS:
        raise KeyError(normalized)
    return {
        "kind": normalized,
        "label": KIND_LABELS[normalized],
        "fields": [*BASE_FIELDS, *PROPERTY_FIELDS.get(normalized, [])],
        "allowed_children": [{"kind": child, "label": KIND_LABELS[child]} for child in CHILD_RULES.get(normalized, ())],
        "protected": normalized in PROTECTED_KINDS,
    }
