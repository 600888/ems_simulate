from typing import List
from src.data.service.point_service import PointService
from src.data.service.yc_service import YcService
from src.data.service.yx_service import YxService
from src.enums.modbus_def import ProtocolType
from src.enums.point_data import Yc


class DataImporter:
    def __init__(self, device) -> None:
        self.device = device
        self.rtu_addr_dict = {}

    def importData(self, grp_code: str, protocol_type: ProtocolType) -> None:
        self.importYcPointData(grp_code, protocol_type)
        self.importYxPointData(grp_code, protocol_type)

    def importYcPointData(self, grp_code: str, protocol_type: ProtocolType) -> None:
        print(f"importYcPointData: {protocol_type.value}")
        yc_list: List[Yc] = YcService.get_yc_list(grp_code, protocol_type)
        for yc in yc_list:
            if yc.rtu_addr not in self.rtu_addr_dict:
                self.rtu_addr_dict[yc.rtu_addr] = 1
                self.device.slave_id_list.append(yc.rtu_addr)
            self.device.yc_dict[yc.rtu_addr].append(yc)
            self.device.codeToDataPointMap[yc.code] = yc

    def importYxPointData(self, grp_code: str, protocol_type: ProtocolType) -> None:
        yx_list = YxService.get_yx_list(grp_code, protocol_type)
        for yx in yx_list:
            if yx.rtu_addr not in self.rtu_addr_dict:
                self.rtu_addr_dict[yx.rtu_addr] = 1
                self.device.slave_id_list.append(yx.rtu_addr)
            self.device.yx_dict[yx.rtu_addr].append(yx)
            self.device.codeToDataPointMap[yx.code] = yx
