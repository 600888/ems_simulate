from typing import List
import c104
import random
import time
from src.proto.iec104.log import log


class IEC104Server:
    def __init__(self, ip="0.0.0.0", port=2404, common_address=1):
        """
        初始化IEC 104服务器
        :param ip: 服务器监听IP地址，默认0.0.0.0表示监听所有接口
        :param port: 服务器监听端口，默认2404是IEC 104标准端口
        :param common_address: 站地址，默认1
        """
        self.ip = ip
        self.port = port
        # 创建c104服务器实例
        self.server = c104.Server(ip=ip, port=port)
        # 添加一个站
        self.station = self.server.add_station(common_address=common_address)
        # 存储所有监控点的列表
        self.points: List[c104.Point] = []
        # 存储所有命令点的列表
        self.commands = []
        # 关联测点map
        self.related_point_map = {}
        # 设置默认回调函数
        self._setup_callbacks()

    def _setup_callbacks(self):
        """设置默认的回调函数"""
        pass
        # self._on_step_command = self._default_step_command_handler
        # self._before_auto_transmit = self._default_before_auto_transmit
        self._before_read = self._default_before_read

    def add_monitoring_point(
        self, io_address, point_type=c104.Type.M_ME_NC_1, report_ms=1000
    ):
        """
        添加一个监控点到站
        :param io_address: 信息对象地址(IOA)
        :param point_type: 点类型，默认是归一化值测量量(M_ME_NC_1)
        :param report_ms: 自动上报间隔(毫秒)
        :return: 创建的监控点对象
        """
        # 创建监控点
        point = self.station.add_point(
            io_address=io_address, type=point_type, report_ms=report_ms
        )
        if point:
            # # 设置自动传输前的回调
            # point.on_before_auto_transmit(callable=self._before_auto_transmit)
            # # 设置读取前的回调
            # point.on_before_read(callable=self._before_read)
            # 添加到监控点列表
            self.points.append(point)
        return point

    def add_command_point(
        self, io_address, point_type=c104.Type.C_RC_TA_1, related_point_ioa=None
    ):
        """
        添加一个命令点到站
        :param io_address: 信息对象地址(IOA)
        :param point_type: 点类型，默认是调节步命令(C_RC_TA_1)
        :param related_point_ioa: 关联的监控点IOA
        :return: 创建的命令点对象
        """
        # 创建命令点
        command = self.station.add_point(io_address=io_address, type=point_type)
        # 设置接收命令的回调
        # command.on_receive(callable=self._on_step_command)
        # 添加到命令点列表
        self.commands.append(command)
        return command

    def get_point_value(self, io_address: int, frame_type: int = 0) -> float:
        """
        获取指定IOA的监控点值
        :param io_address: 信息对象地址(IOA)
        :return: 监控点值
        """
        try:
            # 如果是遥测或者遥信
            if frame_type == 0 or frame_type == 1:
                for point in self.points:
                    if point.io_address == io_address:
                        point = self.station.get_point(io_address=io_address)
                        if point:
                            if frame_type == 0:
                                return float(point.value)
                            elif frame_type == 1:
                                return bool(point.value)
            elif frame_type == 2 or frame_type == 3:  # 遥测或者遥调
                for command in self.commands:
                    if command.io_address == io_address:
                        command = self.station.get_point(io_address=io_address)
                        if command:
                            if frame_type == 2:
                                return bool(command.value)
                            elif frame_type == 3:
                                return float(command.value)
            return 0
        except Exception as e:
            log.info(f"获取监控点值失败: {e}")
            raise e

    def set_point_value(
        self, io_address: int, value: float, frame_type: int = 0
    ) -> None:
        """
        设置指定IOA的监控点值
        :param io_address: 信息对象地址(IOA)
        :param value: 要设置的值
        :param frame_type: 帧类型，默认遥测
        """
        try:
            # 如果是遥测或者遥信
            if frame_type == 0 or frame_type == 1:
                for point in self.points:
                    if point.io_address == io_address:
                        point = self.station.get_point(io_address=io_address)
                        if point:
                            if frame_type == 0:
                                point.value = float(value)
                            elif frame_type == 1:
                                point.value = bool(value)
            elif frame_type == 2 or frame_type == 3:  # 遥控或者遥调
                for command in self.commands:
                    if command.io_address == io_address:
                        command = self.station.get_point(io_address=io_address)
                        if command:
                            if frame_type == 2:
                                command.value = bool(value)
                            elif frame_type == 3:
                                command.value = float(value)
        except Exception as e:
            log.info(f"设置监控点值失败: {e}")
            raise e

    def start(self):
        """启动IEC 104服务器"""
        self.server.start()

    def run(self, timeout=30):
        """
        运行服务器主循环
        :param timeout: 超时时间(秒)，默认30秒
        """
        # 等待客户端连接
        while not self.server.has_active_connections:
            print("等待客户端连接...")
            time.sleep(1)

        time.sleep(1)

        c = 0
        # 保持连接直到超时或连接断开
        while self.server.has_open_connections and c < timeout:
            c += 1
            print("保持连接中...")
            time.sleep(1)

    def isRunning(self) -> bool:
        """检查服务器是否运行中"""
        return self.server.is_running

    def _default_step_command_handler(
        self,
        point: c104.Point,
        previous_info: c104.Information,
        message: c104.IncomingMessage,
    ) -> c104.ResponseState:
        """
        默认的步进命令处理函数
        :param point: 命令点对象
        :param previous_info: 前一个信息对象
        :param message: 接收到的消息
        :return: 响应状态(SUCCESS/FAILURE)
        """
        log.info(
            "{0} 收到步进命令, IOA: {1}, 消息: {2}, 前值: {3}, 当前值: {4}".format(
                point.type, point.io_address, message, previous_info, point.info
            )
        )

        if point.value == c104.Step.LOWER:
            # 处理降低命令
            return c104.ResponseState.SUCCESS

        if point.value == c104.Step.HIGHER:
            # 处理升高命令
            return c104.ResponseState.SUCCESS

        return c104.ResponseState.FAILURE

    def _default_before_auto_transmit(self, point: c104.Point) -> None:
        """
        默认的自动传输前回调函数
        :param point: 监控点对象
        """
        # 生成随机值模拟数据变化
        point.value = random.random() * 100
        log.info(
            "{0} 自动上报前更新值, IOA: {1}, 新值: {2}".format(
                point.type, point.io_address, point.value
            )
        )

    def _default_before_read(self, point: c104.Point) -> None:
        """
        默认的读取前回调函数
        :param point: 监控点对象
        """
        if point in self.related_point_map:
            related_point: c104.Point = self.related_point_map[point]
            if related_point:
                related_point.value = point.value

    def set_step_command_handler(self, handler):
        """
        设置自定义步进命令处理函数
        :param handler: 自定义处理函数
        """
        self._on_step_command = handler
        # 更新所有命令点的回调函数
        for cmd in self.commands:
            cmd.on_receive(callable=self._on_step_command)

    def set_before_auto_transmit_handler(self, handler):
        """
        设置自定义自动传输前回调函数
        :param handler: 自定义处理函数
        """
        self._before_auto_transmit = handler
        # 更新所有监控点的回调函数
        for point in self.points:
            point.on_before_auto_transmit(callable=self._before_auto_transmit)

    def set_before_read_handler(self, handler):
        """
        设置自定义读取前回调函数
        :param handler: 自定义处理函数
        """
        self._before_read = handler
        # 更新所有监控点的回调函数
        for point, _ in self.related_point_map:
            point.on_before_read(callable=self._before_read)

    # 绑定关联测点
    def bind_related_point(self, io_address: int, related_io_address: int):
        """
        绑定遥调点到遥测点上面
        :param yc_point: 遥调点对象
        """
        a_point = None
        b_point = None
        for command in self.commands:
            if command.io_address == io_address:
                command = self.station.get_point(io_address=io_address)
                if command:
                    a_point = command
                    log.info("找到测点A")
        for point in self.points:
            if point.io_address == related_io_address:
                point = self.station.get_point(io_address=related_io_address)
                if point:
                    b_point = point
                    log.info("找到测点B")
        if a_point and b_point:
            self.related_point_map[a_point] = b_point
            a_point.on_before_read(callable=self._before_read)
            log.info(f"绑定成功, {a_point.io_address} 关联 {b_point.io_address}")
        else:
            log.error(f"绑定104关联测点失败")


if __name__ == "__main__":
    # 创建服务器实例
    server = IEC104Server(ip="0.0.0.0", port=2404, common_address=1)

    # 添加监控点(IOA=11)和命令点(IOA=12)
    server.add_monitoring_point(io_address=11)
    server.add_command_point(io_address=12)

    # 启动服务器并运行主循环
    server.start()
    server.run(timeout=30)
