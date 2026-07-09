"""
遥测服务模块 (Yc)
frame_type = 0
"""

from src.data.dao.point_dao import PointDao
from src.enums.modbus_def import ProtocolType
from src.enums.point_data import Yc
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


class YcService:
    """遥测服务类"""

    def __init__(self):
        pass

    @classmethod
    def get_list(cls, channel_id: int, protocol_type: ProtocolType) -> list[Yc]:
        """获取遥测点列表

        Args:
            channel_id: 通道ID
            protocol_type: 协议类型

        Returns:
            遥测点列表
        """
        try:
            result = reject_foreign_protocol_points(PointDao.get_yc_list(channel_id), channel_id, protocol_type, "遥测")
            point_list: list[Yc] = []

            for item in result:
                point = cls._create_point(item, protocol_type)
                if point:
                    point_list.append(point)

            return point_list
        except Exception as e:
            print(f"获取遥测列表失败: {e}")
            raise

    @classmethod
    def get_all(cls, protocol_type: ProtocolType) -> list[Yc]:
        """获取所有遥测点"""
        try:
            result = reject_foreign_protocol_points(PointDao.get_all_yc(), 0, protocol_type, "遥测")
            point_list: list[Yc] = []

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
            ProtocolType.ModbusRtuClient,
            ProtocolType.ModbusRtuServer,
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
            address = decimal_to_hex(int(item["reg_addr"], 0))
            iec_type_id = item.get("iec_type_id")
            iec_quality = item.get("iec_quality", 0)
            return Yc(
                rtu_addr=item["rtu_addr"],
                address=address,
                name=item["name"],
                code=item["code"],
                value=0,
                max_value_limit=item["max_limit"],
                min_value_limit=item["min_limit"],
                add_coe=item["add_coe"],
                mul_coe=item["mul_coe"],
                frame_type=0,
                iec_type_id=iec_type_id,
                iec_quality=iec_quality,
            )

        elif protocol_type in [ProtocolType.Iec61850Server, ProtocolType.Iec61850Client]:
            address = item["reg_addr"]
            # 优先使用数据库中的 FC, 仅在未存储时推断
            fc = item.get("fc") or _infer_iec61850_fc(address, 0)
            return Yc(
                rtu_addr=item["rtu_addr"],
                address=address,
                name=item["name"],
                code=item["code"],
                value=0,
                max_value_limit=item["max_limit"],
                min_value_limit=item["min_limit"],
                add_coe=item["add_coe"],
                mul_coe=item["mul_coe"],
                frame_type=0,
                fc=fc,
            )

        elif protocol_type in [ProtocolType.Dlt645Server, ProtocolType.Dlt645Client]:
            return Yc(
                rtu_addr=item["rtu_addr"],
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
