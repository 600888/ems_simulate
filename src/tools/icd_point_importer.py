"""
ICD 文件解析导入模块
解析 IEC 61850 ICD/SCD/CID 文件，将数据模型映射为系统测点（遥测/遥信/遥控/遥调）

ICD 文件遵循 IEC 61850 SCL (Substation Configuration Language) 的 XML Schema，
主要结构:
  <SCL>
    <IED>
      <AccessPoint>
        <Server>
          <LDevice inst="...">
            <LN lnClass="..." inst="..." lnType="...">
              <DOI name="..."> ...
    <DataTypeTemplates>
      <LNodeType id="..." lnClass="...">
        <DO name="..." type="..."/>
      <DOType id="..." cdc="...">
        <DA name="..." fc="..." bType="..."/>
        <SDO name="..." type="..."/>

分类策略（基于 CDC 和 FC）:
  - CDC=MV/CMV/SAV + FC=MX  → 遥测 (Yc)，数据属性路径 mag.f / cVal.mag.f
  - CDC=SPS/DPS/INS + FC=ST → 遥信 (Yx)，数据属性路径 stVal
  - CDC=SPC/DPC + FC=CO     → 遥控 (Yk)，数据属性路径 ctlVal / Oper.ctlVal
  - CDC=APC/INC + FC=CO     → 遥调 (Yt)，数据属性路径 Oper.ctlVal / setVal
"""

import os
from typing import Dict, List, Optional, Tuple
import xml.etree.ElementTree as ET

from src.data.controller.db import local_session
from src.data.log import log
from src.data.model.point_yc import PointYc
from src.data.model.point_yk import PointYk
from src.data.model.point_yt import PointYt
from src.data.model.point_yx import PointYx

# IEC 61850 SCL 命名空间
SCL_NS = "http://www.iec.ch/61850/2003/SCL"


# CDC 到测点类型的映射
CDC_YC = {"MV", "CMV", "SAV", "WYE", "DEL", "SEQ", "HMV"}  # 遥测
CDC_YX = {"SPS", "DPS", "INS", "ENS", "ENC", "ACT", "ACD", "SEC", "BCR"}  # 遥信 (ENC=枚举控制, stVal为整型)
CDC_YK = {"SPC", "DPC"}  # 遥控
CDC_YT = {"APC", "INC", "ASG", "ING", "SPG", "BAC"}  # 遥调


def _ns(tag: str) -> str:
    """给 tag 加 SCL 命名空间前缀"""
    return f"{{{SCL_NS}}}{tag}"


