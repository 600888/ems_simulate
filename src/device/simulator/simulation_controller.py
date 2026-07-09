import threading
import time

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

    def stop_simulation(self):
        """停止模拟线程"""
        self._stop_event.set()
        if self._simulation_thread and self._simulation_thread.is_alive():
            self._simulation_thread.join(timeout=1)

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
            for point_simulator in self.points.values():
                if point_simulator.is_running and not self._stop_event.is_set():
                    point = point_simulator.point

                    # 性能优化：仅当开启追溯时才进入上下文
                    if point.change_tracking_enabled:
                        with track_change(ChangeSource.SIMULATION, f"自动模拟 {point.code}", local_addr):
                            self._perform_point_simulation(point_simulator)
                    else:
                        self._perform_point_simulation(point_simulator)
            time.sleep(1)  # 适当降低CPU占用

    def _perform_point_simulation(self, point_simulator: PointSimulator):
        """执行单个点的模拟逻辑"""
        point_simulator.simulate()
        try:
            point = point_simulator.point
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

    def is_simulation_running(self) -> bool:
        """检查模拟线程是否运行"""
        return self._simulation_thread is not None and self._simulation_thread.is_alive()
