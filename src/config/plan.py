import json
import os.path
import threading
from bisect import bisect_right
from os import listdir
from typing import Optional, Union, List, Dict

from src.config.global_config import PCS_PLAN_DIR, BMS_PLAN_DIR, METER_PLAN_DIR
from src.config.simulation_thread import SimulationThread
from src.enums.point_data import Yc, Yx, DeviceType
from src.tools.time_tools import TimeTools


class PlanPoint:
    def __init__(
        self, time_offset: int, point: Optional[Union[Yc, Yx]], plan_value: int
    ) -> None:
        self.time_offset: int = time_offset
        self.point: Optional[Union[Yc, Yx]] = point
        self.plan_value: int = plan_value


class PlanData:
    def __init__(
        self,
        start_time: str,
        end_time: str,
        point: Optional[Union[Yc, Yx]],
        plan_value: int,
    ) -> None:
        self.start_time: str = start_time
        self.end_time: str = end_time
        self.point: Optional[Union[Yc, Yx]] = point
        self.plan_value: int = plan_value


class Plan:
    def __init__(self, device) -> None:
        super().__init__()
        self.thread: Optional[SimulationThread] = SimulationThread()
        self.plan_dict: Dict[str, Dict[str, List[PlanData]]] = (
            {}
        )  # 计划列表,[plan_name, [point_code, list[plan_data]]]
        self.plan_point_dict: Dict[str, Dict[str, List[PlanPoint]]] = (
            {}
        )  # 计划测点列表,[plan_name, [point_code, list[plan_point_data]]]
        self.is_set_plan_dict: Dict[str, Dict[str, Dict[int, bool]]] = (
            {}
        )  # 某个计划某个时间是否已经设置过计划值
        self.device = device  # 记录父设备
        self.current_plan_name: str = ""  # 记录当前正在执行的计划名

    def clearAllPlan(self) -> None:
        self.plan_dict.clear()
        self.plan_point_dict.clear()
        self.is_set_plan_dict.clear()

    def importAllPlan(self) -> None:
        # 找到PLAN_DIR目录下的所有json文件
        plan_path = ""
        if self.device.device_type == DeviceType.Pcs:
            plan_path = PCS_PLAN_DIR
        elif self.device.device_type == DeviceType.Bms:
            plan_path = BMS_PLAN_DIR
        elif self.device.device_type == DeviceType.ElectricityMeter:
            plan_path = METER_PLAN_DIR
        elif self.device.device_type == DeviceType.GridMeter:
            pass
        for plan in listdir(plan_path):
            if plan.endswith(".json"):
                self.importPlanJson(plan, os.path.join(plan_path, plan))

    def importPlanJson(self, plan_name: str, plan_path: str) -> None:
        temp_plan_data_dict: Dict[str, List[PlanData]] = {}
        temp_plan_point_dict: Dict[str, List[PlanPoint]] = {}
        with open(plan_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            for point in data:
                point_code = point["point"]  # 获取测点编码
                plan_list = point["plan"]
                temp_plan_data_dict[point_code] = []
                temp_plan_point_dict[point_code] = []
                for plan in plan_list:
                    start = TimeTools.getDaySeconds(plan["start"])
                    end = TimeTools.getDaySeconds(plan["end"])
                    value = plan["value"]
                    temp_plan_data_dict[point_code].append(
                        PlanData(
                            plan["start"],
                            plan["end"],
                            self.device.codeToDataPointMap[point_code],
                            value,
                        )
                    )
                    temp_plan_point_dict[point_code].append(
                        PlanPoint(
                            start, self.device.codeToDataPointMap[point_code], value
                        )
                    )
                    temp_plan_point_dict[point_code].append(
                        PlanPoint(
                            end, self.device.codeToDataPointMap[point_code], value
                        )
                    )
            self.plan_dict[plan_name] = temp_plan_data_dict
            # 将plan_point_list添加最后一个值，预置为无穷大
            temp_plan_point_dict[point_code].append(PlanPoint(99999999999, None, 0))
            self.plan_point_dict[plan_name] = temp_plan_point_dict
            self.is_set_plan_dict[plan_name] = {}

    def planThread(self) -> None:
        plan_point_dict = self.plan_point_dict[self.current_plan_name]
        is_set_plan_dict = self.is_set_plan_dict[
            self.current_plan_name
        ]  # 获取某个计划下的计划map
        time_list = []
        plan_point_list = []
        # 预计算每个测点的时间偏移序列
        is_set_plans = None
        for point_code in plan_point_dict.keys():
            is_set_plans = is_set_plan_dict.get(point_code)
            if is_set_plans is None:
                is_set_plans = {}
                is_set_plan_dict[point_code] = is_set_plans
            times = []
            plan_points = []
            for plan_point in plan_point_dict[point_code]:
                times.append(plan_point.time_offset)
                plan_points.append(plan_point)
                # is_set_plans[plan_point.time_offset] = False
            time_list.append(times)
            plan_point_list.append(plan_points)
        nowTime = TimeTools.getNowTime()  # 获取当前时间并移出循环

        while not self.thread.stop_event.is_set():
            count = TimeTools.getDaySeconds(nowTime)  # 获取当前时间的秒数并移出循环

            for i in range(0, len(plan_point_list)):
                # 使用二分查找找到当前时间对应的计划点索引（注意：这里假设times是已排序的）
                index = bisect_right(time_list[i], count) - 1

                times = time_list[i]
                plan_points = plan_point_list[i]

                # 检查索引是否有效且计划点尚未设置值
                if 0 <= index < len(plan_points) - 1:
                    # and is_set_plans.get(index) is None
                    next_index = index + 1
                    if times[index] <= count < times[next_index]:
                        plan_point = plan_points[index]
                        # is_set_plans[index] = True  # 更新已设置计划点的标记
                        self.device.modbus_tcp_server.setValueByAddress(
                            plan_point.point.func_code,
                            plan_point.point.rtu_addr,
                            plan_point.point.address,
                            plan_point.plan_value,
                        )

    def start(self, targetThread=None) -> None:
        if self.current_plan_name not in self.plan_point_dict.keys():
            raise KeyError(f"没有名为{self.current_plan_name}的计划，启动失败！")
        if targetThread is None:
            self.thread.setThread(threading.Thread(target=self.planThread))
        else:
            self.thread.setThread(threading.Thread(target=targetThread))
        self.thread.start()

    def stop(self) -> None:
        self.thread.stop()

    def isRunning(self) -> None:
        return self.thread.isAlive()

    @staticmethod
    def getTableHead() -> List[str]:
        return [
            "从机地址",
            "测点地址",
            "测点类型",
            "测点编码",
            "测点名称",
            "起始时间",
            "结束时间",
            "计划值",
        ]

    def getTableData(self, plan_name: str, point_name: str = "") -> List[List[str]]:
        if plan_name not in self.plan_dict.keys():
            raise KeyError(f"没有找到名为{plan_name}的计划")
        table_data = []
        frame_type_dict = self.device.frame_type_dict()
        plan_dict = self.plan_dict[plan_name]
        for point_code in plan_dict.keys():
            plan_list = plan_dict[point_code]
            for plan_data in plan_list:
                if plan_data.point is not None:
                    if point_name == "" or plan_data.point.name.find(point_name) != -1:
                        table_data.append(
                            [
                                str(plan_data.point.rtu_addr),
                                str(plan_data.point.hex_address),
                                str(frame_type_dict[plan_data.point.frame_type]),
                                str(plan_data.point.code),
                                str(plan_data.point.name),
                                str(plan_data.start_time),
                                str(plan_data.end_time),
                                str(plan_data.plan_value),
                            ]
                        )
        return table_data
