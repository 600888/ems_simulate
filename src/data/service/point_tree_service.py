from src.device_controller import get_device_controller
from src.enums.modbus_def import ProtocolType
from src.enums.points.base_point import BasePoint
from src.log import log
from src.web.api.schemas.tree import DeviceNode, GroupNode, PointLeaf, TypeNode


class PointTreeService:
    # DLT645 数据标识前缀定义（与侧边栏 buildDlt645Children 一致）
    DLT645_PREFIX_DEFS = [
        (0, "电能量", True),
        (1, "最大需量及发生时间", True),
        (2, "变量", False),
        (3, "事件记录", False),
        (4, "参变量", False),
    ]

    @staticmethod
    async def get_tree(device_name: str | None = None) -> list[DeviceNode]:
        """获取测点树，可只返回指定设备的测点"""
        devices_node_list: list[DeviceNode] = []

        try:
            dc = await get_device_controller()

            # 遍历所有活动设备
            for device in dc.device_list:
                # 按设备名过滤（可选）
                if device_name and device.name != device_name:
                    continue
                # 获取设备名称
                device_label = device.name or f"Device_{device.device_id}"

                # 初始化类型节点
                # 使用列表来保持顺序: YC, YX, YT, YK
                type_nodes_map = {
                    "YC": TypeNode(label="遥测", children=[]),
                    "YX": TypeNode(label="遥信", children=[]),
                    "YT": TypeNode(label="遥调", children=[]),
                    "YK": TypeNode(label="遥控", children=[]),
                }

                # 辅助函数：添加测点
                def add_points(points, type_key):
                    if not points:
                        return
                    for p in points:
                        leaf = PointTreeService._create_leaf(p, type_key)
                        type_nodes_map[type_key].children.append(leaf)  # noqa: B023

                # 遥测：DLT645 设备按数据标识前缀/结算日分组（与侧边栏一致）
                is_dlt645 = device.protocol_type in (
                    ProtocolType.Dlt645Server,
                    ProtocolType.Dlt645Client,
                )
                if is_dlt645:
                    yc_points = []
                    for _, points in device.yc_dict.items():
                        yc_points.extend(points)
                    if yc_points:
                        type_nodes_map["YC"].children = PointTreeService._build_dlt645_yc_groups(yc_points)
                else:
                    for _, points in device.yc_dict.items():
                        add_points(points, "YC")

                # 遥信
                for _, points in device.yx_dict.items():
                    add_points(points, "YX")

                # 遥调
                for _, points in device.point_manager.yt_dict.items():
                    add_points(points, "YT")

                # 遥控
                for _, points in device.point_manager.yk_dict.items():
                    add_points(points, "YK")

                # 收集非空类型节点
                children = []
                # 按顺序检查
                if type_nodes_map["YC"].children:
                    children.append(type_nodes_map["YC"])
                if type_nodes_map["YX"].children:
                    children.append(type_nodes_map["YX"])
                if type_nodes_map["YT"].children:
                    children.append(type_nodes_map["YT"])
                if type_nodes_map["YK"].children:
                    children.append(type_nodes_map["YK"])

                if children:
                    devices_node_list.append(DeviceNode(label=device_label, children=children))

        except Exception as e:
            log.error(f"Failed to build point tree: {e}")

        return devices_node_list

    @staticmethod
    def _create_leaf(point: BasePoint, type_label: str) -> PointLeaf:
        """创建测点叶子节点"""
        # 获取值：优先 real_value
        val = point.real_value

        return PointLeaf(
            code=point.code,
            name=point.name,
            value=val,
            rtu_addr=point.rtu_addr,
            reg_addr=str(point.hex_address),
            type=type_label,
        )

    @staticmethod
    def _dlt645_branch(point: BasePoint) -> tuple[int, int]:
        """解析 DLT645 测点地址：高 8 位 = 数据标识前缀(0-4)，低 8 位 = 结算日(0=当前,1-12=上N结算日)

        与 data_exporter.matches_dlt645_branch 的解析方式保持一致。
        """
        address = point.address
        if isinstance(address, str):
            try:
                address = int(address, 16)
            except (TypeError, ValueError):
                return -1, 0
        if not isinstance(address, int):
            return -1, 0
        return (address >> 24) & 0xFF, address & 0xFF

    @staticmethod
    def _build_dlt645_yc_groups(points: list[BasePoint]) -> list[GroupNode]:
        """按数据标识前缀 → 结算日 构建 DLT645 遥测分组（与侧边栏结构一致）"""
        prefix_map: dict[int, list[BasePoint]] = {}
        for p in points:
            prefix, _ = PointTreeService._dlt645_branch(p)
            if prefix < 0:
                continue
            prefix_map.setdefault(prefix, []).append(p)

        groups: list[GroupNode] = []
        for prefix, label, has_settlement in PointTreeService.DLT645_PREFIX_DEFS:
            pts = prefix_map.get(prefix)
            if not pts:
                continue
            if has_settlement:
                settlement_map: dict[int, list[BasePoint]] = {}
                for p in pts:
                    _, settlement = PointTreeService._dlt645_branch(p)
                    settlement_map.setdefault(settlement, []).append(p)
                settlement_groups = []
                for settlement in sorted(settlement_map):
                    settlement_groups.append(
                        GroupNode(
                            label="当前" if settlement == 0 else f"上{settlement}结算日",
                            dlt645_prefix=prefix,
                            dlt645_settlement=settlement,
                            children=[PointTreeService._create_leaf(p, "YC") for p in settlement_map[settlement]],
                        )
                    )
                groups.append(GroupNode(label=label, dlt645_prefix=prefix, children=settlement_groups))
            else:
                groups.append(
                    GroupNode(
                        label=label,
                        dlt645_prefix=prefix,
                        children=[PointTreeService._create_leaf(p, "YC") for p in pts],
                    )
                )
        return groups
