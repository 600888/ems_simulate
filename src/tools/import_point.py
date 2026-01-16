import copy
import csv

from src.enums.point_data import Yc, Yx
from src.tools.transform import process_hex_address


class PointImporter:
    def __init__(self, device, file_name=None) -> None:
        self.device = device
        self.file_name = file_name

    def importDataPointCsv(self) -> None:
        # 读取 modbus_point.csv 数据表
        with open(self.file_name, "r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f, skipinitialspace=True)
            rows = [
                row for row in reader if any(field.strip() for field in row)
            ]  # 去除没有数据的空行
            count = 0  # 记录读取到第几行

            try:
                for row in rows:
                    count += 1
                    if str(row[0]).find("grp_type") != -1:
                        continue
                    elif str(row[0]).find("yc") != -1:
                        break

                    self.device.set_name(str(row[1]))
                    if str(row[8]) != "":
                        self.device.slave_cnt = int(row[8])
                    # 如果是英文字母开头，说明是串口
                    server_port = str(row[6])
                    if server_port[0].isalpha():
                        # 截取第一个冒号前的串口
                        server_port = server_port[: server_port.find(":")]
                        self.device.serial_port = server_port
                    else:
                        # 截取冒号后的端口号
                        server_port = server_port[server_port.find(":") + 1 :]
                        self.device.port = int(server_port)

                # 读取modbus_point数据,分别导入yc和yx
                is_yx = False
                modbus_rows = rows[count:]
                for row in modbus_rows:
                    count += 1
                    # 跳过yc开始标志
                    if str(row[0]).find("yc") != -1:
                        continue
                    elif str(row[0]).find("rtu_addr") != -1:
                        continue
                    elif str(row[0]).find("yx") != -1:
                        is_yx = True
                        continue

                    slave_id = int(row[0])
                    if not is_yx:
                        slave_id = int(row[0])
                        if slave_id not in self.device.slave_id_list:
                            self.device.slave_id_list.append(slave_id)
                        mul_coe = float(row[7])
                        add_coe = float(row[8])
                        max_value_limit = float(row[9])
                        min_value_limit = float(row[10])
                        max_value_limit = int((max_value_limit - add_coe) / mul_coe)
                        min_value_limit = int((min_value_limit - add_coe) / mul_coe)
                        max_value_limit = min(max_value_limit, 65535)
                        min_value_limit = max(min_value_limit, 0)
                        yc_data = Yc(
                            str(row[0]),
                            process_hex_address(str(row[1])),
                            str(row[2]),
                            str(row[5]),
                            str(row[4]),
                            0,
                            max_value_limit,
                            min_value_limit,
                            mul_coe,
                            add_coe,
                            self.device.set_frame_type(True, int(row[2])),
                        )
                        self.device.yc_dict[slave_id].append(yc_data)
                        self.device.codeToDataPointMap[yc_data.code] = yc_data
                    else:
                        slave_id = int(row[0])
                        if slave_id not in self.device.slave_id_list:
                            self.device.slave_id_list.append(slave_id)
                        yx_data = Yx(
                            str(row[0]),
                            process_hex_address(str(row[1])),
                            str(row[2]),
                            str(row[3]),
                            str(row[6]),
                            str(row[5]),
                            0,
                            self.device.set_frame_type(False, int(row[3])),
                        )
                        self.device.yx_dict[slave_id].append(yx_data)
                        self.device.codeToDataPointMap[yx_data.code] = yx_data
            except Exception as e:
                print(f"读取堆文件第{count}行出现错误：{e}")
                raise e

    # 导入电池簇相关测点csv文件
    def importClusterDataPoint(self) -> None:
        # 读取 modbus_point.csv 数据表
        with open(self.file_name, "r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f, skipinitialspace=True)
            rows = [
                row for row in reader if any(field.strip() for field in row)
            ]  # 去除没有数据的空行
            count = 0  # 记录读取到第几行
            slave_cnt = 0  # 记录从机数量
            try:
                for row in rows:
                    count += 1
                    if str(row[0]).find("grp_type") != -1:
                        continue
                    elif str(row[0]).find("yc") != -1:
                        break

                    if str(row[8]) != "":
                        slave_cnt = int(row[8]) + 1  # 算上主机，数量加1
                        self.device.slave_cnt = slave_cnt

                # 导入遥测和遥信数据
                temp_yc_list = []
                temp_yx_list = []
                is_yx = False
                modbus_rows = rows[count:]
                for row in modbus_rows:
                    count += 1
                    # 跳过yc开始标志
                    if str(row[0]).find("yc") != -1:
                        continue
                    elif str(row[0]).find("rtu_addr") != -1:
                        continue
                    elif str(row[0]).find("yx") != -1:
                        is_yx = True
                        continue

                    if not is_yx:
                        mul_coe = float(row[7])
                        add_coe = float(row[8])
                        max_value_limit = float(row[9])
                        min_value_limit = float(row[10])
                        max_value_limit = int((max_value_limit - add_coe) / mul_coe)
                        min_value_limit = int((min_value_limit - add_coe) / mul_coe)
                        max_value_limit = min(max_value_limit, 65535)
                        min_value_limit = max(min_value_limit, 0)
                        yc_data = Yc(
                            str(1),
                            str(row[1]),
                            str(row[2]),
                            str(row[5]),
                            str(row[4]),
                            0,
                            max_value_limit,
                            min_value_limit,
                            mul_coe,
                            add_coe,
                            self.device.set_frame_type(True, int(row[2])),
                        )
                        temp_yc_list.append(yc_data)
                    else:
                        yx_data = Yx(
                            str(1),
                            str(row[1]),
                            str(row[2]),
                            str(row[3]),
                            str(row[6]),
                            str(row[5]),
                            0,
                            self.device.set_frame_type(False, int(row[3])),
                        )
                        temp_yx_list.append(yx_data)

                for i in range(0, int(slave_cnt - 1)):  # 这里不算主机数量,所以需要减去1
                    slave_id = i + 2  # 电池簇从机地址从2开始
                    if slave_id not in self.device.slave_id_list:
                        self.device.slave_id_list.append(slave_id)
                    cl_id = i + 1  # 电池簇号从1开始
                    cluster_yc_list = []
                    cluster_yx_list = []
                    for j in range(0, len(temp_yc_list)):
                        yc_data = copy.deepcopy(temp_yc_list[j])  # 深拷贝
                        yc_data.rtu_addr = str(slave_id)
                        yc_data.code = str("c" + str(cl_id) + "." + yc_data.code)
                        cluster_yc_list.append(yc_data)
                        self.device.codeToDataPointMap[yc_data.code] = yc_data
                    for j in range(0, len(temp_yx_list)):
                        yx_data = copy.deepcopy(temp_yx_list[j])  # 深拷贝
                        yx_data.rtu_addr = str(slave_id)
                        yx_data.code = str("c" + str(cl_id) + "." + yx_data.code)
                        cluster_yx_list.append(yx_data)
                        self.device.codeToDataPointMap[yx_data.code] = yx_data
                    self.device.yc_dict[slave_id] = cluster_yc_list
                    self.device.yx_dict[slave_id] = cluster_yx_list
            except Exception as e:
                print(f"读取簇文件第{count}行出现错误：{e}")
                raise e
