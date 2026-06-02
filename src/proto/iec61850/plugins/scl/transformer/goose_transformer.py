"""SclGooseTransformer — SclDocument → GOOSE 配置数据

替代 IcdGooseImporter 的核心逻辑:
  SclDocument → GSEControl + GSE 通信地址 → Publisher/Subscriber 配置
"""
from __future__ import annotations

import contextlib
import re
from dataclasses import dataclass, field
from typing import Any

from ..model.scl_document import (
    SclDocument, SclGSE, SclGSEControl, SclLN, SclLDevice, SclIED,
    SclDataSet,
)
from ..model.enums import FC_TO_IEC_TYPE


@dataclass
class GseControlInfo:
    """GSEControl 解析结果 (含通信地址)"""
    name: str = ""
    go_cb_ref: str = ""
    app_id: str = ""
    dat_set: str = ""
    conf_rev: int = 1
    control_type: str = "GOOSE"
    desc: str = ""

    # 所属 LD/LN 信息
    ied_name: str = ""
    ld_inst: str = ""
    ln_class: str = "LLN0"
    ln_inst: str = ""
    ln_prefix: str = ""

    # 通信地址
    gse_app_id: str = ""
    mac_address: str = ""
    vlan_id: int = 0
    vlan_priority: int = 4
    min_time: int = 10
    max_time: int = 1000

    # 数据集成员
    dataset_members: list[dict[str, str]] = field(default_factory=list)

    def to_publisher_dict(self, interface: str = "eth0") -> dict[str, Any]:
        """转换为 GoosePublisher 创建参数"""
        app_id_int = self._parse_app_id(self.app_id or self.gse_app_id)
        dst_mac = self._parse_mac(self.mac_address) if self.mac_address else None

        entries = []
        for member in self.dataset_members:
            iec_type = _fcda_to_iec_type(member)
            entries.append({
                "name": member.get("fcda_ref", ""),
                "value": _default_value_for_type(iec_type),
                "iec_type": iec_type,
                "fc": member.get("fc", ""),
            })

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


@dataclass
class GooseTransformResult:
    """GOOSE 转换结果"""
    gse_controls: list[GseControlInfo] = field(default_factory=list)
    pure_datasets: list[dict[str, Any]] = field(default_factory=list)


class SclGooseTransformer:
    """SCL GOOSE 转换器"""

    def __init__(self, doc: SclDocument):
        self._doc = doc

    def transform(self) -> GooseTransformResult:
        """执行转换"""
        result = GooseTransformResult()

        for ied in self._doc.ieds:
            for ap in ied.access_points:
                if not ap.server:
                    continue
                for ld in ap.server.ldevices:
                    if ld.ln0 is None:
                        continue
                    self._transform_ln0(ld.ln0, ld, ied, result)

        return result

    def _transform_ln0(
        self,
        ln0: SclLN,
        ld: SclLDevice,
        ied: SclIED,
        result: GooseTransformResult,
    ) -> None:
        """转换 LN0 中的 GSEControl"""
        # DataSet 索引
        ds_map: dict[str, SclDataSet] = {ds.name: ds for ds in ln0.datasets}

        # 记录被 GSEControl/ReportControl 引用的 DataSet
        referenced_datasets: set[str] = set()

        # GSEControl
        for gse_ctrl in ln0.gse_controls:
            info = self._build_gse_control_info(gse_ctrl, ln0, ld, ied, ds_map)
            result.gse_controls.append(info)
            if info.dat_set:
                referenced_datasets.add(info.dat_set)

        # ReportControl 也引用 DataSet
        for rc in ln0.report_controls:
            if rc.dat_set:
                referenced_datasets.add(rc.dat_set)

        # 纯 DataSet (未被任何控制块引用)
        for ds_name, ds in ds_map.items():
            if ds_name not in referenced_datasets:
                members = [self._fcda_to_dict(m) for m in ds.members]
                ds_ref = f"{ld.inst}/{ln0.ln_name}${ds_name}"
                entries = []
                for m in members:
                    iec_type = _fcda_to_iec_type(m)
                    entries.append({
                        "name": m.get("fcda_ref", ""),
                        "value": _default_value_for_type(iec_type),
                        "iec_type": iec_type,
                        "fc": m.get("fc", ""),
                    })
                result.pure_datasets.append({
                    "ld_inst": ld.inst,
                    "ds_name": ds_name,
                    "ds_ref": ds_ref,
                    "data_set_ref": ds_ref,
                    "member_count": len(members),
                    "entries": entries,
                })

    def _build_gse_control_info(
        self,
        gse_ctrl: SclGSEControl,
        ln0: SclLN,
        ld: SclLDevice,
        ied: SclIED,
        ds_map: dict[str, SclDataSet],
    ) -> GseControlInfo:
        """构建 GseControlInfo"""
        info = GseControlInfo(
            name=gse_ctrl.name,
            app_id=gse_ctrl.app_id,
            dat_set=gse_ctrl.dat_set,
            conf_rev=gse_ctrl.conf_rev,
            control_type=gse_ctrl.control_type,
            desc=gse_ctrl.desc,
            ied_name=ied.name,
            ld_inst=ld.inst,
            ln_class=ln0.ln_class,
            ln_inst=ln0.inst,
            ln_prefix=ln0.prefix,
        )

        # GoCBRef
        info.go_cb_ref = f"{ld.inst}/{ln0.ln_name}$GO${gse_ctrl.name}"

        # 匹配通信地址
        gse_addr = self._doc.get_gse_address(ied.name, ld.inst, gse_ctrl.name)
        if gse_addr:
            self._apply_gse_address(info, gse_addr)

        # 数据集成员
        if gse_ctrl.dat_set and gse_ctrl.dat_set in ds_map:
            info.dataset_members = [
                self._fcda_to_dict(m) for m in ds_map[gse_ctrl.dat_set].members
            ]

        return info

    @staticmethod
    def _apply_gse_address(info: GseControlInfo, gse: SclGSE) -> None:
        """从 GSE 通信地址应用参数"""
        for p in gse.address:
            if p.type == "APPID":
                info.gse_app_id = p.value
            elif p.type == "Multicast":
                info.mac_address = p.value
            elif p.type == "VLAN-PRIORITY":
                try:
                    info.vlan_priority = int(p.value)
                except ValueError:
                    info.vlan_priority = 4
            elif p.type == "VLAN-ID":
                try:
                    info.vlan_id = int(p.value, 16) if p.value else 0
                except ValueError:
                    info.vlan_id = 0
        info.min_time = gse.min_time
        info.max_time = gse.max_time

    @staticmethod
    def _fcda_to_dict(fcda: Any) -> dict[str, str]:
        """将 SclFCDA 转为兼容 dict"""
        return {
            "ld_inst": fcda.ld_inst,
            "ln_class": fcda.ln_class,
            "ln_inst": fcda.ln_inst,
            "ln_prefix": fcda.ln_prefix,
            "do_name": fcda.do_name,
            "da_name": fcda.da_name,
            "fc": fcda.fc,
            "fcda_ref": fcda.fcda_ref,
        }


def _fcda_to_iec_type(fcda: dict[str, str]) -> str:
    """根据 FCDA 的 fc 推断 IEC 数据类型"""
    return FC_TO_IEC_TYPE.get(fcda.get("fc", ""), "boolean")


def _default_value_for_type(iec_type: str) -> Any:
    """返回数据类型的默认值"""
    defaults = {
        "boolean": False,
        "integer": 0,
        "float": 0.0,
        "string": "",
        "bitstring": 0,
        "timestamp": 0,
    }
    return defaults.get(iec_type, False)
