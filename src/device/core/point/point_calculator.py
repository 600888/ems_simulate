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
        self._source_usage: Dict[str, List[int]] = {}  # source_code -> [mapping_ids]
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="CalcThread")
        
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
            mappings = PointMappingService.get_all_mappings()
            # 仅加载目标为当前设备的映射
            self._mappings = [
                m for m in mappings 
                if m['enable'] and m.get('device_name') == self.device.name
            ]
            self._build_dependency_map()
            self._subscribe_events()
            log.info(f"PointCalculator for {self.device.name} loaded {len(self._mappings)} mappings")
        except Exception as e:
            log.error(f"Failed to reload mappings: {e}")

    def _build_dependency_map(self):
        """构建依赖关系图"""
        self._source_usage.clear()
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
        from src.device_controller import get_device_controller
        import asyncio
        
        # 由于 device_controller 是异步初始化的，这里可能需要等待或者假设已初始化
        # 简单起见，尝试直接获取
        try:
            # get_device_controller 是异步的，但通常实例已存在
            # 这里的代码是在同步上下文中运行的，我们暂时 hack 一下
            # 或者直接从 global 获取（如果有的话），device_controller 模块有一个全局变量
            from src.device_controller import device_controller
            dc = device_controller
        except ImportError:
            dc = None
            
        if not dc:
            log.warning("DeviceController not ready for PointCalculator subscription")
            return

        for source_key in self._source_usage.keys():
            try:
                device_name, point_code = source_key.split(':', 1)
                
                # 查找设备
                target_device = dc.device_map.get(device_name)
                if not target_device:
                    # 可能是当前设备？虽然通常当前设备也在 device_map 中
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
                else:
                    log.warning(f"Point {point_code} not found in device {device_name}")
            except ValueError:
                log.error(f"Invalid source key format: {source_key}")

    def on_source_changed(self, sender: BasePoint, **kwargs):
        """源测点值变化回调"""
        if not sender or not sender.code:
            return
            
        mapping_ids = self._source_usage.get(sender.code, [])
        for mapping_id in mapping_ids:
            self._executor.submit(self._execute_calculation, mapping_id)

    def _execute_calculation(self, mapping_id: int):
        """执行计算"""
        mapping = next((m for m in self._mappings if m['id'] == mapping_id), None)
        if not mapping:
            return

        from src.device_controller import device_controller
        dc = device_controller

        if not dc:
            return

        try:
            target_code = mapping['target_point_code']
            target_point = self.pm.get_point_by_code(target_code)
            if not target_point:
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

        except Exception as e:
            log.warning(f"Calculation failed for mapping {mapping_id}: {e}")

        except Exception as e:
            log.warning(f"Calculation failed for mapping {mapping_id}: {e}")

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
