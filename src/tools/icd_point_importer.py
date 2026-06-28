"""
ICD 文件解析导入模块
解析 IEC 61850 ICD/SCD/CID 文件，将数据模型映射为系统测点（遥测/遥信/遥控/遥调）

Phase 8 迁移: 内部委托 SclParser + SclPointTransformer，保持外部接口不变。

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
"""

from __future__ import annotations

import os

from src.data.log import log

# CDC 到测点类型的映射 (与 SCL enums 保持一致)
CDC_YC = frozenset({"MV", "CMV", "SAV", "WYE", "DEL", "SEQ", "HMV"})
CDC_YX = frozenset({"SPS", "DPS", "INS", "ENS", "ENC", "ACT", "ACD", "SEC", "BCR"})
CDC_YK = frozenset({"SPC", "DPC"})
CDC_YT = frozenset({"APC", "INC", "ASG", "ING", "SPG", "BAC"})


class IcdPointImporter:
    """ICD 文件解析导入器

    Phase 8 迁移: 内部使用 SclParser + SclPointTransformer 进行解析，
    保持 import_from_icd() / preview_from_icd() / get_ied_name() 接口不变。
    """

    def __init__(self, channel_id: int):
        self.channel_id = channel_id
        self.yc_count = 0
        self.yx_count = 0
        self.yk_count = 0
        self.yt_count = 0
        self._ied_name: str | None = None

    def get_ied_name(self) -> str | None:
        """获取从 ICD 文件提取的 IED 名称"""
        return self._ied_name

    def import_from_icd(self, file_path: str) -> tuple[int, int, int, int]:
        """从 ICD/SCD/CID 文件解析测点（仅解析，不写入数据库）

        v3.0+: 不再将测点写入数据库表，仅解析返回数量。
        IEC61850 测点数据完全由 ICD 模型文件在运行时管理。

        Args:
            file_path: ICD 文件路径

        Returns:
            (yc_count, yx_count, yk_count, yt_count) 各类型数量
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        # 使用 SclParser + SclPointTransformer 解析
        from src.proto.iec61850.plugins.scl.parser.scl_parser import SclParser
        from src.proto.iec61850.plugins.scl.transformer.point_transformer import SclPointTransformer

        parser = SclParser()
        doc = parser.parse_file(file_path)

        # 提取 IED 名称
        ied = doc.first_ied
        self._ied_name = ied.name if ied else ""

        # 转换测点
        transformer = SclPointTransformer(doc)
        result = transformer.transform()

        self.yc_count = len(result.yc_points)
        self.yx_count = len(result.yx_points)
        self.yk_count = len(result.yk_points)
        self.yt_count = len(result.yt_points)

        log.info(
            f"ICD解析完成 (SclParser, 不写入数据库): "
            f"遥测={self.yc_count}, 遥信={self.yx_count}, 遥控={self.yk_count}, 遥调={self.yt_count}"
        )
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

        from src.proto.iec61850.plugins.scl.parser.scl_parser import SclParser
        from src.proto.iec61850.plugins.scl.transformer.point_transformer import SclPointTransformer

        parser = SclParser()
        doc = parser.parse_file(file_path)

        transformer = SclPointTransformer(doc)
        result = transformer.transform()

        yc_count = len(result.yc_points)
        yx_count = len(result.yx_points)
        yk_count = len(result.yk_points)
        yt_count = len(result.yt_points)

        log.info(f"ICD预览 (SclParser): 遥测={yc_count}, 遥信={yx_count}, 遥控={yk_count}, 遥调={yt_count}")
        return (yc_count, yx_count, yk_count, yt_count)
