"""
ICD/SCD/CID 文件 GOOSE 配置解析模块

从 IEC 61850 SCL 文件中提取 GOOSE 控制块(GSEControl)、数据集(DataSet)
和通信地址(GSE)信息，用于自动创建 GOOSE Publisher / Subscriber。

Phase 8 迁移: 内部委托 SclParser + SclGooseTransformer + SclReportTransformer，
保持外部接口不变。

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

from __future__ import annotations

import contextlib
import os
import re
from typing import Any

from src.data.log import log

# 已知结构体 DA 到完整叶子 DA 路径的映射
_KNOWN_STRUCT_DA_TO_FULL_PATH = {
    "mag": "mag.f",
    "instMag": "instMag.f",
    "cVal": "cVal.mag.f",
    "mxVal": "mxVal.f",
    "fCVal": "fCVal.mag.f",
    "wVal": "wVal.f",
    "setMag": "setMag.f",
    "Oper": "Oper.ctlVal",
    "SBOw": "SBOw.ctlVal",
    "Cancel": "Cancel.ctlVal",
    "origin": "origin.orCat",
}


class GooseGseControlInfo:
    """GSEControl 解析结果"""

    def __init__(self):
        self.name: str = ""
        self.go_cb_ref: str = ""
        self.app_id: str = ""
        self.dat_set: str = ""
        self.conf_rev: int = 1
        self.control_type: str = "GOOSE"
        self.desc: str = ""

        # 所属 LD/LN 信息
        self.ied_name: str = ""
        self.ld_inst: str = ""
        self.ln_class: str = "LLN0"
        self.ln_inst: str = ""
        self.ln_prefix: str = ""

        # 通信地址
        self.gse_app_id: str = ""
        self.mac_address: str = ""
        self.vlan_id: int = 0
        self.vlan_priority: int = 4
        self.min_time: int = 10
        self.max_time: int = 1000

        # 数据集成员
        self.dataset_members: list[dict[str, str]] = []

    def to_publisher_dict(self, interface: str = "eth0") -> dict[str, Any]:
        """转换为 GoosePublisher 创建参数"""
        app_id_int = self._parse_app_id(self.app_id or self.gse_app_id)
        dst_mac = self._parse_mac(self.mac_address) if self.mac_address else None

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
            app_id_int = self._parse_app_id(aid)
        dst_mac = self._parse_mac(self.mac_address) if self.mac_address else None

        return {
            "go_cb_ref": self.go_cb_ref,
            "app_id": app_id_int,
            "dst_mac": dst_mac,
            "description": f"从 ICD 导入 ({self.ied_name})",
        }

    @staticmethod
    def _parse_app_id(val: str) -> int:
        if not val:
            return 0x0001
        try:
            return int(val, 16)
        except ValueError:
            with contextlib.suppress(ValueError):
                return int(val)
            return 0x0001

    @staticmethod
    def _parse_mac(mac_str: str) -> list[int] | None:
        parts = re.split(r"[-:]", mac_str.strip())
        if len(parts) != 6:
            return None
        try:
            return [int(p, 16) for p in parts]
        except ValueError:
            return None

    @staticmethod
    def _fcda_to_iec_type(fcda: dict[str, str]) -> str:
        fc = fcda.get("fc", "")
        fc_map = {
            "ST": "boolean", "MX": "float", "CO": "boolean",
            "SP": "string", "SV": "boolean", "CF": "float",
            "DC": "string",
        }
        return fc_map.get(fc, "boolean")

    @staticmethod
    def _default_value_for_type(iec_type: str) -> Any:
        defaults = {
            "boolean": False, "integer": 0, "float": 0.0,
            "string": "", "bitstring": 0, "timestamp": 0,
        }
        return defaults.get(iec_type, False)

    @staticmethod
    def _expand_da_path(da_name: str) -> str:
        if not da_name:
            return da_name
        return _KNOWN_STRUCT_DA_TO_FULL_PATH.get(da_name, da_name)


class IcdGooseImporter:
    """ICD 文件 GOOSE 配置解析器

    Phase 8 迁移: 内部使用 SclParser + SclGooseTransformer + SclReportTransformer 进行解析，
    保持 parse_icd() / get_pure_datasets() / get_report_controls() / get_import_summary() 接口不变。
    """

    def __init__(self):
        self._gse_controls: list[GooseGseControlInfo] = []
        self._pure_datasets: list[dict[str, Any]] = []
        self._report_controls: list[dict[str, Any]] = []

    def parse_icd(self, file_path: str) -> list[GooseGseControlInfo]:
        """解析 ICD/SCD/CID 文件，提取 GOOSE 配置

        Args:
            file_path: ICD 文件路径

        Returns:
            GOOSE 控制块信息列表
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        from src.proto.iec61850.plugins.scl.parser.scl_parser import SclParser
        from src.proto.iec61850.plugins.scl.transformer.goose_transformer import SclGooseTransformer
        from src.proto.iec61850.plugins.scl.transformer.report_transformer import SclReportTransformer

        parser = SclParser()
        doc = parser.parse_file(file_path)

        # GOOSE 转换
        goose_transformer = SclGooseTransformer(doc)
        goose_result = goose_transformer.transform()

        # Report 转换
        report_transformer = SclReportTransformer(doc)
        report_result = report_transformer.transform()

        # 转换为旧接口格式
        self._gse_controls = [_convert_gse_info(g) for g in goose_result.gse_controls]
        self._pure_datasets = list(goose_result.pure_datasets)
        self._report_controls = [
            {
                "ld_inst": rc.ld_inst,
                "name": rc.name,
                "rcb_type": rc.rcb_type,
                "rpt_id": rc.rpt_id,
                "dat_set": rc.dat_set,
                "data_set_ref": rc.data_set_ref,
                "conf_rev": rc.conf_rev,
                "buf_time": rc.buf_time,
                "intg_period": rc.intg_period,
                "ln_name": rc.ln_name,
                "trg_ops": rc.trg_ops,
                "opt_fields": rc.opt_fields,
                "entries": rc.entries,
            }
            for rc in report_result.report_controls
        ]

        log.info(f"ICD GOOSE 解析完成 (SclParser): 共 {len(self._gse_controls)} 个 GSEControl")
        return self._gse_controls

    def get_pure_datasets(self) -> list[dict[str, Any]]:
        """获取未被 GSEControl 引用的纯 DataSet 列表"""
        return list(self._pure_datasets)

    def get_report_controls(self) -> list[dict[str, Any]]:
        """获取从 ICD 解析的 ReportControl 列表"""
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


