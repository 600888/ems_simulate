"""
ICD/SCD/CID 文件 GOOSE 配置解析模块

从 IEC 61850 SCL 文件中提取 GOOSE 控制块(GSEControl)、数据集(DataSet)
和通信地址(GSE)信息，用于自动创建 GOOSE Publisher / Subscriber。

ICD 文件中 GOOSE 相关结构:
  <SCL>
    <IED name="...">
      <AccessPoint>
        <Server>
          <LDevice inst="...">
            <LN0 lnClass="LLN0" lnType="...">
              <GSEControl name="gcb1" appID="0001" datSet="dsGOOSE1"
                          confRev="1" type="GOOSE"/>
              <DataSet name="dsGOOSE1">
                <FCDA ldInst="LD0" prefix="" lnClass="LLN0" lnInst=""
                      doName="GoCB1" daName="stVal" fc="ST"/>
              </DataSet>
    <Communication>
      <SubNetwork>
        <ConnectedAP iedName="IED1" apName="S1">
          <GSE ldInst="LD0" lnClass="LLN0" lnInst="">
            <Address>
              <P type="APPID">0001</P>
              <P type="Multicast">01-0C-CD-01-00-01</P>
              <P type="VLAN-PRIORITY">4</P>
              <P type="VLAN-ID">000</P>
            </Address>
            <MinTime unit="s" multiplier="m">10</MinTime>
            <MaxTime unit="s" multiplier="m">1000</MaxTime>
          </GSE>
"""

import contextlib
import os
import re
from typing import Any, Dict, List, Optional, Tuple
import xml.etree.ElementTree as ET

from src.data.log import log

# IEC 61850 SCL 命名空间
SCL_NS = "http://www.iec.ch/61850/2003/SCL"

# 已知结构体 DA 到完整叶子 DA 路径的映射
# ICD 文件的 FCDA 中 daName 只给出顶级 DA 名（如 "mag"），
# 但 MMS 引用需要完整路径（如 "mag.f"），用于值读取和树形展示
_KNOWN_STRUCT_DA_TO_FULL_PATH = {
    "mag": "mag.f",  # MV CDC: 浮点测量值
    "instMag": "instMag.f",  # SAV CDC: 瞬时测量值
    "cVal": "cVal.mag.f",  # CMV CDC: 复数测量值
    "mxVal": "mxVal.f",  # 某些实现
    "fCVal": "fCVal.mag.f",  # 复数浮点
    "wVal": "wVal.f",  # 设定值
    "setMag": "setMag.f",  # 设定幅值
    "Oper": "Oper.ctlVal",  # SPC/DPC CDC: 操作
    "SBOw": "SBOw.ctlVal",  # SBO 带值
    "Cancel": "Cancel.ctlVal",  # 取消操作
    "origin": "origin.orCat",  # Origin 结构体
}


