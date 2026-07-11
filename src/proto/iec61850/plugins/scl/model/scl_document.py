"""SCL 数据模型 — 完整的 ICD/SCD/CID 文件对象表示

使用 dataclass(slots=True) 优化内存。
不依赖 pyiec61850、FastAPI、SQLAlchemy，仅依赖标准库。
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ===== 数据类型模板 =====


@dataclass(slots=True)
class SclEnumVal:
    """枚举值"""

    ord: int = 0
    value: str = ""
    desc: str = ""


@dataclass(slots=True)
class SclEnumType:
    """EnumType — 枚举类型定义"""

    id: str = ""
    values: list[SclEnumVal] = field(default_factory=list)


@dataclass(slots=True)
class SclBDA:
    """BDA — 数据属性类型成员 (DAType 子元素)"""

    name: str = ""
    b_type: str = ""
    fc: str = ""
    type_id: str = ""  # 引用 DAType / EnumType id
    desc: str = ""
    val: str = ""


@dataclass(slots=True)
class SclDAType:
    """DAType — 数据属性类型定义"""

    id: str = ""
    desc: str = ""
    bdas: list[SclBDA] = field(default_factory=list)


@dataclass(slots=True)
class SclDA:
    """DA — 数据属性定义 (DOType 子元素)"""

    name: str = ""
    fc: str = ""
    b_type: str = ""
    type_id: str = ""  # 引用 DAType / EnumType id
    dchg: bool = False
    qchg: bool = False
    dupd: bool = False
    desc: str = ""
    val: str = ""
    sdo_name: str = ""  # 仅用于 SDO


@dataclass(slots=True)
class SclSDO:
    """SDO — 子数据对象定义 (DOType 子元素)"""

    name: str = ""
    type_id: str = ""  # 引用 DOType id
    desc: str = ""


@dataclass(slots=True)
class SclDOType:
    """DOType — 数据对象类型定义"""

    id: str = ""
    cdc: str = ""  # Common Data Class
    desc: str = ""
    das: list[SclDA] = field(default_factory=list)
    sdos: list[SclSDO] = field(default_factory=list)


@dataclass(slots=True)
class SclDO:
    """DO — 逻辑节点类型中的数据对象定义 (LNodeType 子元素)"""

    name: str = ""
    type_id: str = ""  # 引用 DOType id
    desc: str = ""
    access_control: str = ""  # presCond (如 "sg", "sp", "fp")


@dataclass(slots=True)
class SclLNodeType:
    """LNodeType — 逻辑节点类型定义"""

    id: str = ""
    ln_class: str = ""
    desc: str = ""
    dos: list[SclDO] = field(default_factory=list)


# ===== IED 结构 =====


@dataclass(slots=True)
class SclFCDA:
    """FCDA — 功能约束数据属性 (DataSet 成员)"""

    ld_inst: str = ""
    ln_class: str = ""
    ln_inst: str = ""
    ln_prefix: str = ""
    do_name: str = ""
    da_name: str = ""
    fc: str = ""

    @property
    def fcda_ref(self) -> str:
        """构建完整 FCDA 引用路径"""
        ln_name = "LLN0" if self.ln_class == "LLN0" else f"{self.ln_prefix}{self.ln_class}{self.ln_inst}"
        parts = [f"{self.ld_inst}/{ln_name}"]
        do_da = []
        if self.do_name:
            do_da.append(self.do_name)
        if self.da_name:
            do_da.append(self.da_name)
        if do_da:
            parts.append(".".join(do_da))
        return parts[0] + "." + parts[1] if len(parts) > 1 else parts[0]


@dataclass(slots=True)
class SclDataSet:
    """DataSet — 数据集定义"""

    name: str = ""
    desc: str = ""
    members: list[SclFCDA] = field(default_factory=list)


@dataclass(slots=True)
class SclTrgOps:
    """触发选项"""

    dchg: bool = False
    qchg: bool = False
    dupd: bool = False
    period: bool = False
    gi: bool = False


@dataclass(slots=True)
class SclOptFields:
    """可选字段"""

    seq_num: bool = False
    time_stamp: bool = False
    data_set: bool = False
    reason_code: bool = False
    data_ref: bool = False
    entry_id: bool = False
    config_ref: bool = False
    buf_ovfl: bool = False


@dataclass(slots=True)
class SclReportControl:
    """ReportControl — 报告控制块"""

    name: str = ""
    rpt_id: str = ""
    buffered: bool = False
    dat_set: str = ""
    conf_rev: int = 1
    buf_time: int = 0
    intg_period: int = 0
    desc: str = ""
    rpt_enabled_max: int = 1  # <RptEnabled max="N">，多实例 URCB 的实例数，默认 1
    trg_ops: SclTrgOps = field(default_factory=SclTrgOps)
    opt_fields: SclOptFields = field(default_factory=SclOptFields)


@dataclass(slots=True)
class SclGSEControl:
    """GSEControl — GOOSE 控制块"""

    name: str = ""
    app_id: str = ""
    dat_set: str = ""
    conf_rev: int = 1
    control_type: str = "GOOSE"  # type 属性
    desc: str = ""


@dataclass(slots=True)
class SclExtRef:
    """Inputs/ExtRef — 本 IED 对外部数据流的工程绑定。"""

    ied_name: str = ""
    ld_inst: str = ""
    ln_class: str = ""
    ln_inst: str = ""
    prefix: str = ""
    do_name: str = ""
    da_name: str = ""
    service_type: str = ""
    src_ld_inst: str = ""
    src_ln_class: str = ""
    src_ln_inst: str = ""
    src_prefix: str = ""
    src_cb_name: str = ""
    int_addr: str = ""
    desc: str = ""


@dataclass(slots=True)
class SclDOI:
    """DOI — 数据对象实例 (IED 部分)"""

    name: str = ""
    desc: str = ""
    dai_values: dict[str, str] = field(default_factory=dict)  # da_name → val


@dataclass(slots=True)
class SclLN:
    """LN / LN0 — 逻辑节点实例"""

    ln_class: str = ""
    inst: str = ""
    ln_type: str = ""  # 引用 LNodeType id
    prefix: str = ""
    desc: str = ""
    dois: list[SclDOI] = field(default_factory=list)
    datasets: list[SclDataSet] = field(default_factory=list)
    report_controls: list[SclReportControl] = field(default_factory=list)
    gse_controls: list[SclGSEControl] = field(default_factory=list)
    inputs: list[SclExtRef] = field(default_factory=list)

    @property
    def ln_name(self) -> str:
        """构造 LN 名称"""
        if self.ln_class == "LLN0":
            return "LLN0"
        return f"{self.prefix}{self.ln_class}{self.inst}"


@dataclass(slots=True)
class SclLDevice:
    """LDevice — 逻辑设备"""

    inst: str = ""
    desc: str = ""
    ln0: SclLN | None = None
    lns: list[SclLN] = field(default_factory=list)


@dataclass(slots=True)
class SclServer:
    """Server — 服务端"""

    ldevices: list[SclLDevice] = field(default_factory=list)


@dataclass(slots=True)
class SclAccessPoint:
    """AccessPoint — 访问点"""

    name: str = ""
    server: SclServer | None = None


@dataclass(slots=True)
class SclIED:
    """IED — 智能电子设备"""

    name: str = ""
    desc: str = ""
    manufacturer: str = ""
    config_revision: str = ""
    access_points: list[SclAccessPoint] = field(default_factory=list)


# ===== 通信配置 =====


@dataclass(slots=True)
class SclP:
    """P — 通信参数"""

    type: str = ""
    value: str = ""


@dataclass(slots=True)
class SclGSE:
    """GSE — GOOSE 通信地址"""

    ld_inst: str = ""
    ln_class: str = "LLN0"
    ln_inst: str = ""
    cb_name: str = ""
    address: list[SclP] = field(default_factory=list)
    min_time: int = 10  # ms
    max_time: int = 1000  # ms


@dataclass(slots=True)
class SclConnectedAP:
    """ConnectedAP — 连接访问点"""

    ied_name: str = ""
    ap_name: str = ""
    address: list[SclP] = field(default_factory=list)
    gses: list[SclGSE] = field(default_factory=list)


@dataclass(slots=True)
class SclSubNetwork:
    """SubNetwork — 子网"""

    name: str = ""
    type: str = ""
    connected_aps: list[SclConnectedAP] = field(default_factory=list)


@dataclass(slots=True)
class SclCommunication:
    """Communication — 通信配置"""

    sub_networks: list[SclSubNetwork] = field(default_factory=list)


# ===== 顶层容器 =====


@dataclass(slots=True)
class SclDataTypeTemplates:
    """DataTypeTemplates — 数据类型模板"""

    ln_node_types: dict[str, SclLNodeType] = field(default_factory=dict)
    do_types: dict[str, SclDOType] = field(default_factory=dict)
    da_types: dict[str, SclDAType] = field(default_factory=dict)
    enum_types: dict[str, SclEnumType] = field(default_factory=dict)


@dataclass(slots=True)
class SclHeader:
    """Header — SCL 文件头"""

    id: str = ""
    version: str = ""
    revision: str = ""
    tool_id: str = ""
    name_structure: str = ""  # "IEDName" 或 ""，影响 LD 实例名的组织方式


@dataclass(slots=True)
class SclDocument:
    """SCL 文档 — 顶层不可变容器

    解析 ICD/SCD/CID 文件的完整结果。
    不依赖任何外部库，纯 Python dataclass。
    """

    header: SclHeader = field(default_factory=SclHeader)
    communication: SclCommunication = field(default_factory=SclCommunication)
    ieds: list[SclIED] = field(default_factory=list)
    data_type_templates: SclDataTypeTemplates = field(default_factory=SclDataTypeTemplates)
    ns_prefix: str = ""  # 检测到的命名空间前缀

    # ===== 便捷方法 =====

    @property
    def first_ied(self) -> SclIED | None:
        """获取第一个 IED"""
        return self.ieds[0] if self.ieds else None

    def get_all_ldevices(self) -> list[SclLDevice]:
        """获取所有 LDevice"""
        result = []
        for ied in self.ieds:
            for ap in ied.access_points:
                if ap.server:
                    result.extend(ap.server.ldevices)
        return result

    def get_gse_address(self, ied_name: str, ld_inst: str, cb_name: str) -> SclGSE | None:
        """查找 GSE 通信地址"""
        # nameStructure="IEDName" 时 ld_inst 可能已含 IED 名称前缀（如
        # KG_BAMSSTCK01），而 GSE ldInst 在 ICD Communication 节中存储的
        # 是原始短名（STCK01），需要同时尝试两种匹配。
        candidates = [ld_inst]
        if self.header.name_structure == "IEDName" and ld_inst.startswith(ied_name):
            candidates.append(ld_inst[len(ied_name) :])
        for sub_net in self.communication.sub_networks:
            for conn_ap in sub_net.connected_aps:
                if conn_ap.ied_name != ied_name:
                    continue
                for gse in conn_ap.gses:
                    if gse.cb_name == cb_name and gse.ld_inst in candidates:
                        return gse
        return None

    def get_do_type(self, type_id: str) -> SclDOType | None:
        """获取 DOType"""
        return self.data_type_templates.do_types.get(type_id)

    def get_ln_node_type(self, type_id: str) -> SclLNodeType | None:
        """获取 LNodeType"""
        return self.data_type_templates.ln_node_types.get(type_id)

    def get_da_type(self, type_id: str) -> SclDAType | None:
        """获取 DAType"""
        return self.data_type_templates.da_types.get(type_id)

    def get_enum_type(self, type_id: str) -> SclEnumType | None:
        """获取 EnumType"""
        return self.data_type_templates.enum_types.get(type_id)
