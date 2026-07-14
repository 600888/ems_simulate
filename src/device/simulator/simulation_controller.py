import threading

from src.device.simulator.log import log
from src.device.simulator.point_simulator import PointSimulator
from src.enums.point_data import SimulateMethod, Yc, Yt, Yx
from src.enums.points.change_tracker import ChangeSource, track_change


class SimulationController:
    def __init__(self, device):
        self.points: dict[Yc | Yx, PointSimulator] = {}
        self.device = device
        self._simulation_thread = None  # 单线程控制
        self._stop_event = threading.Event()  # 线程停止信号

    def add_point(self, point: Yc | Yx, simulate_method: SimulateMethod, step: int):
        # IEC61850 标准元数据 DA（品质 q、时标 t、描述 dU）不参与模拟
        from src.enums.modbus_def import ProtocolType

        if self.device.protocol_type in (ProtocolType.Iec61850Server,):
            addr = str(point.hex_address)
            if addr.endswith(".q") or addr.endswith(".t") or addr.endswith(".dU"):
                return
        self.points[point] = PointSimulator(point, simulate_method, step)

    def set_all_point_simulate_method(self, simulate_method: SimulateMethod):
        for point_simulator in self.points.values():
            point_simulator.simulate_method = simulate_method

    def set_point_status(self, point: Yc | Yx, is_running: bool):
        if point in self.points:
            self.points[point].is_running = is_running

    def set_single_point_simulate_method(self, point_code: str, simulate_method: SimulateMethod):
        """设置单个点的模拟方法"""
        for point, simulator in self.points.items():
            if point.code == point_code:
                simulator.simulate_method = simulate_method
                log.info(f"设置点 {point_code} 的模拟方法为 {simulate_method.value}")
                return True
        log.error(f"未找到点 {point_code}")
        return False

    def set_single_point_step(self, point_code: str, step: int):
        """设置单个点的模拟步长"""
        for point, simulator in self.points.items():
            if point.code == point_code:
                simulator.step = step
                log.info(f"设置点 {point_code} 的模拟步长为 {step}")
                return True
        log.error(f"未找到点 {point_code}")
        return False

    def get_point_info(self, point_code: str) -> dict | None:
        """获取单个点的信息"""
        for point, simulator in self.points.items():
            if point.code == point_code:
                info = {
                    "code": point.code,
                    "name": point.name,
                    "rtu_addr": point.rtu_addr,
                    "reg_addr": point.hex_address,
                    "func_code": point.func_code,
                    "decode_code": point.decode,
                    "value": point.real_value if isinstance(point, (Yc, Yt)) else point.value,
                    "simulate_method": simulator.simulate_method.value,
                    "step": simulator.step,
                    "is_running": simulator.is_running,
                    "frame_type": point.frame_type,
                    "iec_type_id": getattr(point, "iec_type_id", None),
                    "iec_quality": getattr(point, "iec_quality_value", 0),
                }
                # 遥测和遥调特有字段
                if isinstance(point, (Yc, Yt)):
                    info["mul_coe"] = point.mul_coe
                if isinstance(point, Yt):
                    info["add_coe"] = point.add_coe
                if isinstance(point, Yx):
                    info["bit"] = point.bit
                # 上下限值（Yc/Yt 都有）
                if isinstance(point, (Yc, Yt)):
                    info["min_value"] = point.min_value_limit
                    info["max_value"] = point.max_value_limit
                return info
        return None

    def set_point_simulation_range(self, point_code: str, min_value: float, max_value: float):
        """设置单个点的模拟范围"""
        for point, _simulator in self.points.items():
            if point.code == point_code and isinstance(point, (Yc, Yt)):
                point.min_value_limit = min_value
                point.max_value_limit = max_value
                log.info(f"设置点 {point_code} 的模拟范围为 [{min_value}, {max_value}]")
                return True
        log.error(f"未找到点 {point_code} 或该点不支持设置模拟范围")
        return False

    def start_simulation(self):
        """启动单线程模拟"""
        if not self._simulation_thread or not self._simulation_thread.is_alive():
            self._stop_event.clear()
            self._simulation_thread = threading.Thread(target=self._run_simulation, daemon=True)
            self._simulation_thread.start()

    def stop_simulation(self, timeout: float = 1.0) -> bool:
        """停止模拟线程，并返回线程是否已在超时内退出。"""
        self._stop_event.set()
        if self._simulation_thread and self._simulation_thread.is_alive():
            self._simulation_thread.join(timeout=max(0.0, timeout))
        return not self.is_simulation_running()

    def _run_simulation(self):
        """单线程模拟循环"""
        log.info(f"模拟线程启动, 模拟测点个数: {len(self.points)}")
        # 获取设备本地地址信息
        from src.enums.modbus_def import ProtocolType

        if self.device.protocol_type in (
            ProtocolType.ModbusRtu,
            ProtocolType.ModbusRtuClient,
            ProtocolType.ModbusRtuServer,
            ProtocolType.ModbusRtuOverTcp,
        ):
            local_addr = self.device.serial_port or "未知串口"
        else:
            local_addr = f"{self.device.ip}:{self.device.port}"
        while not self._stop_event.is_set():
            # IEC 61850 服务端必须按轮次批量提交。逐点调用 IedServer_update*
            # 会让每个变化都立即生成报告，订阅后很容易形成报告风暴。
            batch_writer = getattr(self.device.protocol_handler, "write_values_batch", None)
            batch_values = [] if callable(batch_writer) else None

            # 配置接口可能同时增删模拟点，使用快照避免迭代期间字典变化。
            for point_simulator in tuple(self.points.values()):
                if point_simulator.is_running and not self._stop_event.is_set():
                    point = point_simulator.point

                    # 性能优化：仅当开启追溯时才进入上下文
                    if point.change_tracking_enabled:
                        with track_change(ChangeSource.SIMULATION, f"自动模拟 {point.code}", local_addr):
                            changed = self._perform_point_simulation(
                                point_simulator,
                                write_protocol=batch_values is None,
                            )
                    else:
                        changed = self._perform_point_simulation(
                            point_simulator,
                            write_protocol=batch_values is None,
                        )

                    if batch_values is not None and changed:
                        # 与 PointOperator.edit_value 保持一致：协议层接收编码后
                        # 的 point.value，而变化判断仍使用 Yc.real_value。
                        batch_values.append((point, point.value))

            if batch_values:
                try:
                    if not batch_writer(batch_values):
                        log.warning(f"IEC61850 模拟值批量写入失败: count={len(batch_values)}")
                except Exception as e:
                    log.error(f"IEC61850 模拟值批量写入异常: count={len(batch_values)}, error={e}")

            self._stop_event.wait(1)  # 可被 stop 立即唤醒

    def _perform_point_simulation(self, point_simulator: PointSimulator, *, write_protocol: bool = True) -> bool:
        """执行单个点的模拟逻辑"""
        point = point_simulator.point
        before = point.real_value if isinstance(point, Yc) else point.value
        point_simulator.simulate()
        after = point.real_value if isinstance(point, Yc) else point.value
        changed = after != before
        if not changed or not write_protocol:
            return changed

        try:
            slave_id = int(point.rtu_addr) if hasattr(point, "rtu_addr") and point.rtu_addr else None
            if isinstance(point, Yc):
                self.device.editPointData(
                    point.code,
                    point.real_value,
                    source=ChangeSource.SIMULATION,
                    detail=f"自动模拟 {point.code}",
                    slave_id=slave_id,
                )
            else:
                self.device.editPointData(
                    point.code,
                    point.value,
                    source=ChangeSource.SIMULATION,
                    detail=f"自动模拟 {point.code}",
                    slave_id=slave_id,
                )
        except ValueError:
            # 忽略模拟超出范围异常，避免停止后续测点的模拟
            pass
        return changed

    def is_simulation_running(self) -> bool:
        """检查模拟线程是否运行"""
        return self._simulation_thread is not None and self._simulation_thread.is_alive()
