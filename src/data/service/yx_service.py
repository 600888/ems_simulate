"""
遥信服务模块 (Yx)
frame_type = 1
"""

from typing import List
from src.data.dao.point_dao import PointDao
from src.enums.modbus_def import ProtocolType
from src.enums.point_data import Yx
from src.tools.transform import process_hex_address, decimal_to_hex


class YxService:
    """遥信服务类"""

    def __init__(self):
        pass

    @classmethod
    def get_list(cls, channel_id: int, protocol_type: ProtocolType) -> List[Yx]:
        """获取遥信点列表

        Args:
            channel_id: 通道ID
            protocol_type: 协议类型

        Returns:
            遥信点列表
        """
        result = PointDao.get_yx_list(channel_id)
        point_list: List[Yx] = []

        for item in result:
            point = cls._create_point(item, protocol_type)
            if point:
                point_list.append(point)

        return point_list

    @classmethod
    def get_all(cls, protocol_type: ProtocolType) -> List[Yx]:
        """获取所有遥信点"""
        result = PointDao.get_all_yx()
        point_list: List[Yx] = []

        for item in result:
            point = cls._create_point(item, protocol_type)
            if point:
                point_list.append(point)

        return point_list

    @classmethod
    def _create_point(cls, item: dict, protocol_type: ProtocolType) -> Yx | None:
        """创建遥信点对象"""
        if protocol_type in [
            ProtocolType.ModbusTcp,
            ProtocolType.ModbusTcpClient,
            ProtocolType.ModbusRtu,
            ProtocolType.ModbusRtuOverTcp,
        ]:
            return Yx(
                rtu_addr=item["rtu_addr"],
                address=process_hex_address(item["reg_addr"]),
                bit=item["bit"] if item.get("bit") is not None else 0,
                func_code=item["func_code"] if item.get("func_code") else 1,
                name=item["name"],
                code=item["code"],
                value=0,
                frame_type=1,
                decode=item["decode_code"] if item.get("decode_code") else "0x20",
            )

        elif protocol_type in [ProtocolType.Iec104Server, ProtocolType.Iec104Client]:
            address = decimal_to_hex(int(item["reg_addr"]) + 1)
            return Yx(
                rtu_addr=1,
                address=address,
                bit=0,
                name=item["name"],
                code=item["code"],
                value=0,
                frame_type=1,
            )

        return None
