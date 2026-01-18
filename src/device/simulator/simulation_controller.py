import threading
import time
from typing import Dict, List, Union

from src.device.simulator.point_simulator import PointSimulator
from src.enums.point_data import SimulateMethod, Yc, Yx
from src.device.simulator.log import log


class SimulationController:
    def __init__(self, device):
        self.points: Dict[Union[Yc, Yx], PointSimulator] = {}
        self.device = device
        self._simulation_thread = None  # 单线程控制
        self._stop_event = threading.Event()  # 线程停止信号

    def add_point(
        self, point: Union[Yc, Yx], simulate_method: SimulateMethod, step: int
    ):
        self.points[point] = PointSimulator(point, simulate_method, step)

    def set_all_point_simulate_method(self, simulate_method: SimulateMethod):
        for point_simulator in self.points.values():
            point_simulator.simulate_method = simulate_method

    def set_point_status(self, point: Union[Yc, Yx], is_running: bool):
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
    
    def get_point_info(self, point_code: str) -> dict:
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
                    "value": point.real_value if isinstance(point, Yc) else point.value,
                    "simulate_method": simulator.simulate_method.value,
                    "step": simulator.step,
                    "is_running": simulator.is_running,
                    "frame_type": point.frame_type
                }
                # 遥测和遥调特有字段
                if hasattr(point, "mul_coe"):
                    info["mul_coe"] = point.mul_coe
                if hasattr(point, "add_coe"):
                    info["add_coe"] = point.add_coe
                return info
        return None
    
    def set_point_simulation_range(self, point_code: str, min_value: float, max_value: float):
        """设置单个点的模拟范围"""
        for point, simulator in self.points.items():
            if point.code == point_code and isinstance(point, Yc):
                point.min_value_limit = min_value
                point.max_value_limit = max_value
                log.info(f"设置点 {point_code} 的模拟范围为 [{min_value}, {max_value}]")
                return True
        log.error(f"未找到点 {point_code} 或该点不是遥测值")
        return False

    def start_simulation(self):
        """启动单线程模拟"""
        if not self._simulation_thread or not self._simulation_thread.is_alive():
            self._stop_event.clear()
            self._simulation_thread = threading.Thread(
                target=self._run_simulation, daemon=True
            )
            self._simulation_thread.start()

    def stop_simulation(self):
        """停止模拟线程"""
        self._stop_event.set()
        if self._simulation_thread and self._simulation_thread.is_alive():
            self._simulation_thread.join(timeout=1)

    def _run_simulation(self):
        """单线程模拟循环"""
        log.info(f"模拟线程启动, 模拟测点个数: {len(self.points)}")
        while not self._stop_event.is_set():
            for point_simulator in self.points.values():
                if point_simulator.is_running and not self._stop_event.is_set():
                    point_simulator.simulate()
                    if isinstance(point_simulator.point, Yc):
                        self.device.editPointData(
                            point_simulator.point.code, point_simulator.point.real_value
                        )
                    else:
                        self.device.editPointData(
                            point_simulator.point.code, point_simulator.point.value
                        )
            time.sleep(1)  # 适当降低CPU占用

    def is_simulation_running(self) -> bool:
        """检查模拟线程是否运行"""
        return self._simulation_thread and self._simulation_thread.is_alive()
