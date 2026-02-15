from typing import List, Dict, Any
from src.web.schemas.schemas_tree import DeviceNode, TypeNode, PointLeaf
from src.device_controller import get_device_controller
from src.enums.points.base_point import BasePoint
from src.log import log

class PointTreeService:
    @staticmethod
    async def get_tree() -> List[DeviceNode]:
        """获取系统测点树"""
        devices_node_list: List[DeviceNode] = []
        
        try:
            dc = await get_device_controller()
            
            # 遍历所有活动设备
            for device in dc.device_list:
                # 获取设备名称
                device_label = device.name or f"Device_{device.device_id}"
                
                # 初始化类型节点
                # 使用列表来保持顺序: YC, YX, YT, YK
                type_nodes_map = {
                    "YC": TypeNode(label="遥测", children=[]),
                    "YX": TypeNode(label="遥信", children=[]),
                    "YT": TypeNode(label="遥调", children=[]),
                    "YK": TypeNode(label="遥控", children=[])
                }
                
                # 辅助函数：添加测点
                def add_points(points, type_key):
                    if not points: return
                    for p in points:
                        leaf = PointTreeService._create_leaf(p, type_key)
                        type_nodes_map[type_key].children.append(leaf)

                # 遥测
                for _, points in device.yc_dict.items():
                    add_points(points, "YC")
                
                # 遥信
                for _, points in device.yx_dict.items():
                    add_points(points, "YX")
                        
                # 遥调
                # PointManager 中维护了所有类型的字典
                if hasattr(device.point_manager, 'yt_dict'):
                    for _, points in device.point_manager.yt_dict.items():
                        add_points(points, "YT")
                        
                # 遥控
                if hasattr(device.point_manager, 'yk_dict'):
                    for _, points in device.point_manager.yk_dict.items():
                        add_points(points, "YK")
                
                # 收集非空类型节点
                children = []
                # 按顺序检查
                if type_nodes_map["YC"].children: children.append(type_nodes_map["YC"])
                if type_nodes_map["YX"].children: children.append(type_nodes_map["YX"])
                if type_nodes_map["YT"].children: children.append(type_nodes_map["YT"])
                if type_nodes_map["YK"].children: children.append(type_nodes_map["YK"])
                
                if children:
                    devices_node_list.append(DeviceNode(label=device_label, children=children))
                    
        except Exception as e:
            log.error(f"Failed to build point tree: {e}")
            
        return devices_node_list

    @staticmethod
    def _create_leaf(point: BasePoint, type_label: str) -> PointLeaf:
        """创建测点叶子节点"""
        # 获取值：优先 real_value
        val = point.real_value if hasattr(point, 'real_value') else point.value
        
        return PointLeaf(
            code=point.code,
            name=point.name,
            value=val,
            rtu_addr=point.rtu_addr,
            reg_addr=str(point.hex_address),
            type=type_label
        )
