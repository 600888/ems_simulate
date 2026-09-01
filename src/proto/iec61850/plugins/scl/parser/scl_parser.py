"""SCL 统一解析器

解析 IEC 61850 ICD/SCD/CID 文件，构建 SclDocument。

替代:
- IcdPointImporter 的 XML 解析逻辑
- IcdGooseImporter 的 XML 解析逻辑

统一一次解析，多处消费。

优化: 使用 iterparse 增量解析 + 逐节清除，替代 ET.parse 全量加载。
大文件场景峰值内存占用从 100%（全量 DOM）降为 max(DataTypeTemplates, IED) 的 DOM。
"""

from __future__ import annotations

import os
from typing import Any
import xml.etree.ElementTree as ET

from ....log import log
from ..model.enums import STRUCT_DA_TO_FULL_PATH
from ..model.scl_document import (
    SclAccessPoint,
    SclBDA,
    SclCommunication,
    SclConnectedAP,
    SclDA,
    SclDataSet,
    SclDAType,
    SclDO,
    SclDocument,
    SclDOI,
    SclDOType,
    SclEnumType,
    SclEnumVal,
    SclExtRef,
    SclFCDA,
    SclGSE,
    SclGSEControl,
    SclHeader,
    SclIED,
    SclLDevice,
    SclLN,
    SclLNodeType,
    SclLog,
    SclLogControl,
    SclOptFields,
    SclP,
    SclReportControl,
    SclSDO,
    SclServer,
    SclSettingControl,
    SclSubNetwork,
    SclTrgOps,
)
from .namespace import NamespaceHelper

# 顶级元素集合，用于 iterparse 过滤
_TOP_LEVEL_SECTIONS = frozenset({"Header", "Communication", "DataTypeTemplates", "IED"})


def _get_local_tag(elem: ET.Element) -> str:
    """获取去除命名空间的本地标签名"""
    tag = elem.tag
    idx = tag.rfind("}")
    return tag[idx + 1 :] if idx >= 0 else tag


