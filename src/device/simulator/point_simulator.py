import random
import math
import time

from typing import Union

from src.enums.point_data import Yc, Yx, SimulateMethod


class PointSimulator:
    def __init__(self, point, method, step):
        self.point: Union[Yc, Yx] = point
        self.simulate_method = method
        self.step = step
        self.is_running = False
        # 添加新的模拟参数
        self.cycle = 60  # 周期（秒），用于波形模拟
        self.phase = 0  # 相位，用于波形模拟
        self.last_value = point.real_value if isinstance(point, Yc) else point.value
        self.ramp_time = 5  # 斜坡时间（秒），用于斜坡模拟
        self.target_value = self.last_value
        self.ramp_start_time = 0

    def simulate(self):
        """模拟测点值变化"""
        current_time = time.time()

        if isinstance(self.point, Yx):
            # 遥信点模拟
            if self.simulate_method == SimulateMethod.Random:
                # 随机模拟：50%的概率改变状态
                if random.random() < 0.5:
                    self.point.value = 1 - self.point.value
            elif (
                hasattr(SimulateMethod, "Pulse")
                and self.simulate_method == SimulateMethod.Pulse
            ):
                # 脉冲模拟
                pulse_duration = 1  # 脉冲持续时间
                if int(current_time) % self.cycle < pulse_duration:
                    self.point.value = 1
                else:
                    self.point.value = 0
            else:
                # 默认行为（如果选了不支持的方法）：也按50%概率翻转
                if random.random() < 0.5:
                    self.point.value = 1 - self.point.value
        elif hasattr(self.point, 'min_value_limit') and hasattr(self.point, 'max_value_limit'):
            # 遥测点模拟（只有 Yc 类型有 min_value_limit/max_value_limit）
            if self.simulate_method == SimulateMethod.AutoIncrement:
                # 自增模拟，随机步长
                step = random.randint(1, self.step)
                value = self.point.real_value + step
                if value <= self.point.max_value_limit:
                    self.point.set_real_value(value)
                else:
                    # 如果达到最大值，则重置到最小值或开始递减
                    self.point.set_real_value(self.point.min_value_limit)
                    # 可以选择切换到递减模式
                    # self.simulate_method = SimulateMethod.AutoDecrement

            elif self.simulate_method == SimulateMethod.AutoDecrement:
                # 自减模拟，修复原有的条件判断错误
                step = random.randint(1, self.step)
                value = self.point.real_value - step
                if value >= self.point.min_value_limit:
                    self.point.set_real_value(value)
                else:
                    # 如果达到最小值，则重置到最大值或开始递增
                    self.point.set_real_value(self.point.max_value_limit)
                    # 可以选择切换到递增模式
                    # self.simulate_method = SimulateMethod.AutoIncrement

            elif self.simulate_method == SimulateMethod.Random:
                # 随机模拟，在限制范围内随机生成值
                min_value_limit = max(self.point.min_value_limit, -100000)
                max_value_limit = min(self.point.max_value_limit, 100000)
                value = random.uniform(min_value_limit, max_value_limit)
                self.point.set_real_value(value)

            # 添加新的模拟方法
            elif (
                hasattr(SimulateMethod, "SineWave")
                and self.simulate_method == SimulateMethod.SineWave
            ):
                # 正弦波模拟
                amplitude = (
                    self.point.max_value_limit - self.point.min_value_limit
                ) / 2
                mid_value = (
                    self.point.max_value_limit + self.point.min_value_limit
                ) / 2
                # 使用当前时间作为角度，产生连续的正弦波
                angle = (
                    2 * math.pi * (current_time % self.cycle) / self.cycle + self.phase
                )
                value = mid_value + amplitude * math.sin(angle)
                self.point.set_real_value(value)

            elif (
                hasattr(SimulateMethod, "Ramp")
                and self.simulate_method == SimulateMethod.Ramp
            ):
                # 斜坡模拟
                if self.ramp_start_time == 0:
                    self.ramp_start_time = current_time
                    self.target_value = random.uniform(
                        self.point.min_value_limit, self.point.max_value_limit
                    )

                elapsed = current_time - self.ramp_start_time
                if elapsed >= self.ramp_time:
                    # 到达目标值，设置新的目标值
                    self.last_value = self.target_value
                    self.ramp_start_time = 0
                    self.point.set_real_value(self.target_value)
                else:
                    # 计算斜坡中间值
                    progress = elapsed / self.ramp_time
                    value = (
                        self.last_value
                        + (self.target_value - self.last_value) * progress
                    )
                    self.point.set_real_value(value)

            elif (
                hasattr(SimulateMethod, "Pulse")
                and self.simulate_method == SimulateMethod.Pulse
            ):
                # 脉冲模拟
                pulse_duration = 1  # 脉冲持续时间（秒）
                if int(current_time) % self.cycle < pulse_duration:
                    self.point.set_real_value(self.point.max_value_limit)
                else:
                    self.point.set_real_value(self.point.min_value_limit)

            # 保存当前值用于下一次模拟
            self.last_value = self.point.real_value
