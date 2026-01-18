"""
遥测服务模块 (Yc)
frame_type = 0
"""

from typing import List
from src.data.dao.point_dao import PointDao
from src.enums.modbus_def import ProtocolType
from src.enums.point_data import Yc
from src.tools.transform import decimal_to_hex, process_hex_address, transform


class YcService:
    """遥测服务类"""

    def __init__(self):
        pass

    @classmethod
    def get_list(cls, channel_id: int, protocol_type: ProtocolType) -> List[Yc]:
        """获取遥测点列表

        Args:
            channel_id: 通道ID
            protocol_type: 协议类型

        Returns:
            遥测点列表
        """
        try:
            result = PointDao.get_yc_list(channel_id)
            point_list: List[Yc] = []

            for item in result:
                point = cls._create_point(item, protocol_type)
                if point:
                    point_list.append(point)

            return point_list
        except Exception as e:
            print(f"获取遥测列表失败: {e}")
            raise e

    @classmethod
    def get_all(cls, protocol_type: ProtocolType) -> List[Yc]:
        """获取所有遥测点"""
        try:
            result = PointDao.get_all_yc()
            point_list: List[Yc] = []

            for item in result:
                point = cls._create_point(item, protocol_type)
                if point:
                    point_list.append(point)

            return point_list
        except Exception as e:
            print(f"获取遥测列表失败: {e}")
            raise e

    @classmethod
    def _create_point(cls, item: dict, protocol_type: ProtocolType) -> Yc | None:
        """创建遥测点对象"""
        if protocol_type in [
            ProtocolType.ModbusTcp,
            ProtocolType.ModbusTcpClient,
            ProtocolType.ModbusRtu,
            ProtocolType.ModbusRtuOverTcp,
        ]:
            return Yc(
                rtu_addr=item["rtu_addr"],
                address=process_hex_address(item["reg_addr"]),
                func_code=int(item["func_code"]) if item.get("func_code") else 3,
                name=item["name"],
                code=item["code"],
                value=0,
                max_value_limit=item["max_limit"],
                min_value_limit=item["min_limit"],
                add_coe=item["add_coe"],
                mul_coe=item["mul_coe"],
                frame_type=0,
                decode=item["decode_code"] if item.get("decode_code") else "0x41",
            )

        elif protocol_type in [ProtocolType.Iec104Server, ProtocolType.Iec104Client]:
            address = decimal_to_hex(int(item["reg_addr"]) + 16385)
            return Yc(
                rtu_addr=1,
                address=address,
                name=item["name"],
                code=item["code"],
                value=0,
                max_value_limit=item["max_limit"],
                min_value_limit=item["min_limit"],
                add_coe=item["add_coe"],
                mul_coe=item["mul_coe"],
                frame_type=0,
            )

        elif protocol_type in [ProtocolType.Dlt645Server, ProtocolType.Dlt645Client]:
            return Yc(
                rtu_addr=1,
                address=transform(process_hex_address(item["reg_addr"])),
                func_code=int(item["func_code"]) if item.get("func_code") else 3,
                name=item["name"],
                code=item["code"],
                value=0,
                max_value_limit=item["max_limit"],
                min_value_limit=item["min_limit"],
                add_coe=item["add_coe"],
                mul_coe=item["mul_coe"],
                frame_type=0,
            )

        return None
