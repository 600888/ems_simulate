"""
IEC104 客户端实现

基于 c104 库，支持多 Station（多从站/多公共地址）。
每个从站（slave_id）映射为一个独立的 common_address 的 c104.Station。
"""

import asyncio
from collections.abc import Callable
import time
from typing import Any

import c104

from src.device.core.message.message_capture import MessageCapture
from src.proto.iec104.log import log
from src.proto.iec104.tls import IEC104BasicTlsConfig, TlsClientBridge


class IEC104Client:
    def __init__(
        self,
        ip: str = "127.0.0.1",
        port: int = 2404,
        transport_security: c104.TransportSecurity | None = None,
        basic_tls_config: IEC104BasicTlsConfig | None = None,
    ):
        """
        初始化IEC 104客户端
        :param ip: 服务器IP地址，默认127.0.0.1
        :param port: 服务器端口，默认2404
        """
        self.ip = ip
        self.port = port
        self._tls_bridge = (
            TlsClientBridge(ip, port, basic_tls_config.create_client_context()) if basic_tls_config else None
        )
        connection_ip = "127.0.0.1" if self._tls_bridge else self.ip
        connection_port = self._tls_bridge.local_port if self._tls_bridge else self.port
        self.client = c104.Client(transport_security=transport_security)
        self.connection: c104.Connection = self.client.add_connection(
            ip=connection_ip,
            port=connection_port,
            init=c104.Init.INTERROGATION,  # 连接时触发全召唤
        )
        # 多 Station 支持：common_address -> c104.Station
        self.stations: dict[int, c104.Station] = {}
        self.points: list[c104.Point] = []
        self._on_data_received: Callable | None = None
        self._on_command_response: Callable | None = None

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

    def get_captured_messages(self, limit: int = 100) -> list[dict[str, Any]]:
        """获取捕获的报文列表"""
        return self.message_capture.get_messages(limit)

    def clear_captured_messages(self) -> None:
        """清空捕获的报文"""
        self.message_capture.clear()

    async def connect(self, timeout: float = 3) -> bool:
        """
        连接到IEC 104服务器
        :param timeout: 连接超时时间(秒)
        :return: 是否连接成功
        """
        try:
            if self._tls_bridge:
                self._tls_bridge.start()
            self.client.start()
            start_time = time.time()
            while not self.is_connected:
                if time.time() - start_time > timeout:
                    log.error("连接服务器超时")
                    self.client.stop()
                    if self._tls_bridge and self._tls_bridge.last_error:
                        log.error(f"TLS 握手失败: {self._tls_bridge.last_error}")
                    return False
                await asyncio.sleep(0.1)

            log.info(f"成功连接到服务器 {self.ip}:{self.port}")
            return True
        except Exception as e:
            log.error(f"连接服务器失败: {e}")
            self.client.stop()
            return False

    def disconnect(self):
        """断开与服务器的连接"""
        if self.connection and self.connection.is_connected:
            self.connection.disconnect()

        if self.client:
            self.client.stop()
        if self._tls_bridge:
            self._tls_bridge.stop()
        log.info("已断开与服务器的连接")

    @property
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self.connection is not None and self.connection.is_connected

    def get_station(self, common_address: int) -> c104.Station:
        """获取或创建指定公共地址的 Station

        Args:
            common_address: 公共地址（对应从站 slave_id）

        Returns:
            c104.Station 对象
        """
        if common_address not in self.stations:
            self.stations[common_address] = self.connection.add_station(common_address=common_address)
        return self.stations[common_address]

    def add_point(
        self,
        io_address: int,
        point_type: c104.Type = c104.Type.M_ME_NC_1,
        common_address: int = 1,
    ) -> c104.Point | None:
        """
        添加一个监控点到指定站
        :param io_address: 信息对象地址(IOA)
        :param point_type: 点类型，默认是归一化值测量量(M_ME_NC_1)
        :param common_address: 站地址（对应从站 slave_id）
        :return: 创建的监控点对象
        """
        station = self.get_station(common_address)
        # 创建监控点
        point = station.add_point(io_address=io_address, type=point_type)
        if point:
            self.points.append(point)
        return point

    def read_point(self, io_address: int, frame_type: int = 0, common_address: int = 1) -> float | None:
        """
        读取指定站中指定IOA的监控点值（仅读取本地缓存，不发送网络请求）
        :param io_address: 信息对象地址(IOA)
        :param frame_type: 帧类型，0-遥测，1-遥信，2-遥控，3-遥调
        :param common_address: 站地址（对应从站 slave_id）
        :return: 监控点值（Python float），失败返回None
        """
        if not self.is_connected:
            log.error("未连接到服务器，无法读取数据")
            return None

        station = self.stations.get(common_address)
        if not station:
            log.error(f"未找到站地址 {common_address}")
            return None

        try:
            point = station.get_point(io_address=io_address)
            if point:
                return float(point.value)
            return None
        except Exception as e:
            log.error(f"读取监控点值失败: {e}")
            return None

    def send_interrogation(self, common_address: int | None = None) -> bool:
        """
        发送总召唤命令(C_IC_NA_1)，请求服务端发送所有点的最新值

        c104 库会在收到响应后自动更新本地缓存的 point.value，
        之后通过 read_point() 即可获取最新值。

        :param common_address: 站地址，为 None 时向所有已注册的站发送总召唤
        :return: 是否成功发送
        """
        if not self.is_connected:
            log.error("未连接到服务器，无法发送总召唤")
            return False

        try:
            if common_address is not None:
                # 向指定站发送总召唤
                self.connection.interrogation(common_address=common_address)
                log.info(f"已发送总召唤命令(C_IC_NA_1)，站地址: {common_address}")
            else:
                # 向所有站发送总召唤
                for ca in self.stations:
                    self.connection.interrogation(common_address=ca)
                    log.info(f"已发送总召唤命令(C_IC_NA_1)，站地址: {ca}")
            return True
        except Exception as e:
            log.error(f"发送总召唤失败: {e}")
            return False

    def active_read_point(self, io_address: int, common_address: int = 1) -> float | None:
        """
        主动读取指定站中指定监控点的最新值（发送C_RD_NA_1请求）

        与 read_point() 不同，此方法会向服务器发送网络请求获取最新值，
        而非读取本地缓存。

        :param io_address: 信息对象地址(IOA)
        :param common_address: 站地址（对应从站 slave_id）
        :return: 监控点值（Python float），失败返回None
        """
        if not self.is_connected:
            log.error("未连接到服务器，无法主动读取数据")
            return None

        station = self.stations.get(common_address)
        if not station:
            log.error(f"未找到站地址 {common_address}")
            return None

        try:
            point = station.get_point(io_address=io_address)
            if point is None:
                log.error(f"IOA {io_address} 未找到对应的点")
                return None

            # 使用 Point.read() 发送 C_RD_NA_1（单点读取）
            success = point.read()
            if not success:
                log.warning(f"单点读取命令发送失败（IOA: {io_address}），尝试总召唤刷新")
                self.send_interrogation(common_address=common_address)
                time.sleep(0.3)
            else:
                # 等待短暂时间让服务端响应
                time.sleep(0.15)
            return float(point.value)
        except Exception as e:
            log.error(f"主动读取监控点值失败: {e}")
            return None

    def write_point(self, io_address: int, value, frame_type: int = 0, common_address: int = 1) -> bool:
        """
        写入指定站中指定IOA的监控点值（发送遥控/遥调命令）

        c104 库要求对命令类型使用特定的 Info 对象：
        - 单点遥控(C_SC_*): point.info = SingleCmd(state, qualifier)
        - 双点遥控(C_DC_*): point.info = DoubleCmd(state, qualifier)
        - 步命令(C_RC_*):   point.value = Step (然后 transmit)
        - 设定值(C_SE_*):   point.value = float (然后 transmit)

        :param io_address: 信息对象地址(IOA)
        :param value: 要写入的值
        :param frame_type: 帧类型，0-遥测，1-遥信，2-遥控，3-遥调
        :param common_address: 站地址（对应从站 slave_id）
        :return: 是否写入成功
        """
        if not self.is_connected:
            log.error("未连接到服务器，无法写入数据")
            raise Exception("未连接到服务器，无法写入数据")

        if frame_type == 0 or frame_type == 1:
            log.error("遥测和遥信帧类型不支持写入")
            raise Exception("遥测和遥信帧类型不支持写入")

        station = self.stations.get(common_address)
        if not station:
            log.error(f"未找到站地址 {common_address}")
            return False

        try:
            point = station.get_point(io_address=io_address)
            if not point:
                log.error(f"IOA {io_address} 未找到对应的点")
                return False

            pt_type = point.type
            # 根据点类型设置命令信息
            if pt_type in (c104.Type.C_SC_NA_1, c104.Type.C_SC_TA_1):
                # 单点遥控: 使用 SingleCmd(on=bool, qualifier=Qoc)
                point.info = c104.SingleCmd(on=bool(value), qualifier=c104.Qoc.SHORT_PULSE)
            elif pt_type in (c104.Type.C_DC_NA_1, c104.Type.C_DC_TA_1):
                # 双点遥控: 使用 DoubleCmd
                point.info = c104.DoubleCmd(
                    state=c104.Double.ON if bool(value) else c104.Double.OFF,
                    qualifier=c104.Qoc.LONG_PULSE,
                )
            elif pt_type in (c104.Type.C_SE_NA_1, c104.Type.C_SE_TA_1):
                # 设定值-归一化: 使用 NormalizedFloat
                point.value = c104.NormalizedFloat(float(value))
            elif pt_type in (c104.Type.C_SE_NB_1, c104.Type.C_SE_TB_1):
                # 设定值-标度化: 使用 ScaledCmd
                point.info = c104.ScaledCmd(target=c104.Int16(int(value)), qualifier=c104.UInt7(0))
            elif pt_type in (c104.Type.C_SE_NC_1, c104.Type.C_SE_TC_1):
                # 设定值-短浮点: 直接设 float
                point.value = float(value)
            elif pt_type in (c104.Type.C_RC_NA_1, c104.Type.C_RC_TA_1):
                # 步调节命令: 直接设 value（如 c104.Step.HIGHER）
                point.value = value
            else:
                # 未知类型回退
                point.value = value

            # 调用 transmit() 实际发送命令报文
            if not point.transmit(cause=c104.Cot.ACTIVATION):
                log.error(f"发送命令到IOA {io_address} 失败: transmit返回False (type={pt_type})")
                return False
            log.info(f"已发送命令到IOA {io_address}: {value} (type={pt_type})")
            return True
        except Exception as e:
            log.error(f"写入监控点值失败: {e}")
            return False

    def send_command(self, io_address: int, command: c104.Step, common_address: int = 1) -> bool:
        """
        发送步进命令
        :param io_address: 命令点IOA
        :param command: 命令类型(c104.Step.LOWER/c104.Step.HIGHER)
        :param common_address: 站地址（对应从站 slave_id）
        :return: 是否发送成功
        """
        if not self.is_connected:
            log.error("未连接到服务器，无法发送命令")
            return False

        station = self.stations.get(common_address)
        if not station:
            log.error(f"未找到站地址 {common_address}")
            return False

        try:
            point = station.get_point(io_address=io_address)
            if point and isinstance(point, c104.Point):
                point.value = command
                # 必须调用 transmit() 才能实际发送命令报文
                if not point.transmit(cause=c104.Cot.ACTIVATION):
                    log.error(f"发送步进命令到IOA {io_address} 失败: transmit返回False")
                    return False
                log.info(f"已发送步进命令到IOA {io_address}: {command}")
                return True
            return False
        except Exception as e:
            log.error(f"发送命令失败: {e}")
            return False

    def subscribe(self, io_address: int, report_interval_ms: int = 1000, common_address: int = 1) -> bool:
        """
        订阅监控点变化
        :param io_address: 信息对象地址(IOA)
        :param report_interval_ms: 上报间隔(毫秒)
        :param common_address: 站地址（对应从站 slave_id）
        :return: 是否订阅成功
        """
        if not self.is_connected:
            log.error("未连接到服务器，无法订阅")
            return False

        station = self.stations.get(common_address)
        if not station:
            log.error(f"未找到站地址 {common_address}")
            return False

        try:
            point: c104.Point = station.get_point(io_address=io_address)
            if point:
                point.report_ms = report_interval_ms
                return True
            return False
        except Exception as e:
            log.error(f"订阅监控点失败: {e}")
            return False


if __name__ == "__main__":
    import asyncio

    async def main():
        # 示例用法
        client = IEC104Client(ip="10.8.0.102", port=2404)

        # 设置回调函数
        def on_data_received(point):
            print(f"收到数据更新 - IOA: {point.io_address}, 值: {point.value}")

        if await client.connect():
            client.add_point(io_address=16385, point_type=c104.Type.M_ME_NC_1, common_address=1)
            while True:
                # 读取遥测点(IOA=16385)
                value = client.read_point(io_address=16385, frame_type=0, common_address=1)
                print(f"IOA 16385 的值为: {value}")
                # 保持连接一段时间
                await asyncio.sleep(1)

    asyncio.run(main())
