"""SCL 统一解析器

解析 IEC 61850 ICD/SCD/CID 文件，构建 SclDocument。

替代:
- IcdPointImporter 的 XML 解析逻辑
- IcdGooseImporter 的 XML 解析逻辑

统一一次解析，多处消费。
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
    SclFCDA,
    SclGSE,
    SclGSEControl,
    SclHeader,
    SclIED,
    SclLDevice,
    SclLN,
    SclLNodeType,
    SclOptFields,
    SclP,
    SclReportControl,
    SclSDO,
    SclServer,
    SclSubNetwork,
    SclTrgOps,
)
from .namespace import NamespaceHelper


class SclParser:
    """SCL 统一解析器

    解析 ICD/SCD/CID 文件为 SclDocument 对象。
    支持:
    - 有/无 SCL 命名空间
    - Communication / IED / DataTypeTemplates 三大节
    """

    def __init__(self):
        self._ns = NamespaceHelper()

    def parse_file(self, file_path: str) -> SclDocument:
        """解析 SCL 文件

        Args:
            file_path: ICD/SCD/CID 文件路径

        Raises:
            FileNotFoundError: 文件不存在
            ValueError: XML 解析失败
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        tree = ET.parse(file_path)
        root = tree.getroot()
        return self._parse_root(root)

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
        return SclHeader(
            id=elem.get("id", ""),
            version=elem.get("version", ""),
            revision=elem.get("revision", ""),
            tool_id=elem.get("toolID", ""),
        )

    # ===== Communication =====

    def _parse_communication(self, elem: ET.Element) -> SclCommunication:
        sub_nets = []
        for sn_elem in self._ns.findall(elem, "SubNetwork"):
            sub_nets.append(self._parse_sub_network(sn_elem))
        return SclCommunication(sub_networks=sub_nets)

    def _parse_sub_network(self, elem: ET.Element) -> SclSubNetwork:
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
            result.append(SclP(
                type=p.get("type", ""),
                value=(p.text or "").strip(),
            ))
        return result

    # ===== DataTypeTemplates =====

    def _parse_data_type_templates(self, elem: ET.Element) -> Any:
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
        dos = []
        for do_elem in self._ns.findall(elem, "DO"):
            dos.append(SclDO(
                name=do_elem.get("name", ""),
                type_id=do_elem.get("type", ""),
                desc=do_elem.get("desc", ""),
                access_control=do_elem.get("presCond", ""),
            ))
        return SclLNodeType(
            id=elem.get("id", ""),
            ln_class=elem.get("lnClass", ""),
            desc=elem.get("desc", ""),
            dos=dos,
        )

    def _parse_do_type(self, elem: ET.Element) -> SclDOType:
        das = []
        sdos = []

        for da_elem in self._ns.findall(elem, "DA"):
            val = ""
            val_elem = self._ns.find(da_elem, "Val")
            if val_elem is not None and val_elem.text:
                val = val_elem.text.strip()
            das.append(SclDA(
                name=da_elem.get("name", ""),
                fc=da_elem.get("fc", ""),
                b_type=da_elem.get("bType", ""),
                type_id=da_elem.get("type", ""),
                dchg=da_elem.get("dchg", "false").lower() == "true",
                qchg=da_elem.get("qchg", "false").lower() == "true",
                dupd=da_elem.get("dupd", "false").lower() == "true",
                desc=da_elem.get("desc", ""),
                val=val,
            ))

        for sdo_elem in self._ns.findall(elem, "SDO"):
            sdos.append(SclSDO(
                name=sdo_elem.get("name", ""),
                type_id=sdo_elem.get("type", ""),
                desc=sdo_elem.get("desc", ""),
            ))

        return SclDOType(
            id=elem.get("id", ""),
            cdc=elem.get("cdc", ""),
            desc=elem.get("desc", ""),
            das=das,
            sdos=sdos,
        )

    def _parse_da_type(self, elem: ET.Element) -> SclDAType:
        bdas = []
        for bda_elem in self._ns.findall(elem, "BDA"):
            val = ""
            val_elem = self._ns.find(bda_elem, "Val")
            if val_elem is not None and val_elem.text:
                val = val_elem.text.strip()
            bdas.append(SclBDA(
                name=bda_elem.get("name", ""),
                b_type=bda_elem.get("bType", ""),
                fc=bda_elem.get("fc", ""),
                type_id=bda_elem.get("type", ""),
                desc=bda_elem.get("desc", ""),
                val=val,
            ))
        return SclDAType(
            id=elem.get("id", ""),
            desc=elem.get("desc", ""),
            bdas=bdas,
        )

    def _parse_enum_type(self, elem: ET.Element) -> SclEnumType:
        values = []
        for ev_elem in self._ns.findall(elem, "EnumVal"):
            try:
                ord_val = int(ev_elem.get("ord", "0"))
            except ValueError:
                ord_val = 0
            values.append(SclEnumVal(
                ord=ord_val,
                value=(ev_elem.text or "").strip(),
                desc=ev_elem.get("desc", ""),
            ))
        return SclEnumType(
            id=elem.get("id", ""),
            values=values,
        )

    # ===== IED =====

    def _parse_ied(self, elem: ET.Element) -> SclIED:
        access_points = []
        for ap_elem in self._ns.findall(elem, "AccessPoint"):
            access_points.append(self._parse_access_point(ap_elem))

        return SclIED(
            name=elem.get("name", ""),
            desc=elem.get("desc", ""),
            manufacturer=elem.get("manufacturer", ""),
            config_revision=elem.get("configRevision", ""),
            access_points=access_points,
        )

    def _parse_access_point(self, elem: ET.Element) -> SclAccessPoint:
        server = None
        server_elem = self._ns.find(elem, "Server")
        if server_elem is not None:
            server = self._parse_server(server_elem)

        return SclAccessPoint(
            name=elem.get("name", ""),
            server=server,
        )

    def _parse_server(self, elem: ET.Element) -> SclServer:
        ldevices = []
        for ld_elem in self._ns.findall(elem, "LDevice"):
            ldevices.append(self._parse_ldevice(ld_elem))
        return SclServer(ldevices=ldevices)

    def _parse_ldevice(self, elem: ET.Element) -> SclLDevice:
        ln0 = None
        lns = []

        ln0_elem = self._ns.find(elem, "LN0")
        if ln0_elem is not None:
            ln0 = self._parse_ln(ln0_elem)

        for ln_elem in self._ns.findall(elem, "LN"):
            lns.append(self._parse_ln(ln_elem))

        return SclLDevice(
            inst=elem.get("inst", ""),
            desc=elem.get("desc", ""),
            ln0=ln0,
            lns=lns,
        )

    def _parse_ln(self, elem: ET.Element) -> SclLN:
        # DOI
        dois = []
        for doi_elem in self._ns.findall(elem, "DOI"):
            dois.append(self._parse_doi(doi_elem))

        # DataSet
        datasets = []
        for ds_elem in self._ns.findall(elem, "DataSet"):
            datasets.append(self._parse_dataset(ds_elem))

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
        )

    def _parse_doi(self, elem: ET.Element) -> SclDOI:
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

    def _parse_dataset(self, elem: ET.Element) -> SclDataSet:
        members = []
        for fcda_elem in self._ns.findall(elem, "FCDA"):
            da_name = fcda_elem.get("daName", "")
            # 展开结构体 DA 路径
            da_name = STRUCT_DA_TO_FULL_PATH.get(da_name, da_name)
            members.append(SclFCDA(
                ld_inst=fcda_elem.get("ldInst", ""),
                ln_class=fcda_elem.get("lnClass", ""),
                ln_inst=fcda_elem.get("lnInst", ""),
                ln_prefix=fcda_elem.get("prefix", ""),
                do_name=fcda_elem.get("doName", ""),
                da_name=da_name,
                fc=fcda_elem.get("fc", ""),
            ))
        return SclDataSet(
            name=elem.get("name", ""),
            desc=elem.get("desc", ""),
            members=members,
        )

    def _parse_report_control(self, elem: ET.Element) -> SclReportControl | None:
        name = elem.get("name", "")
        if not name:
            return None

        buffered = elem.get("buffered", "false").lower() == "true"

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
            trg_ops=trg_ops,
            opt_fields=opt_fields,
        )

    def _parse_gse_control(self, elem: ET.Element) -> SclGSEControl:
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
