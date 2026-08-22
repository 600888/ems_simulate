"""
遥信服务模块 (Yx)
frame_type = 1
"""

from src.data.dao.point_dao import PointDao
from src.enums.modbus_def import ProtocolType
from src.enums.point_data import Yx
from src.tools.transform import decimal_to_hex, process_hex_address

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


class YxService:
    """遥信服务类"""

    def __init__(self):
        pass

    @classmethod
    def get_list(cls, channel_id: int, protocol_type: ProtocolType) -> list[Yx]:
        """获取遥信点列表

        Args:
            channel_id: 通道ID
            protocol_type: 协议类型

        Returns:
            遥信点列表
        """
        result = reject_foreign_protocol_points(PointDao.get_yx_list(channel_id), channel_id, protocol_type, "遥信")
        point_list: list[Yx] = []

        for item in result:
            point = cls._create_point(item, protocol_type)
            if point:
                point_list.append(point)

        return point_list

    @classmethod
    def get_all(cls, protocol_type: ProtocolType) -> list[Yx]:
        """获取所有遥信点"""
        result = reject_foreign_protocol_points(PointDao.get_all_yx(), 0, protocol_type, "遥信")
        point_list: list[Yx] = []

        for item in result:
            point = cls._create_point(item, protocol_type)
            if point:
                point_list.append(point)

        return point_list

    @classmethod
    def _create_point(cls, item: dict, protocol_type: ProtocolType) -> Yx | None:
        """创建遥信点对象"""
        if protocol_type in [
            ProtocolType.ModbusTcpServer,
            ProtocolType.ModbusTcpClient,
            ProtocolType.ModbusRtu,
            ProtocolType.ModbusRtuClient,
            ProtocolType.ModbusRtuServer,
            ProtocolType.ModbusRtuOverTcp,
        ]:
            return Yx(
                rtu_addr=item["rtu_addr"],
                address=process_hex_address(item["reg_addr"]),
                bit=item.get("bit"),
                func_code=item["func_code"] if item.get("func_code") else 1,
                name=item["name"],
                code=item["code"],
                value=0,
                frame_type=1,
                decode=item["decode_code"] if item.get("decode_code") else "0x20",
            )

        elif protocol_type in [ProtocolType.Iec104Server, ProtocolType.Iec104Client]:
            address = decimal_to_hex(int(item["reg_addr"], 0))
            iec_type_id = item.get("iec_type_id")
            iec_quality = item.get("iec_quality", 0)
            return Yx(
                rtu_addr=item["rtu_addr"],
                address=address,
                bit=None,
                name=item["name"],
                code=item["code"],
                value=0,
                frame_type=1,
                iec_type_id=iec_type_id,
                iec_quality=iec_quality,
            )

        elif protocol_type in [ProtocolType.Iec61850Server, ProtocolType.Iec61850Client]:
            address = item["reg_addr"]
            # 优先使用数据库中的 FC, 仅在未存储时推断
            fc = item.get("fc") or _infer_iec61850_fc(address, 1)
            return Yx(
                rtu_addr=item["rtu_addr"],
                address=address,
                bit=None,
                name=item["name"],
                code=item["code"],
                value=0,
                frame_type=1,
                fc=fc,
            )

        elif protocol_type in [ProtocolType.Dnp3Server, ProtocolType.Dnp3Client]:
            # DNP3 以 index 寻址：reg_addr 存十进制 index，经 process_hex_address 还原为数值
            return Yx(
                rtu_addr=item["rtu_addr"],
                address=process_hex_address(item["reg_addr"]),
                bit=None,
                name=item["name"],
                code=item["code"],
                value=0,
                frame_type=1,
            )

        return None
