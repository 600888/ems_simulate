"""
测点计算器
负责管理和执行测点映射计算
"""

import ast
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
import json
import operator
import threading
from typing import Any

from src.data.service.point_mapping_service import PointMappingService
from src.enums.points.base_point import BasePoint
from src.enums.points.change_tracker import ChangeContext, ChangeSource, capture_context, restore_context
from src.log import log


class PointCalculator:
    """测点计算器"""

    def __init__(self, device):
        self.device = device
        self.pm = device.point_manager
        self._mappings: list[dict[str, Any]] = []
        self._mapping_by_id: dict[int, dict[str, Any]] = {}
        self._source_points_by_id: dict[int, list[Any]] = {}
        self._formula_ast_by_id: dict[int, ast.AST] = {}
        self._source_usage: dict[
            str, list[int]
        ] = {}  # source_code -> [mapping_ids] (DEPRECATED: still used for debug or display)
        self._sender_map: dict[int, list[int]] = {}  # id(sender) -> [mapping_ids]
        self._executor: ThreadPoolExecutor | None = None
        self._running = False
        self._schedule_lock = threading.Lock()
        self._pending_mapping_ids: set[int] = set()
        self._latest_context: dict[int, ChangeContext | None] = {}
        self._device_provider: Any = None

        # 受限的操作符映射
        self._operators: dict[type, Callable] = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.BitAnd: operator.and_,
            ast.BitOr: operator.or_,
            ast.BitXor: operator.xor,
            ast.LShift: operator.lshift,
            ast.RShift: operator.rshift,
            ast.USub: operator.neg,
        }

    def set_device_provider(self, provider: Any, mappings: list[dict[str, Any]] | None = None):
        """设置设备提供者"""
        self._device_provider = provider
        # 运行中的设备可能是先启动协议、后注册到 DeviceController 的重建实例。
        # 此时 start() 会直接返回，必须显式重载才能恢复测点订阅和目标点锁定。
        if self._running:
            self.reload_mappings(mappings)
        else:
            self.start(mappings)

    def start(self, mappings: list[dict[str, Any]] | None = None):
        """启动计算器"""
        if self._running:
            return
        self._running = True
        self._ensure_executor()
        self.reload_mappings(mappings)
        log.info("PointCalculator started")

    def stop(self):
        """停止计算器"""
        with self._schedule_lock:
            self._running = False
            self._pending_mapping_ids.clear()
            self._latest_context.clear()
        executor = self._executor
        self._executor = None
        if executor:
            executor.shutdown(wait=False, cancel_futures=True)
        log.info("PointCalculator stopped")

    def _ensure_executor(self) -> ThreadPoolExecutor:
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="CalcThread")
        return self._executor

    def _schedule_mapping(self, mapping_id: int, context: ChangeContext | None = None) -> None:
        """合并同一映射的高频变化，避免 ThreadPoolExecutor 队列无界增长。"""
        with self._schedule_lock:
            if not self._running:
                return
            self._latest_context[mapping_id] = context
            if mapping_id in self._pending_mapping_ids:
                return
            self._pending_mapping_ids.add(mapping_id)
        try:
            self._ensure_executor().submit(self._drain_mapping, mapping_id)
        except RuntimeError:
            with self._schedule_lock:
                self._pending_mapping_ids.discard(mapping_id)
                self._latest_context.pop(mapping_id, None)

    def _drain_mapping(self, mapping_id: int) -> None:
        while True:
            with self._schedule_lock:
                if not self._running or mapping_id not in self._latest_context:
                    self._pending_mapping_ids.discard(mapping_id)
                    self._latest_context.pop(mapping_id, None)
                    return
                context = self._latest_context.pop(mapping_id)

            self._execute_calculation(mapping_id, context)

            with self._schedule_lock:
                if self._running and mapping_id in self._latest_context:
                    continue
                self._pending_mapping_ids.discard(mapping_id)
                return

    def reload_mappings(self, mappings: list[dict[str, Any]] | None = None):
        """重新加载映射规则"""
        try:
            # 1. 重置所有测点的锁定状态
            if self.pm:
                for point in self.pm.get_all_points():
                    point.is_locked_by_mapping = False

            if mappings is None:
                mappings = PointMappingService.get_all_mappings()
            # 仅加载目标为当前设备的映射
            self._mappings = [m for m in mappings if m["enable"] and m.get("device_name") == self.device.name]
            self._mapping_by_id = {mapping["id"]: mapping for mapping in self._mappings}
            self._source_points_by_id.clear()
            self._formula_ast_by_id.clear()
            self._build_dependency_map()
            self._subscribe_events()

            # 立即执行所有映射计算，确保值更新，并锁定目标点
            for mapping in self._mappings:
                try:
                    target_code = mapping.get("target_point_code")
                    if target_code:
                        target_point = self.pm.get_point_by_code(target_code)
                        if target_point:
                            target_point.is_locked_by_mapping = True
                            log.info(f"Point {target_code} is now locked by mapping {mapping['id']}")
                except Exception as ex:
                    log.warning(f"Failed to lock target point for mapping {mapping['id']}: {ex}")

                self._schedule_mapping(mapping["id"])

            log.info(f"PointCalculator for {self.device.name} loaded {len(self._mappings)} mappings")
        except Exception as e:
            log.error(f"Failed to reload mappings: {e}")

    def _build_dependency_map(self):
        """构建依赖关系图"""
        self._source_usage.clear()
        self._sender_map.clear()
        for mapping in self._mappings:
            try:
                # source_point_codes 是 List[Dict]
                mapping_id = mapping["id"]
                source_points = json.loads(mapping["source_point_codes"])
                self._source_points_by_id[mapping_id] = source_points
                self._formula_ast_by_id[mapping_id] = ast.parse(mapping["formula"], mode="eval").body
                for point_info in source_points:
                    # 兼容旧格式（如果是字符串列表）
                    if isinstance(point_info, str):
                        continue

                    device_name = point_info.get("device_name")
                    point_code = point_info.get("point_code")

                    if device_name and point_code:
                        key = f"{device_name}:{point_code}"
                        if key not in self._source_usage:
                            self._source_usage[key] = []
                        self._source_usage[key].append(mapping["id"])
            except (json.JSONDecodeError, SyntaxError):
                log.error(f"Invalid source_point_codes JSON for mapping {mapping['id']}")

    def _subscribe_events(self):
        """订阅源测点变化事件"""
        dc = self._device_provider

        if not dc:
            log.warning("DeviceController not ready for PointCalculator subscription")
            return

        for source_key in self._source_usage:
            try:
                device_name, point_code = source_key.split(":", 1)

                # 查找设备
                target_device = dc.device_map.get(device_name)
                if not target_device:
                    if device_name == self.device.name:
                        target_device = self.device
                    else:
                        log.warning(f"Device {device_name} not found for point mapping source")
                        continue

                # 查找测点
                point = target_device.point_manager.get_point_by_code(point_code)
                if point:
                    # 避免重复绑定：blinker 的 connect 会自动处理去重
                    point.value_changed.connect(self.on_source_changed)
                    # 确保测点发出信号
                    point.is_send_signal = True

                    # 注册到 sender_map
                    sender_id = id(point)
                    if sender_id not in self._sender_map:
                        self._sender_map[sender_id] = []

                    # 找到对应的 mapping_ids
                    mapping_ids = self._source_usage.get(source_key, [])
                    for mid in mapping_ids:
                        if mid not in self._sender_map[sender_id]:
                            self._sender_map[sender_id].append(mid)

                    log.info(f"Subscribed to point {point_code} in device {device_name} (ID: {sender_id})")
                else:
                    log.warning(f"Point {point_code} not found in device {device_name}")
            except ValueError:
                log.error(f"Invalid source key format: {source_key}")

    def on_source_changed(self, sender: BasePoint, **kwargs):
        """源测点值变化回调"""
        if not self._running:
            return
        # 尝试从 kwargs 中获取 sender (以防 signal 发送时漏传 sender)
        if not sender:
            log.warning(f"Invalid sender: None. kwargs: {kwargs}")
            sender = kwargs.get("old_point")

        if not sender or not getattr(sender, "code", None):
            log.warning(f"Invalid sender: {sender}")
            return

        # 使用对象的 id 精确查找
        sender_id = id(sender)
        mapping_ids = self._sender_map.get(sender_id, [])

        if not mapping_ids:
            known_ids = list(self._sender_map.keys())
            log.warning(f"Sender {sender.code} (ID: {sender_id}) not found in sender_map. Known IDs: {known_ids}")

        # 捕获当前上下文 (可能是 PROTOCOL, MANUAL 或 SIMULATION)
        context_snapshot = capture_context()

        for mapping_id in set(mapping_ids):  # 去重
            self._schedule_mapping(mapping_id, context_snapshot)

    def _execute_calculation(self, mapping_id: int, context: ChangeContext | None = None):
        """执行计算"""
        # 如果提供了上下文，先还原它
        if context:
            with restore_context(context):
                self._do_execute_calculation(mapping_id)
        else:
            self._do_execute_calculation(mapping_id)

    def _do_execute_calculation(self, mapping_id: int):
        """实际计算逻辑"""
        mapping = self._mapping_by_id.get(mapping_id)
        if not mapping:
            log.error(f"Mapping {mapping_id} not found")
            return

        dc = self._device_provider

        if not dc:
            return

        try:
            target_code = mapping["target_point_code"]
            target_point = self.pm.get_point_by_code(target_code)
            if not target_point:
                log.error(f"Target point {target_code} not found")
                return

            source_points = self._source_points_by_id.get(mapping_id, [])
            formula = mapping["formula"]

            # 准备上下文
            context = {}
            for point_info in source_points:
                if isinstance(point_info, str):  # 兼容旧数据
                    # 假设旧数据只在本机
                    val = 0
                    p = self.pm.get_point_by_code(point_info)
                    if p:
                        val = p.real_value if hasattr(p, "real_value") else p.value
                    context[point_info] = val
                    continue

                dev_name = point_info.get("device_name")
                code = point_info.get("point_code")
                alias = point_info.get("alias", code)

                val = 0
                if dev_name and code:
                    target_dev = dc.device_map.get(dev_name)
                    if target_dev:
                        p = target_dev.point_manager.get_point_by_code(code)
                        if p:
                            val = p.real_value if hasattr(p, "real_value") else p.value

                context[alias] = val

            # 计算
            result = self._safe_eval(self._formula_ast_by_id.get(mapping_id, formula), context)

            # 更新目标点
            if result is not None:
                # 只有值变化且差异够大时才更新，避免无限循环
                current_val = target_point.real_value if hasattr(target_point, "real_value") else target_point.value

                should_update = False
                update_val = result

                # 尝试将 result 转为 float 比较
                try:
                    res_float = float(result)
                    cur_float = float(current_val)
                    if abs(cur_float - res_float) > 1e-6:
                        should_update = True
                        update_val = res_float
                except (ValueError, TypeError):
                    # 如果不是数字，直接比较
                    if current_val != result:
                        should_update = True

                if should_update:
                    # 调用 editPointData 将值写入协议，该方法内会自动更新内存值并记录变更(track_change)
                    try:
                        self.device.editPointData(
                            target_point.code,
                            update_val,
                            source=ChangeSource.MAPPING,
                            detail=f"映射计算 mapping_id={mapping_id}, formula={formula}",
                        )
                    except ValueError as e:
                        log.warning(f"Mapping calculation result invalid for point {target_point.code}: {e}")
                    except Exception as e:
                        log.error(f"Failed to update mapped point {target_point.code}: {e}")

                log.info(f"Setting point {target_point.code} to {result}")
            else:
                log.error(f"Calculation result {result} is not a number")

        except Exception as e:
            log.error(f"Calculation failed for mapping {mapping_id}: {e}")

    def _safe_eval(self, expr: str | ast.AST, context: dict[str, Any]) -> Any:
        """安全评估表达式"""
        try:
            # 1. 替换变量
            # 简单实现：使用 eval 但限制 globals/locals
            # 更好的实现是解析 AST
            node = ast.parse(expr, mode="eval").body if isinstance(expr, str) else expr
            return self._eval_expr(node, context)
        except Exception as e:
            log.warning(f"Eval error: {e}")
            return None

    def _eval_expr(self, node: ast.AST, context: dict[str, Any]) -> Any:
        if isinstance(node, ast.Num):
            return node.n
        elif isinstance(node, ast.Constant):  # python 3.8+
            return node.value
        elif isinstance(node, ast.Name):
            return context.get(node.id, 0)
        elif isinstance(node, ast.BinOp):
            left = self._eval_expr(node.left, context)
            right = self._eval_expr(node.right, context)
            op_func = self._operators.get(type(node.op))
            if op_func:
                return op_func(left, right)
        elif isinstance(node, ast.UnaryOp):
            operand = self._eval_expr(node.operand, context)
            op_func = self._operators.get(type(node.op))
            if op_func:
                return op_func(operand)

        raise ValueError(f"Unsupported operation: {type(node)}")
