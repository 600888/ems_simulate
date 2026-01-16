#!/usr/bin/env python3
"""
Modbus RTU 读取单个寄存器示例
功能：读取从站地址为 1 的设备中，保持寄存器地址 0x007B (123) 的数据
"""

from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusException

# Modbus RTU 连接参数配置
SERIAL_PORT = "/dev/ttyS0"  # Windows 系统串口，例如 'COM1', 'COM2'
# SERIAL_PORT = '/dev/ttyUSB0' # Linux 系统串口，例如 '/dev/ttyUSB0', '/dev/ttyS0'
# SERIAL_PORT = '/dev/tty.usbserial' # macOS 系统串口

BAUD_RATE = 9600  # 波特率，需与从站设备设置一致
PARITY = "N"  # 校验位：'N' (无), 'E' (偶校验), 'O' (奇校验)
STOP_BITS = 1  # 停止位：1 或 2
BYTE_SIZE = 8  # 数据位：通常为 8


# Modbus 从站参数
def read_register(slave_id: int, address: int, register_cnt: int):
    """
    连接Modbus RTU从站并读取一个保持寄存器
    """
    # 创建Modbus RTU客户端
    client = ModbusSerialClient(
        port=SERIAL_PORT,
        baudrate=BAUD_RATE,
        parity=PARITY,
        stopbits=STOP_BITS,
        bytesize=BYTE_SIZE,
        timeout=3,  # 响应超时时间（秒）
    )

    # 尝试建立连接
    if not client.connect():
        print(f"[错误] 无法连接到串口设备 {SERIAL_PORT}")
        return None

    print(f"已成功连接到 {SERIAL_PORT}")

    try:
        # 读取保持寄存器
        # 注意：在Modbus协议中，保持寄存器的功能码是 0x03
        response = client.read_holding_registers(
            address=address, count=register_cnt, slave=slave_id
        )

        # 检查响应是否有效
        if response.isError():
            print(f"[错误] Modbus响应错误: {response}")
            return None

        # 解析响应数据
        # 响应中的数据是一个列表，即使只读取一个寄存器
        register_value = response.registers[0]
        print(f"成功读取寄存器 0x{address:04X} (地址 {address})")
        print(f"原始值 (16位无符号整数): {register_value}")
        print(f"十六进制表示: 0x{register_value:04X}")

        return register_value

    except ModbusException as e:
        print(f"[异常] Modbus通信错误: {e}")
        return None
    except Exception as e:
        print(f"[异常] 发生未知错误: {e}")
        return None
    finally:
        # 确保连接总是被关闭
        client.close()
        print("连接已关闭")


if __name__ == "__main__":
    value = read_register(1, 0x007B, 1)
    if value is not None:
        print(f"- 有符号整数: {value if value < 32768 else value - 65536}")
