from typing import List, Optional, Callable, Dict, Any
import c104
import time
from src.proto.iec104.log import log
from src.device.core.message.message_capture import MessageCapture


class IEC104Client:
    def __init__(
        self, ip: str = "127.0.0.1", port: int = 2404, common_address: int = 1
    ):
        """
        初始化IEC 104客户端
        :param ip: 服务器IP地址，默认127.0.0.1
        :param port: 服务器端口，默认2404
        :param common_address: 站地址，默认1
        """
        self.ip = ip
        self.port = port
        self.common_address = common_address
        self.client = c104.Client()
        self.connection: c104.Connection = self.client.add_connection(
            ip=self.ip, port=self.port, init=c104.Init.INTERROGATION    # 连接时触发全召唤
        )
        # 添加从站
        self.station: c104.Station = self.connection.add_station(
            common_address=self.common_address
        )
        self.points: List[c104.Point] = []
        self._on_data_received: Optional[Callable] = None
        self._on_command_response: Optional[Callable] = None

        # 报文捕获器
        self.message_capture = MessageCapture()
        
        # 注册原始报文回调
        if self.connection:
             self.connection.on_receive_raw(callable=self._on_receive_raw)
             self.connection.on_send_raw(callable=self._on_send_raw)

    def _on_receive_raw(self, connection: c104.Connection, data: bytes) -> None:
        """接收原始报文回调"""
        try:
             self.message_capture.add_rx(data)
        except Exception as e:
            log.error(f"记录接收报文失败: {e}")

    def _on_send_raw(self, connection: c104.Connection, data: bytes) -> None:
        """发送原始报文回调"""
        try:
            self.message_capture.add_tx(data)
        except Exception as e:
            log.error(f"记录发送报文失败: {e}")

    def get_captured_messages(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取捕获的报文列表"""
        return self.message_capture.get_messages(limit)

    def clear_captured_messages(self) -> None:
        """清空捕获的报文"""
        self.message_capture.clear()

    def connect(self, timeout: int = 10) -> bool:
        """
        连接到IEC 104服务器
        :param timeout: 连接超时时间(秒)
        :return: 是否连接成功
        """
        try:
            self.client.start()
            start_time = time.time()
            while not self.is_connected:
                if time.time() - start_time > timeout:
                    log.error("连接服务器超时")
                    return False
                time.sleep(0.1)

            log.info(f"成功连接到服务器 {self.ip}:{self.port}")
            return True
        except Exception as e:
            log.error(f"连接服务器失败: {e}")
            return False

    def disconnect(self):
        """断开与服务器的连接"""
        if self.connection and self.connection.is_connected:
            self.connection.disconnect()
        
        if self.client:
            self.client.stop()
        
        log.info("已断开与服务器的连接")

    @property
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self.connection is not None and self.connection.is_connected

    def add_point(self, io_address: int, point_type: c104.Type = c104.Type.M_ME_NC_1):
        """
        添加一个监控点
        :param io_address: 信息对象地址(IOA)
        :param point_type: 点类型，默认是归一化值测量量(M_ME_NC_1)
        :return: 创建的监控点对象
        """
        # 创建监控点
        point = self.station.add_point(io_address=io_address, type=point_type)
        if point:
            self.points.append(point)
        return point

    def read_point(self, io_address: int, frame_type: int = 0) -> Optional[float]:
        """
        读取指定IOA的监控点值
        :param io_address: 信息对象地址(IOA)
        :param frame_type: 帧类型，0-遥测，1-遥信，2-遥控，3-遥调
        :return: 监控点值，失败返回None
        """
        if not self.is_connected:
            log.error("未连接到服务器，无法读取数据")
            return None

        try:
            point = self.station.get_point(io_address=io_address)
            if point:
                if frame_type == 0:
                    return float(point.value)
                elif frame_type == 1:
                    return bool(point.value)
                elif frame_type == 2:
                    return bool(point.value)
                elif frame_type == 3:
                    return float(point.value)
            return None
        except Exception as e:
            log.error(f"读取监控点值失败: {e}")
            return None

    def write_point(self, io_address: int, value: float, frame_type: int = 0) -> bool:
        """
        写入指定IOA的监控点值
        :param io_address: 信息对象地址(IOA)
        :param value: 要写入的值
        :param frame_type: 帧类型，0-遥测，1-遥信，2-遥控，3-遥调
        :return: 是否写入成功
        """
        if not self.is_connected:
            log.error("未连接到服务器，无法写入数据")
            raise Exception("未连接到服务器，无法写入数据")

        if frame_type == 0 or frame_type == 1:
            log.error("遥信和遥控帧类型不支持写入")
            raise Exception("遥信和遥控帧类型不支持写入")

        try:
            point = self.station.get_point(io_address=io_address)
            if point:
                if frame_type == 0:
                    point.value = float(value)
                elif frame_type == 1:
                    point.value = bool(value)
                elif frame_type == 2:
                    point.value = bool(value)
                elif frame_type == 3:
                    point.value = float(value)
                return True
            return False
        except Exception as e:
            log.error(f"写入监控点值失败: {e}")
            return False

    def send_command(self, io_address: int, command: c104.Step) -> bool:
        """
        发送步进命令
        :param io_address: 命令点IOA
        :param command: 命令类型(c104.Step.LOWER/c104.Step.HIGHER)
        :return: 是否发送成功
        """
        if not self.is_connected:
            log.error("未连接到服务器，无法发送命令")
            return False

        try:
            point = self.station.get_point(io_address=io_address)
            if point and isinstance(point, c104.Point):
                point.value = command
                log.info(f"已发送命令到IOA {io_address}: {command}")
                return True
            return False
        except Exception as e:
            log.error(f"发送命令失败: {e}")
            return False

    # def set_data_received_callback(self, callback: Callable):
    #     """
    #     设置数据接收回调函数
    #     :param callback: 回调函数，格式应为 func(point: c104.Point)
    #     """
    #     self._on_data_received = callback
    #     if self.connection:
    #         self.station.on_data_received(callable=self._on_data_received)

    # def set_command_response_callback(self, callback: Callable):
    #     """
    #     设置命令响应回调函数
    #     :param callback: 回调函数，格式应为 func(point: c104.Point, response: c104.ResponseState)
    #     """
    #     self._on_command_response = callback
    #     if self.connection:
    #         self.connection.on_command_response(callable=self._on_command_response)

    def subscribe(self, io_address: int, report_interval_ms: int = 1000) -> bool:
        """
        订阅监控点变化
        :param io_address: 信息对象地址(IOA)
        :param report_interval_ms: 上报间隔(毫秒)
        :return: 是否订阅成功
        """
        if not self.is_connected:
            log.error("未连接到服务器，无法订阅")
            return False

        try:
            point: c104.Point = self.station.get_point(io_address=io_address)
            if point:
                point.report_ms = report_interval_ms
                return True
            return False
        except Exception as e:
            log.error(f"订阅监控点失败: {e}")
            return False

    # def unsubscribe(self, io_address: int) -> bool:
    #     """
    #     取消订阅监控点
    #     :param io_address: 信息对象地址(IOA)
    #     :return: 是否取消成功
    #     """
    #     if not self.is_connected():
    #         log.error("未连接到服务器，无法取消订阅")
    #         return False

    #     try:
    #         point = self.connection.get_point(io_address=io_address)
    #         if point:
    #             point.report_ms = 0  # 设置为0表示不自动上报
    #             return True
    #         return False
    #     except Exception as e:
    #         log.error(f"取消订阅监控点失败: {e}")
    #         return False


if __name__ == "__main__":
    # 示例用法
    client = IEC104Client(ip="10.8.0.102", port=2404, common_address=1)

    # 设置回调函数
    def on_data_received(point):
        print(f"收到数据更新 - IOA: {point.io_address}, 值: {point.value}")

    if client.connect():
        client.station.add_point(io_address=16385, type=c104.Type.M_ME_NC_1)
        while True:
            # 读取遥测点(IOA=1)
            value = client.read_point(io_address=16385, frame_type=0)
            print(f"IOA 16385 的值为: {value}")
            # 保持连接一段时间
            time.sleep(1)