class SclParser:
    """SCL 统一解析器

    解析 ICD/SCD/CID 文件为 SclDocument 对象。
    支持:
    - 有/无 SCL 命名空间
    - Communication / IED / DataTypeTemplates 三大节
    - 增量解析（iterparse），大文件内存友好
    """

    def __init__(self):
        """创建 SCL 解析器，并初始化命名空间助手和解析中的类型模板索引。"""
        self._ns = NamespaceHelper()
        self._name_structure: str = ""
        self._ied_name: str = ""

    def parse_file(self, file_path: str) -> SclDocument:
        """解析 SCL 文件（iterparse 增量模式）

        Args:
            file_path: ICD/SCD/CID 文件路径

        Raises:
            FileNotFoundError: 文件不存在
            ValueError: XML 解析失败

        优化:
        - 使用 iterparse 增量解析，每处理完一个顶级节后清除其 DOM
        - 峰值内存占用 ≈ max(DataTypeTemplates, IED_size) 而非全文件 DOM
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        doc = SclDocument()

        # iterparse: 增量解析，处理完一个顶级节就释放其 DOM 子树
        context = ET.iterparse(file_path, events=("end",))

        for _event, elem in context:
            local_tag = _get_local_tag(elem)

            # 首次遇到元素时检测命名空间
            if not self._ns.ns_prefix:
                self._ns = NamespaceHelper(ns_prefix=elem.tag[: elem.tag.index("}") + 1] if "}" in elem.tag else "")
                doc.ns_prefix = self._ns.ns_prefix

            if local_tag not in _TOP_LEVEL_SECTIONS:
                continue

            if local_tag == "Header":
                doc.header = self._parse_header(elem)
            elif local_tag == "Communication":
                doc.communication = self._parse_communication(elem)
            elif local_tag == "DataTypeTemplates":
                doc.data_type_templates = self._parse_data_type_templates(elem)
            elif local_tag == "IED":
                doc.ieds.append(self._parse_ied(elem))

            # 清除已处理的顶级元素子树，释放内存
            elem.clear()

        log.info(
            f"SCL 解析完成: IEDs={len(doc.ieds)}, "
            f"LNodeType={len(doc.data_type_templates.ln_node_types)}, "
            f"DOType={len(doc.data_type_templates.do_types)}, "
            f"DAType={len(doc.data_type_templates.da_types)}, "
            f"EnumType={len(doc.data_type_templates.enum_types)}"
        )
        return doc

    def parse_string(self, xml_string: str) -> SclDocument:
        """解析 SCL XML 字符串"""
        root = ET.fromstring(xml_string)
        return self._parse_root(root)

    def _parse_root(self, root: ET.Element) -> SclDocument:
        """解析根元素"""
        self._ns = NamespaceHelper.from_root(root)

        doc = SclDocument(ns_prefix=self._ns.ns_prefix)

        # Header
        header_elem = self._ns.find(root, "Header")
        if header_elem is not None:
            doc.header = self._parse_header(header_elem)

        # Communication
        comm_elem = self._ns.find(root, "Communication")
        if comm_elem is not None:
            doc.communication = self._parse_communication(comm_elem)

        # DataTypeTemplates (先解析，IED 解析时需要引用)
        dtt_elem = self._ns.find(root, "DataTypeTemplates")
        if dtt_elem is not None:
            doc.data_type_templates = self._parse_data_type_templates(dtt_elem)

        # IED
        for ied_elem in self._ns.findall(root, "IED"):
            doc.ieds.append(self._parse_ied(ied_elem))

        log.info(
            f"SCL 解析完成: IEDs={len(doc.ieds)}, "
            f"LNodeType={len(doc.data_type_templates.ln_node_types)}, "
            f"DOType={len(doc.data_type_templates.do_types)}, "
            f"DAType={len(doc.data_type_templates.da_types)}, "
            f"EnumType={len(doc.data_type_templates.enum_types)}"
        )
        return doc

    # ===== Header =====

    def _parse_header(self, elem: ET.Element) -> SclHeader:
        """解析 SCL 中的 Header 元素并构建对应模型对象。"""
        self._name_structure = elem.get("nameStructure", "")
        return SclHeader(
            id=elem.get("id", ""),
            version=elem.get("version", ""),
            revision=elem.get("revision", ""),
            tool_id=elem.get("toolID", ""),
            name_structure=self._name_structure,
        )

    # ===== Communication =====

    def _parse_communication(self, elem: ET.Element) -> SclCommunication:
        """解析 SCL 中的 Communication 元素并构建对应模型对象。"""
        sub_nets = []
        for sn_elem in self._ns.findall(elem, "SubNetwork"):
            sub_nets.append(self._parse_sub_network(sn_elem))
        return SclCommunication(sub_networks=sub_nets)

    def _parse_sub_network(self, elem: ET.Element) -> SclSubNetwork:
        """解析 SCL 中的 SubNetwork 元素并构建对应模型对象。"""
        conn_aps = []
        for ap_elem in self._ns.findall(elem, "ConnectedAP"):
            conn_aps.append(self._parse_connected_ap(ap_elem))
        return SclSubNetwork(
            name=elem.get("name", ""),
            type=elem.get("type", ""),
            connected_aps=conn_aps,
        )

    def _parse_connected_ap(self, elem: ET.Element) -> SclConnectedAP:
        # Address
        """解析 SCL 中的 ConnectedAP 元素并构建对应模型对象。"""
        address = self._parse_p_list(self._ns.find(elem, "Address"))

        # GSE
        gses = []
        for gse_elem in self._ns.findall(elem, "GSE"):
            gses.append(self._parse_gse(gse_elem))

        return SclConnectedAP(
            ied_name=elem.get("iedName", ""),
            ap_name=elem.get("apName", ""),
            address=address,
            gses=gses,
        )

    def _parse_gse(self, elem: ET.Element) -> SclGSE:
        """解析 SCL 中的 GSE 元素并构建对应模型对象。"""
        address = self._parse_p_list(self._ns.find(elem, "Address"))

        min_time = 10
        max_time = 1000

        min_elem = self._ns.find(elem, "MinTime")
        if min_elem is not None:
            min_time = self._parse_time_element(min_elem, 10)

        max_elem = self._ns.find(elem, "MaxTime")
        if max_elem is not None:
            max_time = self._parse_time_element(max_elem, 1000)

        return SclGSE(
            ld_inst=elem.get("ldInst", ""),
            ln_class=elem.get("lnClass", "LLN0"),
            ln_inst=elem.get("lnInst", ""),
            cb_name=elem.get("cbName", ""),
            address=address,
            min_time=min_time,
            max_time=max_time,
        )

    def _parse_time_element(self, elem: ET.Element, default: int) -> int:
        """解析 MinTime/MaxTime 元素"""
        val_text = elem.text or str(default)
        mult = elem.get("multiplier", "m")
        try:
            val = float(val_text)
            if mult == "m":
                return int(val)
            elif mult == "s":
                return int(val * 1000)
            return int(val)
        except ValueError:
            return default

    def _parse_p_list(self, address_elem: ET.Element | None) -> list[SclP]:
        """解析 Address/P 列表"""
        if address_elem is None:
            return []
        result = []
        for p in self._ns.findall(address_elem, "P"):
            result.append(
                SclP(
                    type=p.get("type", ""),
                    value=(p.text or "").strip(),
                )
            )
        return result

    # ===== DataTypeTemplates =====

    def _parse_data_type_templates(self, elem: ET.Element) -> Any:
        """解析 SCL 中的 DataTypeTemplates 元素并构建对应模型对象。"""
        from ..model.scl_document import SclDataTypeTemplates

        dtt = SclDataTypeTemplates()

        # LNodeType
        for lt_elem in self._ns.findall(elem, "LNodeType"):
            ln_type = self._parse_ln_node_type(lt_elem)
            dtt.ln_node_types[ln_type.id] = ln_type

        # DOType
        for dt_elem in self._ns.findall(elem, "DOType"):
            do_type = self._parse_do_type(dt_elem)
            dtt.do_types[do_type.id] = do_type

        # DAType
        for dat_elem in self._ns.findall(elem, "DAType"):
            da_type = self._parse_da_type(dat_elem)
            dtt.da_types[da_type.id] = da_type

        # EnumType
        for et_elem in self._ns.findall(elem, "EnumType"):
            enum_type = self._parse_enum_type(et_elem)
            dtt.enum_types[enum_type.id] = enum_type

        return dtt

    def _parse_ln_node_type(self, elem: ET.Element) -> SclLNodeType:
        """解析 SCL 中的 LNodeType 元素并构建对应模型对象。"""
        dos = []
        for do_elem in self._ns.findall(elem, "DO"):
            dos.append(
                SclDO(
                    name=do_elem.get("name", ""),
                    type_id=do_elem.get("type", ""),
                    desc=do_elem.get("desc", ""),
                    access_control=do_elem.get("presCond", ""),
                )
            )
        return SclLNodeType(
            id=elem.get("id", ""),
            ln_class=elem.get("lnClass", ""),
            desc=elem.get("desc", ""),
            dos=dos,
        )

    def _parse_do_type(self, elem: ET.Element) -> SclDOType:
        """解析 SCL 中的 DOType 元素并构建对应模型对象。"""
        das = []
        sdos = []

        for da_elem in self._ns.findall(elem, "DA"):
            val = ""
            val_elem = self._ns.find(da_elem, "Val")
            if val_elem is not None and val_elem.text:
                val = val_elem.text.strip()
            das.append(
                SclDA(
                    name=da_elem.get("name", ""),
                    fc=da_elem.get("fc", ""),
                    b_type=da_elem.get("bType", ""),
                    type_id=da_elem.get("type", ""),
                    dchg=da_elem.get("dchg", "false").lower() == "true",
                    qchg=da_elem.get("qchg", "false").lower() == "true",
                    dupd=da_elem.get("dupd", "false").lower() == "true",
                    desc=da_elem.get("desc", ""),
                    val=val,
                )
            )

        for sdo_elem in self._ns.findall(elem, "SDO"):
            sdos.append(
                SclSDO(
                    name=sdo_elem.get("name", ""),
                    type_id=sdo_elem.get("type", ""),
                    desc=sdo_elem.get("desc", ""),
                )
            )

        return SclDOType(
            id=elem.get("id", ""),
            cdc=elem.get("cdc", ""),
            desc=elem.get("desc", ""),
            das=das,
            sdos=sdos,
        )

    def _parse_da_type(self, elem: ET.Element) -> SclDAType:
        """解析 SCL 中的 DAType 元素并构建对应模型对象。"""
        bdas = []
        for bda_elem in self._ns.findall(elem, "BDA"):
            val = ""
            val_elem = self._ns.find(bda_elem, "Val")
            if val_elem is not None and val_elem.text:
                val = val_elem.text.strip()
            bdas.append(
                SclBDA(
                    name=bda_elem.get("name", ""),
                    b_type=bda_elem.get("bType", ""),
                    fc=bda_elem.get("fc", ""),
                    type_id=bda_elem.get("type", ""),
                    desc=bda_elem.get("desc", ""),
                    val=val,
                )
            )
        return SclDAType(
            id=elem.get("id", ""),
            desc=elem.get("desc", ""),
            bdas=bdas,
        )

    def _parse_enum_type(self, elem: ET.Element) -> SclEnumType:
        """解析 SCL 中的 EnumType 元素并构建对应模型对象。"""
        values = []
        for ev_elem in self._ns.findall(elem, "EnumVal"):
            try:
                ord_val = int(ev_elem.get("ord", "0"))
            except ValueError:
                ord_val = 0
            values.append(
                SclEnumVal(
                    ord=ord_val,
                    value=(ev_elem.text or "").strip(),
                    desc=ev_elem.get("desc", ""),
                )
            )
        return SclEnumType(
            id=elem.get("id", ""),
            values=values,
        )

    # ===== IED =====

    def _parse_ied(self, elem: ET.Element) -> SclIED:
        """解析 SCL 中的 IED 元素并构建对应模型对象。"""
        self._ied_name = elem.get("name", "")
        access_points = []
        for ap_elem in self._ns.findall(elem, "AccessPoint"):
            access_points.append(self._parse_access_point(ap_elem))

        return SclIED(
            name=self._ied_name,
            desc=elem.get("desc", ""),
            manufacturer=elem.get("manufacturer", ""),
            config_revision=elem.get("configRevision", ""),
            access_points=access_points,
        )

    def _parse_access_point(self, elem: ET.Element) -> SclAccessPoint:
        """解析 SCL 中的 AccessPoint 元素并构建对应模型对象。"""
        server = None
        server_elem = self._ns.find(elem, "Server")
        if server_elem is not None:
            server = self._parse_server(server_elem)

        return SclAccessPoint(
            name=elem.get("name", ""),
            server=server,
        )

    def _parse_server(self, elem: ET.Element) -> SclServer:
        """解析 SCL 中的 Server 元素并构建对应模型对象。"""
        ldevices = []
        for ld_elem in self._ns.findall(elem, "LDevice"):
            ldevices.append(self._parse_ldevice(ld_elem))
        return SclServer(ldevices=ldevices)

    def _parse_ldevice(self, elem: ET.Element) -> SclLDevice:
        """解析 SCL 中的 LDevice 元素并构建对应模型对象。"""
        ln0 = None
        lns = []

        ld_inst = elem.get("inst", "")
        # IEC 61850-6: nameStructure="IEDName" 时，MMS 逻辑设备名由
        # IED 名称 + LDevice.inst 拼接而成（如 IED=KG_BAMS, inst=STCK01
        # → MMS LD 名 = KG_BAMSSTCK01）。
        if self._ied_name and self._name_structure == "IEDName" and not ld_inst.startswith(self._ied_name):
            ld_inst = f"{self._ied_name}{ld_inst}"

        ln0_elem = self._ns.find(elem, "LN0")
        if ln0_elem is not None:
            ln0 = self._parse_ln(ln0_elem, ld_inst)

        for ln_elem in self._ns.findall(elem, "LN"):
            lns.append(self._parse_ln(ln_elem, ld_inst))

        return SclLDevice(
            inst=ld_inst,
            desc=elem.get("desc", ""),
            ln0=ln0,
            lns=lns,
        )

    def _parse_ln(self, elem: ET.Element, ld_inst: str = "") -> SclLN:
        # DOI
        """解析 SCL 中的 LN/LN0 元素并构建对应模型对象。"""
        dois = []
        for doi_elem in self._ns.findall(elem, "DOI"):
            dois.append(self._parse_doi(doi_elem))

        # DataSet
        datasets = []
        for ds_elem in self._ns.findall(elem, "DataSet"):
            datasets.append(self._parse_dataset(ds_elem, ld_inst))

        # ReportControl
        report_controls = []
        for rc_elem in self._ns.findall(elem, "ReportControl"):
            rc = self._parse_report_control(rc_elem)
            if rc:
                report_controls.append(rc)

        # GSEControl
        gse_controls = []
        for gse_elem in self._ns.findall(elem, "GSEControl"):
            gse_controls.append(self._parse_gse_control(gse_elem))

        # SettingControl (IEC 61850-6 allows one in LN0)
        setting_control = None
        setting_elem = self._ns.find(elem, "SettingControl")
        if setting_elem is not None:
            try:
                num_of_sg = max(1, int(setting_elem.get("numOfSGs", "1")))
            except ValueError:
                num_of_sg = 1
            try:
                act_sg = int(setting_elem.get("actSG", "1"))
            except ValueError:
                act_sg = 1
            setting_control = SclSettingControl(num_of_sg=num_of_sg, act_sg=min(max(1, act_sg), num_of_sg))

        # Log / LogControl
        logs = [SclLog(name=item.get("name", ""), desc=item.get("desc", "")) for item in self._ns.findall(elem, "Log")]
        log_controls = []
        for item in self._ns.findall(elem, "LogControl"):
            name = item.get("name", "")
            log_name = item.get("logName", "")
            if not name or not log_name:
                continue
            trg_ops = SclTrgOps()
            trg_elem = self._ns.find(item, "TrgOps")
            if trg_elem is not None:
                trg_ops.dchg = trg_elem.get("dchg", "false").lower() == "true"
                trg_ops.qchg = trg_elem.get("qchg", "false").lower() == "true"
                trg_ops.dupd = trg_elem.get("dupd", "false").lower() == "true"
                trg_ops.period = trg_elem.get("period", "false").lower() == "true"
                trg_ops.gi = trg_elem.get("gi", "false").lower() == "true"
            try:
                intg_period = max(0, int(item.get("intgPd", "0")))
            except ValueError:
                intg_period = 0
            log_controls.append(
                SclLogControl(
                    name=name,
                    dat_set=item.get("datSet", ""),
                    log_name=log_name,
                    intg_period=intg_period,
                    log_ena=item.get("logEna", "true").lower() == "true",
                    reason_code=item.get("reasonCode", "true").lower() == "true",
                    desc=item.get("desc", ""),
                    trg_ops=trg_ops,
                )
            )

        # Inputs/ExtRef 描述的是当前 IED 对外部 GOOSE/SMV/Report 数据的
        # 订阅关系，不能从本 IED 的 GSEControl 反向猜测。
        inputs = []
        inputs_elem = self._ns.find(elem, "Inputs")
        if inputs_elem is not None:
            for ext_ref_elem in self._ns.findall(inputs_elem, "ExtRef"):
                inputs.append(self._parse_ext_ref(ext_ref_elem))

        return SclLN(
            ln_class=elem.get("lnClass", ""),
            inst=elem.get("inst", ""),
            ln_type=elem.get("lnType", ""),
            prefix=elem.get("prefix", ""),
            desc=elem.get("desc", ""),
            dois=dois,
            datasets=datasets,
            report_controls=report_controls,
            gse_controls=gse_controls,
            setting_control=setting_control,
            log_controls=log_controls,
            logs=logs,
            inputs=inputs,
        )

    @staticmethod
    def _parse_ext_ref(elem: ET.Element) -> SclExtRef:
        """解析 SCL 中的 ExtRef 元素并构建对应模型对象。"""
        return SclExtRef(
            ied_name=elem.get("iedName", ""),
            ld_inst=elem.get("ldInst", ""),
            ln_class=elem.get("lnClass", ""),
            ln_inst=elem.get("lnInst", ""),
            prefix=elem.get("prefix", ""),
            do_name=elem.get("doName", ""),
            da_name=elem.get("daName", ""),
            service_type=elem.get("serviceType", ""),
            src_ld_inst=elem.get("srcLDInst", ""),
            src_ln_class=elem.get("srcLNClass", ""),
            src_ln_inst=elem.get("srcLNInst", ""),
            src_prefix=elem.get("srcPrefix", ""),
            src_cb_name=elem.get("srcCBName", ""),
            int_addr=elem.get("intAddr", ""),
            desc=elem.get("desc", ""),
        )

    def _parse_doi(self, elem: ET.Element) -> SclDOI:
        """解析 SCL 中的 DOI 元素并构建对应模型对象。"""
        dai_values = {}
        for dai_elem in self._ns.findall(elem, "DAI"):
            dai_name = dai_elem.get("name", "")
            val_elem = self._ns.find(dai_elem, "Val")
            if val_elem is not None and val_elem.text:
                dai_values[dai_name] = val_elem.text.strip()
        return SclDOI(
            name=elem.get("name", ""),
            desc=elem.get("desc", ""),
            dai_values=dai_values,
        )

    def _parse_dataset(self, elem: ET.Element, ld_inst: str = "") -> SclDataSet:
        """解析 SCL 中的 DataSet 元素并构建对应模型对象。"""
        members = []
        for fcda_elem in self._ns.findall(elem, "FCDA"):
            da_name = fcda_elem.get("daName", "")
            # 展开结构体 DA 路径
            da_name = STRUCT_DA_TO_FULL_PATH.get(da_name, da_name)
            # 部分 ICD 文件的 FCDA 省略 ldInst，需从父 LDevice 继承
            fcda_ld_inst = fcda_elem.get("ldInst", "") or ld_inst
            # nameStructure="IEDName" 时 FCDA ldInst 也需要 IEDName 前缀
            if self._ied_name and self._name_structure == "IEDName" and not fcda_ld_inst.startswith(self._ied_name):
                fcda_ld_inst = f"{self._ied_name}{fcda_ld_inst}"
            members.append(
                SclFCDA(
                    ld_inst=fcda_ld_inst,
                    ln_class=fcda_elem.get("lnClass", ""),
                    ln_inst=fcda_elem.get("lnInst", ""),
                    ln_prefix=fcda_elem.get("prefix", ""),
                    do_name=fcda_elem.get("doName", ""),
                    da_name=da_name,
                    fc=fcda_elem.get("fc", ""),
                )
            )
        return SclDataSet(
            name=elem.get("name", ""),
            desc=elem.get("desc", ""),
            members=members,
        )

    def _parse_report_control(self, elem: ET.Element) -> SclReportControl | None:
        """解析 SCL 中的 ReportControl 元素并构建对应模型对象。"""
        name = elem.get("name", "")
        if not name:
            return None

        buffered = elem.get("buffered", "false").lower() == "true"

        # RptEnabled — 多实例 URCB 的实例数 (IEC 61850-6)
        rpt_enabled_max = 1
        rpt_enabled_elem = self._ns.find(elem, "RptEnabled")
        if rpt_enabled_elem is not None:
            try:
                rpt_enabled_max = int(rpt_enabled_elem.get("max", "1"))
            except ValueError:
                rpt_enabled_max = 1

        # TrgOps
        trg_ops = SclTrgOps()
        trg_elem = self._ns.find(elem, "TrgOps")
        if trg_elem is not None:
            trg_ops.dchg = trg_elem.get("dchg", "false").lower() == "true"
            trg_ops.qchg = trg_elem.get("qchg", "false").lower() == "true"
            trg_ops.dupd = trg_elem.get("dupd", "false").lower() == "true"
            trg_ops.period = trg_elem.get("period", "false").lower() == "true"
            trg_ops.gi = trg_elem.get("gi", "false").lower() == "true"

        # OptFields
        opt_fields = SclOptFields()
        opt_elem = self._ns.find(elem, "OptFields")
        if opt_elem is not None:
            opt_fields.seq_num = opt_elem.get("seqNum", "false").lower() == "true"
            opt_fields.time_stamp = opt_elem.get("timeStamp", "false").lower() == "true"
            opt_fields.data_set = opt_elem.get("dataSet", "false").lower() == "true"
            opt_fields.reason_code = opt_elem.get("reasonCode", "false").lower() == "true"
            opt_fields.data_ref = opt_elem.get("dataRef", "false").lower() == "true"
            opt_fields.entry_id = opt_elem.get("entryID", "false").lower() == "true"
            opt_fields.config_ref = opt_elem.get("configRef", "false").lower() == "true"
            opt_fields.buf_ovfl = opt_elem.get("bufOvfl", "false").lower() == "true"

        try:
            conf_rev = int(elem.get("confRev", "1"))
        except ValueError:
            conf_rev = 1
        try:
            buf_time = int(elem.get("bufTime", "0"))
        except ValueError:
            buf_time = 0
        try:
            intg_period = int(elem.get("intgPd", "0"))
        except ValueError:
            intg_period = 0

        return SclReportControl(
            name=name,
            rpt_id=elem.get("rptID", name),
            buffered=buffered,
            dat_set=elem.get("datSet", ""),
            conf_rev=conf_rev,
            buf_time=buf_time,
            intg_period=intg_period,
            desc=elem.get("desc", ""),
            rpt_enabled_max=rpt_enabled_max,
            trg_ops=trg_ops,
            opt_fields=opt_fields,
        )

    def _parse_gse_control(self, elem: ET.Element) -> SclGSEControl:
        """解析 SCL 中的 GSEControl 元素并构建对应模型对象。"""
        try:
            conf_rev = int(elem.get("confRev", "1"))
        except ValueError:
            conf_rev = 1

        return SclGSEControl(
            name=elem.get("name", ""),
            app_id=elem.get("appID", ""),
            dat_set=elem.get("datSet", ""),
            conf_rev=conf_rev,
            control_type=elem.get("type", "GOOSE"),
            desc=elem.get("desc", ""),
        )