class IcdPointImporter:
    """ICD 文件解析导入器"""

    def __init__(self, channel_id: int):
        self.channel_id = channel_id
        self.yc_count = 0
        self.yx_count = 0
        self.yk_count = 0
        self.yt_count = 0
        self._ied_name: str | None = None  # ICD 文件中的 IED 名称

        # DataTypeTemplates 缓存
        self._ln_types: dict[str, ET.Element] = {}  # id -> LNodeType
        self._do_types: dict[str, ET.Element] = {}  # id -> DOType
        self._da_types: dict[str, ET.Element] = {}  # id -> DAType

    def get_ied_name(self) -> str | None:
        """获取从 ICD 文件提取的 IED 名称"""
        return self._ied_name

    def _clear_existing_points(self) -> None:
        """清除该通道已有的测点数据"""
        try:
            with local_session() as session, session.begin():
                session.query(PointYc).where(PointYc.channel_id == self.channel_id).delete()
                session.query(PointYx).where(PointYx.channel_id == self.channel_id).delete()
                session.query(PointYk).where(PointYk.channel_id == self.channel_id).delete()
                session.query(PointYt).where(PointYt.channel_id == self.channel_id).delete()
            log.info(f"已清除通道 {self.channel_id} 的旧测点数据")
        except Exception as e:
            log.error(f"清除旧测点数据失败: {e}")
            raise e

    def import_from_icd(self, file_path: str) -> tuple[int, int, int, int]:
        """从 ICD/SCD/CID 文件导入测点

        Args:
            file_path: ICD 文件路径

        Returns:
            (yc_count, yx_count, yk_count, yt_count) 各类型导入数量
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        # 清除旧数据
        self._clear_existing_points()

        # 解析 XML
        tree = ET.parse(file_path)
        root = tree.getroot()

        # 检测是否有命名空间
        self._detect_namespace(root)

        # 构建 DataTypeTemplates 缓存
        self._build_type_cache(root)

        # 收集所有测点
        yc_points = []
        yx_points = []
        yk_points = []
        yt_points = []

        # 遍历所有 IED -> Server -> LDevice -> LN
        for ied in root.iter(self._tag("IED")):
            ied_name = ied.get("name", "IED")
            if self._ied_name is None:
                self._ied_name = ied_name  # 保存第一个 IED 名称

            for ap in ied.iter(self._tag("AccessPoint")):
                server = ap.find(self._tag("Server"))
                if server is None:
                    continue

                for ld in server.iter(self._tag("LDevice")):
                    ld_inst = ld.get("inst", "LD0")

                    # 处理 LN0 和 LN
                    for ln_elem in self._get_logical_nodes(ld):
                        ln_class = ln_elem.get("lnClass", "")
                        ln_inst = ln_elem.get("inst", "")
                        ln_prefix = ln_elem.get("prefix", "")
                        ln_type = ln_elem.get("lnType", "")

                        # 构造 LN 名称: prefix + lnClass + inst
                        if ln_elem.tag == self._tag("LN0") or ln_elem.tag == "LN0":
                            ln_name = "LLN0"
                        else:
                            ln_name = f"{ln_prefix}{ln_class}{ln_inst}"

                        # 从 DataTypeTemplates 获取 LN 类型定义
                        ln_type_def = self._ln_types.get(ln_type)
                        if ln_type_def is None:
                            continue

                        # 遍历 DO
                        for do_elem in ln_type_def.findall(self._tag("DO")):
                            do_name = do_elem.get("name", "")
                            do_type_id = do_elem.get("type", "")

                            do_type_def = self._do_types.get(do_type_id)
                            if do_type_def is None:
                                continue

                            cdc = do_type_def.get("cdc", "")
                            ref_prefix = f"{ld_inst}/{ln_name}.{do_name}"

                            # 获取 DO 的描述 (优先从 IED 部分 DOI/DAI/Val 获取 dU 实际值)
                            do_desc = self._get_do_desc(do_elem, do_type_def, do_name, ln_elem)

                            # 收集该 DO 下的所有 DA (包括主值 DA 和元数据 DA)
                            all_das = self._collect_all_das(do_type_def, cdc)

                            # 根据 CDC 分类, 确定主值 DA
                            if cdc in CDC_YC:
                                main_da_ref = self._get_value_ref(do_type_def, cdc, "MX")
                                if main_da_ref:
                                    yc_points.append(
                                        {
                                            "code": f"{ld_inst}_{ln_name}_{do_name}_{main_da_ref.replace('.', '_')}",
                                            "name": do_desc,
                                            "reg_addr": f"{ref_prefix}.{main_da_ref}",
                                            "cdc": cdc,
                                            "da_name": main_da_ref,
                                            "fc": "MX",
                                        }
                                    )
                                # 为其他非主值 DA 也创建测点 (q, t, du 等)
                                for da_info in all_das:
                                    da_info["name"]
                                    da_path = da_info["path"]
                                    da_fc = da_info["fc"]
                                    if da_path == main_da_ref:
                                        continue  # 主值已添加
                                    if da_fc in ("MX", "ST", "DC"):
                                        yc_points.append(
                                            {
                                                "code": f"{ld_inst}_{ln_name}_{do_name}_{da_path.replace('.', '_')}",
                                                "name": do_desc,
                                                "reg_addr": f"{ref_prefix}.{da_path}",
                                                "cdc": cdc,
                                                "da_name": da_path,
                                                "fc": da_fc,
                                            }
                                        )

                            elif cdc in CDC_YX:
                                main_da_ref = self._get_value_ref(do_type_def, cdc, "ST")
                                if main_da_ref:
                                    yx_points.append(
                                        {
                                            "code": f"{ld_inst}_{ln_name}_{do_name}_{main_da_ref.replace('.', '_')}",
                                            "name": do_desc,
                                            "reg_addr": f"{ref_prefix}.{main_da_ref}",
                                            "cdc": cdc,
                                            "da_name": main_da_ref,
                                            "fc": "ST",
                                        }
                                    )
                                for da_info in all_das:
                                    da_info["name"]
                                    da_path = da_info["path"]
                                    da_fc = da_info["fc"]
                                    if da_path == main_da_ref:
                                        continue
                                    if da_fc in ("ST", "MX", "DC"):
                                        yx_points.append(
                                            {
                                                "code": f"{ld_inst}_{ln_name}_{do_name}_{da_path.replace('.', '_')}",
                                                "name": do_desc,
                                                "reg_addr": f"{ref_prefix}.{da_path}",
                                                "cdc": cdc,
                                                "da_name": da_path,
                                                "fc": da_fc,
                                            }
                                        )

                            elif cdc in CDC_YK:
                                main_da_ref = self._get_control_ref(do_type_def, cdc)
                                if main_da_ref:
                                    yk_points.append(
                                        {
                                            "code": f"{ld_inst}_{ln_name}_{do_name}_{main_da_ref.replace('.', '_')}",
                                            "name": do_desc,
                                            "reg_addr": f"{ref_prefix}.{main_da_ref}",
                                            "cdc": cdc,
                                            "da_name": main_da_ref,
                                            "fc": "CO",
                                        }
                                    )
                                for da_info in all_das:
                                    da_info["name"]
                                    da_path = da_info["path"]
                                    da_fc = da_info["fc"]
                                    if da_path == main_da_ref:
                                        continue
                                    if da_fc in ("CO", "ST", "DC"):
                                        yk_points.append(
                                            {
                                                "code": f"{ld_inst}_{ln_name}_{do_name}_{da_path.replace('.', '_')}",
                                                "name": do_desc,
                                                "reg_addr": f"{ref_prefix}.{da_path}",
                                                "cdc": cdc,
                                                "da_name": da_path,
                                                "fc": da_fc,
                                            }
                                        )

                            elif cdc in CDC_YT:
                                main_da_ref = self._get_control_ref(do_type_def, cdc)
                                if main_da_ref:
                                    yt_points.append(
                                        {
                                            "code": f"{ld_inst}_{ln_name}_{do_name}_{main_da_ref.replace('.', '_')}",
                                            "name": do_desc,
                                            "reg_addr": f"{ref_prefix}.{main_da_ref}",
                                            "cdc": cdc,
                                            "da_name": main_da_ref,
                                            "fc": "CO",
                                        }
                                    )
                                for da_info in all_das:
                                    da_info["name"]
                                    da_path = da_info["path"]
                                    da_fc = da_info["fc"]
                                    if da_path == main_da_ref:
                                        continue
                                    if da_fc in ("CO", "ST", "DC"):
                                        yt_points.append(
                                            {
                                                "code": f"{ld_inst}_{ln_name}_{do_name}_{da_path.replace('.', '_')}",
                                                "name": do_desc,
                                                "reg_addr": f"{ref_prefix}.{da_path}",
                                                "cdc": cdc,
                                                "da_name": da_path,
                                                "fc": da_fc,
                                            }
                                        )

        # 批量写入数据库
        self._save_yc(yc_points)
        self._save_yx(yx_points)
        self._save_yk(yk_points)
        self._save_yt(yt_points)

        log.info(f"ICD导入完成: 遥测={self.yc_count}, 遥信={self.yx_count}, 遥控={self.yk_count}, 遥调={self.yt_count}")
        return (self.yc_count, self.yx_count, self.yk_count, self.yt_count)

    def preview_from_icd(self, file_path: str) -> tuple[int, int, int, int]:
        """预览 ICD 文件中的测点数量（只解析不保存）

        Args:
            file_path: ICD 文件路径

        Returns:
            (yc_count, yx_count, yk_count, yt_count) 各类型数量
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        # 解析 XML（不执行清除和保存操作）
        tree = ET.parse(file_path)
        root = tree.getroot()
        self._detect_namespace(root)
        self._build_type_cache(root)

        yc_points = []
        yx_points = []
        yk_points = []
        yt_points = []

        # 遍历所有 IED -> Server -> LDevice -> LN（与 import 逻辑一致，但不执行 DB 操作）
        for ied in root.iter(self._tag("IED")):
            for ap in ied.iter(self._tag("AccessPoint")):
                server = ap.find(self._tag("Server"))
                if server is None:
                    continue
                for ld in server.iter(self._tag("LDevice")):
                    ld_inst = ld.get("inst", "LD0")
                    for ln_elem in self._get_logical_nodes(ld):
                        ln_class = ln_elem.get("lnClass", "")
                        ln_inst = ln_elem.get("inst", "")
                        ln_prefix = ln_elem.get("prefix", "")
                        ln_type = ln_elem.get("lnType", "")
                        if ln_elem.tag == self._tag("LN0") or ln_elem.tag == "LN0":
                            ln_name = "LLN0"
                        else:
                            ln_name = f"{ln_prefix}{ln_class}{ln_inst}"
                        ln_type_def = self._ln_types.get(ln_type)
                        if ln_type_def is None:
                            continue
                        for do_elem in ln_type_def.findall(self._tag("DO")):
                            do_name = do_elem.get("name", "")
                            do_type_id = do_elem.get("type", "")
                            do_type_def = self._do_types.get(do_type_id)
                            if do_type_def is None:
                                continue
                            cdc = do_type_def.get("cdc", "")
                            if cdc in CDC_YC:
                                main_da_ref = self._get_value_ref(do_type_def, cdc, "MX")
                                if main_da_ref:
                                    yc_points.append(
                                        {"code": f"{ld_inst}_{ln_name}_{do_name}_{main_da_ref.replace('.', '_')}"}
                                    )
                            elif cdc in CDC_YX:
                                main_da_ref = self._get_value_ref(do_type_def, cdc, "ST")
                                if main_da_ref:
                                    yx_points.append(
                                        {"code": f"{ld_inst}_{ln_name}_{do_name}_{main_da_ref.replace('.', '_')}"}
                                    )
                            elif cdc in CDC_YK:
                                main_da_ref = self._get_control_ref(do_type_def, cdc)
                                if main_da_ref:
                                    yk_points.append(
                                        {"code": f"{ld_inst}_{ln_name}_{do_name}_{main_da_ref.replace('.', '_')}"}
                                    )
                            elif cdc in CDC_YT:
                                main_da_ref = self._get_control_ref(do_type_def, cdc)
                                if main_da_ref:
                                    yt_points.append(
                                        {"code": f"{ld_inst}_{ln_name}_{do_name}_{main_da_ref.replace('.', '_')}"}
                                    )

        yc_count = len(yc_points)
        yx_count = len(yx_points)
        yk_count = len(yk_points)
        yt_count = len(yt_points)

        log.info(f"ICD预览: 遥测={yc_count}, 遥信={yx_count}, 遥控={yk_count}, 遥调={yt_count}")
        return (yc_count, yx_count, yk_count, yt_count)

    def _detect_namespace(self, root: ET.Element) -> None:
        """检测 XML 根元素是否使用了 SCL 命名空间"""
        tag = root.tag
        if tag.startswith("{"):
            # 有命名空间
            ns = tag.split("}")[0] + "}"
            self._ns_prefix = ns
        else:
            self._ns_prefix = ""

    def _tag(self, name: str) -> str:
        """根据检测到的命名空间构造完整 tag"""
        if self._ns_prefix:
            return f"{self._ns_prefix}{name}"
        return name

    def _build_type_cache(self, root: ET.Element) -> None:
        """构建 DataTypeTemplates 缓存"""
        dtt = root.find(self._tag("DataTypeTemplates"))
        if dtt is None:
            log.warning("ICD 文件中未找到 DataTypeTemplates 节")
            return

        for lt in dtt.findall(self._tag("LNodeType")):
            lt_id = lt.get("id", "")
            if lt_id:
                self._ln_types[lt_id] = lt

        for dt in dtt.findall(self._tag("DOType")):
            dt_id = dt.get("id", "")
            if dt_id:
                self._do_types[dt_id] = dt

        for dat in dtt.findall(self._tag("DAType")):
            dat_id = dat.get("id", "")
            if dat_id:
                self._da_types[dat_id] = dat

        log.info(
            f"DataTypeTemplates 解析完成: "
            f"LNodeType={len(self._ln_types)}, "
            f"DOType={len(self._do_types)}, "
            f"DAType={len(self._da_types)}"
        )

    def _get_logical_nodes(self, ld: ET.Element) -> list:
        """获取 LDevice 下所有逻辑节点 (LN0 + LN)"""
        nodes = []
        ln0 = ld.find(self._tag("LN0"))
        if ln0 is not None:
            nodes.append(ln0)
        nodes.extend(ld.findall(self._tag("LN")))
        return nodes

    def _get_du_value_from_doi(self, ln_elem: ET.Element, do_name: str) -> str:
        """从 IED 部分的 DOI/DAI 获取 dU 的实际值

        ICD 文件结构:
          <LN ...>
            <DOI name="AnIn1">
              <DAI name="du">
                <Val>Phase A Current</Val>
              </DAI>
            </DOI>
          </LN>
        """
        for doi in ln_elem.findall(self._tag("DOI")):
            if doi.get("name") == do_name:
                for dai in doi.findall(self._tag("DAI")):
                    if dai.get("name") in ("du", "dU"):
                        val_elem = dai.find(self._tag("Val"))
                        if val_elem is not None and val_elem.text:
                            return val_elem.text.strip()
        return ""

    def _get_do_desc(
        self, do_elem: ET.Element, do_type_def: ET.Element, do_name: str, ln_elem: ET.Element = None
    ) -> str:
        """获取 DO 的描述信息

        优先级: DOI/DAI 中 dU 的 Val → DO 元素 desc → DOType desc →
                du DA 的 <Val> 元素 → du DA 的 desc → DO 名称
        """
        # 最高优先级: 从 IED 部分的 DOI/DAI 获取 dU 实际值
        if ln_elem is not None:
            du_val = self._get_du_value_from_doi(ln_elem, do_name)
            if du_val:
                return du_val

        # 从 DO 元素获取 desc
        desc = do_elem.get("desc", "")
        if not desc:
            # 从 DOType 获取 desc
            desc = do_type_def.get("desc", "")
        if not desc:
            # 从 du DA 获取描述 (<Val> 子元素 > desc 属性 > val 属性)
            for da in do_type_def.findall(self._tag("DA")):
                if da.get("name") in ("dU", "du"):
                    val_elem = da.find(self._tag("Val"))
                    if val_elem is not None and val_elem.text:
                        desc = val_elem.text.strip()
                    if not desc:
                        desc = da.get("desc", "")
                    if not desc:
                        desc = da.get("val", "")
                    break
        if not desc:
            desc = do_name
        return desc

    # DA 名称 -> (完整 DA 路径, FC) 映射 (ICD 中常见元数据 DA)
    _EXTRA_DA_MAP = {
        "q": ("q", "MX"),
        "t": ("t", "MX"),
        "du": ("dU", "DC"),
        "dU": ("dU", "DC"),
        "subEna": ("subEna", "SV"),
        "blkEna": ("blkEna", "BL"),
        "origin": ("origin", "OR"),
        "ctlNum": ("ctlNum", "CO"),
    }

    # 结构体 DA 的子 BDA 展开规则 (DA名 -> 需要展开的 BDA 列表)
    # None 表示展开所有 BDA; 列表表示只展开指定的 BDA
    # 注意: mag/instMag/mxVal 等测量值 DA 不在这里展开，它们的主值路径在 _collect_all_das 中硬编码
    _STRUCT_DA_EXPAND = {
        "q": [],  # Quality: MMS 映射为单值 BitString, 不展开子 BDA
        "t": [],  # Timestamp: MMS 映射为单值 UTC_Time, 不展开子 BDA
        "origin": None,  # Origin: 展开 orIdent, orCat, ...
    }

    # 已知 struct DA 的硬编码 BDA 子节点 (当 ICD 文件中 DAType 缺失时使用)
    _KNOWN_BDA_FALLBACK = {
        "q": [  # Quality
            {"name": "validity", "bType": "Dbpos"},
            {"name": "detailQuality", "bType": "Struct"},  # 展开时会被跳过 (Struct)
            {"name": "source", "bType": "Dbpos"},
            {"name": "operatorBlocked", "bType": "Boolean"},
            {"name": "test", "bType": "Boolean"},
            {"name": "origin", "bType": "Struct"},  # 展开时会被跳过 (Struct)
        ],
        "t": [  # Timestamp
            {"name": "seconds", "bType": "Int32"},
            {"name": "fraction", "bType": "UInt32"},
            {"name": "TimeQuality", "bType": "Struct"},  # 展开时会被跳过 (Struct)
        ],
        "origin": [  # Origin
            {"name": "orCat", "bType": "Dbpos"},
            {"name": "orIdent", "bType": "Octet64"},
        ],
    }

    def _expand_struct_da(self, da_name: str, da_fc: str, da_type_id: str) -> list[dict[str, str]]:
        """展开结构体 DA 的子 BDA

        优先从 ICD 文件的 DAType 定义中获取 BDA 列表;
        若 DAType 不存在, 则使用硬编码的 _KNOWN_BDA_FALLBACK 作为回退。

        Args:
            da_name: DA 名称 (如 "q", "t")
            da_fc: DA 的 FC
            da_type_id: DA 引用的 DAType id

        Returns:
            子 BDA 信息列表, 每个 {"name": "q.validity", "path": "q.validity", "fc": "MX", "bType": "..."}
        """
        # 确定需要展开的 BDA 过滤规则
        expand_filter = self._STRUCT_DA_EXPAND.get(da_name)
        if expand_filter is None and da_name not in self._STRUCT_DA_EXPAND:
            return []

        # 尝试从 ICD 文件的 DAType 中获取 BDA
        if da_type_id and da_type_id in self._da_types:
            da_type = self._da_types[da_type_id]
            result = []
            for bda in da_type.findall(self._tag("BDA")):
                bda_name = bda.get("name", "")
                bda_btype = bda.get("bType", "")
                if not bda_name:
                    continue
                # 如果有过滤列表, 只展开指定的 BDA
                if expand_filter is not None and bda_name not in expand_filter:
                    continue
                # 跳过嵌套结构体 (如 q 中的 detailQuality 也是 Struct)
                if bda_btype == "Struct":
                    continue
                full_name = f"{da_name}.{bda_name}"
                result.append(
                    {
                        "name": full_name,
                        "path": full_name,
                        "fc": da_fc,
                        "bType": bda_btype,
                    }
                )
            if result:
                return result
            log.warning(f"_expand_struct_da: DA '{da_name}' 的 DAType '{da_type_id}' 中无有效 BDA, 使用硬编码回退")

        # 回退: 使用硬编码的 BDA 列表
        if da_name in self._KNOWN_BDA_FALLBACK:
            if not da_type_id:
                log.info(f"_expand_struct_da: DA '{da_name}' 无 type 属性, 使用硬编码 BDA 回退")
            elif da_type_id not in self._da_types:
                log.info(
                    f"_expand_struct_da: DA '{da_name}' 的 type='{da_type_id}' 不在 _da_types 中, 使用硬编码 BDA 回退"
                )
            result = []
            for bda_info in self._KNOWN_BDA_FALLBACK[da_name]:
                bda_name = bda_info["name"]
                bda_btype = bda_info["bType"]
                # 如果有过滤列表, 只展开指定的 BDA
                if expand_filter is not None and bda_name not in expand_filter:
                    continue
                # 跳过嵌套结构体
                if bda_btype == "Struct":
                    continue
                full_name = f"{da_name}.{bda_name}"
                result.append(
                    {
                        "name": full_name,
                        "path": full_name,
                        "fc": da_fc,
                        "bType": bda_btype,
                    }
                )
            return result

        if not da_type_id:
            log.warning(f"_expand_struct_da: DA '{da_name}' 无 type 属性, 且无硬编码回退")
        elif da_type_id not in self._da_types:
            log.warning(f"_expand_struct_da: DA '{da_name}' 的 type='{da_type_id}' 不在 _da_types 中, 且无硬编码回退")
        return []

    def _collect_all_das(self, do_type: ET.Element, cdc: str) -> list[dict[str, str]]:
        """收集 DOType 下所有 DA (包括主值和元数据)

        Returns:
            DA 信息列表, 如 [{"name": "mag", "path": "mag", "fc": "MX"}, ...]
        """
        result = []
        for da in do_type.findall(self._tag("DA")):
            da_name = da.get("name", "")
            da_fc = da.get("fc", "")
            da_btype = da.get("bType", "")
            da_type_id = da.get("type", "")

            if da_name in self._EXTRA_DA_MAP:
                # _EXTRA_DA_MAP 中的 DA (q, t, du, dU 等)
                da_path, default_fc = self._EXTRA_DA_MAP[da_name]
                da_fc = da_fc or default_fc
                # 结构体 DA: 展开子 BDA
                if da_btype == "Struct" and da_name in self._STRUCT_DA_EXPAND:
                    result.append(
                        {
                            "name": da_name,
                            "path": da_path,
                            "fc": da_fc,
                            "bType": da_btype,
                        }
                    )
                    expanded = self._expand_struct_da(da_name, da_fc, da_type_id)
                    result.extend(expanded)
                else:
                    result.append(
                        {
                            "name": da_name,
                            "path": da_path,
                            "fc": da_fc,
                            "bType": da_btype,
                        }
                    )
            elif da_name in ("mag", "cVal", "instMag", "mxVal", "fCVal"):
                # 测量值类 DA - 使用硬编码主值路径 (不展开为 struct DA)
                da_fc = da_fc or "MX"
                if da_name == "mag":
                    da_path = "mag.f"
                elif da_name == "cVal":
                    da_path = "cVal.mag.f"
                elif da_name == "instMag":
                    da_path = "instMag.f"
                elif da_name == "mxVal":
                    da_path = "mxVal.f"
                elif da_name == "fCVal":
                    da_path = "fCVal.mag.f"
                else:
                    da_path = da_name
                result.append(
                    {
                        "name": da_name,
                        "path": da_path,
                        "fc": da_fc,
                        "bType": da_btype,
                    }
                )
            elif da_name in ("stVal", "ctlVal", "setVal", "wVal"):
                da_path = da_name
                result.append(
                    {
                        "name": da_name,
                        "path": da_path,
                        "fc": da_fc,
                        "bType": da_btype,
                    }
                )
            elif da_name in ("Oper", "SBOw", "Cancel", "SBO"):
                if da_name == "Oper":
                    da_path = "Oper.ctlVal"
                    da_fc = da_fc or "CO"
                elif da_name == "SBOw":
                    da_path = "SBOw.ctlVal"
                    da_fc = da_fc or "CO"
                elif da_name == "Cancel":
                    da_path = "Cancel.ctlVal"
                    da_fc = da_fc or "CO"
                else:
                    da_path = da_name
                result.append(
                    {
                        "name": da_name,
                        "path": da_path,
                        "fc": da_fc,
                        "bType": da_btype,
                    }
                )
            else:
                # 其他 DA (如 pixTyp, frVal 等), 使用名称作为路径
                da_path = da_name
                # 结构体 DA: 展开子 BDA
                if da_btype == "Struct":
                    result.append(
                        {
                            "name": da_name,
                            "path": da_path,
                            "fc": da_fc,
                            "bType": da_btype,
                        }
                    )
                    expanded = self._expand_struct_da(da_name, da_fc, da_type_id)
                    result.extend(expanded)
                else:
                    result.append(
                        {
                            "name": da_name,
                            "path": da_path,
                            "fc": da_fc,
                            "bType": da_btype,
                        }
                    )

        return result

    def _get_value_ref(self, do_type: ET.Element, cdc: str, target_fc: str) -> str | None:
        """获取测量/状态类型 DO 的值引用路径

        根据 CDC 类型确定数据属性路径:
        - MV: mag.f (或 mag.i)
        - CMV: cVal.mag.f
        - SPS: stVal
        - DPS: stVal
        - INS/ENS: stVal
        - BCR: actVal
        """
        if cdc == "MV":
            # 查找 mag SDO，然后找 f DA
            return self._find_da_path(do_type, ["mag", "f"], target_fc) or "mag.f"
        elif cdc == "CMV":
            return self._find_da_path(do_type, ["cVal", "mag", "f"], target_fc) or "cVal.mag.f"
        elif cdc == "SAV":
            return self._find_da_path(do_type, ["instMag", "f"], target_fc) or "instMag.f"
        elif cdc in ("SPS", "DPS", "INS", "ENS", "ENC", "ACT", "ACD", "SEC"):
            return "stVal"
        elif cdc == "BCR":
            return "actVal"
        elif cdc in ("WYE", "DEL", "SEQ", "HMV"):
            # 复合 CDC，取第一个可用子 DO
            return self._find_composite_ref(do_type, target_fc)
        return None

    def _get_control_ref(self, do_type: ET.Element, cdc: str) -> str | None:
        """获取控制类型 DO 的控制引用路径

        - SPC/DPC: Oper.ctlVal 或直接 ctlVal
        - APC/INC/BAC: Oper.ctlVal 或 setVal
        """
        # 先查 Oper SDO
        for sdo in do_type.findall(self._tag("SDO")):
            if sdo.get("name") == "Oper":
                return "Oper.ctlVal"

        # 查找直接的 ctlVal DA
        for da in do_type.findall(self._tag("DA")):
            if da.get("name") == "ctlVal":
                return "ctlVal"

        # APC/INC 的 setVal
        if cdc in ("APC", "INC", "ASG", "ING", "SPG"):
            for da in do_type.findall(self._tag("DA")):
                if da.get("name") == "setVal":
                    return "setVal"

        return "ctlVal"  # 默认

    def _find_da_path(self, do_type: ET.Element, path_parts: list, target_fc: str) -> str | None:
        """在 DOType 中递归查找 DA 路径"""
        if not path_parts:
            return None

        name = path_parts[0]

        # 查找 DA
        for da in do_type.findall(self._tag("DA")):
            if da.get("name") == name:
                if len(path_parts) == 1:
                    return name
                # DA 有子类型
                da_type_id = da.get("type", "")
                if da_type_id and da_type_id in self._da_types:
                    sub_result = self._find_bda_path(self._da_types[da_type_id], path_parts[1:])
                    if sub_result:
                        return f"{name}.{sub_result}"

        # 查找 SDO
        for sdo in do_type.findall(self._tag("SDO")):
            if sdo.get("name") == name:
                sdo_type_id = sdo.get("type", "")
                if sdo_type_id and sdo_type_id in self._do_types:
                    sub_result = self._find_da_path(self._do_types[sdo_type_id], path_parts[1:], target_fc)
                    if sub_result:
                        return f"{name}.{sub_result}"

        return None

    def _find_bda_path(self, da_type: ET.Element, path_parts: list) -> str | None:
        """在 DAType 中递归查找 BDA 路径"""
        if not path_parts:
            return None

        name = path_parts[0]
        for bda in da_type.findall(self._tag("BDA")):
            if bda.get("name") == name:
                if len(path_parts) == 1:
                    return name
                bda_type_id = bda.get("type", "")
                if bda_type_id and bda_type_id in self._da_types:
                    sub_result = self._find_bda_path(self._da_types[bda_type_id], path_parts[1:])
                    if sub_result:
                        return f"{name}.{sub_result}"
        return None

    def _find_composite_ref(self, do_type: ET.Element, target_fc: str) -> str | None:
        """为复合 CDC (WYE/DEL 等) 查找第一个可用的 SDO"""
        for sdo in do_type.findall(self._tag("SDO")):
            sdo_name = sdo.get("name", "")
            sdo_type_id = sdo.get("type", "")
            if sdo_type_id in self._do_types:
                sub_type = self._do_types[sdo_type_id]
                sub_cdc = sub_type.get("cdc", "")
                if sub_cdc == "MV":
                    return f"{sdo_name}.mag.f"
        return None

    def _save_yc(self, points: list) -> None:
        """批量保存遥测测点"""
        if not points:
            return
        # 按 (code, channel_id, rtu_addr) 去重，避免 UNIQUE 约束冲突
        seen = set()
        unique_points = []
        for p in points:
            key = (p["code"], self.channel_id, 1)
            if key not in seen:
                seen.add(key)
                unique_points.append(p)
        if len(unique_points) < len(points):
            log.warning(f"遥测测点去重: 原始 {len(points)} 条，去重后 {len(unique_points)} 条")

        with local_session() as session, session.begin():
            for p in unique_points:
                point = PointYc(
                    code=p["code"],
                    name=p["name"],
                    channel_id=self.channel_id,
                    rtu_addr=1,
                    reg_addr=p["reg_addr"],
                    func_code=0,  # IEC 61850 不需要功能码
                    decode_code="",
                    mul_coe=1.0,
                    add_coe=0.0,
                    max_limit=999999.0,
                    min_limit=-999999.0,
                    fc=p.get("fc"),
                )
                session.add(point)
                self.yc_count += 1

    def _save_yx(self, points: list) -> None:
        """批量保存遥信测点"""
        if not points:
            return
        # 按 (code, channel_id, rtu_addr) 去重，避免 UNIQUE 约束冲突
        seen = set()
        unique_points = []
        for p in points:
            key = (p["code"], self.channel_id, 1)
            if key not in seen:
                seen.add(key)
                unique_points.append(p)
        if len(unique_points) < len(points):
            log.warning(f"遥信测点去重: 原始 {len(points)} 条，去重后 {len(unique_points)} 条")

        with local_session() as session, session.begin():
            for p in unique_points:
                point = PointYx(
                    code=p["code"],
                    name=p["name"],
                    channel_id=self.channel_id,
                    rtu_addr=1,
                    reg_addr=p["reg_addr"],
                    func_code=0,
                    decode_code="",
                    bit=None,
                    reverse=False,
                    fc=p.get("fc"),
                )
                session.add(point)
                self.yx_count += 1

    def _save_yk(self, points: list) -> None:
        """批量保存遥控测点"""
        if not points:
            return
        # 按 (code, channel_id, rtu_addr) 去重，避免 UNIQUE 约束冲突
        seen = set()
        unique_points = []
        for p in points:
            key = (p["code"], self.channel_id, 1)
            if key not in seen:
                seen.add(key)
                unique_points.append(p)
        if len(unique_points) < len(points):
            log.warning(f"遥控测点去重: 原始 {len(points)} 条，去重后 {len(unique_points)} 条")

        with local_session() as session, session.begin():
            for p in unique_points:
                point = PointYk(
                    code=p["code"],
                    name=p["name"],
                    channel_id=self.channel_id,
                    rtu_addr=1,
                    reg_addr=p["reg_addr"],
                    func_code=0,
                    decode_code="",
                    bit=None,
                    command_type=0,
                    fc=p.get("fc"),
                )
                session.add(point)
                self.yk_count += 1

    def _save_yt(self, points: list) -> None:
        """批量保存遥调测点"""
        if not points:
            return
        # 按 (code, channel_id, rtu_addr) 去重，避免 UNIQUE 约束冲突
        seen = set()
        unique_points = []
        for p in points:
            key = (p["code"], self.channel_id, 1)
            if key not in seen:
                seen.add(key)
                unique_points.append(p)
        if len(unique_points) < len(points):
            log.warning(f"遥调测点去重: 原始 {len(points)} 条，去重后 {len(unique_points)} 条")

        with local_session() as session, session.begin():
            for p in unique_points:
                point = PointYt(
                    code=p["code"],
                    name=p["name"],
                    channel_id=self.channel_id,
                    rtu_addr=1,
                    reg_addr=p["reg_addr"],
                    func_code=0,
                    decode_code="",
                    mul_coe=1.0,
                    add_coe=0.0,
                    max_limit=999999.0,
                    min_limit=-999999.0,
                    fc=p.get("fc"),
                )
                session.add(point)
                self.yt_count += 1
