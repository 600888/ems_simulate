from typing import List
from pymysql import DatabaseError
from src.data.model.point import ModbusPoint, ModbusPointDict
from src.data.model.dlt645_point import DLT645Point, DLT645PointDict
from src.data.log import log
from src.data.controller.db import local_session


class PointDao:
    def __init__(self):
        pass

    @classmethod
    def get_point_list(
        cls, grp_code: str, frame_type: List[int]
    ) -> List[ModbusPointDict]:
        """
        获取测点列表

        Args:
            grp_code: 组代码
            frame_type: 帧类型列表，用于筛选特定类型的测点
        """
        try:
            with local_session() as session:
                with session.begin():
                    query = session.query(ModbusPoint).where(
                        ModbusPoint.grp_code == grp_code,
                        ModbusPoint.frame_type.in_(frame_type) if frame_type else True,
                    )
                    result = query.all()
                    return [item.to_dict() for item in result]
        except DatabaseError as e:
            log.error(f"通道获取失败: {str(e)}")
            raise e
        except Exception as e:
            log.critical(f"系统异常: {str(e)}")
            raise e
        return []

    @classmethod
    def get_dlt645_point_list(
        cls, grp_code: str, frame_type: List[int]
    ) -> List[DLT645PointDict]:
        """
        获取DLT645测点列表

        Args:
            grp_code: 组代码
        """
        try:
            with local_session() as session:
                with session.begin():
                    query = session.query(DLT645Point).where(
                        DLT645Point.grp_code == grp_code,
                        DLT645Point.frame_type.in_(frame_type) if frame_type else True,
                    )
                    result = query.all()
                    return [item.to_dict() for item in result]
        except DatabaseError as e:
            log.error(f"通道获取失败: {str(e)}")
            raise e
        except Exception as e:
            log.critical(f"系统异常: {str(e)}")
            raise e
        return []

    @classmethod
    def get_rtu_addr_list(cls, grp_code: str) -> list:
        """
        获取测点列表（去重后的rtu_addr列表）

        Args:
            grp_code: 组代码
        """
        try:
            with local_session() as session:
                with session.begin():
                    # 使用distinct()方法获取不重复的rtu_addr
                    query = (
                        session.query(ModbusPoint.rtu_addr)
                        .where(ModbusPoint.grp_code == grp_code)
                        .distinct()
                    )
                    result = query.all()
                    # 提取标量值并排序
                    return sorted([item[0] for item in result if item[0] is not None])
        except DatabaseError as e:
            log.error(f"从机列表获取失败: {str(e)}")
            raise e
        except Exception as e:
            log.critical(f"系统异常: {str(e)}")
            raise e

    @classmethod
    def update_point_limit(
        cls, grp_code, code, min_value_limit, max_value_limit
    ) -> bool:
        try:
            with local_session() as session:
                with session.begin():
                    query = session.query(ModbusPoint).where(
                        ModbusPoint.grp_code == grp_code, ModbusPoint.code == code
                    )
                    result = query.first()
                    if result:
                        result.min_limit = min_value_limit
                        result.max_limit = max_value_limit
                        log.info(
                            f"更新测点 {grp_code}/{code} 的上下限值为 {min_value_limit} - {max_value_limit}"
                        )
                        return True
                    else:
                        log.warning(f"未找到测点 {grp_code}/{code}")
                        return False
        except DatabaseError as e:
            log.error(f"测点更新失败: {str(e)}")
            raise e
        except Exception as e:
            log.critical(f"系统异常: {str(e)}")
            raise e
