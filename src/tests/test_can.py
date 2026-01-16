import socket
import struct
import can
import time
from collections import defaultdict

# CAN over TCP配置
TCP_IP = "192.168.11.105"
TCP_PORT = 2404
DEVICE_ADDR = 0x01  # 要监控的空调地址

# 报警地址定义（根据协议文档）
ALARM_ADDRESSES = {
    0xE000: [
        "电源过电压告警",
        "电源欠电压告警",
        "电源缺相告警",
        "电源错相告警",
        "开关电源故障",
        "电加热保护告警",
        "烟雾告警",
        "水浸告警",
        "预留",
        "水箱低水位告警",
        "预留",
        "电加热过载告警锁定",
        "预留",
        "群控通讯地址冲突",
        "群控联网通信故障",
    ],
    0xE001: [
        "室内温度探头故障",
        "室内湿度探头故障",
        "进水温度探头故障",
        "出水温度探头故障",
        "进水压力探头故障",
        "出水压力探头故障",
        "进水高温告警",
        "进水低温告警",
        "出水高温告警",
        "出水低温告警",
        "SPI通信故障",
        "室外温度探头故障",
        "进出水温探头接反",
        "进出水压探头接反",
        "A/B系统吸排气温度探头接线异常",
        "CAN通讯故障",
    ],
    0xE003: [
        "外风机1故障锁定",
        "预留",
        "外风机2故障锁定",
        "预留",
        "外风机3故障锁定",
        "预留",
        "外风机4故障锁定",
        "预留",
        "外风机5故障锁定",
        "预留",
        "外风机6故障锁定",
        "预留",
        "进水低压压力告警",
        "出水高压压力告警锁定",
        "远程485通讯故障",
    ],
    0xE008: [
        "系统A高压告警锁定",
        "系统A低压告警锁定",
        "系统A高压开关故障",
        "系统A低压开关故障",
        "",
        "系统A排气高温锁定",
        "系统A液管温度传感器故障",
        "系统A排气温度探头故障",
        "系统A吸气温度探头故障",
        "系统A吸气压力探头故障",
        "系统A排气压力探头故障",
        "系统A制冷剂泄漏或不足",
        "系统A吸排气温度探头接线异常",
    ],
    0xE009: [
        "系统A压机通信故障",
        "",
        "系统A压机频率异常",
        "系统A泵通讯故障",
        "",
        "系统A外机通信故障",
        "",
        "系统A压机驱动故障告警锁定",
        "系统A外风机驱动故障告警锁定",
        "循环水泵1驱动故障告警锁定",
        "循环水泵1过载告警",
        "循环水泵1过载告警锁定",
    ],
    # 添加更多报警地址定义...
}


class CANMonitor:
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(5)
        self.alarm_status = defaultdict(dict)
        self.polling_interval = 5  # 轮询间隔(秒)

    def connect(self):
        try:
            print(f"连接 {TCP_IP}:{TCP_PORT}...")
            self.sock.connect((TCP_IP, TCP_PORT))
            print("连接成功")
            return True
        except Exception as e:
            print(f"连接失败: {str(e)}")
            return False

    def send_polling_frame(self, data_addr=0xA000):
        """发送轮询请求帧"""
        can_id = (
            (0x00 << 24)  # 源地址(动环系统)
            | (DEVICE_ADDR << 21)  # 目标地址
            | (data_addr << 5)  # 数据地址
        )
        frame = struct.pack(">I", can_id) + bytes([0] * 8)
        self.sock.sendall(frame)
        print(f"轮询地址 0x{data_addr:04X}")
        print(f"发送轮询帧: {frame.hex()}")

    def parse_frame(self, data):
        """解析CAN帧"""
        if len(data) < 12:
            return None

        can_id = struct.unpack(">I", data[:4])[0]
        data_addr = (can_id >> 5) & 0xFFFF
        payload = data[4:12]

        return {
            "src": (can_id >> 24) & 0xF,
            "dst": (can_id >> 21) & 0xF,
            "data_addr": data_addr,
            "data": payload,
        }

    def handle_alarm_frame(self, frame):
        """处理报警帧"""
        if frame["data_addr"] not in ALARM_ADDRESSES:
            return

        active_alarms = []
        for byte_idx in range(len(frame["data"])):
            for bit in range(8):
                idx = byte_idx * 8 + bit
                if idx < len(ALARM_ADDRESSES[frame["data_addr"]]):
                    if frame["data"][byte_idx] & (1 << bit):
                        alarm = ALARM_ADDRESSES[frame["data_addr"]][idx]
                        if alarm and alarm != "预留":
                            active_alarms.append(alarm)

        if active_alarms:
            self.alarm_status[frame["data_addr"]] = {
                "timestamp": time.time(),
                "alarms": active_alarms,
            }
            print(f"检测到报警: {', '.join(active_alarms)}")

    def monitor(self):
        try:
            while True:
                # 发送轮询请求（可轮询不同地址）
                self.send_polling_frame(0xA000)  # 基础状态
                self.send_polling_frame(0xE000)  # 报警状态1
                self.send_polling_frame(0xE001)  # 报警状态2

                # 接收并处理响应
                start_time = time.time()
                while time.time() - start_time < self.polling_interval:
                    try:
                        data = self.sock.recv(1024)
                        if not data:
                            break

                        frame = self.parse_frame(data)
                        if frame and frame["dst"] == 0x00:  # 确认是发给动环系统的消息
                            self.handle_alarm_frame(frame)

                    except socket.timeout:
                        break

                # 打印状态摘要
                self.print_status()

        except KeyboardInterrupt:
            print("\n监控终止")
        except Exception as e:
            print(f"错误: {str(e)}")
        finally:
            self.sock.close()

    def print_status(self):
        print("\n=== 设备状态 ===")
        for addr, status in self.alarm_status.items():
            print(f"\n地址 0x{addr:04X}:")
            for alarm in status["alarms"]:
                print(f"  - {alarm}")
        print("===============")


if __name__ == "__main__":
    monitor = CANMonitor()
    if monitor.connect():
        monitor.monitor()
