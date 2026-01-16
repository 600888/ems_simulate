from ast import Dict
from src.data.model.dlt645_point import DLT645PointDict


from typing import Any, List
from src.data.dao.point_dao import PointDao
from src.enums.modbus_def import ProtocolType
from src.enums.point_data import Yc
from src.tools.transform import decimal_to_hex, process_hex_address, transform


class YcService:
    meter_address_dict: dict[str, bytes] = {}

    def __init__(self):
        pass

    @classmethod
    def get_yc_list(cls, grp_code: str, protocol_type: ProtocolType) -> List[Yc]:
        try:
            if protocol_type in [ProtocolType.Dlt645Server, ProtocolType.Dlt645Client]:
                result = PointDao.get_dlt645_point_list(
                    grp_code=grp_code, frame_type=[0, 3]
                )
            else:
                result = PointDao.get_point_list(grp_code=grp_code, frame_type=[0, 3])
            yc_list = []
            for index, item in enumerate(result):
                if protocol_type in [
                    ProtocolType.ModbusTcp,
                    ProtocolType.ModbusRtu,
                    ProtocolType.ModbusRtuOverTcp,
                    ProtocolType.ModbusRtu,
                ]:
                    yc = Yc(
                        rtu_addr=item["rtu_addr"],
                        address=process_hex_address(item["reg_addr"]),
                        func_code=int(item["func_code"]) if item["func_code"] else 3,
                        name=item["desc"],
                        code=item["code"],
                        value=0,
                        max_value_limit=item["max_limit"],
                        min_value_limit=item["min_limit"],
                        add_coe=item["add_coe"],
                        mul_coe=item["mul_coe"],
                        frame_type=item["frame_type"],
                        decode=item["decode_code"] if item["decode_code"] else "0x41",
                    )
                elif protocol_type in [
                    ProtocolType.Iec104Server,
                    ProtocolType.Iec104Client,
                ]:
                    frame_type = item["frame_type"]
                    if frame_type == 0:
                        address = decimal_to_hex(int(item["reg_addr"]) + 16385)
                    elif frame_type == 3:
                        address = decimal_to_hex(
                            int(item["reg_addr"])
                        )  # 遥调信息体地址
                    else:
                        address = "0x0000"  # 默认地址
                    yc = Yc(
                        rtu_addr="1",
                        address=address,
                        name=item["desc"],
                        code=item["code"],
                        value=0,
                        max_value_limit=item["max_limit"],
                        min_value_limit=item["min_limit"],
                        add_coe=item["add_coe"],
                        mul_coe=item["mul_coe"],
                        frame_type=frame_type,
                    )
                elif protocol_type in [
                    ProtocolType.Dlt645Server,
                    ProtocolType.Dlt645Client,
                ]:
                    if cls.meter_address_dict.get(grp_code) is None:
                        meter_address = item["rtu_addr"]
                        cls.meter_address_dict[grp_code] = meter_address
                    yc = Yc(
                        rtu_addr="1",
                        address=transform(process_hex_address(item["reg_addr"])),
                        func_code=int(item["func_code"]) if item["func_code"] else 3,
                        name=item["desc"],
                        code=item["code"],
                        value=0,
                        max_value_limit=item["max_limit"],
                        min_value_limit=item["min_limit"],
                        add_coe=item["add_coe"],
                        mul_coe=item["mul_coe"],
                        frame_type=item["frame_type"],
                    )
                else:
                    continue
                yc_list.append(yc)
            return yc_list
        except Exception as e:
            print(f"获取yc列表失败: {e}")
            raise e