def _convert_gse_info(gse_info) -> GooseGseControlInfo:
    """将 SclGooseTransformer 的 GseControlInfo 转为旧 GooseGseControlInfo"""
    info = GooseGseControlInfo()
    info.name = gse_info.name
    info.go_cb_ref = gse_info.go_cb_ref
    info.app_id = gse_info.app_id
    info.dat_set = gse_info.dat_set
    info.conf_rev = gse_info.conf_rev
    info.control_type = gse_info.control_type
    info.desc = gse_info.desc
    info.ied_name = gse_info.ied_name
    info.ld_inst = gse_info.ld_inst
    info.ln_class = gse_info.ln_class
    info.ln_inst = gse_info.ln_inst
    info.ln_prefix = gse_info.ln_prefix
    info.gse_app_id = gse_info.gse_app_id
    info.mac_address = gse_info.mac_address
    info.vlan_id = gse_info.vlan_id
    info.vlan_priority = gse_info.vlan_priority
    info.min_time = gse_info.min_time
    info.max_time = gse_info.max_time
    info.dataset_members = list(gse_info.dataset_members)
    return info


def import_goose_from_icd(file_path: str, interface: str = "eth0") -> dict[str, Any]:
    """从 ICD 文件导入 GOOSE 配置

    Args:
        file_path: ICD/SCD/CID 文件路径
        interface: 网络接口名称

    Returns:
        {
            "publishers": [...],
            "subscriptions": [...],
            "summary": {...},
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
