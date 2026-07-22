"""IEC 61850 建模节点目录、父子约束和属性表单定义。"""

from typing import Any

from src.modeling.standards import default_standard

CHILD_RULES: dict[str, tuple[str, ...]] = {
    "ROOT": ("HEADER", "COMMUNICATION", "IED", "DATA_TYPE_TEMPLATES", "EXTENSION"),
    "HEADER": ("HISTORY", "EXTENSION"),
    "HISTORY": ("HITEM",),
    "COMMUNICATION": ("SUBNETWORK", "EXTENSION"),
    "SUBNETWORK": ("CONNECTED_AP", "EXTENSION"),
    "CONNECTED_AP": ("ADDRESS", "GSE", "SMV", "EXTENSION"),
    "ADDRESS": ("P",),
    "GSE": ("ADDRESS",),
    "SMV": ("ADDRESS",),
    "IED": ("SERVICES", "ACCESS_POINT", "EXTENSION"),
    "SERVICES": ("SERVICE_CAPABILITY", "EXTENSION"),
    "ACCESS_POINT": ("SERVER",),
    "SERVER": ("AUTHENTICATION", "LDEVICE", "EXTENSION"),
    "LDEVICE": ("LN0", "LN"),
    "LN0": (
        "DOI",
        "DATASET",
        "REPORT_CONTROL",
        "GSE_CONTROL",
        "SETTING_CONTROL",
        "INPUTS",
        "EXTENSION",
    ),
    "LN": ("DOI", "DATASET", "REPORT_CONTROL", "GSE_CONTROL", "INPUTS", "EXTENSION"),
    "DOI": ("DAI", "SDI", "EXTENSION"),
    "SDI": ("DAI", "SDI", "EXTENSION"),
    "DAI": ("VAL", "EXTENSION"),
    "DATASET": ("FCDA",),
    "REPORT_CONTROL": ("TRG_OPS", "OPT_FIELDS", "RPT_ENABLED", "EXTENSION"),
    "RPT_ENABLED": ("CLIENT_LN",),
    "INPUTS": ("EXT_REF",),
    "DATA_TYPE_TEMPLATES": ("LNODE_TYPE", "DO_TYPE", "DA_TYPE", "ENUM_TYPE"),
    "LNODE_TYPE": ("DO_DEF",),
    "DO_TYPE": ("DA_DEF", "SDO_DEF", "EXTENSION"),
    "DA_DEF": ("VAL", "EXTENSION"),
    "DA_TYPE": ("BDA_DEF", "EXTENSION"),
    "BDA_DEF": ("VAL", "EXTENSION"),
    "ENUM_TYPE": ("ENUM_VALUE",),
}

KIND_LABELS = {
    "ROOT": "模型根节点",
    "HEADER": "SCL 头信息",
    "HISTORY": "修改历史",
    "HITEM": "历史记录",
    "COMMUNICATION": "通信配置",
    "SUBNETWORK": "子网",
    "CONNECTED_AP": "已连接访问点",
    "ADDRESS": "通信地址",
    "P": "地址参数",
    "GSE": "GOOSE 通信参数",
    "SMV": "采样值通信参数",
    "IED": "智能电子设备 (IED)",
    "SERVICES": "IED 服务能力",
    "SERVICE_CAPABILITY": "服务能力项",
    "ACCESS_POINT": "访问点",
    "SERVER": "服务实例",
    "AUTHENTICATION": "认证能力",
    "LDEVICE": "逻辑设备",
    "LN0": "零逻辑节点 (LLN0)",
    "LN": "逻辑节点",
    "DOI": "数据对象实例",
    "DAI": "数据属性实例",
    "SDI": "子数据实例",
    "DATASET": "数据集",
    "FCDA": "功能约束数据属性",
    "REPORT_CONTROL": "报告控制块",
    "TRG_OPS": "报告触发选项",
    "OPT_FIELDS": "报告可选字段",
    "RPT_ENABLED": "报告实例能力",
    "CLIENT_LN": "报告客户端",
    "GSE_CONTROL": "GOOSE 控制块",
    "SETTING_CONTROL": "定值组控制",
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
    "VAL": "默认值/实例值",
    "EXTENSION": "保真扩展片段",
}

BASE_FIELDS = [
    {"key": "name", "label": "节点名称", "component": "input", "required": True},
    {"key": "desc", "label": "描述", "component": "textarea"},
]

_DEFAULT_STANDARD = default_standard()
FC_OPTIONS = list(_DEFAULT_STANDARD["functionalConstraints"])
BTYPE_OPTIONS = list(_DEFAULT_STANDARD["basicTypes"])

