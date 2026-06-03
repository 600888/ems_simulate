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

from src.data.controller.db import local_session
from src.data.log import log
from src.data.model.point_yc import PointYc
from src.data.model.point_yk import PointYk
from src.data.model.point_yt import PointYt
from src.data.model.point_yx import PointYx

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

        # 构建兼容的 dict 格式并持久化
        yc_dicts = _points_to_dicts(result.yc_points, "YC")
        yx_dicts = _points_to_dicts(result.yx_points, "YX")
        yk_dicts = _points_to_dicts(result.yk_points, "YK")
        yt_dicts = _points_to_dicts(result.yt_points, "YT")

        self._save_yc(yc_dicts)
        self._save_yx(yx_dicts)
        self._save_yk(yk_dicts)
        self._save_yt(yt_dicts)

        log.info(
            f"ICD导入完成 (SclParser): "
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

    # ===== 数据库持久化 (保持不变) =====

    def _save_yc(self, points: list) -> None:
        """批量保存遥测测点"""
        if not points:
            return
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
                    func_code=0,
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


def _points_to_dicts(points: list, category: str) -> list[dict]:
    """将 SclPointTransformer 的 PointData 转为 IcdPointImporter 兼容的 dict 格式"""
    result = []
    for p in points:
        result.append({
            "code": p.code,
            "name": p.name,
            "reg_addr": p.reg_addr,
            "cdc": p.cdc,
            "da_name": p.da_name,
            "fc": p.fc,
        })
    return result
