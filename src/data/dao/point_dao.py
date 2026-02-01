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


def _format_reg_addr(addr: str) -> str:
    """将寄存器地址格式化为 0x 格式
    
    支持输入格式:
    - 纯数字: "0", "100" -> "0x0000", "0x0064"
    - 十六进制: "0x10", "0x0100" -> 保持原样或补齐
    
    Returns:
        格式化后的地址，如 "0x0000"
    """
    addr = str(addr).strip()
    
    if addr.startswith("0x") or addr.startswith("0X"):
        # 已经是十六进制格式，补齐到4位
        hex_digits = addr[2:]
        if len(hex_digits) < 4:
            hex_digits = hex_digits.zfill(4)
        return "0x" + hex_digits.upper()
    else:
        # 纯数字，转换为十六进制
        try:
            decimal_value = int(addr)
            return "0x" + format(decimal_value, '04X')
        except ValueError:
            # 无法解析，原样返回（让后续验证处理）
            return addr


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

    @classmethod
    def delete_points_by_channel(cls, channel_id: int) -> int:
        """删除通道下的所有测点（用于重新导入前清理）
        
        Args:
            channel_id: 通道ID
            
        Returns:
            删除的总测点数
        """
        try:
            total_deleted = 0
            with local_session() as session:
                with session.begin():
                    for model in [PointYc, PointYx, PointYk, PointYt]:
                        deleted = session.query(model).where(
                            model.channel_id == channel_id
                        ).delete()
                        total_deleted += deleted
            log.info(f"已删除通道 {channel_id} 的 {total_deleted} 个测点")
            return total_deleted
        except Exception as e:
            log.error(f"删除通道测点失败: {str(e)}")
            raise e

    # ===== 动态创建测点 =====
    @classmethod
    def create_yc(cls, channel_id: int, point_data: dict) -> PointYcDict:
        """创建遥测点"""
        try:
            with local_session() as session:
                with session.begin():
                    point = PointYc(
                        channel_id=channel_id,
                        code=point_data["code"],
                        name=point_data["name"],
                        rtu_addr=point_data.get("rtu_addr", 1),
                        reg_addr=_format_reg_addr(point_data["reg_addr"]),
                        func_code=point_data.get("func_code", 3),
                        decode_code=point_data.get("decode_code", "0x41"),
                        mul_coe=point_data.get("mul_coe", 1.0),
                        add_coe=point_data.get("add_coe", 0.0),
                        max_limit=point_data.get("max_limit", 9999999),
                        min_limit=point_data.get("min_limit", -9999999),
                        enable=True
                    )
                    session.add(point)
                    session.flush()
                    return point.to_dict()
        except Exception as e:
            log.error(f"创建遥测点失败: {str(e)}")
            raise e

    @classmethod
    def create_yx(cls, channel_id: int, point_data: dict) -> PointYxDict:
        """创建遥信点"""
        try:
            with local_session() as session:
                with session.begin():
                    point = PointYx(
                        channel_id=channel_id,
                        code=point_data["code"],
                        name=point_data["name"],
                        rtu_addr=point_data.get("rtu_addr", 1),
                        reg_addr=_format_reg_addr(point_data["reg_addr"]),
                        func_code=point_data.get("func_code", 2),
                        decode_code=point_data.get("decode_code", "0x10"),
                        enable=True
                    )
                    session.add(point)
                    session.flush()
                    return point.to_dict()
        except Exception as e:
            log.error(f"创建遥信点失败: {str(e)}")
            raise e

    @classmethod
    def create_yk(cls, channel_id: int, point_data: dict) -> PointYkDict:
        """创建遥控点"""
        try:
            with local_session() as session:
                with session.begin():
                    point = PointYk(
                        channel_id=channel_id,
                        code=point_data["code"],
                        name=point_data["name"],
                        rtu_addr=point_data.get("rtu_addr", 1),
                        reg_addr=_format_reg_addr(point_data["reg_addr"]),
                        func_code=point_data.get("func_code", 5),
                        decode_code=point_data.get("decode_code", "0x10"),
                        enable=True
                    )
                    session.add(point)
                    session.flush()
                    return point.to_dict()
        except Exception as e:
            log.error(f"创建遥控点失败: {str(e)}")
            raise e

    @classmethod
    def create_yt(cls, channel_id: int, point_data: dict) -> PointYtDict:
        """创建遥调点"""
        try:
            with local_session() as session:
                with session.begin():
                    point = PointYt(
                        channel_id=channel_id,
                        code=point_data["code"],
                        name=point_data["name"],
                        rtu_addr=point_data.get("rtu_addr", 1),
                        reg_addr=_format_reg_addr(point_data["reg_addr"]),
                        func_code=point_data.get("func_code", 6),
                        decode_code=point_data.get("decode_code", "0x41"),
                        mul_coe=point_data.get("mul_coe", 1.0),
                        add_coe=point_data.get("add_coe", 0.0),
                        enable=True
                    )
                    session.add(point)
                    session.flush()
                    return point.to_dict()
        except Exception as e:
            log.error(f"创建遥调点失败: {str(e)}")
            raise e

    @classmethod
    def create_point(cls, channel_id: int, frame_type: int, point_data: dict) -> dict:
        """根据类型创建测点
        
        Args:
            channel_id: 通道ID
            frame_type: 测点类型 (0=遥测, 1=遥信, 2=遥控, 3=遥调)
            point_data: 测点数据
            
        Returns:
            创建的测点字典
        """
        creators = {
            0: cls.create_yc,
            1: cls.create_yx,
            2: cls.create_yk,
            3: cls.create_yt
        }
        creator = creators.get(frame_type)
        if not creator:
            raise ValueError(f"无效的测点类型: {frame_type}")
        result = creator(channel_id, point_data)
        result["frame_type"] = frame_type
        return result

    @classmethod
    def create_points_batch(cls, channel_id: int, frame_type: int, points_data_list: List[dict]) -> List[dict]:
        """批量创建测点"""
        try:
            points_to_add = []
            with local_session() as session:
                with session.begin():
                    for point_data in points_data_list:
                        if frame_type == 0:  # 遥测
                            point = PointYc(
                                channel_id=channel_id,
                                code=point_data["code"],
                                name=point_data["name"],
                                rtu_addr=point_data.get("rtu_addr", 1),
                                reg_addr=_format_reg_addr(point_data["reg_addr"]),
                                func_code=point_data.get("func_code", 3),
                                decode_code=point_data.get("decode_code", "0x41"),
                                mul_coe=point_data.get("mul_coe", 1.0),
                                add_coe=point_data.get("add_coe", 0.0),
                                max_limit=point_data.get("max_limit", 9999999),
                                min_limit=point_data.get("min_limit", -9999999),
                                enable=True
                            )
                        elif frame_type == 1:  # 遥信
                            point = PointYx(
                                channel_id=channel_id,
                                code=point_data["code"],
                                name=point_data["name"],
                                rtu_addr=point_data.get("rtu_addr", 1),
                                reg_addr=_format_reg_addr(point_data["reg_addr"]),
                                func_code=point_data.get("func_code", 2),
                                decode_code=point_data.get("decode_code", "0x10"),
                                enable=True
                            )
                        elif frame_type == 2:  # 遥控
                            point = PointYk(
                                channel_id=channel_id,
                                code=point_data["code"],
                                name=point_data["name"],
                                rtu_addr=point_data.get("rtu_addr", 1),
                                reg_addr=_format_reg_addr(point_data["reg_addr"]),
                                func_code=point_data.get("func_code", 5),
                                decode_code=point_data.get("decode_code", "0x10"),
                                enable=True
                            )
                        elif frame_type == 3:  # 遥调
                            point = PointYt(
                                channel_id=channel_id,
                                code=point_data["code"],
                                name=point_data["name"],
                                rtu_addr=point_data.get("rtu_addr", 1),
                                reg_addr=_format_reg_addr(point_data["reg_addr"]),
                                func_code=point_data.get("func_code", 6),
                                decode_code=point_data.get("decode_code", "0x41"),
                                mul_coe=point_data.get("mul_coe", 1.0),
                                add_coe=point_data.get("add_coe", 0.0),
                                enable=True
                            )
                        else:
                            raise ValueError(f"无效的测点类型: {frame_type}")
                        
                        session.add(point)
                        points_to_add.append(point)
                    
                    session.flush()
                    # 转换为字典并添加 frame_type
                    result = []
                    for p in points_to_add:
                        d = p.to_dict()
                        d["frame_type"] = frame_type
                        result.append(d)
                    return result
        except Exception as e:
            log.error(f"批量创建测点失败: {str(e)}")
            raise e

    @classmethod
    def delete_point_by_code(cls, code: str) -> bool:
        """根据编码删除测点
        
        Args:
            code: 测点编码
            
        Returns:
            是否删除成功
        """
        try:
            with local_session() as session:
                with session.begin():
                    for model in [PointYc, PointYx, PointYk, PointYt]:
                        deleted = session.query(model).where(model.code == code).delete()
                        if deleted > 0:
                            log.info(f"已删除测点: {code}")
                            return True
                    log.warning(f"未找到测点: {code}")
                    return False
        except Exception as e:
            log.error(f"删除测点失败: {str(e)}")
            raise e
