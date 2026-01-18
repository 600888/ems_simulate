"""
遥调服务模块 (Yt)
frame_type = 3
"""

from typing import List
from src.data.dao.point_dao import PointDao
from src.enums.modbus_def import ProtocolType
from src.enums.point_data import Yt
from src.tools.transform import decimal_to_hex, process_hex_address, transform


class YtService:
    """遥调服务类"""

    def __init__(self):
        pass

    @classmethod
    def get_list(cls, channel_id: int, protocol_type: ProtocolType) -> List[Yt]:
        """获取遥调点列表

        Args:
            channel_id: 通道ID
            protocol_type: 协议类型

        Returns:
            遥调点列表
        """
        try:
            result = PointDao.get_yt_list(channel_id)
            point_list: List[Yt] = []

            for item in result:
                point = cls._create_point(item, protocol_type)
                if point:
                    point_list.append(point)

            return point_list
        except Exception as e:
            print(f"获取遥调列表失败: {e}")
            raise e

    @classmethod
    def get_all(cls, protocol_type: ProtocolType) -> List[Yt]:
        """获取所有遥调点"""
        try:
            result = PointDao.get_all_yt()
            point_list: List[Yt] = []

            for item in result:
                point = cls._create_point(item, protocol_type)
                if point:
                    point_list.append(point)

            return point_list
        except Exception as e:
            print(f"获取遥调列表失败: {e}")
            raise e

    @classmethod
    def _create_point(cls, item: dict, protocol_type: ProtocolType) -> Yt | None:
        """创建遥调点对象"""
        if protocol_type in [
            ProtocolType.ModbusTcp,
            ProtocolType.ModbusRtu,
            ProtocolType.ModbusRtuOverTcp,
        ]:
            return Yt(
                rtu_addr=item["rtu_addr"],
                address=process_hex_address(item["reg_addr"]),
                func_code=int(item["func_code"]) if item.get("func_code") else 6,
                name=item["name"],
                code=item["code"],
                value=0,
                max_value_limit=item["max_limit"],
                min_value_limit=item["min_limit"],
                add_coe=item["add_coe"],
                mul_coe=item["mul_coe"],
                frame_type=3,
                decode=item["decode_code"] if item.get("decode_code") else "0x41",
            )

        elif protocol_type in [ProtocolType.Iec104Server, ProtocolType.Iec104Client]:
            address = decimal_to_hex(int(item["reg_addr"]))
            return Yt(
                rtu_addr=1,
                address=address,
                name=item["name"],
                code=item["code"],
                value=0,
                max_value_limit=item["max_limit"],
                min_value_limit=item["min_limit"],
                add_coe=item["add_coe"],
                mul_coe=item["mul_coe"],
                frame_type=3,
            )

        elif protocol_type in [ProtocolType.Dlt645Server, ProtocolType.Dlt645Client]:
            return Yt(
                rtu_addr=1,
                address=transform(process_hex_address(item["reg_addr"])),
                func_code=int(item["func_code"]) if item.get("func_code") else 6,
                name=item["name"],
                code=item["code"],
                value=0,
                max_value_limit=item["max_limit"],
                min_value_limit=item["min_limit"],
                add_coe=item["add_coe"],
                mul_coe=item["mul_coe"],
                frame_type=3,
            )

        return None
