"""
测点计算器
负责管理和执行测点映射计算
"""
import json
import ast
import operator
from typing import Dict, List, Set, Any, Optional, Callable
from concurrent.futures import ThreadPoolExecutor

from src.device.core.point.point_manager import PointManager
from src.data.service.point_mapping_service import PointMappingService
from src.enums.points.base_point import BasePoint
from src.log import log


class PointCalculator:
    """测点计算器"""

    def __init__(self, device):
        self.device = device
        self.pm = device.point_manager
        self._mappings: List[Dict[str, Any]] = []
        self._source_usage: Dict[str, List[int]] = {}  # source_code -> [mapping_ids] (DEPRECATED: still used for debug or display)
        self._sender_map: Dict[int, List[int]] = {}  # id(sender) -> [mapping_ids]
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="CalcThread")
        self._device_provider: Any = None 
        
        # 受限的操作符映射
        self._operators: Dict[type, Callable] = {
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

    def set_device_provider(self, provider: Any):
        """设置设备提供者"""
        self._device_provider = provider
        # 立即启动计算器（加载映射并订阅事件）
        self.start()

    def start(self):
        """启动计算器"""
        self.reload_mappings()
        log.info("PointCalculator started")

    def stop(self):
        """停止计算器"""
        if self._executor:
            self._executor.shutdown(wait=False)
        log.info("PointCalculator stopped")

    def reload_mappings(self):
        """重新加载映射规则"""
        try:
            # 1. 重置所有测点的锁定状态
            if self.pm:
                for point in self.pm.get_all_points():
                    point.is_locked_by_mapping = False

            mappings = PointMappingService.get_all_mappings()
            # 仅加载目标为当前设备的映射
            self._mappings = [
                m for m in mappings 
                if m['enable'] and m.get('device_name') == self.device.name
            ]
            self._build_dependency_map()
            self._subscribe_events()
            
            # 立即执行所有映射计算，确保值更新，并锁定目标点
            for mapping in self._mappings:
                try:
                    target_code = mapping.get('target_point_code')
                    if target_code:
                        target_point = self.pm.get_point_by_code(target_code)
                        if target_point:
                            target_point.is_locked_by_mapping = True
                            log.info(f"Point {target_code} is now locked by mapping {mapping['id']}")
                except Exception as ex:
                    log.warning(f"Failed to lock target point for mapping {mapping['id']}: {ex}")

                self._executor.submit(self._execute_calculation, mapping['id'])

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
                source_points = json.loads(mapping['source_point_codes'])
                for point_info in source_points:
                    # 兼容旧格式（如果是字符串列表）
                    if isinstance(point_info, str):
                        continue
                    
                    device_name = point_info.get('device_name')
                    point_code = point_info.get('point_code')
                    
                    if device_name and point_code:
                        key = f"{device_name}:{point_code}"
                        if key not in self._source_usage:
                            self._source_usage[key] = []
                        self._source_usage[key].append(mapping['id'])
            except json.JSONDecodeError:
                log.error(f"Invalid source_point_codes JSON for mapping {mapping['id']}")

    def _subscribe_events(self):
        """订阅源测点变化事件"""
        dc = self._device_provider
        
        if not dc:
            log.warning("DeviceController not ready for PointCalculator subscription")
            return

        for source_key in self._source_usage.keys():
            try:
                device_name, point_code = source_key.split(':', 1)
                
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
        # 尝试从 kwargs 中获取 sender (以防 signal 发送时漏传 sender)
        if not sender:
            log.warning(f"Invalid sender: None. kwargs: {kwargs}")
            sender = kwargs.get('old_point')

        if not sender or not getattr(sender, 'code', None):
            log.warning(f"Invalid sender: {sender}")
            return
            
        # 使用对象的 id 精确查找
        sender_id = id(sender)
        mapping_ids = self._sender_map.get(sender_id, [])
        
        if not mapping_ids:
             log.warning(f"Sender {sender.code} (ID: {sender_id}) not found in sender_map. Known IDs: {list(self._sender_map.keys())}")

        for mapping_id in set(mapping_ids): # 去重
            self._executor.submit(self._execute_calculation, mapping_id)

    def _execute_calculation(self, mapping_id: int):
        """执行计算"""
        mapping = next((m for m in self._mappings if m['id'] == mapping_id), None)
        if not mapping:
            log.error(f"Mapping {mapping_id} not found")
            return

        dc = self._device_provider

        if not dc:
            return

        try:
            target_code = mapping['target_point_code']
            target_point = self.pm.get_point_by_code(target_code)
            if not target_point:
                log.error(f"Target point {target_code} not found")
                return

            source_points = json.loads(mapping['source_point_codes'])
            formula = mapping['formula']
            
            # 准备上下文
            context = {}
            for point_info in source_points:
                if isinstance(point_info, str): # 兼容旧数据
                     # 假设旧数据只在本机
                     val = 0
                     p = self.pm.get_point_by_code(point_info)
                     if p:
                         val = p.real_value if hasattr(p, 'real_value') else p.value
                     context[point_info] = val
                     continue

                dev_name = point_info.get('device_name')
                code = point_info.get('point_code')
                alias = point_info.get('alias', code)
                
                val = 0
                if dev_name and code:
                    target_dev = dc.device_map.get(dev_name)
                    if target_dev:
                        p = target_dev.point_manager.get_point_by_code(code)
                        if p:
                             val = p.real_value if hasattr(p, 'real_value') else p.value
                
                context[alias] = val

            # 计算
            result = self._safe_eval(formula, context)
            
            # 更新目标点
            if result is not None:
                # 只有值变化且差异够大时才更新，避免无限循环
                current_val = target_point.real_value if hasattr(target_point, 'real_value') else target_point.value
                
                # 尝试将 result 转为 float 比较
                try:
                    res_float = float(result)
                    cur_float = float(current_val)
                    if abs(cur_float - res_float) > 1e-6:
                        if hasattr(target_point, 'set_real_value'):
                            target_point.set_real_value(res_float)
                        else:
                            target_point.value = int(res_float)
                except (ValueError, TypeError):
                    # 如果不是数字，直接比较
                    if current_val != result:
                         if hasattr(target_point, 'set_real_value'):
                            target_point.set_real_value(result)
                         else:
                            # 尽力而为
                            try: 
                                target_point.value = int(result)
                            except:
                                pass
                log.info(f"Setting point {target_point.code} to {result}")
            else:
                log.error(f"Calculation result {result} is not a number")

        except Exception as e:
            log.error(f"Calculation failed for mapping {mapping_id}: {e}")

    def _safe_eval(self, expr: str, context: Dict[str, Any]) -> Any:
        """安全评估表达式"""
        try:
            # 1. 替换变量
            # 简单实现：使用 eval 但限制 globals/locals
            # 更好的实现是解析 AST
            return self._eval_expr(ast.parse(expr, mode='eval').body, context)
        except Exception as e:
            log.warning(f"Eval error: {e}")
            return None

    def _eval_expr(self, node: ast.AST, context: Dict[str, Any]) -> Any:
        if isinstance(node, ast.Num):
            return node.n
        elif isinstance(node, ast.Constant): # python 3.8+
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
