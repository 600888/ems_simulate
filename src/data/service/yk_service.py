"""
遥控服务模块 (Yk)
frame_type = 2
"""

from typing import List
from src.data.dao.point_dao import PointDao
from src.enums.modbus_def import ProtocolType
from src.enums.point_data import Yk
from src.tools.transform import process_hex_address, decimal_to_hex, transform


class YkService:
    """遥控服务类"""

    def __init__(self):
        pass

    @classmethod
    def get_list(cls, channel_id: int, protocol_type: ProtocolType) -> List[Yk]:
        """获取遥控点列表

        Args:
            channel_id: 通道ID
            protocol_type: 协议类型

        Returns:
            遥控点列表
        """
        result = PointDao.get_yk_list(channel_id)
        point_list: List[Yk] = []

        for item in result:
            point = cls._create_point(item, protocol_type)
            if point:
                point_list.append(point)

        return point_list

    @classmethod
    def get_all(cls, protocol_type: ProtocolType) -> List[Yk]:
        """获取所有遥控点"""
        result = PointDao.get_all_yk()
        point_list: List[Yk] = []

        for item in result:
            point = cls._create_point(item, protocol_type)
            if point:
                point_list.append(point)

        return point_list

    @classmethod
    def _create_point(cls, item: dict, protocol_type: ProtocolType) -> Yk | None:
        """创建遥控点对象"""
        if protocol_type in [
            ProtocolType.ModbusTcp,
            ProtocolType.ModbusRtu,
            ProtocolType.ModbusRtuOverTcp,
            ProtocolType.ModbusTcpClient,
            ProtocolType.ModbusUdp,
        ]:
            return Yk(
                rtu_addr=item["rtu_addr"],
                address=process_hex_address(item["reg_addr"]),
                bit=item["bit"] if item.get("bit") is not None else 0,
                func_code=item["func_code"] if item.get("func_code") else 5,
                name=item["name"],
                code=item["code"],
                value=0,
                frame_type=2,
                decode=item["decode_code"] if item.get("decode_code") else "0x20",
                command_type=item.get("command_type", 0),
            )

        elif protocol_type in [ProtocolType.Iec104Server, ProtocolType.Iec104Client]:
            address = decimal_to_hex(int(item["reg_addr"], 0))
            return Yk(
                rtu_addr=1,
                address=address,
                bit=0,
                name=item["name"],
                code=item["code"],
                value=0,
                frame_type=2,
                command_type=item.get("command_type", 0),
            )

        elif protocol_type in [ProtocolType.Dlt645Server, ProtocolType.Dlt645Client]:
            return Yk(
                rtu_addr=1,
                address=transform(process_hex_address(item["reg_addr"])),
                bit=item["bit"] if item.get("bit") is not None else 0,
                func_code=item["func_code"] if item.get("func_code") else 5,
                name=item["name"],
                code=item["code"],
                value=0,
                frame_type=2,
                decode=item["decode_code"] if item.get("decode_code") else "0x20",
                command_type=item.get("command_type", 0),
            )

        return None