class GooseGseControlInfo:
    """GSEControl 解析结果"""

    def __init__(self):
        self.name: str = ""  # GSEControl name (如 "gcb1")
        self.go_cb_ref: str = ""  # 完整引用 (如 "LD0/LLN0$GO$gcb1")
        self.app_id: str = ""  # appID 属性值
        self.dat_set: str = ""  # 数据集名称
        self.conf_rev: int = 1  # 配置修订号
        self.control_type: str = "GOOSE"  # type 属性
        self.desc: str = ""  # 描述

        # 所属 LD/LN 信息
        self.ied_name: str = ""
        self.ld_inst: str = ""
        self.ln_class: str = "LLN0"
        self.ln_inst: str = ""
        self.ln_prefix: str = ""

        # 通信地址 (从 GSE 元素获取)
        self.gse_app_id: str = ""  # APPID (通信部分)
        self.mac_address: str = ""  # 组播 MAC 地址
        self.vlan_id: int = 0
        self.vlan_priority: int = 4
        self.min_time: int = 10  # ms, 最小重发时间 (T1)
        self.max_time: int = 1000  # ms, 最大重发时间 (T0, 即 TimeAllowedToLive)

        # 数据集成员
        self.dataset_members: list[dict[str, str]] = []

    def to_publisher_dict(self, interface: str = "eth0") -> dict[str, Any]:
        """转换为 GoosePublisher 创建参数"""
        app_id_int = 0x0001
        if self.app_id:
            try:
                app_id_int = int(self.app_id, 16)
            except ValueError:
                with contextlib.suppress(ValueError):
                    app_id_int = int(self.app_id)
        elif self.gse_app_id:
            try:
                app_id_int = int(self.gse_app_id, 16)
            except ValueError:
                with contextlib.suppress(ValueError):
                    app_id_int = int(self.gse_app_id)

        dst_mac = None
        if self.mac_address:
            dst_mac = self._parse_mac(self.mac_address)

        entries = []
        for member in self.dataset_members:
            iec_type = self._fcda_to_iec_type(member)
            entries.append(
                {
                    "name": member.get("fcda_ref", ""),
                    "value": self._default_value_for_type(iec_type),
                    "iec_type": iec_type,
                    "fc": member.get("fc", ""),
                }
            )

        return {
            "interface": interface,
            "go_cb_ref": self.go_cb_ref,
            "go_id": self.name,
            "data_set_ref": f"{self.ld_inst}/{self.ln_class}${self.dat_set}" if self.dat_set else "",
            "app_id": app_id_int,
            "conf_rev": self.conf_rev,
            "time_allowed_to_live": self.max_time,
            "dst_mac": dst_mac,
            "vlan_id": self.vlan_id,
            "vlan_prio": self.vlan_priority,
            "simulation": True,
            "entries": entries,
        }

    def to_subscription_dict(self) -> dict[str, Any]:
        """转换为 GooseSubscription 创建参数"""
        app_id_int = None
        aid = self.gse_app_id or self.app_id
        if aid:
            try:
                app_id_int = int(aid, 16)
            except ValueError:
                with contextlib.suppress(ValueError):
                    app_id_int = int(aid)

        dst_mac = None
        if self.mac_address:
            dst_mac = self._parse_mac(self.mac_address)

        return {
            "go_cb_ref": self.go_cb_ref,
            "app_id": app_id_int,
            "dst_mac": dst_mac,
            "description": f"从 ICD 导入 ({self.ied_name})",
        }

    @staticmethod
    def _parse_mac(mac_str: str) -> list[int] | None:
        """解析 MAC 地址字符串为字节数组"""
        # 支持格式: 01-0C-CD-01-00-01, 01:0C:CD:01:00:01
        parts = re.split(r"[-:]", mac_str.strip())
        if len(parts) != 6:
            return None
        try:
            return [int(p, 16) for p in parts]
        except ValueError:
            return None

    @staticmethod
    def _fcda_to_iec_type(fcda: dict[str, str]) -> str:
        """根据 FCDA 的 fc 推断 IEC 数据类型"""
        fc = fcda.get("fc", "")
        if fc == "ST":
            return "boolean"
        elif fc == "MX":
            return "float"
        elif fc == "CO":
            return "boolean"
        elif fc == "SP":
            return "string"
        elif fc == "SV":
            return "boolean"
        elif fc == "CF":
            return "float"
        elif fc == "DC":
            return "string"
        return "boolean"

    @staticmethod
    def _default_value_for_type(iec_type: str) -> Any:
        """返回数据类型的默认值"""
        if iec_type == "boolean":
            return False
        elif iec_type == "integer":
            return 0
        elif iec_type == "float":
            return 0.0
        elif iec_type == "string":
            return ""
        elif iec_type == "bitstring" or iec_type == "timestamp":
            return 0
        return False