PROPERTY_FIELDS: dict[str, list[dict[str, Any]]] = {
    "HEADER": [
        {"key": "id", "label": "SCL 标识", "component": "input", "required": True},
        {"key": "version", "label": "版本", "component": "input"},
        {"key": "revision", "label": "修订", "component": "input"},
        {"key": "toolID", "label": "建模工具", "component": "input"},
        {"key": "nameStructure", "label": "名称结构", "component": "select", "options": ["IEDName", "FuncName"]},
        {"key": "schemaLocation", "label": "Schema 位置", "component": "input"},
    ],
    "HITEM": [
        {"key": "who", "label": "修改人", "component": "input"},
        {"key": "what", "label": "修改内容", "component": "input"},
        {"key": "why", "label": "修改原因", "component": "input"},
        {"key": "when", "label": "修改时间", "component": "input"},
        {"key": "version", "label": "版本", "component": "input"},
        {"key": "revision", "label": "修订", "component": "input"},
    ],
    "SERVICE_CAPABILITY": [
        {"key": "tag", "label": "服务元素", "component": "input", "required": True},
        {"key": "max", "label": "最大数量", "component": "number"},
        {"key": "modify", "label": "允许修改", "component": "switch"},
    ],
    "SUBNETWORK": [
        {"key": "type", "label": "网络类型", "component": "input", "required": True},
        {"key": "bitRate", "label": "比特率", "component": "number"},
        {"key": "multiplier", "label": "倍率", "component": "select", "options": ["", "k", "M", "G"]},
    ],
    "CONNECTED_AP": [
        {"key": "iedName", "label": "IED 名称", "component": "input", "required": True},
        {"key": "apName", "label": "AccessPoint 名称", "component": "input", "required": True},
    ],
    "P": [
        {
            "key": "type",
            "label": "参数类型",
            "component": "select",
            "required": True,
            "options": [
                "IP",
                "IP-SUBNET",
                "IP-GATEWAY",
                "OSI-TSEL",
                "OSI-SSEL",
                "OSI-PSEL",
                "OSI-AP-Title",
                "OSI-AE-Qualifier",
                "MAC-Address",
                "APPID",
                "VLAN-PRIORITY",
                "VLAN-ID",
            ],
        },
        {"key": "value", "label": "参数值", "component": "input", "required": True},
    ],
    "GSE": [
        {"key": "ldInst", "label": "逻辑设备", "component": "input", "required": True},
        {"key": "cbName", "label": "控制块名称", "component": "input", "required": True},
        {"key": "minTime", "label": "最小重发时间", "component": "number"},
        {"key": "maxTime", "label": "最大重发时间", "component": "number"},
    ],
    "SMV": [
        {"key": "ldInst", "label": "逻辑设备", "component": "input", "required": True},
        {"key": "cbName", "label": "控制块名称", "component": "input", "required": True},
    ],
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
        {"key": "lnType", "label": "类型引用 lnType", "component": "input", "required": True},
    ],
    "LN0": [{"key": "lnType", "label": "类型引用 lnType", "component": "input", "required": True}],
    "DOI": [{"key": "accessControl", "label": "访问控制", "component": "input"}],
    "DAI": [
        {"key": "sAddr", "label": "短地址", "component": "input"},
        {"key": "value", "label": "初始值", "component": "input"},
    ],
    "FCDA": [
        {"key": "ldInst", "label": "逻辑设备 ldInst", "component": "input", "required": True},
        {"key": "prefix", "label": "逻辑节点前缀", "component": "input"},
        {"key": "lnClass", "label": "逻辑节点类", "component": "input", "required": True},
        {"key": "lnInst", "label": "逻辑节点实例", "component": "input"},
        {"key": "doName", "label": "数据对象", "component": "input", "required": True},
        {"key": "daName", "label": "数据属性", "component": "input"},
        {
            "key": "fc",
            "label": "功能约束 FC",
            "component": "select",
            "required": True,
            "options": FC_OPTIONS,
        },
    ],
    "REPORT_CONTROL": [
        {"key": "rptID", "label": "报告标识", "component": "input"},
        {"key": "datSet", "label": "数据集引用", "component": "input", "required": True},
        {"key": "buffered", "label": "缓冲报告", "component": "switch"},
        {"key": "bufTime", "label": "缓存时间 (ms)", "component": "number"},
        {"key": "intgPd", "label": "完整性周期 (ms)", "component": "number"},
        {"key": "confRev", "label": "配置版本", "component": "number"},
    ],
    "TRG_OPS": [
        {"key": key, "label": label, "component": "switch"}
        for key, label in (
            ("dchg", "数据变化"),
            ("qchg", "品质变化"),
            ("dupd", "数据更新"),
            ("period", "周期触发"),
            ("gi", "总召唤"),
        )
    ],
    "OPT_FIELDS": [
        {"key": key, "label": label, "component": "switch"}
        for key, label in (
            ("seqNum", "序号"),
            ("timeStamp", "时间戳"),
            ("reasonCode", "原因码"),
            ("dataSet", "数据集名"),
            ("dataRef", "数据引用"),
            ("bufOvfl", "缓冲溢出"),
            ("entryID", "条目标识"),
            ("configRef", "配置版本"),
            ("segmentation", "分段"),
        )
    ],
    "RPT_ENABLED": [{"key": "max", "label": "最大实例数", "component": "number", "required": True}],
    "CLIENT_LN": [
        {"key": key, "label": label, "component": "input"}
        for key, label in (
            ("iedName", "客户端 IED"),
            ("apRef", "访问点"),
            ("ldInst", "逻辑设备"),
            ("prefix", "前缀"),
            ("lnClass", "逻辑节点类"),
            ("lnInst", "实例"),
        )
    ],
    "GSE_CONTROL": [
        {"key": "appID", "label": "应用标识", "component": "input"},
        {"key": "datSet", "label": "数据集引用", "component": "input", "required": True},
        {"key": "confRev", "label": "配置版本", "component": "number"},
        {"key": "type", "label": "类型", "component": "select", "options": ["GOOSE", "GSSE"]},
    ],
    "SETTING_CONTROL": [
        {"key": "actSG", "label": "当前定值组", "component": "number"},
        {"key": "numOfSGs", "label": "定值组数量", "component": "number", "required": True},
    ],
    "LNODE_TYPE": [
        {"key": "id", "label": "类型 ID", "component": "input", "required": True},
        {"key": "lnClass", "label": "逻辑节点类", "component": "input", "required": True},
        {"key": "iedType", "label": "IED 类型", "component": "input"},
    ],
    "DO_TYPE": [
        {"key": "id", "label": "类型 ID", "component": "input", "required": True},
        {"key": "cdc", "label": "公共数据类 CDC", "component": "input", "required": True},
        {"key": "iedType", "label": "IED 类型", "component": "input"},
    ],
    "DA_TYPE": [{"key": "id", "label": "类型 ID", "component": "input", "required": True}],
    "ENUM_TYPE": [{"key": "id", "label": "类型 ID", "component": "input", "required": True}],
    "ENUM_VALUE": [{"key": "ord", "label": "枚举序号", "component": "number", "required": True}],
    "DO_DEF": [
        {"key": "type", "label": "DOType 引用", "component": "input", "required": True},
        {"key": "transient", "label": "瞬变数据", "component": "switch"},
    ],
    "SDO_DEF": [{"key": "type", "label": "DOType 引用", "component": "input", "required": True}],
    "DA_DEF": [
        {
            "key": "bType",
            "label": "基础类型 bType",
            "component": "select",
            "required": True,
            "options": BTYPE_OPTIONS,
        },
        {"key": "type", "label": "类型引用", "component": "input"},
        {
            "key": "fc",
            "label": "功能约束 FC",
            "component": "select",
            "required": True,
            "options": FC_OPTIONS,
        },
        {"key": "dchg", "label": "数据变化触发", "component": "switch"},
        {"key": "qchg", "label": "品质变化触发", "component": "switch"},
        {"key": "dupd", "label": "数据更新触发", "component": "switch"},
        {"key": "sAddr", "label": "短地址", "component": "input"},
        {"key": "valKind", "label": "值类型", "component": "select", "options": ["RO", "Set", "Conf"]},
    ],
    "BDA_DEF": [
        {
            "key": "bType",
            "label": "基础类型 bType",
            "component": "select",
            "required": True,
            "options": BTYPE_OPTIONS,
        },
        {"key": "type", "label": "类型引用", "component": "input"},
        {"key": "sAddr", "label": "短地址", "component": "input"},
    ],
    "EXT_REF": [
        {"key": "iedName", "label": "源 IED", "component": "input"},
        {"key": "ldInst", "label": "源逻辑设备", "component": "input"},
        {"key": "lnClass", "label": "源逻辑节点类", "component": "input"},
        {"key": "lnInst", "label": "源逻辑节点实例", "component": "input"},
        {"key": "doName", "label": "源数据对象", "component": "input"},
        {"key": "daName", "label": "源数据属性", "component": "input"},
        {"key": "intAddr", "label": "内部地址", "component": "input"},
        {
            "key": "serviceType",
            "label": "服务类型",
            "component": "select",
            "options": ["Poll", "Report", "GOOSE", "SMV"],
        },
    ],
    "VAL": [{"key": "value", "label": "值", "component": "textarea"}],
    "EXTENSION": [
        {"key": "tag", "label": "元素名称", "component": "input"},
        {"key": "xml", "label": "原始 XML", "component": "textarea", "required": True},
    ],
}

PROTECTED_KINDS = {"ROOT", "HEADER", "DATA_TYPE_TEMPLATES", "LN0", "EXTENSION"}
SINGLETON_CHILD_KINDS = {
    "HEADER",
    "COMMUNICATION",
    "DATA_TYPE_TEMPLATES",
    "LN0",
    "SERVER",
    "INPUTS",
    "ADDRESS",
    "SERVICES",
    "HISTORY",
    "TRG_OPS",
    "OPT_FIELDS",
    "RPT_ENABLED",
    "SETTING_CONTROL",
}


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
