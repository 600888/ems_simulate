"""
IEC 61850 模型导出工具类

独立的模型发现与导出插件，通过持有 IEC61850Client 引用来复用客户端的连接和浏览能力。
用法:
    client = IEC61850Client("192.168.1.100", 102)
    client.connect(auto_discover=False)
    exporter = IEC61850ModelExporter(client)
    model = exporter.discover()
    exporter.export_json(model, "model.json")
    exporter.export_all(model, "./output/")
"""

import csv
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

import xmltodict

from .log import log

if TYPE_CHECKING:
    from .iec61850_client import IEC61850Client

try:
    from pyiec61850 import pyiec61850 as iec61850
    HAS_IEC61850 = True
except ImportError:
    HAS_IEC61850 = False

# 从 client 模块导入共享常量
from .iec61850_client import (
    IEC_TYPE_FLOAT, IEC_TYPE_BOOLEAN, IEC_TYPE_INTEGER,
    IEC_TYPE_STRING, IEC_TYPE_TIMESTAMP, IEC_TYPE_UNKNOWN,
    _DA_PATTERNS, _EXTRA_DA_INFO, _ENC_DO_DA_TYPE_OVERRIDE,
    _BDA_TYPE_MAP, _STRUCT_DA_EXPAND_ONLINE, _KNOWN_BDA_FALLBACK_ONLINE,
)

# ========== ACSI 类常量 ==========

ACSI_CLASS_DATA_OBJECT = 0
ACSI_CLASS_DATA_SET = 3
ACSI_CLASS_BRCB = 5
ACSI_CLASS_URCB = 6
ACSI_CLASS_GOOSE = 9

# frame_type 中文描述
FRAME_TYPE_DESC = {0: "遥测(YC)", 1: "遥信(YX)", 2: "遥控(YK)", 3: "遥调(YT)"}


# ========== 模型数据类 ==========

@dataclass
class DAInfo:
    """数据属性 (DA) 信息"""
    name: str = ""
    path: str = ""
    fc: str = ""
    iec_type: str = ""
    sub_das: List['DAInfo'] = field(default_factory=list)


@dataclass
class DOInfo:
    """数据对象 (DO) 信息"""
    name: str = ""
    ref: str = ""
    frame_type: int = -1
    das: List[DAInfo] = field(default_factory=list)


@dataclass
class DataSetInfo:
    """数据集 (DataSet) 信息"""
    name: str = ""
    ref: str = ""
    is_deletable: bool = False
    members: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class RCBInfo:
    """报告控制块 (RCB) 信息"""
    name: str = ""
    ref: str = ""
    rcb_type: str = ""


@dataclass
class GoCBInfo:
    """GOOSE 控制块信息"""
    name: str = ""
    ref: str = ""


@dataclass
class LNInfo:
    """逻辑节点 (LN) 信息"""
    name: str = ""
    ln_class: str = ""
    ref: str = ""
    dos: List[DOInfo] = field(default_factory=list)
    datasets: List[DataSetInfo] = field(default_factory=list)
    rcb_list: List[RCBInfo] = field(default_factory=list)
    gocb_list: List[GoCBInfo] = field(default_factory=list)


@dataclass
class LDInfo:
    """逻辑设备 (LD) 信息"""
    name: str = ""
    inst: str = ""
    lns: List[LNInfo] = field(default_factory=list)


@dataclass
class ServerModel:
    """服务端完整模型"""
    host: str = ""
    port: int = 102
    discover_time: str = ""
    lds: List[LDInfo] = field(default_factory=list)