class IcdGooseImporter:
    """ICD 文件 GOOSE 配置解析器"""

    def __init__(self):
        self._ns_prefix: str = ""
        self._gse_controls: list[GooseGseControlInfo] = []
        # IED name -> ConnectedAP 下的 GSE 信息缓存
        self._gse_address_map: dict[str, list[dict[str, Any]]] = {}
        # (ied_name, ld_inst, ln_class, ln_inst, ln_prefix) -> [DataSet]
        self._dataset_map: dict[tuple, list[ET.Element]] = {}
        # 未被 GSEControl 引用的纯 DataSet（无 GOOSE 发布）
        self._pure_datasets: list[dict[str, Any]] = []
        # ReportControl 列表（自定义 RCB）
        self._report_controls: list[dict[str, Any]] = []

    def _tag(self, name: str) -> str:
        """根据检测到的命名空间构造完整 tag"""
        if self._ns_prefix:
            return f"{self._ns_prefix}{name}"
        return name

    def _detect_namespace(self, root: ET.Element) -> None:
        """检测 XML 根元素是否使用了 SCL 命名空间"""
        tag = root.tag
        if tag.startswith("{"):
            ns = tag.split("}")[0] + "}"
            self._ns_prefix = ns
        else:
            self._ns_prefix = ""

    def parse_icd(self, file_path: str) -> list[GooseGseControlInfo]:
        """解析 ICD/SCD/CID 文件，提取 GOOSE 配置

        Args:
            file_path: ICD 文件路径

        Returns:
            GOOSE 控制块信息列表
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        tree = ET.parse(file_path)
        root = tree.getroot()
        self._detect_namespace(root)

        self._gse_controls = []
        self._gse_address_map = {}
        self._dataset_map = {}

        # 1. 解析 Communication 部分的 GSE 地址
        self._parse_communication(root)

        # 2. 解析 IED 部分的 GSEControl 和 DataSet
        self._parse_ied(root)

        log.info(f"ICD GOOSE 解析完成: 共 {len(self._gse_controls)} 个 GSEControl")
        return self._gse_controls

    def _parse_communication(self, root: ET.Element) -> None:
        """解析 Communication 部分，提取 GSE 地址信息"""
        comm = root.find(self._tag("Communication"))
        if comm is None:
            log.debug("ICD 文件中未找到 Communication 节")
            return

        for subnetwork in comm.findall(self._tag("SubNetwork")):
            for conn_ap in subnetwork.findall(self._tag("ConnectedAP")):
                ied_name = conn_ap.get("iedName", "")
                ap_name = conn_ap.get("apName", "")

                for gse in conn_ap.findall(self._tag("GSE")):
                    gse_info = self._parse_gse_element(gse)
                    gse_info["ied_name"] = ied_name
                    gse_info["ap_name"] = ap_name

                    if ied_name not in self._gse_address_map:
                        self._gse_address_map[ied_name] = []
                    self._gse_address_map[ied_name].append(gse_info)

    def _parse_gse_element(self, gse: ET.Element) -> dict[str, Any]:
        """解析单个 GSE 元素"""
        info: dict[str, Any] = {
            "ld_inst": gse.get("ldInst", ""),
            "ln_class": gse.get("lnClass", "LLN0"),
            "ln_inst": gse.get("lnInst", ""),
            "cb_name": gse.get("cbName", ""),
        }

        # 解析 Address 子元素
        address = gse.find(self._tag("Address"))
        if address is not None:
            for p in address.findall(self._tag("P")):
                p_type = p.get("type", "")
                p_text = (p.text or "").strip()
                if p_type == "APPID":
                    info["gse_app_id"] = p_text
                elif p_type == "Multicast":
                    info["mac_address"] = p_text
                elif p_type == "VLAN-PRIORITY":
                    try:
                        info["vlan_priority"] = int(p_text)
                    except ValueError:
                        info["vlan_priority"] = 4
                elif p_type == "VLAN-ID":
                    try:
                        info["vlan_id"] = int(p_text, 16) if p_text else 0
                    except ValueError:
                        info["vlan_id"] = 0

        # 解析 MinTime / MaxTime
        min_time = gse.find(self._tag("MinTime"))
        if min_time is not None:
            mult = min_time.get("multiplier", "m")
            val_text = min_time.text or "10"
            try:
                val = float(val_text)
                if mult == "m":
                    info["min_time"] = int(val)
                elif mult == "s":
                    info["min_time"] = int(val * 1000)
                else:
                    info["min_time"] = int(val)
            except ValueError:
                info["min_time"] = 10

        max_time = gse.find(self._tag("MaxTime"))
        if max_time is not None:
            mult = max_time.get("multiplier", "m")
            val_text = max_time.text or "1000"
            try:
                val = float(val_text)
                if mult == "m":
                    info["max_time"] = int(val)
                elif mult == "s":
                    info["max_time"] = int(val * 1000)
                else:
                    info["max_time"] = int(val)
            except ValueError:
                info["max_time"] = 1000

        return info

    def _parse_ied(self, root: ET.Element) -> None:
        """解析 IED 部分，提取 GSEControl 和 DataSet"""
        for ied in root.findall(self._tag("IED")):
            ied_name = ied.get("name", "")

            for ap in ied.findall(self._tag("AccessPoint")):
                server = ap.find(self._tag("Server"))
                if server is None:
                    continue

                for ld in server.findall(self._tag("LDevice")):
                    ld_inst = ld.get("inst", "")

                    # LN0 是 GOOSE 控制块的载体
                    ln0 = ld.find(self._tag("LN0"))
                    if ln0 is None:
                        continue

                    # 收集数据集
                    datasets = ln0.findall(self._tag("DataSet"))
                    dataset_by_name: dict[str, ET.Element] = {}
                    for ds in datasets:
                        ds_name = ds.get("name", "")
                        if ds_name:
                            dataset_by_name[ds_name] = ds

                    # 解析 GSEControl，并记录已引用的 DataSet 名称
                    referenced_datasets: set = set()
                    for gse_ctrl in ln0.findall(self._tag("GSEControl")):
                        info = self._parse_gse_control(gse_ctrl, ied_name, ld_inst, ln0, dataset_by_name)
                        if info:
                            self._gse_controls.append(info)
                            if info.dat_set:
                                referenced_datasets.add(info.dat_set)

                    # 解析 ReportControl（自定义 RCB，非标准 brcb/urcb 命名）
                    ln_name = self._build_ln_name(
                        ln0.get("prefix", ""), ln0.get("lnClass", "LLN0"), ln0.get("inst", "")
                    )
                    for rc_elem in ln0.findall(self._tag("ReportControl")):
                        rc_info = self._parse_report_control(rc_elem, ld_inst, ln_name, dataset_by_name)
                        if rc_info:
                            self._report_controls.append(rc_info)
                            # 追踪 ReportControl 引用的 DataSet，避免被加入 pure_datasets
                            rc_dat_set = rc_info.get("dat_set", "")
                            if rc_dat_set:
                                referenced_datasets.add(rc_dat_set)

                    # 收集未被任何 GSEControl/ReportControl 引用的纯 DataSet
                    for ds_name, ds_elem in dataset_by_name.items():
                        if ds_name not in referenced_datasets:
                            pure_ds_members = self._parse_dataset(ds_elem, ld_inst)
                            ds_ref = f"{ld_inst}/{ln_name}${ds_name}"
                            entries = []
                            for m in pure_ds_members:
                                iec_type = GooseGseControlInfo._fcda_to_iec_type(m)
                                default_val = GooseGseControlInfo._default_value_for_type(iec_type)
                                entries.append(
                                    {
                                        "name": m.get("fcda_ref", ""),
                                        "value": default_val,
                                        "iec_type": iec_type,
                                        "fc": m.get("fc", ""),
                                    }
                                )
                            self._pure_datasets.append(
                                {
                                    "ld_inst": ld_inst,
                                    "ds_name": ds_name,
                                    "ds_ref": ds_ref,
                                    "data_set_ref": ds_ref,
                                    "member_count": len(pure_ds_members),
                                    "entries": entries,
                                }
                            )

    def _parse_gse_control(
        self,
        gse_ctrl: ET.Element,
        ied_name: str,
        ld_inst: str,
        ln0: ET.Element,
        dataset_by_name: dict[str, ET.Element],
    ) -> GooseGseControlInfo | None:
        """解析单个 GSEControl 元素"""
        info = GooseGseControlInfo()

        info.ied_name = ied_name
        info.ld_inst = ld_inst
        info.ln_class = ln0.get("lnClass", "LLN0")
        info.ln_inst = ln0.get("inst", "")
        info.ln_prefix = ln0.get("prefix", "")

        info.name = gse_ctrl.get("name", "")
        info.app_id = gse_ctrl.get("appID", "")
        info.dat_set = gse_ctrl.get("datSet", "")
        info.desc = gse_ctrl.get("desc", "")
        info.control_type = gse_ctrl.get("type", "GOOSE")

        # confRev
        conf_rev_str = gse_ctrl.get("confRev", "1")
        try:
            info.conf_rev = int(conf_rev_str)
        except ValueError:
            info.conf_rev = 1

        # 构建 GoCBRef: ldInst/lnClass$GO$name
        ln_name = self._build_ln_name(info.ln_prefix, info.ln_class, info.ln_inst)
        info.go_cb_ref = f"{ld_inst}/{ln_name}$GO${info.name}"

        # 从 Communication 匹配 GSE 地址
        self._apply_gse_address(info)

        # 解析数据集成员
        if info.dat_set and info.dat_set in dataset_by_name:
            info.dataset_members = self._parse_dataset(dataset_by_name[info.dat_set], ld_inst)

        return info

    def _build_ln_name(self, prefix: str, ln_class: str, ln_inst: str) -> str:
        """构建 LN 名称"""
        if ln_class == "LLN0":
            return "LLN0"
        return f"{prefix}{ln_class}{ln_inst}"

    def _apply_gse_address(self, info: GooseGseControlInfo) -> None:
        """从 GSE 地址缓存中匹配并应用通信参数"""
        gse_list = self._gse_address_map.get(info.ied_name, [])

        for gse in gse_list:
            # 匹配条件: ldInst + cbName 或 ldInst + lnClass
            ld_match = gse.get("ld_inst", "") == info.ld_inst
            cb_match = gse.get("cb_name", "") == info.name
            ln_match = gse.get("ln_class", "LLN0") == info.ln_class

            if ld_match and (cb_match or ln_match):
                info.gse_app_id = gse.get("gse_app_id", "")
                info.mac_address = gse.get("mac_address", "")
                info.vlan_id = gse.get("vlan_id", 0)
                info.vlan_priority = gse.get("vlan_priority", 4)
                info.min_time = gse.get("min_time", 10)
                info.max_time = gse.get("max_time", 1000)
                return

    @staticmethod
    def _expand_da_path(da_name: str) -> str:
        """将 ICD FCDA 中的顶级 DA 名展开为完整的叶子 DA 路径

        ICD 文件的 FCDA 通常只给出顶级 DA 名称（如 "mag"），
        但 MMS 引用需要完整路径（如 "mag.f"）。
        对于已知的结构体 DA 进行自动补全，未知的保持原样。

        Args:
            da_name: ICD 文件中的 daName 属性值

        Returns:
            补全后的 DA 路径
        """
        if not da_name:
            return da_name
        return _KNOWN_STRUCT_DA_TO_FULL_PATH.get(da_name, da_name)

    def _parse_dataset(self, ds_elem: ET.Element, ld_inst: str) -> list[dict[str, str]]:
        """解析 DataSet 中的 FCDA 元素"""
        members = []
        for fcda in ds_elem.findall(self._tag("FCDA")):
            member = {
                "ld_inst": fcda.get("ldInst", ""),
                "ln_class": fcda.get("lnClass", ""),
                "ln_inst": fcda.get("lnInst", ""),
                "ln_prefix": fcda.get("prefix", ""),
                "do_name": fcda.get("doName", ""),
                "da_name": self._expand_da_path(fcda.get("daName", "")),
                "fc": fcda.get("fc", ""),
            }

            # 构建完整的 FCDA 引用路径
            fcda_ld = member["ld_inst"] or ld_inst
            fcda_ln = self._build_ln_name(member["ln_prefix"], member["ln_class"], member["ln_inst"])
            ref_parts = [fcda_ld, fcda_ln]
            if member["do_name"]:
                ref_parts.append(member["do_name"])
            if member["da_name"]:
                ref_parts.append(member["da_name"])

            member["fcda_ref"] = "/".join(ref_parts[:2]) + "." + ".".join(ref_parts[2:])
            members.append(member)

        return members

    def _parse_report_control(
        self,
        rc_elem: ET.Element,
        ld_inst: str,
        ln_name: str,
        dataset_by_name: dict[str, ET.Element] | None = None,
    ) -> dict[str, Any] | None:
        """解析单个 ReportControl 元素

        Args:
            rc_elem: ReportControl XML 元素
            ld_inst: 逻辑设备实例名
            ln_name: 逻辑节点名称
            dataset_by_name: DataSet 名称到 XML 元素的映射，用于查找 RCB 引用的 DataSet 条目
        """
        name = rc_elem.get("name", "")
        if not name:
            return None

        buffered = rc_elem.get("buffered", "false").lower() == "true"
        rcb_type = "BRCB" if buffered else "URCB"

        rpt_id = rc_elem.get("rptID", name)
        dat_set = rc_elem.get("datSet", "")
        try:
            conf_rev = int(rc_elem.get("confRev", "1"))
        except ValueError:
            conf_rev = 1
        try:
            buf_time = int(rc_elem.get("bufTime", "0"))
        except ValueError:
            buf_time = 0
        try:
            intg_period = int(rc_elem.get("intgPd", "0"))
        except ValueError:
            intg_period = 0

        # 解析 TrgOps
        trg_ops = {"dchg": False, "qchg": False, "dupd": False, "period": False, "gi": False}
        trg_elem = rc_elem.find(self._tag("TrgOps"))
        if trg_elem is not None:
            for k in trg_ops:
                v = trg_elem.get(k, "false")
                trg_ops[k] = v.lower() == "true"

        # 解析 OptFields
        opt_fields = {
            "seq_num": False,
            "time_stamp": False,
            "data_set": False,
            "reason_code": False,
            "data_ref": False,
            "entry_id": False,
            "config_ref": False,
            "buf_ovfl": False,
        }
        opt_elem = rc_elem.find(self._tag("OptFields"))
        if opt_elem is not None:
            key_map = {
                "seqNum": "seq_num",
                "timeStamp": "time_stamp",
                "dataSet": "data_set",
                "reasonCode": "reason_code",
                "dataRef": "data_ref",
                "entryID": "entry_id",
                "configRef": "config_ref",
                "bufOvfl": "buf_ovfl",
            }
            for xml_key, py_key in key_map.items():
                v = opt_elem.get(xml_key, "false")
                opt_fields[py_key] = v.lower() == "true"

        data_set_ref = f"{ld_inst}/{ln_name}${dat_set}" if dat_set else ""

        # 解析 RCB 引用的 DataSet 条目 (FCDA entries)
        entries = []
        if dat_set and dataset_by_name and dat_set in dataset_by_name:
            ds_members = self._parse_dataset(dataset_by_name[dat_set], ld_inst)
            for m in ds_members:
                iec_type = GooseGseControlInfo._fcda_to_iec_type(m)
                default_val = GooseGseControlInfo._default_value_for_type(iec_type)
                entries.append(
                    {
                        "name": m.get("fcda_ref", ""),
                        "value": default_val,
                        "iec_type": iec_type,
                        "fc": m.get("fc", ""),
                    }
                )

        rc_info = {
            "ld_inst": ld_inst,
            "name": name,
            "rcb_type": rcb_type,
            "rpt_id": rpt_id,
            "dat_set": dat_set,
            "data_set_ref": data_set_ref,
            "conf_rev": conf_rev,
            "buf_time": buf_time,
            "intg_period": intg_period,
            "ln_name": ln_name,
            "trg_ops": trg_ops,
            "opt_fields": opt_fields,
            "entries": entries,
        }
        log.info(
            f"ICD ReportControl: {ld_inst}/{ln_name}.{name}, type={rcb_type}, datSet={dat_set}, entries={len(entries)}"
        )
        return rc_info

    def get_pure_datasets(self) -> list[dict[str, Any]]:
        """获取未被 GSEControl 引用的纯 DataSet 列表

        Returns:
            [{
                "ld_inst": str,       # 逻辑设备实例名
                "ds_name": str,        # DataSet 名称
                "ds_ref": str,         # DataSet 引用路径
                "data_set_ref": str,
                "member_count": int,
                "entries": [{"name", "value", "iec_type"}]
            }]
        """
        return list(self._pure_datasets)

    def get_report_controls(self) -> list[dict[str, Any]]:
        """获取从 ICD 解析的 ReportControl 列表

        Returns:
            [{
                "ld_inst": str,        # 逻辑设备实例名
                "name": str,            # ReportControl name (如 rpRack1CellTemp)
                "rcb_type": str,        # "BRCB" (buffered=true) / "URCB" (buffered=false)
                "rpt_id": str,          # rptID 属性
                "data_set_ref": str,    # datSet 属性引用的 DataSet 引用路径
                "conf_rev": int,        # 配置修订号
                "buf_time": int,        # 缓冲时间 (ms), 仅 BRCB
                "intg_period": int,     # 完整性周期 (ms), 仅 URCB
                "ln_name": str,         # 所属 LN 名称 (通常是 LLN0)
                "trg_ops": dict,        # 触发选项
                "opt_fields": dict,     # 可选字段
            }]
        """
        return list(self._report_controls)

    def get_import_summary(self) -> dict[str, Any]:
        """获取解析摘要"""
        return {
            "gse_control_count": len(self._gse_controls),
            "gse_controls": [
                {
                    "go_cb_ref": g.go_cb_ref,
                    "go_id": g.name,
                    "app_id": g.app_id or g.gse_app_id,
                    "dat_set": g.dat_set,
                    "conf_rev": g.conf_rev,
                    "mac_address": g.mac_address,
                    "dataset_member_count": len(g.dataset_members),
                }
                for g in self._gse_controls
            ],
        }


def import_goose_from_icd(file_path: str, interface: str = "eth0") -> dict[str, Any]:
    """从 ICD 文件导入 GOOSE 配置

    Args:
        file_path: ICD/SCD/CID 文件路径
        interface: 网络接口名称

    Returns:
        {
            "publishers": [...],     # 可创建的 Publisher 配置列表
            "subscriptions": [...],  # 可创建的 Subscription 配置列表
            "summary": {...},        # 解析摘要
        }
    """
    importer = IcdGooseImporter()
    gse_controls = importer.parse_icd(file_path)

    publishers = []
    subscriptions = []

    for gse in gse_controls:
        publishers.append(gse.to_publisher_dict(interface))
        subscriptions.append(gse.to_subscription_dict())

    return {
        "publishers": publishers,
        "subscriptions": subscriptions,
        "pure_datasets": importer.get_pure_datasets(),
        "report_controls": importer.get_report_controls(),
        "summary": importer.get_import_summary(),
    }
