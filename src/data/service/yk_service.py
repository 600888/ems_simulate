"""
遥控服务模块 (Yk)
frame_type = 2
"""

from src.data.dao.point_dao import PointDao
from src.enums.modbus_def import ProtocolType
from src.enums.point_data import Yk
from src.tools.transform import decimal_to_hex, process_hex_address, transform

from .point_protocol_filter import reject_foreign_protocol_points


def _infer_iec61850_fc(address: str, frame_type: int) -> str:
    """从 IEC61850 地址推断 FC, 推断失败则根据帧类型回退"""
    try:
        from src.proto.iec61850.defs import infer_fc_from_address

        fc = infer_fc_from_address(address)
        if fc:
            return fc
    except Exception:
        pass
    return {0: "MX", 1: "ST", 2: "CO", 3: "CO"}.get(frame_type, "")


class YkService:
    """遥控服务类"""

    def __init__(self):
        pass

    @classmethod
    def get_list(cls, channel_id: int, protocol_type: ProtocolType) -> list[Yk]:
        """获取遥控点列表

        Args:
            channel_id: 通道ID
            protocol_type: 协议类型

        Returns:
            遥控点列表
        """
        result = reject_foreign_protocol_points(PointDao.get_yk_list(channel_id), channel_id, protocol_type, "YK")
        point_list: list[Yk] = []

        for item in result:
            point = cls._create_point(item, protocol_type)
            if point:
                point_list.append(point)

        return point_list

    @classmethod
    def get_all(cls, protocol_type: ProtocolType) -> list[Yk]:
        """获取所有遥控点"""
        result = reject_foreign_protocol_points(PointDao.get_all_yk(), 0, protocol_type, "遥控")
        point_list: list[Yk] = []

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
            ProtocolType.ModbusRtuClient,
            ProtocolType.ModbusRtuServer,
            ProtocolType.ModbusRtuOverTcp,
            ProtocolType.ModbusTcpClient,
            ProtocolType.ModbusUdp,
        ]:
            return Yk(
                rtu_addr=item["rtu_addr"],
                address=process_hex_address(item["reg_addr"]),
                bit=item.get("bit"),
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
            iec_type_id = item.get("iec_type_id")
            iec_quality = item.get("iec_quality", 0)
            return Yk(
                rtu_addr=item["rtu_addr"],
                address=address,
                bit=None,
                name=item["name"],
                code=item["code"],
                value=0,
                frame_type=2,
                command_type=item.get("command_type", 0),
                iec_type_id=iec_type_id,
                iec_quality=iec_quality,
            )

        elif protocol_type in [ProtocolType.Iec61850Server, ProtocolType.Iec61850Client]:
            address = item["reg_addr"]
            # 优先使用数据库中的 FC, 仅在未存储时推断
            fc = item.get("fc") or _infer_iec61850_fc(address, 2)
            return Yk(
                rtu_addr=item["rtu_addr"],
                address=address,
                bit=None,
                name=item["name"],
                code=item["code"],
                value=0,
                frame_type=2,
                command_type=item.get("command_type", 0),
                fc=fc,
            )

        elif protocol_type in [ProtocolType.Dlt645Server, ProtocolType.Dlt645Client]:
            return Yk(
                rtu_addr=item["rtu_addr"],
                address=transform(process_hex_address(item["reg_addr"])),
                bit=item.get("bit"),
                func_code=item["func_code"] if item.get("func_code") else 5,
                name=item["name"],
                code=item["code"],
                value=0,
                frame_type=2,
                decode=item["decode_code"] if item.get("decode_code") else "0x20",
                command_type=item.get("command_type", 0),
            )

        return None
