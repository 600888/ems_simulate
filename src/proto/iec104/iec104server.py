"""
IEC104 服务端实现

基于 c104 库，支持多 Station（多从站/多公共地址）。
每个从站（slave_id）映射为一个独立的 common_address 的 c104.Station。
"""

from typing import Any

import c104
from c104 import Quality

from src.device.core.message.message_capture import MessageCapture
from src.proto.iec104.log import log


class IEC104Server:
    def __init__(self, ip="0.0.0.0", port=2404):
        """
        初始化IEC 104服务器
        :param ip: 服务器监听IP地址，默认0.0.0.0表示监听所有接口
        :param port: 服务器监听端口，默认2404是IEC 104标准端口
        """
        self.ip = ip
        self.port = port
        # 创建c104服务器实例
        self.server = c104.Server(ip=ip, port=port)
        # 多 Station 支持：common_address -> c104.Station
        self.stations: dict[int, c104.Station] = {}
        # 存储所有监控点的列表
        self.points: list[c104.Point] = []
        # 存储所有命令点的列表
        self.commands: list[c104.Point] = []
        # 关联测点map
        self.related_point_map = {}
        # 命令接收后的应用层回调（由 handler 注册，用于同步应用层 BasePoint）
        self._on_command_received_callback = None
        # IOA → common_address 映射，用于命令回调反查站地址
        self._ioa_to_ca: dict[int, int] = {}
        # 设置默认回调函数
        self._setup_callbacks()

        # 报文捕获器
        self.message_capture = MessageCapture()

        # 注册原始报文回调
        if self.server:
            self.server.on_receive_raw(callable=self._on_receive_raw)
            self.server.on_send_raw(callable=self._on_send_raw)

    def _on_receive_raw(self, server: c104.Server, data: bytes) -> None:
        """接收原始报文回调"""
        try:
            self.message_capture.add_rx(data)
        except Exception as e:
            log.error(f"记录接收报文失败: {e}")

    def _on_send_raw(self, server: c104.Server, data: bytes) -> None:
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

    def _setup_callbacks(self):
        """设置默认的回调函数"""
        # 初始化通用命令接收处理函数
        self._on_command_received = self._default_command_handler

    def get_station(self, common_address: int) -> c104.Station:
        """获取或创建指定公共地址的 Station

        Args:
            common_address: 公共地址（对应从站 slave_id）

        Returns:
            c104.Station 对象
        """
        if common_address not in self.stations:
            self.stations[common_address] = self.server.add_station(common_address=common_address)
        return self.stations[common_address]

    def add_monitoring_point(
        self,
        io_address: int,
        point_type: c104.Type = c104.Type.M_ME_NC_1,
        report_ms: int = 1000,
        common_address: int = 1,
    ) -> c104.Point | None:
        """
        添加一个监控点到指定站
        :param io_address: 信息对象地址(IOA)
        :param point_type: 点类型，默认是归一化值测量量(M_ME_NC_1)
        :param report_ms: 自动上报间隔(毫秒)
        :param common_address: 站地址（对应从站 slave_id）
        :return: 创建的监控点对象
        """
        station = self.get_station(common_address)
        # 创建监控点
        point = station.add_point(io_address=io_address, type=point_type, report_ms=report_ms)
        if point:
            self.points.append(point)
            self._ioa_to_ca[io_address] = common_address
        return point

    def add_command_point(
        self,
        io_address: int,
        point_type: c104.Type = c104.Type.C_RC_TA_1,
        related_point_ioa: int | None = None,
        common_address: int = 1,
    ) -> c104.Point | None:
        """
        添加一个命令点到指定站
        :param io_address: 信息对象地址(IOA)
        :param point_type: 点类型，默认是调节步命令(C_RC_TA_1)
        :param related_point_ioa: 关联的监控点IOA
        :param common_address: 站地址（对应从站 slave_id）
        :return: 创建的命令点对象
        """
        station = self.get_station(common_address)
        # 创建命令点
        command = station.add_point(io_address=io_address, type=point_type)
        # 注册命令接收回调（c104 接收到命令后自动更新 point.value，然后触发此回调）
        command.on_receive(callable=self._on_command_received)
        # 添加到命令点列表
        self.commands.append(command)
        self._ioa_to_ca[io_address] = common_address
        return command

    def get_point_value(self, io_address: int, frame_type: int = 0, common_address: int = 1) -> float:
        """
        获取指定站中指定IOA的监控点值
        :param io_address: 信息对象地址(IOA)
        :param frame_type: 帧类型
        :param common_address: 站地址（对应从站 slave_id）
        :return: 监控点值（Python float）
        """
        station = self.stations.get(common_address)
        if not station:
            return 0
        try:
            point = station.get_point(io_address=io_address)
            if point:
                # 遥控点(2)返回 bool，其余返回 float
                if frame_type == 2:
                    return bool(point.value)
                return float(point.value)
            return 0
        except Exception as e:
            log.info(f"获取监控点值失败: {e}")
            raise e

    def set_point_value(self, io_address: int, value, frame_type: int = 0, common_address: int = 1) -> None:
        """
        设置指定站中指定IOA的监控点值
        :param io_address: 信息对象地址(IOA)
        :param value: 要设置的值（c104 原生类型，如 NormalizedFloat、Int16、float、bool）
        :param frame_type: 帧类型，默认遥测
        :param common_address: 站地址（对应从站 slave_id）
        """
        station = self.stations.get(common_address)
        if not station:
            return
        try:
            point = station.get_point(io_address=io_address)
            if point:
                point.value = value
        except Exception as e:
            log.info(f"设置监控点值失败: {e}")
            raise e

    def set_point_quality(self, io_address: int, quality: int, frame_type: int = 0, common_address: int = 1) -> None:
        """
        设置指定站中指定IOA的品质描述符
        :param io_address: 信息对象地址(IOA)
        :param quality: 品质描述符整数值 (位标志: OV=0x01 BL=0x02 SB=0x04 NT=0x08 IV=0x10)
        :param frame_type: 帧类型，默认遥测
        :param common_address: 站地址（对应从站 slave_id）
        """
        station = self.stations.get(common_address)
        if not station:
            return
        try:
            point = station.get_point(io_address=io_address)
            if point and hasattr(point, "quality"):
                point.quality = Quality(value=quality)
        except Exception as e:
            log.error(f"设置监控点品质失败: {e}")
            raise

    def get_point_quality(self, io_address: int, frame_type: int = 0, common_address: int = 1) -> int:
        """
        获取指定站中指定IOA的品质描述符
        :param io_address: 信息对象地址(IOA)
        :param frame_type: 帧类型
        :param common_address: 站地址（对应从站 slave_id）
        :return: 品质描述符整数值
        """
        station = self.stations.get(common_address)
        if not station:
            return 0
        try:
            point = station.get_point(io_address=io_address)
            if point and hasattr(point, "quality"):
                return int(point.quality)
            return 0
        except Exception as e:
            log.error(f"获取监控点品质失败: {e}")
            raise

    def start(self):
        """启动IEC 104服务器"""
        self.server.start()

    def stop(self):
        """停止IEC 104服务器"""
        if self.server:
            self.server.stop()
            log.info("IEC 104服务器已停止")

    async def run(self, timeout=30):
        """
        运行服务器主循环
        :param timeout: 超时时间(秒)，默认30秒
        """
        import asyncio

        # 等待客户端连接
        while not self.server.has_active_connections:
            print("等待客户端连接...")
            await asyncio.sleep(1)

        await asyncio.sleep(1)

        c = 0
        # 保持连接直到超时或连接断开
        while self.server.has_open_connections and c < timeout:
            c += 1
            print("保持连接中...")
            await asyncio.sleep(1)

    def isRunning(self) -> bool:
        """检查服务器是否运行中"""
        return self.server.is_running

    def _default_command_handler(
        self,
        point: c104.Point,
        previous_info: c104.Information,
        message: c104.IncomingMessage,
    ) -> c104.ResponseState:
        """
        默认的通用命令接收处理函数
        处理单点遥控(C_SC_NA_1)、双点遥控(C_DC_NA_1)、设定值(C_SE_*)等命令。

        c104 在收到命令后会先更新 point.value 再触发此回调，
        回调只需返回响应状态即可。

        :param point: 命令点对象（point.value 已更新为接收到的命令值）
        :param previous_info: 前一个信息对象
        :param message: 接收到的消息
        :return: 响应状态(SUCCESS/FAILURE)
        """
        log.info(f"收到命令 - IOA: {point.io_address}, 类型: {point.type}, 值: {point.value}")
        # 查找 IOA 对应的站地址
        common_address = self._ioa_to_ca.get(point.io_address, 1)
        # 通知应用层回调（如果有注册），传递 IOA、值、帧类型和站地址
        if self._on_command_received_callback:
            try:
                self._on_command_received_callback(
                    point.io_address,
                    point.value,
                    point.type,
                    common_address,
                )
            except Exception as e:
                log.error(f"命令接收回调执行失败: {e}")
        return c104.ResponseState.SUCCESS

    def set_on_command_callback(self, callback):
        """
        设置命令接收通知回调
        当服务端收到客户端的遥控/遥调命令时，会调用此回调通知应用层。
        :param callback: 回调函数，签名 callback(io_address, value, point_type, common_address)
        """
        self._on_command_received_callback = callback

    # 绑定关联测点
    def bind_related_point(self, io_address: int, related_io_address: int, common_address: int = 1):
        """
        绑定遥调点到遥测点上面
        :param io_address: 遥调点IOA
        :param related_io_address: 遥测点IOA
        :param common_address: 站地址（对应从站 slave_id）
        """
        station = self.stations.get(common_address)
        if not station:
            log.error(f"绑定104关联测点失败，未找到站地址 {common_address}")
            return
        a_point = station.get_point(io_address=io_address)
        b_point = station.get_point(io_address=related_io_address)
        if a_point:
            log.info(f"找到测点A (IOA={io_address})")
        if b_point:
            log.info(f"找到测点B (IOA={related_io_address})")
        if a_point and b_point:
            self.related_point_map[a_point] = b_point
            if hasattr(self, "_before_read"):
                a_point.on_before_read(callable=self._before_read)
            log.info(f"绑定成功, {a_point.io_address} 关联 {b_point.io_address}")
        else:
            log.error("绑定104关联测点失败")


if __name__ == "__main__":
    import asyncio

    async def main():
        # 创建服务器实例
        server = IEC104Server(ip="0.0.0.0", port=2404)

        # 添加监控点(IOA=11)和命令点(IOA=12)到站地址1
        server.add_monitoring_point(io_address=11, common_address=1)
        server.add_command_point(io_address=12, common_address=1)

        # 启动服务器并运行主循环
        server.start()
        await server.run(timeout=30)

    asyncio.run(main())