class IEC61850ModelExporter:
    """IEC 61850 模型发现与导出工具类

    通过持有 IEC61850Client 引用复用连接和浏览能力，
    提供结构化模型发现和多格式导出功能。

    参考 C++ 侧 IedClientModel::createTree() 的树形遍历逻辑。
    """

    def __init__(self, client: "IEC61850Client"):
        self._client = client

    # ========== 模型发现 ==========

    def discover(self) -> ServerModel:
        """动态发现服务端完整数据模型 (结构化)

        遍历 LD -> LN -> DO/DS/RCB/GoCB -> DA/BDA 完整树形层次。

        Returns:
            ServerModel 完整模型对象
        """
        if not self._client._connection or not self._client._is_connected:
            raise RuntimeError("未连接到服务端，请先调用 client.connect()")

        log.info("开始 IEC 61850 结构化模型发现...")
        start_time = time.time()

        model = ServerModel(
            host=self._client.ip,
            port=self._client.port,
            discover_time=time.strftime("%Y-%m-%d %H:%M:%S"),
        )

        # 1. 获取逻辑设备列表
        ld_names = self._client.browse_logical_devices()
        if not ld_names:
            log.warning("未发现任何逻辑设备")
            return model

        log.info(f"发现逻辑设备: {ld_names}")

        # 2. 遍历每个 LD
        for ld_name in ld_names:
            ld_info = LDInfo(name=ld_name, inst=ld_name)
            log.info(f"正在发现逻辑设备: {ld_name}")

            ln_names = self._client.browse_logical_nodes(ld_name)

            for ln_name in ln_names:
                ln_ref = f"{ld_name}/{ln_name}"
                ln_class = self._client._extract_ln_class(ln_name) or ""
                ln_info = LNInfo(name=ln_name, ln_class=ln_class, ref=ln_ref)

                ln_info.dos = self._discover_data_objects(ld_name, ln_ref, ln_name)
                ln_info.datasets = self._discover_datasets(ld_name, ln_ref)
                ln_info.rcb_list = self._discover_rcbs(ln_ref)
                ln_info.gocb_list = self._discover_gocbs(ln_ref)

                ld_info.lns.append(ln_info)

            model.lds.append(ld_info)

        elapsed = time.time() - start_time
        total_das = sum(
            len(do.das)
            for ld in model.lds for ln in ld.lns for do in ln.dos
        )
        log.info(
            f"结构化模型发现完成, 耗时 {elapsed:.2f}s, "
            f"{len(model.lds)} LD, "
            f"{sum(len(ld.lns) for ld in model.lds)} LN, "
            f"{total_das} DA"
        )

        return model

    def _discover_data_objects(self, ld_name: str, ln_ref: str, ln_name: str) -> List[DOInfo]:
        """发现逻辑节点下的所有数据对象 (DO) 及其数据属性 (DA)"""
        do_list = []

        try:
            result = iec61850.IedConnection_getLogicalNodeDirectory(
                self._client._connection, ln_ref, ACSI_CLASS_DATA_OBJECT
            )
            do_names_raw = result[0] if isinstance(result, (list, tuple)) else result
            error = result[1] if isinstance(result, (list, tuple)) else 0

            if error != iec61850.IED_ERROR_OK or do_names_raw is None:
                return []

            do_name_list = self._client._get_list_from_linked_list(do_names_raw)

            for do_name in do_name_list:
                do_ref = f"{ln_ref}.{do_name}"
                frame_type = self._client._infer_frame_type_from_do(ln_name, do_name)
                if frame_type is None:
                    frame_type = -1

                das = self._discover_data_attributes(ld_name, do_ref, do_name, ln_name, frame_type)

                do_list.append(DOInfo(
                    name=do_name, ref=do_ref, frame_type=frame_type, das=das,
                ))

        except Exception as e:
            log.debug(f"发现数据对象异常: {ln_ref}, {e}")

        return do_list

    def _discover_data_attributes(
        self, ld_name: str, do_ref: str, do_name: str,
        ln_name: str, do_frame_type: int,
    ) -> List[DAInfo]:
        """发现 DO 下的所有数据属性 (DA)，包括递归展开子 DA (BDA)"""
        da_list = []

        try:
            result = iec61850.IedConnection_getDataDirectory(self._client._connection, do_ref)
            da_names_raw = result[0] if isinstance(result, (list, tuple)) else result
            error = result[1] if isinstance(result, (list, tuple)) else 0

            if error != iec61850.IED_ERROR_OK or da_names_raw is None:
                return []

            da_name_list = self._client._get_list_from_linked_list(da_names_raw)

            for da_name in da_name_list:
                da_info = self._resolve_da_info(da_name, do_name, ln_name)

                if da_name in _STRUCT_DA_EXPAND_ONLINE:
                    sub_ref = f"{do_ref}.{da_name}"
                    fc = da_info.fc or self._infer_fc_from_da(da_name, do_frame_type)
                    sub_das = self._discover_sub_das(sub_ref, fc, f"{da_info.path}.")
                    da_info.sub_das = sub_das

                da_list.append(da_info)

        except Exception as e:
            log.debug(f"发现数据属性异常: {do_ref}, {e}")

        return da_list

    def _discover_sub_das(self, parent_ref: str, parent_fc: str, path_prefix: str) -> List[DAInfo]:
        """递归发现子数据属性 (BDA)"""
        sub_das = []
        try:
            result = iec61850.IedConnection_getDataDirectory(self._client._connection, parent_ref)
            bda_names_raw = result[0] if isinstance(result, (list, tuple)) else result
            error = result[1] if isinstance(result, (list, tuple)) else 0

            if error != iec61850.IED_ERROR_OK or bda_names_raw is None:
                # 回退: 使用已知 BDA
                parent_name = parent_ref.split(".")[-1]
                if parent_name in _KNOWN_BDA_FALLBACK_ONLINE:
                    bda_type_map = {"orCat": IEC_TYPE_INTEGER, "orIdent": IEC_TYPE_UNKNOWN}
                    for bda_name in _KNOWN_BDA_FALLBACK_ONLINE.get(parent_name, []):
                        sub_das.append(DAInfo(
                            name=bda_name, path=f"{path_prefix}{bda_name}",
                            fc=parent_fc, iec_type=bda_type_map.get(bda_name, IEC_TYPE_UNKNOWN),
                        ))
                return sub_das

            bda_name_list = self._client._get_list_from_linked_list(bda_names_raw)
            for bda_name in bda_name_list:
                bda_type = _BDA_TYPE_MAP.get(bda_name, IEC_TYPE_UNKNOWN)
                sub_das.append(DAInfo(
                    name=bda_name, path=f"{path_prefix}{bda_name}",
                    fc=parent_fc, iec_type=bda_type,
                ))

        except Exception as e:
            log.debug(f"发现子数据属性异常: {parent_ref}, {e}")

        return sub_das

    def _discover_datasets(self, ld_name: str, ln_ref: str) -> List[DataSetInfo]:
        """发现逻辑节点下的所有数据集"""
        datasets = []

        try:
            result = iec61850.IedConnection_getLogicalNodeDirectory(
                self._client._connection, ln_ref, ACSI_CLASS_DATA_SET
            )
            ds_names_raw = result[0] if isinstance(result, (list, tuple)) else result
            error = result[1] if isinstance(result, (list, tuple)) else 0

            if error != iec61850.IED_ERROR_OK or ds_names_raw is None:
                return []

            ds_name_list = self._client._get_list_from_linked_list(ds_names_raw)

            for ds_name in ds_name_list:
                ds_ref = f"{ln_ref}.{ds_name}"
                ds_info = DataSetInfo(name=ds_name, ref=ds_ref)
                ds_info.members = self._client.browse_dataset_directory(ds_ref)
                datasets.append(ds_info)

        except Exception as e:
            log.debug(f"发现数据集异常: {ln_ref}, {e}")

        return datasets

    def _discover_rcbs(self, ln_ref: str) -> List[RCBInfo]:
        """发现逻辑节点下的报告控制块"""
        rcb_list = []
        for _rcb_type, acsi_class, type_name in [
            ("URCB", ACSI_CLASS_URCB, "URCB"),
            ("BRCB", ACSI_CLASS_BRCB, "BRCB"),
        ]:
            try:
                result = iec61850.IedConnection_getLogicalNodeDirectory(
                    self._client._connection, ln_ref, acsi_class
                )
                rcb_names_raw = result[0] if isinstance(result, (list, tuple)) else result
                error = result[1] if isinstance(result, (list, tuple)) else 0

                if error != iec61850.IED_ERROR_OK or rcb_names_raw is None:
                    continue

                rcb_name_list = self._client._get_list_from_linked_list(rcb_names_raw)
                for rcb_name in rcb_name_list:
                    rcb_list.append(RCBInfo(
                        name=rcb_name, ref=f"{ln_ref}.{rcb_name}", rcb_type=type_name,
                    ))
            except Exception:
                pass

        return rcb_list

    def _discover_gocbs(self, ln_ref: str) -> List[GoCBInfo]:
        """发现逻辑节点下的 GOOSE 控制块"""
        gocb_list = []
        try:
            result = iec61850.IedConnection_getLogicalNodeDirectory(
                self._client._connection, ln_ref, ACSI_CLASS_GOOSE
            )
            gocb_names_raw = result[0] if isinstance(result, (list, tuple)) else result
            error = result[1] if isinstance(result, (list, tuple)) else 0

            if error != iec61850.IED_ERROR_OK or gocb_names_raw is None:
                return []

            gocb_name_list = self._client._get_list_from_linked_list(gocb_names_raw)
            for gocb_name in gocb_name_list:
                gocb_list.append(GoCBInfo(name=gocb_name, ref=f"{ln_ref}.{gocb_name}"))
        except Exception:
            pass

        return gocb_list

    def _resolve_da_info(self, da_name: str, do_name: str, ln_name: str) -> DAInfo:
        """根据 DA 名称推断完整路径、FC 和类型"""
        if da_name in _DA_PATTERNS:
            full_path, frame_type, iec_type = _DA_PATTERNS[da_name]
            fc_map = {0: "MX", 1: "ST", 2: "CO", 3: "CO"}
            return DAInfo(name=da_name, path=full_path, fc=fc_map.get(frame_type, ""), iec_type=iec_type)

        if da_name in _EXTRA_DA_INFO:
            full_path, fc, iec_type = _EXTRA_DA_INFO[da_name]
            return DAInfo(name=da_name, path=full_path, fc=fc, iec_type=iec_type)

        if do_name in _ENC_DO_DA_TYPE_OVERRIDE and da_name in _ENC_DO_DA_TYPE_OVERRIDE[do_name]:
            return DAInfo(
                name=da_name, path=da_name,
                fc="ST" if da_name == "stVal" else "CO",
                iec_type=_ENC_DO_DA_TYPE_OVERRIDE[do_name][da_name],
            )

        return DAInfo(name=da_name, path=da_name, fc="", iec_type=IEC_TYPE_UNKNOWN)

    def _infer_fc_from_da(self, da_name: str, do_frame_type: int) -> str:
        """根据 DA 名称和 DO 帧类型推断 FC"""
        if da_name in _DA_PATTERNS:
            frame_type = _DA_PATTERNS[da_name][1]
            return {0: "MX", 1: "ST", 2: "CO", 3: "CO"}.get(frame_type, "")
        if da_name in _EXTRA_DA_INFO:
            return _EXTRA_DA_INFO[da_name][1]
        return {0: "MX", 1: "ST", 2: "CO", 3: "CO"}.get(do_frame_type, "")

    # ========== 模型导出 ==========

    def export_json(self, model: ServerModel, output_path: str, indent: int = 2) -> None:
        """导出模型为 JSON 文件"""
        data = self._model_to_dict(model)
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=indent)
        log.info(f"模型已导出为 JSON: {output_path}")

    def export_xml(self, model: ServerModel, output_path: str, pretty: bool = True) -> None:
        """导出模型为自定义 XML 文件 (非标准 SCL 格式)

        使用 xmltodict 将结构化模型序列化为 XML。

        Args:
            model: ServerModel 对象
            output_path: 输出文件路径
            pretty: 是否格式化输出 (缩进换行)
        """
        xml_dict = self._model_to_xml_dict(model)
        xml_str = xmltodict.unparse(xml_dict, pretty=pretty, indent="  ")

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(xml_str)
        log.info(f"模型已导出为 XML: {output_path}")

    def export_icd(self, model: ServerModel, output_path: str,
                   ied_name: str = "", pretty: bool = True) -> None:
        """导出模型为 IEC 61850 SCL/ICD 标准格式

        生成符合 IEC 61850-6 SCL Schema 的 XML 文件，可直接导入支持 SCL 的工具。

        输出结构:
            SCL
            ├── Header
            ├── Communication (含 IP 地址)
            ├── IED
            │   └── AccessPoint > Server
            │       └── LDevice
            │           ├── LN0 (含 DataSet / ReportControl)
            │           └── LN (含 DOI / DAI)
            └── DataTypeTemplates
                ├── LNodeType (每个 LN 类一个)
                ├── DOType (每个 DO CDC 类型)
                ├── DAType (struct 类型的 DA)
                └── EnumType (枚举类型)

        Args:
            model: ServerModel 对象
            output_path: 输出文件路径 (.icd)
            ied_name: IED 名称 (为空则从模型推断)
            pretty: 是否格式化输出
        """
        if not ied_name:
            # 从第一个 LD 名称推断 IED 名称 (去掉最后一个 _XX 部分)
            if model.lds:
                parts = model.lds[0].name.rsplit("_", 1)
                ied_name = parts[0] if len(parts) > 1 else model.lds[0].name
            else:
                ied_name = "IED"

        scl_dict = self._model_to_scl_dict(model, ied_name)
        xml_str = xmltodict.unparse(scl_dict, pretty=pretty, indent="\t")

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(xml_str)
        log.info(f"模型已导出为 ICD (SCL): {output_path}")

    def export_csv(self, model: ServerModel, output_path: str) -> None:
        """导出模型为 CSV 文件 (扁平化测点表)

        CSV 列: LD, LN, LN类, DO, DA路径, FC, 数据类型, 帧类型, 帧类型描述, 完整引用
        """
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        rows = self._flatten_model(model)

        with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "逻辑设备(LD)", "逻辑节点(LN)", "LN类", "数据对象(DO)",
                "DA路径", "FC", "数据类型", "帧类型", "帧类型描述", "完整引用",
            ])
            for row in rows:
                writer.writerow(row)

        log.info(f"模型已导出为 CSV: {output_path} ({len(rows)} 条记录)")

    def export_tree_text(self, model: ServerModel, output_path: str) -> None:
        """导出模型为树形文本文件"""
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        lines = []
        lines.append(f"IEC 61850 Server Model — {model.host}:{model.port}")
        lines.append(f"发现时间: {model.discover_time}")
        lines.append("=" * 80)

        for ld in model.lds:
            lines.append(f"├── LD: {ld.name}")
            for i, ln in enumerate(ld.lns):
                is_last_ln = (i == len(ld.lns) - 1)
                ln_prefix = "└──" if is_last_ln else "├──"
                ln_indent = "│   " if not is_last_ln else "    "
                ln_class_str = f" [{ln.ln_class}]" if ln.ln_class else ""
                lines.append(f"│   {ln_prefix} LN: {ln.name}{ln_class_str}")

                # DO
                for j, do in enumerate(ln.dos):
                    is_last_do = (j == len(ln.dos) - 1) and not ln.datasets and not ln.rcb_list
                    do_prefix = "└──" if is_last_do else "├──"
                    ft_desc = FRAME_TYPE_DESC.get(do.frame_type, "未知")
                    lines.append(f"│   {ln_indent}{do_prefix} DO: {do.name} ({ft_desc})")

                    do_indent = ln_indent + ("    " if is_last_do else "│   ")

                    for k, da in enumerate(do.das):
                        is_last_da = (k == len(do.das) - 1) and not da.sub_das
                        da_prefix = "└──" if is_last_da else "├──"
                        fc_str = f" [FC={da.fc}]" if da.fc else ""
                        type_str = f" ({da.iec_type})" if da.iec_type else ""
                        lines.append(f"│   {do_indent}{da_prefix} DA: {da.path}{fc_str}{type_str}")

                        if da.sub_das:
                            bda_indent = do_indent + ("    " if is_last_da else "│   ")
                            for m, bda in enumerate(da.sub_das):
                                is_last_bda = (m == len(da.sub_das) - 1)
                                bda_prefix = "└──" if is_last_bda else "├──"
                                lines.append(f"│   {bda_indent}{bda_prefix} BDA: {bda.path} ({bda.iec_type})")

                # DataSet
                for j, ds in enumerate(ln.datasets):
                    is_last = (j == len(ln.datasets) - 1) and not ln.rcb_list
                    ds_prefix = "└──" if is_last else "├──"
                    lines.append(f"│   {ln_indent}{ds_prefix} DS: {ds.name} ({len(ds.members)} 成员)")
                    ds_indent = ln_indent + ("    " if is_last else "│   ")
                    for m, member in enumerate(ds.members):
                        is_last_m = (m == len(ds.members) - 1)
                        m_prefix = "└──" if is_last_m else "├──"
                        lines.append(f"│   {ds_indent}{m_prefix} {member.get('ref', '')} [{member.get('fc', '')}]")

                # RCB
                for j, rcb in enumerate(ln.rcb_list):
                    is_last = (j == len(ln.rcb_list) - 1) and not ln.gocb_list
                    rcb_prefix = "└──" if is_last else "├──"
                    lines.append(f"│   {ln_indent}{rcb_prefix} RCB: {rcb.name} ({rcb.rcb_type})")

                # GoCB
                for j, gocb in enumerate(ln.gocb_list):
                    is_last = (j == len(ln.gocb_list) - 1)
                    gocb_prefix = "└──" if is_last else "├──"
                    lines.append(f"│   {ln_indent}{gocb_prefix} GoCB: {gocb.name}")

        lines.append("=" * 80)

        total_lds = len(model.lds)
        total_lns = sum(len(ld.lns) for ld in model.lds)
        total_dos = sum(len(ln.dos) for ld in model.lds for ln in ld.lns)
        total_das = sum(len(do.das) for ld in model.lds for ln in ld.lns for do in ln.dos)
        total_ds = sum(len(ln.datasets) for ld in model.lds for ln in ld.lns)
        total_rcb = sum(len(ln.rcb_list) for ld in model.lds for ln in ld.lns)
        total_gocb = sum(len(ln.gocb_list) for ld in model.lds for ln in ld.lns)
        lines.append(f"统计: {total_lds} LD, {total_lns} LN, {total_dos} DO, {total_das} DA, "
                     f"{total_ds} DataSet, {total_rcb} RCB, {total_gocb} GoCB")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        log.info(f"模型已导出为树形文本: {output_path}")

    def export_all(self, model: ServerModel, output_dir: str, ied_name: str = "") -> Dict[str, str]:
        """导出所有格式到指定目录

        Returns:
            {格式: 文件路径} 字典
        """
        os.makedirs(output_dir, exist_ok=True)
        base_name = f"iec61850_model_{model.host}_{model.port}"

        json_path = os.path.join(output_dir, f"{base_name}.json")
        csv_path = os.path.join(output_dir, f"{base_name}.csv")
        txt_path = os.path.join(output_dir, f"{base_name}.txt")
        xml_path = os.path.join(output_dir, f"{base_name}.xml")
        icd_path = os.path.join(output_dir, f"{base_name}.icd")

        self.export_json(model, json_path)
        self.export_csv(model, csv_path)
        self.export_tree_text(model, txt_path)
        self.export_xml(model, xml_path)
        self.export_icd(model, icd_path, ied_name=ied_name)

        return {"json": json_path, "csv": csv_path, "txt": txt_path, "xml": xml_path, "icd": icd_path}

    # ========== 序列化辅助 ==========

    def _model_to_dict(self, model: ServerModel) -> Dict[str, Any]:
        """将 ServerModel 转换为可序列化的字典"""
        return {
            "host": model.host,
            "port": model.port,
            "discover_time": model.discover_time,
            "logicalDevices": [
                {
                    "name": ld.name,
                    "inst": ld.inst,
                    "logicalNodes": [
                        {
                            "name": ln.name,
                            "lnClass": ln.ln_class,
                            "ref": ln.ref,
                            "dataObjects": [
                                {
                                    "name": do_info.name,
                                    "ref": do_info.ref,
                                    "frameType": do_info.frame_type,
                                    "frameTypeDesc": FRAME_TYPE_DESC.get(do_info.frame_type, "未知"),
                                    "dataAttributes": [
                                        {
                                            "name": da.name,
                                            "path": da.path,
                                            "fc": da.fc,
                                            "iecType": da.iec_type,
                                            "subDataAttributes": [
                                                {
                                                    "name": bda.name,
                                                    "path": bda.path,
                                                    "fc": bda.fc,
                                                    "iecType": bda.iec_type,
                                                }
                                                for bda in da.sub_das
                                            ],
                                        }
                                        for da in do_info.das
                                    ],
                                }
                                for do_info in ln.dos
                            ],
                            "dataSets": [
                                {
                                    "name": ds.name,
                                    "ref": ds.ref,
                                    "isDeletable": ds.is_deletable,
                                    "members": ds.members,
                                }
                                for ds in ln.datasets
                            ],
                            "reportControlBlocks": [
                                {"name": rcb.name, "ref": rcb.ref, "type": rcb.rcb_type}
                                for rcb in ln.rcb_list
                            ],
                            "gooseControlBlocks": [
                                {"name": gocb.name, "ref": gocb.ref}
                                for gocb in ln.gocb_list
                            ],
                        }
                        for ln in ld.lns
                    ],
                }
                for ld in model.lds
            ],
            "summary": {
                "totalLDs": len(model.lds),
                "totalLNs": sum(len(ld.lns) for ld in model.lds),
                "totalDOs": sum(len(ln.dos) for ld in model.lds for ln in ld.lns),
                "totalDAs": sum(len(do_info.das) for ld in model.lds for ln in ld.lns for do_info in ln.dos),
                "totalDataSets": sum(len(ln.datasets) for ld in model.lds for ln in ld.lns),
                "totalRCBs": sum(len(ln.rcb_list) for ld in model.lds for ln in ld.lns),
                "totalGoCBs": sum(len(ln.gocb_list) for ld in model.lds for ln in ld.lns),
            },
        }

    def _flatten_model(self, model: ServerModel) -> List[List[str]]:
        """将模型扁平化为 CSV 行列表

        Returns:
            每行为 [LD, LN, LN类, DO, DA路径, FC, 数据类型, 帧类型, 帧类型描述, 完整引用]
        """
        rows = []
        for ld in model.lds:
            for ln in ld.lns:
                for do_info in ln.dos:
                    ft = do_info.frame_type
                    ft_desc = FRAME_TYPE_DESC.get(ft, "未知")
                    for da in do_info.das:
                        full_ref = f"{do_info.ref}.{da.path}"
                        rows.append([
                            ld.name, ln.name, ln.ln_class or "",
                            do_info.name, da.path, da.fc,
                            da.iec_type, str(ft), ft_desc, full_ref,
                        ])
                        for bda in da.sub_das:
                            full_ref_bda = f"{do_info.ref}.{bda.path}"
                            rows.append([
                                ld.name, ln.name, ln.ln_class or "",
                                do_info.name, bda.path, bda.fc,
                                bda.iec_type, str(ft), ft_desc, full_ref_bda,
                            ])
        return rows

    def _model_to_xml_dict(self, model: ServerModel) -> Dict[str, Any]:
        """将 ServerModel 转换为 xmltodict 兼容的字典结构

        xmltodict 约定:
          - "@key" 表示 XML 属性
          - 列表元素需用同一标签名包裹在父节点下
          - "#text" 表示元素文本内容
        """
        ld_list = []
        for ld in model.lds:
            ln_list = []
            for ln in ld.lns:
                ln_item = {"@name": ln.name, "@lnClass": ln.ln_class, "@ref": ln.ref}

                # DataObjects
                if ln.dos:
                    do_list = []
                    for do_info in ln.dos:
                        do_item = {
                            "@name": do_info.name,
                            "@ref": do_info.ref,
                            "@frameType": str(do_info.frame_type),
                            "@frameTypeDesc": FRAME_TYPE_DESC.get(do_info.frame_type, "未知"),
                        }
                        if do_info.das:
                            da_list = []
                            for da in do_info.das:
                                da_item = {
                                    "@name": da.name,
                                    "@path": da.path,
                                    "@fc": da.fc,
                                    "@iecType": da.iec_type,
                                }
                                if da.sub_das:
                                    bda_list = []
                                    for bda in da.sub_das:
                                        bda_list.append({
                                            "@name": bda.name,
                                            "@path": bda.path,
                                            "@fc": bda.fc,
                                            "@iecType": bda.iec_type,
                                        })
                                    da_item["SubDataAttributes"] = {"SubDataAttribute": bda_list if len(bda_list) > 1 else bda_list[0]}
                                da_list.append(da_item)
                            do_item["DataAttributes"] = {"DataAttribute": da_list if len(da_list) > 1 else da_list[0]}
                        do_list.append(do_item)
                    ln_item["DataObjects"] = {"DataObject": do_list if len(do_list) > 1 else do_list[0]}

                # DataSets
                if ln.datasets:
                    ds_list = []
                    for ds in ln.datasets:
                        ds_item = {
                            "@name": ds.name,
                            "@ref": ds.ref,
                            "@isDeletable": str(ds.is_deletable),
                        }
                        if ds.members:
                            member_list = []
                            for m in ds.members:
                                member_item = {"@ref": m.get("ref", ""), "@fc": m.get("fc", "")}
                                if m.get("da"):
                                    member_item["@da"] = m["da"]
                                member_list.append(member_item)
                            ds_item["Members"] = {"Member": member_list if len(member_list) > 1 else member_list[0]}
                        ds_list.append(ds_item)
                    ln_item["DataSets"] = {"DataSet": ds_list if len(ds_list) > 1 else ds_list[0]}

                # ReportControlBlocks
                if ln.rcb_list:
                    rcb_list = []
                    for rcb in ln.rcb_list:
                        rcb_list.append({"@name": rcb.name, "@ref": rcb.ref, "@type": rcb.rcb_type})
                    ln_item["ReportControlBlocks"] = {"ReportControlBlock": rcb_list if len(rcb_list) > 1 else rcb_list[0]}

                # GooseControlBlocks
                if ln.gocb_list:
                    gocb_list = []
                    for gocb in ln.gocb_list:
                        gocb_list.append({"@name": gocb.name, "@ref": gocb.ref})
                    ln_item["GooseControlBlocks"] = {"GooseControlBlock": gocb_list if len(gocb_list) > 1 else gocb_list[0]}

                ln_list.append(ln_item)

            ld_item = {"@name": ld.name, "@inst": ld.inst}
            if ln_list:
                ld_item["LogicalNodes"] = {"LogicalNode": ln_list if len(ln_list) > 1 else ln_list[0]}
            ld_list.append(ld_item)

        result = {
            "ServerModel": {
                "@host": model.host,
                "@port": str(model.port),
                "@discoverTime": model.discover_time,
                "LogicalDevices": {"LogicalDevice": ld_list if len(ld_list) > 1 else ld_list[0]},
                "Summary": {
                    "@totalLDs": str(len(model.lds)),
                    "@totalLNs": str(sum(len(ld.lns) for ld in model.lds)),
                    "@totalDOs": str(sum(len(ln.dos) for ld in model.lds for ln in ld.lns)),
                    "@totalDAs": str(sum(len(do_info.das) for ld in model.lds for ln in ld.lns for do_info in ln.dos)),
                    "@totalDataSets": str(sum(len(ln.datasets) for ld in model.lds for ln in ld.lns)),
                    "@totalRCBs": str(sum(len(ln.rcb_list) for ld in model.lds for ln in ld.lns)),
                    "@totalGoCBs": str(sum(len(ln.gocb_list) for ld in model.lds for ln in ld.lns)),
                },
            }
        }
        return result

    # ========== SCL/ICD 序列化 ==========

    # IEC 61850-7-3 CDC -> bType 映射 (简化)
    _CDC_BTYPE_MAP = {
        # 测量值 (MX)
        "MV": {"mag": ("Struct", None), "q": ("Quality", None), "t": ("Timestamp", None)},
        "CMV": {"cVal": ("Struct", None), "q": ("Quality", None), "t": ("Timestamp", None)},
        "SAV": {"instMag": ("Struct", None), "q": ("Quality", None), "t": ("Timestamp", None)},
        # 状态值 (ST)
        "SPS": {"stVal": ("BOOLEAN", None), "q": ("Quality", None), "t": ("Timestamp", None)},
        "DPS": {"stVal": ("Dbpos", None), "q": ("Quality", None), "t": ("Timestamp", None)},
        "INS": {"stVal": ("INT32", None), "q": ("Quality", None), "t": ("Timestamp", None)},
        "ENS": {"stVal": ("Enum", None), "q": ("Quality", None), "t": ("Timestamp", None)},
        "ACT": {"general": ("BOOLEAN", None), "q": ("Quality", None), "t": ("Timestamp", None)},
        "ACD": {"general": ("BOOLEAN", None), "q": ("Quality", None), "t": ("Timestamp", None)},
        "SEC": {"Cnt": ("INT32", None), "q": ("Quality", None), "t": ("Timestamp", None)},
        # 控制 (CO)
        "SPC": {"stVal": ("BOOLEAN", None), "ctlVal": ("BOOLEAN", None), "Oper": ("Struct", None), "q": ("Quality", None), "t": ("Timestamp", None), "ctlModel": ("Enum", "ctlModel")},
        "DPC": {"stVal": ("Dbpos", None), "ctlVal": ("Dbpos", None), "Oper": ("Struct", None), "q": ("Quality", None), "t": ("Timestamp", None), "ctlModel": ("Enum", "ctlModel")},
        "ENC": {"stVal": ("Enum", None), "ctlVal": ("Enum", None), "Oper": ("Struct", None), "q": ("Quality", None), "t": ("Timestamp", None), "ctlModel": ("Enum", "ctlModel")},
        "INC": {"stVal": ("INT32", None), "Oper": ("Struct", None), "q": ("Quality", None), "t": ("Timestamp", None), "ctlModel": ("Enum", "ctlModel")},
        # 设定 (SP)
        "APC": {"setVal": ("FLOAT32", None), "Oper": ("Struct", None), "q": ("Quality", None), "t": ("Timestamp", None), "ctlModel": ("Enum", "ctlModel")},
        "ASG": {"setMag": ("Struct", None), "setVal": ("FLOAT32", None), "q": ("Quality", None), "t": ("Timestamp", None)},
        # 铭牌 (DC)
        "LPL": {"vendor": ("VisString255", None), "swRev": ("VisString255", None), "d": ("VisString255", None)},
        "DPL": {"vendor": ("VisString255", None), "swRev": ("VisString255", None), "d": ("VisString255", None)},
    }

    # bType 简化映射 (用于在线发现时无法确定 CDC 的情况)
    _IEC_TYPE_TO_BTYPE = {
        IEC_TYPE_FLOAT: "FLOAT32",
        IEC_TYPE_BOOLEAN: "BOOLEAN",
        IEC_TYPE_INTEGER: "INT32",
        IEC_TYPE_STRING: "VisString255",
        IEC_TYPE_TIMESTAMP: "Timestamp",
        IEC_TYPE_UNKNOWN: "Struct",
    }

    # DA name -> fc 映射 (在线发现时推断)
    _DA_NAME_FC_MAP = {
        "mag": "MX", "cVal": "MX", "instMag": "MX", "mxVal": "MX", "fCVal": "MX", "setMag": "SP", "setVal": "SP", "wVal": "SP",
        "stVal": "ST", "general": "ST", "Cnt": "ST", "frVal": "ST", "frTm": "ST", "actVal": "ST", "subVal": "SV", "subEna": "SV",
        "ctlVal": "CO", "Oper": "CO", "SBO": "CO", "SBOw": "CO", "Cancel": "CO", "origin": "OR", "ctlNum": "CO", "AddCause": "CO", "valWTr": "CO",
        "q": "MX", "t": "MX", "blkEna": "BL",
        "dU": "DC", "du": "DC", "vendor": "DC", "swRev": "DC", "configRev": "DC", "d": "DC", "lnNs": "DC",
        "ctlModel": "CF", "dbRef": "CF",
    }

    def _model_to_scl_dict(self, model: ServerModel, ied_name: str) -> Dict[str, Any]:
        """将 ServerModel 转换为 SCL/ICD 标准格式的 xmltodict 字典

        SCL 层级:
          SCL
          ├── Header
          ├── Communication > SubNetwork > ConnectedAP > Address
          ├── IED > AccessPoint > Server > LDevice > LN0 / LN
          └── DataTypeTemplates > LNodeType / DOType / DAType / EnumType
        """
        # 1. 构建 DataTypeTemplates (先构建，因为 IED 引用 lnType)
        type_templates = self._build_data_type_templates(model, ied_name)

        # 2. 构建 IED 段
        ied = self._build_ied_section(model, ied_name, type_templates)

        # 3. 构建 Communication 段
        communication = {
            "SubNetwork": {
                "@name": "MMS",
                "@type": "8-MMS",
                "ConnectedAP": {
                    "@iedName": ied_name,
                    "@apName": "S1",
                    "Address": {
                        "P": [
                            {"@type": "IP", "#text": model.host},
                            {"@type": "OSI-TSEL", "#text": "0001"},
                            {"@type": "OSI-SSEL", "#text": "0001"},
                            {"@type": "OSI-PSEL", "#text": "00000001"},
                        ]
                    },
                },
            }
        }

        # 4. 组装 SCL
        scl_dict = {
            "SCL": {
                "@xmlns": "http://www.iec.ch/61850/2003/SCL",
                "Header": {
                    "@id": "",
                    "@version": "1",
                    "@revision": "",
                    "@toolID": "IEC61850ModelExporter",
                },
                "Communication": communication,
                "IED": ied,
                "DataTypeTemplates": type_templates,
            }
        }
        return scl_dict

    def _build_ied_section(self, model: ServerModel, ied_name: str,
                            type_templates: Dict[str, Any]) -> Dict[str, Any]:
        """构建 IED 段 (含 AccessPoint > Server > LDevice > LN)"""
        ldevice_list = []

        for ld in model.lds:
            ld_inst = self._extract_ld_inst(ld.name, ied_name)

            ln0_item = None
            ln_list = []

            for ln in ld.lns:
                ln_type_id = f"{ied_name}{ld_inst}.{ln.name}"
                ln_inst = self._extract_ln_inst(ln.name)
                ln_class = ln.ln_class or self._extract_ln_class_from_name(ln.name)

                if ln_class == "LLN0":
                    # LLN0 作为 LN0
                    ln0_item = {
                        "@lnType": ln_type_id,
                        "@lnClass": "LLN0",
                        "@inst": "",
                    }
                    # DataSet
                    if ln.datasets:
                        ln0_item["DataSet"] = self._build_datasets(ln.datasets, ld_inst, ln)
                    # ReportControl
                    if ln.rcb_list:
                        ln0_item["ReportControl"] = self._build_report_controls(ln.rcb_list)
                else:
                    # 普通 LN
                    ln_item = {
                        "@lnType": ln_type_id,
                        "@lnClass": ln_class,
                        "@inst": ln_inst,
                    }
                    # DOI / DAI
                    doi_list = self._build_dois(ln)
                    if doi_list:
                        ln_item["DOI"] = doi_list
                    # DataSet
                    if ln.datasets:
                        ln_item["DataSet"] = self._build_datasets(ln.datasets, ld_inst, ln)
                    # ReportControl
                    if ln.rcb_list:
                        ln_item["ReportControl"] = self._build_report_controls(ln.rcb_list)
                    ln_list.append(ln_item)

            ldevice = {"@inst": ld_inst}
            if ln0_item:
                ldevice["LN0"] = ln0_item
            if ln_list:
                ldevice["LN"] = ln_list if len(ln_list) > 1 else ln_list[0]
            ldevice_list.append(ldevice)

        server = {"Authentication": {"@none": "true"}}
        if ldevice_list:
            server["LDevice"] = ldevice_list if len(ldevice_list) > 1 else ldevice_list[0]

        ied = {
            "@name": ied_name,
            "Services": {
                "DynAssociation": None,
                "GetDirectory": None,
                "GetDataObjectDefinition": None,
                "DataObjectDirectory": None,
                "GetDataSetValue": None,
                "SetDataSetValue": None,
                "DataSetDirectory": None,
                "ReadWrite": None,
                "ConfReportControl": {"@max": str(sum(len(ln.rcb_list) for ld in model.lds for ln in ld.lns))},
                "GetCBValues": None,
                "ConfLNs": {"@fixPrefix": "true", "@fixLnInst": "true"},
            },
            "AccessPoint": {
                "@name": "S1",
                "Server": server,
            },
        }
        return ied

    def _build_data_type_templates(self, model: ServerModel, ied_name: str) -> Dict[str, Any]:
        """构建 DataTypeTemplates 段 (LNodeType + DOType + DAType + EnumType)"""
        lnode_types = []
        do_types = []
        da_types = []
        enum_types = {}

        # 收集所有出现的 EnumType
        enum_types["ctlModel"] = [
            {"@ord": str(i), "#text": v}
            for i, v in enumerate(["status-only", "direct-with-normal-security",
                                    "sbo-with-normal-security", "direct-with-enhanced-security",
                                    "sbo-with-enhanced-security"])
        ]
        enum_types["orCategory"] = [
            {"@ord": str(i), "#text": v}
            for i, v in enumerate(["not-supported", "bay-control", "station-control",
                                    "remote-control", "automatic-control", "maintenance-control"])
        ]

        for ld in model.lds:
            ld_inst = self._extract_ld_inst(ld.name, ied_name)

            for ln in ld.lns:
                ln_type_id = f"{ied_name}{ld_inst}.{ln.name}"
                ln_class = ln.ln_class or self._extract_ln_class_from_name(ln.name)

                # LNodeType
                do_refs = []
                for do_info in ln.dos:
                    cdc = self._infer_cdc_from_do(do_info.name, ln_class)
                    do_type_id = f"{ln_type_id}.{do_info.name}"
                    do_refs.append({"@name": do_info.name, "@type": do_type_id})

                    # DOType (每个 DO 一个)
                    do_type_item = {
                        "@id": do_type_id,
                        "@cdc": cdc,
                    }
                    da_refs = []
                    for da in do_info.das:
                        fc = da.fc or self._DA_NAME_FC_MAP.get(da.name, "")
                        btype, da_type_ref = self._resolve_btype(da, do_info.name, cdc, ln_type_id)
                        da_ref = {
                            "@name": da.name,
                            "@fc": fc,
                            "@bType": btype,
                        }
                        if da_type_ref:
                            da_ref["@type"] = da_type_ref
                        # 枚举类型记录
                        if btype == "Enum" and da_type_ref:
                            if da_type_ref not in enum_types:
                                enum_types[da_type_ref] = [{"@ord": "0", "#text": "unknown"}]
                        da_refs.append(da_ref)

                        # 子 DA -> DAType
                        if da.sub_das:
                            da_type_id = f"{ln_type_id}.{do_info.name}.{da.name}"
                            bda_refs = []
                            for bda in da.sub_das:
                                bda_btype = self._IEC_TYPE_TO_BTYPE.get(bda.iec_type, "Struct")
                                bda_ref = {"@name": bda.name, "@bType": bda_btype}
                                if bda.iec_type == IEC_TYPE_INTEGER and bda.name == "orCat":
                                    bda_ref["@bType"] = "Enum"
                                    bda_ref["@type"] = "orCategory"
                                bda_refs.append(bda_ref)
                            # 添加 DAType
                            da_type_item = {"@id": da_type_id}
                            if len(bda_refs) > 1:
                                da_type_item["BDA"] = bda_refs
                            else:
                                da_type_item["BDA"] = bda_refs[0]
                            da_types.append(da_type_item)

                    if da_refs:
                        do_type_item["DA"] = da_refs if len(da_refs) > 1 else da_refs[0]
                    do_types.append(do_type_item)

                # LNodeType 添加固定 DO (Mod, Beh, Health, NamPlt)
                for fixed_do in self._get_fixed_dos(ln_class):
                    do_refs.append(fixed_do)

                lnode_type = {
                    "@id": ln_type_id,
                    "@lnClass": ln_class,
                }
                if do_refs:
                    lnode_type["DO"] = do_refs if len(do_refs) > 1 else do_refs[0]
                lnode_types.append(lnode_type)

        # 组装 DataTypeTemplates
        result = {}
        if lnode_types:
            result["LNodeType"] = lnode_types if len(lnode_types) > 1 else lnode_types[0]
        if do_types:
            result["DOType"] = do_types if len(do_types) > 1 else do_types[0]
        if da_types:
            result["DAType"] = da_types if len(da_types) > 1 else da_types[0]

        # EnumType
        enum_list = []
        for enum_id, vals in enum_types.items():
            enum_item = {"@id": enum_id}
            enum_item["EnumVal"] = vals if len(vals) > 1 else vals[0]
            enum_list.append(enum_item)
        if enum_list:
            result["EnumType"] = enum_list if len(enum_list) > 1 else enum_list[0]

        return result

    def _build_dois(self, ln: LNInfo) -> List[Dict[str, Any]]:
        """构建 DOI 段 (LN 下的 DO 实例化)"""
        doi_list = []
        for do_info in ln.dos:
            doi = {"@name": do_info.name}
            # 为有 dU 描述的 DO 添加 DAI
            dai_list = []
            for da in do_info.das:
                if da.name in ("dU", "du") and da.iec_type == IEC_TYPE_STRING:
                    dai_list.append({"@name": da.name})
            if dai_list:
                doi["DAI"] = dai_list if len(dai_list) > 1 else dai_list[0]
            doi_list.append(doi)
        return doi_list if len(doi_list) > 1 else (doi_list[0] if doi_list else [])

    def _build_datasets(self, datasets: List[DataSetInfo],
                        ld_inst: str, ln: LNInfo) -> Any:
        """构建 DataSet 段"""
        ds_list = []
        for ds in datasets:
            ds_item = {"@name": ds.name}
            fcda_list = []
            for m in ds.members:
                fcda = {
                    "@ldInst": ld_inst,
                    "@prefix": "",
                    "@lnClass": ln.ln_class or "",
                    "@lnInst": self._extract_ln_inst(ln.name),
                    "@doName": m.get("doName", m.get("ref", "").split(".")[-2] if "." in m.get("ref", "") else ""),
                    "@fc": m.get("fc", ""),
                }
                if m.get("da"):
                    fcda["@daName"] = m["da"]
                elif m.get("ref"):
                    parts = m["ref"].split(".")
                    if len(parts) > 2:
                        fcda["@daName"] = ".".join(parts[2:])
                fcda_list.append(fcda)
            if fcda_list:
                ds_item["FCDA"] = fcda_list if len(fcda_list) > 1 else fcda_list[0]
            ds_list.append(ds_item)
        return ds_list if len(ds_list) > 1 else (ds_list[0] if ds_list else [])

    def _build_report_controls(self, rcb_list: List[RCBInfo]) -> Any:
        """构建 ReportControl 段"""
        rcb_items = []
        for rcb in rcb_list:
            buffered = "true" if rcb.rcb_type == "BRCB" else "false"
            rcb_item = {
                "@name": rcb.name,
                "@rptID": rcb.name,
                "@buffered": buffered,
                "@bufTime": "0",
                "@confRev": "1",
                "TrgOps": {"@dchg": "true", "@qchg": "false", "@dupd": "false", "@period": "false"},
                "OptFields": {
                    "@seqNum": "false", "@timeStamp": "false", "@dataSet": "false",
                    "@reasonCode": "false", "@dataRef": "false", "@entryID": "false", "@configRef": "false",
                },
                "RptEnabled": {"@max": "1"},
            }
            rcb_items.append(rcb_item)
        return rcb_items if len(rcb_items) > 1 else (rcb_items[0] if rcb_items else [])

    # ========== SCL 辅助方法 ==========

    def _extract_ld_inst(self, ld_name: str, ied_name: str) -> str:
        """从 LD 名称提取实例名 (去掉 IED 前缀)

        如 "EMS_LD0" -> "LD0" (ied_name="EMS")
        如 "KG_BAMSCTMP01" -> "CTMP01" (ied_name="KG_BAMS")
        """
        if ld_name.startswith(ied_name + "_"):
            return ld_name[len(ied_name) + 1:]
        if ld_name.startswith(ied_name):
            return ld_name[len(ied_name):]
        return ld_name

    def _extract_ln_inst(self, ln_name: str) -> str:
        """从 LN 名称提取实例号

        如 "MMXU1" -> "1", "M0GGIO1" -> "1", "LLN0" -> ""
        """
        if ln_name == "LLN0":
            return ""
        import re
        m = re.search(r'(\d+)$', ln_name)
        return m.group(1) if m else "1"

    def _extract_ln_class_from_name(self, ln_name: str) -> str:
        """从 LN 名称提取 LN 类

        如 "MMXU1" -> "MMXU", "M0GGIO1" -> "GGIO", "LLN0" -> "LLN0"
        """
        if ln_name == "LLN0":
            return "LLN0"
        import re
        # 去掉可能的前缀 (如 M0) 和实例号 (如 1)
        m = re.match(r'^[A-Z]*(\d+)?([A-Z]+)\d*$', ln_name)
        if m:
            return m.group(2)
        # 回退: 去掉末尾数字
        return re.sub(r'\d+$', '', ln_name)

    def _infer_cdc_from_do(self, do_name: str, ln_class: str) -> str:
        """根据 DO 名称和 LN 类推断 CDC (Common Data Class)"""
        # 优先查 _DA_PATTERNS 推断
        from .iec61850_client import _DA_PATTERNS

        if do_name in ("Mod", "Beh", "Health"):
            return "ENC"
        if do_name == "NamPlt":
            return "LPL"
        if do_name == "DNamPlt":
            return "DPL"

        # 基于 LN 类和 DO 前缀推断
        if ln_class in ("MMXU", "MMTR", "MMLN", "MSQI", "MHAN", "MSTA"):
            # 测量 LN -> MV/CMV
            if do_name.startswith("PhV") or do_name.startswith("CV"):
                return "CMV"
            return "MV"
        if ln_class in ("GGIO", "GGIO", "CSWI", "XSWI"):
            if do_name.startswith("DPCSO") or do_name.startswith("SBO"):
                return "DPC"
            if do_name.startswith("SPCSO") or do_name.startswith("Ind"):
                return "SPC"
            if do_name.startswith("AnIn") or do_name.startswith("AnOut"):
                return "MV"
            if do_name.startswith("DInd") or do_name.startswith("BinIn"):
                return "SPS"
            return "SPS"
        if ln_class in ("PTOC", "PDIR", "PVOC", "PIOC", "PSDE"):
            return "ACT"
        if ln_class in ("LLN0",):
            if do_name == "NamPlt":
                return "LPL"
            return "SPS"

        # 回退: 基于 DA 内容推断
        return "MV"

    def _resolve_btype(self, da: DAInfo, do_name: str, cdc: str,
                       ln_type_id: str) -> tuple:
        """推断 DA 的 bType 和 type 引用

        Returns:
            (bType, type_ref) - type_ref 为 None 表示基本类型
        """
        # Quality
        if da.name == "q":
            return ("Quality", None)
        # Timestamp
        if da.name == "t":
            return ("Timestamp", None)
        # ctlModel
        if da.name == "ctlModel":
            return ("Enum", "ctlModel")

        # Struct 类型 DA
        if da.sub_das:
            return ("Struct", f"{ln_type_id}.{do_name}.{da.name}")

        # 基于 iec_type
        btype = self._IEC_TYPE_TO_BTYPE.get(da.iec_type, "Struct")

        # ENC 类型的 stVal/ctlVal 用 Enum
        if do_name in ("Mod", "Beh", "Health") and da.name in ("stVal", "ctlVal"):
            return ("Enum", "Origin")

        return (btype, None)

    def _get_fixed_dos(self, ln_class: str) -> List[Dict[str, Any]]:
        """获取 LN 的固定 DO 引用 (Mod, Beh, Health, NamPlt)"""
        dos = []
        if ln_class != "LLN0":
            dos.append({"@name": "Mod", "@type": f"_ENC_{ln_class}_Mod"})
        dos.append({"@name": "Beh", "@type": f"_ENC_{ln_class}_Beh"})
        dos.append({"@name": "Health", "@type": f"_ENC_{ln_class}_Health"})
        if ln_class == "LLN0":
            dos.append({"@name": "NamPlt", "@type": f"_LPL_{ln_class}_NamPlt"})
        return dos
