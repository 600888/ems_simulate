from typing import List
from src.data.dao.point_dao import PointDao
from src.enums.modbus_def import ProtocolType
from src.enums.point_data import Yx
from src.tools.transform import process_hex_address, decimal_to_hex


class YxService:
    def __init__(self):
        pass

    @classmethod
    def get_yx_list(cls, grp_code: str, protocol_type: ProtocolType) -> List[Yx]:
        result = PointDao.get_point_list(grp_code=grp_code, frame_type=[1, 2])
        yx_list = []
        for item in result:
            if protocol_type in [
                ProtocolType.ModbusTcp,
                ProtocolType.ModbusRtu,
                ProtocolType.ModbusRtuOverTcp,
                ProtocolType.ModbusRtu,
            ]:
                yx = Yx(
                    rtu_addr=item["rtu_addr"],
                    address=process_hex_address(item["reg_addr"]),
                    bit=item["bit"],
                    func_code=item["func_code"],
                    name=item["desc"],
                    code=item["code"],
                    value=0,
                    frame_type=item["frame_type"],
                    decode=item["decode_code"],
                )
            elif protocol_type in [
                ProtocolType.Iec104Server,
                ProtocolType.Iec104Client,
            ]:
                frame_type = item["frame_type"]
                if frame_type == 1:
                    address = decimal_to_hex(
                        int(item["reg_addr"]) + 1
                    )  # 遥信信息体地址
                elif frame_type == 2:
                    address = decimal_to_hex(int(item["reg_addr"]))  # 遥控信息体地址
                yx = Yx(
                    rtu_addr="1",
                    address=address,
                    bit=0,
                    name=item["desc"],
                    code=item["code"],
                    value=0,
                    frame_type=item["frame_type"],
                )
            else:
                continue
            yx_list.append(yx)
        return yx_list
