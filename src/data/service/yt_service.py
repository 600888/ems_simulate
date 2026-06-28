"""
遥调服务模块 (Yt)
frame_type = 3
"""

from src.data.dao.point_dao import PointDao
from src.enums.modbus_def import ProtocolType
from src.enums.point_data import Yt
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


class YtService:
    """遥调服务类"""

    def __init__(self):
        pass

    @classmethod
    def get_list(cls, channel_id: int, protocol_type: ProtocolType) -> list[Yt]:
        """获取遥调点列表

        Args:
            channel_id: 通道ID
            protocol_type: 协议类型

        Returns:
            遥调点列表
        """
        try:
            result = reject_foreign_protocol_points(PointDao.get_yt_list(channel_id), channel_id, protocol_type, "遥调")
            point_list: list[Yt] = []

            for item in result:
                point = cls._create_point(item, protocol_type)
                if point:
                    point_list.append(point)

            return point_list
        except Exception as e:
            print(f"获取遥调列表失败: {e}")
            raise

    @classmethod
    def get_all(cls, protocol_type: ProtocolType) -> list[Yt]:
        """获取所有遥调点"""
        try:
            result = reject_foreign_protocol_points(PointDao.get_all_yt(), 0, protocol_type, "遥调")
            point_list: list[Yt] = []

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
            ProtocolType.ModbusRtuClient,
            ProtocolType.ModbusRtuServer,
            ProtocolType.ModbusRtuOverTcp,
            ProtocolType.ModbusTcpClient,
            ProtocolType.ModbusUdp,
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
            address = decimal_to_hex(int(item["reg_addr"], 0))
            iec_type_id = item.get("iec_type_id")
            iec_quality = item.get("iec_quality", 0)
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
                iec_type_id=iec_type_id,
                iec_quality=iec_quality,
            )

        elif protocol_type in [ProtocolType.Iec61850Server, ProtocolType.Iec61850Client]:
            address = item["reg_addr"]
            # 优先使用数据库中的 FC, 仅在未存储时推断
            fc = item.get("fc") or _infer_iec61850_fc(address, 3)
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
                fc=fc,
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
