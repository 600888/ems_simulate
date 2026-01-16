import sys
import questionary

sys.path.append("../")

from prettytable import PrettyTable
from device_controller import get_device_controller
from src.enums.point_data import DeviceType


def get_first_choice():
    return questionary.select(
        "请输入想要进行的操作",
        choices=[
            "设备监控",
            "一键开启所有设备模拟",
            "一键关闭所有设备模拟",
            "查看所有设备运行状态",
            "退出",
        ],
    ).ask()


def get_third_choice():
    return questionary.select(
        "请输入想要进行的操作",
        choices=[
            "查看测点数据",
            "开启随机值模拟",
            "开启指定计划模拟",
            "关闭模拟",
            "返回上级菜单",
        ],
    ).ask()


if __name__ == "__main__":
    device_controller = get_device_controller()
    first_choice = get_first_choice()
    while True:
        if first_choice == "退出":
            device_controller.stop_all_modbus_server()
        elif first_choice == "设备监控":
            option_list = device_controller.get_device_name_list()
            option_list.append("返回上级菜单")
            second_choice = questionary.select(
                "请输入想要进行的操作",
                choices=option_list,
            ).ask()
            while True:
                if second_choice == "返回上级菜单":
                    first_choice = get_first_choice()
                    break
                else:
                    for device in device_controller.device_list:
                        if device.name == second_choice:
                            device_controller.current_device = device
                            break
                    third_choice = questionary.select(
                        "请输入想要进行的操作",
                        choices=[
                            "查看测点数据",
                            "开启随机值模拟",
                            "开启指定计划模拟",
                            "关闭模拟",
                            "返回上级菜单",
                        ],
                    ).ask()
                    if third_choice == "返回上级菜单":
                        break
                    elif third_choice == "查看测点数据":
                        if isinstance(device_controller.current_device, Dlt645):
                            device_controller.current_device.showDataPointInCmd()
                        else:
                            while True:
                                slave_list = device_controller.get_slave_list()
                                fourth_choice = questionary.select(
                                    "请输入想要进行的操作",
                                    choices=slave_list,
                                ).ask()
                                if fourth_choice == "返回上级菜单":
                                    break
                                else:
                                    current_slave = 0
                                    for i in range(0, len(slave_list)):
                                        if fourth_choice == slave_list[i]:
                                            current_slave = i + 1
                                            break
                                    device_controller.current_device.showDataPointInCmd(
                                        current_slave
                                    )
                    elif third_choice == "开启随机值模拟":
                        device_controller.current_device.startRandomSimulation()
                    elif third_choice == "关闭模拟":
                        device_controller.current_device.stopSimulation()
        elif first_choice == "一键开启所有设备模拟":
            for device in device_controller.device_list:
                device.startRandomSimulation()
            first_choice = get_first_choice()
        elif first_choice == "一键关闭所有设备模拟":
            for device in device_controller.device_list:
                device.stopSimulation()
            first_choice = get_first_choice()
        elif first_choice == "查看所有设备运行状态":
            table = PrettyTable()
            table.field_names = [
                "设备ID",
                "设备名称",
                "设备IP",
                "设备端口",
                "设备状态",
                "模拟状态",
            ]
            for device in device_controller.device_list:
                if isinstance(device, Dlt645):
                    server_status = "运行中" if device.server.isRunning() else "已停止"
                else:
                    server_status = "运行中" if device.server.isRunning() else "已停止"
                    if device.server.protocol_type == device.server.ServerType.Serial:
                        port = device.server.serial_port
                    else:
                        port = device.server.port
                simulation_status = (
                    "运行中" if device.simulation_thread.isAlive() else "已停止"
                )
                if isinstance(device, Dlt645):
                    table.add_row(
                        [
                            device.device_id,
                            device.name,
                            "串口",
                            device.server.port,
                            server_status,
                            simulation_status,
                        ]
                    )
                else:
                    table.add_row(
                        [
                            device.device_id,
                            device.name,
                            device.server.ip,
                            port,
                            server_status,
                            simulation_status,
                        ]
                    )
            print(table)
            first_choice = get_first_choice()
