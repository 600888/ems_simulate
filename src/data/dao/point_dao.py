"""
测点数据访问层
提供四类测点的 CRUD 操作，通过 channel_id 查询
"""

from typing import List, Optional, Union

from src.data.model.point_yc import PointYc, PointYcDict
from src.data.model.point_yx import PointYx, PointYxDict
from src.data.model.point_yk import PointYk, PointYkDict
from src.data.model.point_yt import PointYt, PointYtDict
from src.data.log import log
from src.data.controller.db import local_session


class PointDao:
    """测点数据访问对象"""

    # ===== 遥测 (Yc) =====
    @classmethod
    def get_yc_list(cls, channel_id: int) -> List[PointYcDict]:
        """获取遥测点列表"""
        try:
            with local_session() as session:
                with session.begin():
                    result = (
                        session.query(PointYc)
                        .where(PointYc.channel_id == channel_id, PointYc.enable == True)
                        .all()
                    )
                    return [item.to_dict() for item in result]
        except Exception as e:
            log.error(f"获取遥测点列表失败: {str(e)}")
            raise e

    @classmethod
    def get_all_yc(cls) -> List[PointYcDict]:
        """获取所有遥测点"""
        try:
            with local_session() as session:
                with session.begin():
                    result = session.query(PointYc).where(PointYc.enable == True).all()
                    return [item.to_dict() for item in result]
        except Exception as e:
            log.error(f"获取遥测点列表失败: {str(e)}")
            raise e

    # ===== 遥信 (Yx) =====
    @classmethod
    def get_yx_list(cls, channel_id: int) -> List[PointYxDict]:
        """获取遥信点列表"""
        try:
            with local_session() as session:
                with session.begin():
                    result = (
                        session.query(PointYx)
                        .where(PointYx.channel_id == channel_id, PointYx.enable == True)
                        .all()
                    )
                    return [item.to_dict() for item in result]
        except Exception as e:
            log.error(f"获取遥信点列表失败: {str(e)}")
            raise e

    @classmethod
    def get_all_yx(cls) -> List[PointYxDict]:
        """获取所有遥信点"""
        try:
            with local_session() as session:
                with session.begin():
                    result = session.query(PointYx).where(PointYx.enable == True).all()
                    return [item.to_dict() for item in result]
        except Exception as e:
            log.error(f"获取遥信点列表失败: {str(e)}")
            raise e

    # ===== 遥控 (Yk) =====
    @classmethod
    def get_yk_list(cls, channel_id: int) -> List[PointYkDict]:
        """获取遥控点列表"""
        try:
            with local_session() as session:
                with session.begin():
                    result = (
                        session.query(PointYk)
                        .where(PointYk.channel_id == channel_id, PointYk.enable == True)
                        .all()
                    )
                    return [item.to_dict() for item in result]
        except Exception as e:
            log.error(f"获取遥控点列表失败: {str(e)}")
            raise e

    @classmethod
    def get_all_yk(cls) -> List[PointYkDict]:
        """获取所有遥控点"""
        try:
            with local_session() as session:
                with session.begin():
                    result = session.query(PointYk).where(PointYk.enable == True).all()
                    return [item.to_dict() for item in result]
        except Exception as e:
            log.error(f"获取遥控点列表失败: {str(e)}")
            raise e

    # ===== 遥调 (Yt) =====
    @classmethod
    def get_yt_list(cls, channel_id: int) -> List[PointYtDict]:
        """获取遥调点列表"""
        try:
            with local_session() as session:
                with session.begin():
                    result = (
                        session.query(PointYt)
                        .where(PointYt.channel_id == channel_id, PointYt.enable == True)
                        .all()
                    )
                    return [item.to_dict() for item in result]
        except Exception as e:
            log.error(f"获取遥调点列表失败: {str(e)}")
            raise e

    @classmethod
    def get_all_yt(cls) -> List[PointYtDict]:
        """获取所有遥调点"""
        try:
            with local_session() as session:
                with session.begin():
                    result = session.query(PointYt).where(PointYt.enable == True).all()
                    return [item.to_dict() for item in result]
        except Exception as e:
            log.error(f"获取遥调点列表失败: {str(e)}")
            raise e

    # ===== 通用查询 =====
    @classmethod
    def get_points_by_channel(
        cls, channel_id: int, frame_type: Optional[List[int]] = None
    ) -> List[dict]:
        """根据通道ID获取测点列表"""
        result = []
        if frame_type is None:
            frame_type = [0, 1, 2, 3]

        if 0 in frame_type:
            for item in cls.get_yc_list(channel_id):
                item["frame_type"] = 0
                result.append(item)
        if 1 in frame_type:
            for item in cls.get_yx_list(channel_id):
                item["frame_type"] = 1
                result.append(item)
        if 2 in frame_type:
            for item in cls.get_yk_list(channel_id):
                item["frame_type"] = 2
                result.append(item)
        if 3 in frame_type:
            for item in cls.get_yt_list(channel_id):
                item["frame_type"] = 3
                result.append(item)

        return result

    @classmethod
    def get_rtu_addr_list(cls, channel_id: int) -> List[int]:
        """获取通道下去重后的从机地址列表"""
        try:
            rtu_addrs = set()
            with local_session() as session:
                with session.begin():
                    for model in [PointYc, PointYx, PointYk, PointYt]:
                        result = (
                            session.query(model.rtu_addr)
                            .where(model.channel_id == channel_id)
                            .distinct()
                            .all()
                        )
                        rtu_addrs.update([r[0] for r in result if r[0] is not None])
            return sorted(list(rtu_addrs))
        except Exception as e:
            log.error(f"获取从机地址列表失败: {str(e)}")
            raise e

    @classmethod
    def get_point_by_code(cls, code: str) -> Optional[dict]:
        """根据编码获取测点"""
        try:
            with local_session() as session:
                with session.begin():
                    # 依次在四个表中查找
                    for model, frame_type in [
                        (PointYc, 0),
                        (PointYx, 1),
                        (PointYk, 2),
                        (PointYt, 3),
                    ]:
                        result = session.query(model).where(model.code == code).first()
                        if result:
                            data = result.to_dict()
                            data["frame_type"] = frame_type
                            return data
                    return None
        except Exception as e:
            log.error(f"获取测点失败: {str(e)}")
            raise e

    @classmethod
    def update_point_metadata(
        cls, code: str, metadata: dict
    ) -> bool:
        """更新测点元数据"""
        try:
            with local_session() as session:
                with session.begin():
                    # 依次在四个表中查找
                    for model in [PointYc, PointYx, PointYk, PointYt]:
                        result = session.query(model).where(model.code == code).first()
                        if result:
                            # 如果要修改 code
                            if "code" in metadata and metadata["code"] != code:
                                new_code = metadata["code"]
                                # 检查新编码在所有表中是否唯一
                                for m in [PointYc, PointYx, PointYk, PointYt]:
                                    exists = session.query(m).where(m.code == new_code).first()
                                    if exists:
                                        raise ValueError(f"测点编码 '{new_code}' 已存在")
                                result.code = new_code

                            # 更新允许更新的字段
                            if "name" in metadata and metadata["name"]:
                                result.name = metadata["name"]
                            if "rtu_addr" in metadata and str(metadata["rtu_addr"]) != "":
                                result.rtu_addr = int(metadata["rtu_addr"])
                            if "reg_addr" in metadata and metadata["reg_addr"]:
                                result.reg_addr = metadata["reg_addr"]
                            if "func_code" in metadata and str(metadata["func_code"]) != "":
                                result.func_code = int(metadata["func_code"])
                            if "decode_code" in metadata and metadata["decode_code"]:
                                result.decode_code = metadata["decode_code"]
                            
                            # 遥测和遥调特有字段
                            if model in [PointYc, PointYt]:
                                if "mul_coe" in metadata and str(metadata["mul_coe"]) != "":
                                    result.mul_coe = float(metadata["mul_coe"])
                                if "add_coe" in metadata and str(metadata["add_coe"]) != "":
                                    result.add_coe = float(metadata["add_coe"])
                            
                            return True
                    return False
        except Exception as e:
            log.error(f"更新测点元数据失败: {str(e)}")
            raise e
