"""
数据导出器模块
处理测点数据的导入导出和表格格式化
"""

from src.device.core.point.point_manager import PointManager
from src.enums.point_data import BasePoint, Yc, Yx


class DataExporter:
    """数据导出器"""

    DNP3_POINT_TYPES = {
        0: "Analog Input",
        1: "Binary Input",
        2: "Binary Output",
        3: "Analog Output",
    }

    def __init__(self, point_manager: PointManager):
        self._point_manager = point_manager

    def get_table_head(self) -> list[str]:
        """获取表格头部列名"""
        return [
            "地址",
            "16进制地址",
            "位",
            "功能码",
            "解析码",
            "测点名称",
            "测点编码",
            "寄存器值",
            "真实值",
            "乘法系数",
            "加法系数",
            "帧类型",
            "IEC104类型",
            "状态",
            "FC",
        ]

    def get_table_data(
        self,
        slave_id: int,
        name: str | None = None,
        page_index: int | None = 1,
        page_size: int | None = 10,
        point_types: list[int] | None = None,
        mask_error: bool = True,
        order_by: str | None = None,
        order_direction: str | None = None,
        iec104_types: list[str] | None = None,
        dlt645_prefix: int | None = None,
        dlt645_settlement: int | None = None,
        dnp3_event_class: int | None = None,
        dnp3_event_enabled: bool | None = None,
        include_dnp3_point_type: bool = False,
        include_dnp3_event_class: bool = False,
    ) -> tuple[list[list[str]], int]:
        """获取表格数据

        Args:
            slave_id: 从机 ID
            name: 名称筛选
            page_index: 页码
            page_size: 每页大小
            point_types: 点类型列表
            mask_error: 是否隐藏无效数据(错误/未知)
            order_by: 排序字段 (地址, 功能码, 解析码)
            order_direction: 排序方向 (ascending, descending)
            iec104_types: IEC104 ASDU 类型标识列表
            dnp3_event_class: DNP3 事件类别（1、2 或 3）
            dnp3_event_enabled: DNP3 测点是否产生事件
            include_dnp3_point_type: 是否在每行末尾附加 DNP3 点位类型
            include_dnp3_event_class: 是否在每行末尾附加 DNP3 事件类别

        Returns:
            (数据列表, 总数)
        """
        if point_types is None or len(point_types) == 0:
            point_types = [0, 1, 2, 3]

        yc_list, yx_list, yt_list, yk_list = self._point_manager.get_points_by_slave(slave_id)

        def matches_iec104_type(point: BasePoint) -> bool:
            return not iec104_types or point.iec_type_id in iec104_types

        def matches_dlt645_branch(point: BasePoint) -> bool:
            if dlt645_prefix is None:
                return True
            try:
                address = int(point.address)
            except (TypeError, ValueError):
                return False
            if (address >> 24) != dlt645_prefix:
                return False
            return dlt645_settlement is None or (address & 0xFF) == dlt645_settlement

        def get_dnp3_event(point: BasePoint) -> tuple[bool, int]:
            config = getattr(point, "dnp3_config", None)
            if not isinstance(config, dict):
                config = {}
            frame_type = int(getattr(point, "frame_type", 0))
            event_enabled = bool(config.get("event_enabled", frame_type in (0, 1)))
            try:
                event_class = int(config.get("event_class", 2 if frame_type in (2, 3) else 1))
            except (TypeError, ValueError):
                event_class = 1
            return event_enabled, event_class

        def matches_dnp3_event(point: BasePoint) -> bool:
            event_enabled, event_class = get_dnp3_event(point)

            if dnp3_event_enabled is not None and event_enabled is not dnp3_event_enabled:
                return False
            return dnp3_event_class is None or event_class == dnp3_event_class

        # 先筛选和排序轻量的测点对象，分页后只格式化当前页。
        # 大通道不再为一页少量数据构造数万行字符串。
        matched_points: list[tuple[BasePoint, bool]] = []
        frame_type_dict = PointManager.frame_type_dict()
        has_dnp3_event_filter = dnp3_event_class is not None or dnp3_event_enabled is not None

        def append_matches(points: list[BasePoint], is_analog: bool) -> None:
            for point in points:
                if (
                    (name is None or name in str(point.name))
                    and matches_iec104_type(point)
                    and matches_dlt645_branch(point)
                    and (not has_dnp3_event_filter or matches_dnp3_event(point))
                ):
                    matched_points.append((point, is_analog))

        # 处理遥测数据
        if 0 in point_types:
            append_matches(yc_list, True)

        # 处理遥信数据
        if 1 in point_types:
            append_matches(yx_list, False)

        # 处理遥控数据
        if 2 in point_types:
            append_matches(yk_list, False)

        # 处理遥调数据
        if 3 in point_types:
            append_matches(yt_list, True)

        def address_sort_key(item: tuple[BasePoint, bool]) -> int:
            address = str(item[0].address)
            return int(address) if address.isdigit() else 0

        def function_sort_key(item: tuple[BasePoint, bool]) -> int:
            function_code = str(item[0].func_code)
            return int(function_code) if function_code.isdigit() else 0

        def decode_sort_key(item: tuple[BasePoint, bool]) -> str:
            return str(item[0].decode)

        # Optional custom sorting
        sort_key = address_sort_key
        is_reverse = False
        if order_by and order_direction:
            is_reverse = order_direction == "descending"
            if order_by == "地址":
                sort_key = address_sort_key
            elif order_by == "功能码":
                sort_key = function_sort_key
            elif order_by == "解析码":
                sort_key = decode_sort_key
            else:
                is_reverse = False
        matched_points.sort(key=sort_key, reverse=is_reverse)

        total = len(matched_points)

        if page_index is not None and page_size is not None:
            start = (page_index - 1) * page_size
            matched_points = matched_points[start : start + page_size]

        table_data: list[list[str]] = []
        for point, is_analog in matched_points:
            row = (
                self._format_yc_row(point, frame_type_dict, mask_error)
                if is_analog
                else self._format_yx_row(point, frame_type_dict, mask_error)
            )
            if include_dnp3_point_type:
                row.append(self.DNP3_POINT_TYPES.get(int(getattr(point, "frame_type", 0)), ""))
            if include_dnp3_event_class:
                event_enabled, event_class = get_dnp3_event(point)
                row.append(f"class{event_class}" if event_enabled else "none")
            table_data.append(row)
        return table_data, total

    def _format_yc_row(self, point: Yc, frame_type_dict: dict[int, str], mask_error: bool = True) -> list[str]:
        """格式化遥测/遥调行"""
        is_valid = point.is_valid

        status = "未知"
        if is_valid is True:
            status = "成功"
        elif is_valid is False:
            status = "失败"

        # 仅当 mask_error 为 True 且数据无效时，才隐藏数值
        if mask_error and (is_valid is None or is_valid is False):
            reg_val = ""
            real_val = ""
        else:
            reg_val = str(point.hex_value)
            # IEC61850: FC=DC 的 DA 为描述/元数据 (如 dU, d, cDCnam), 真实值返回描述文本
            point_fc = getattr(point, "fc", "") or ""
            # DLT645 复合 DI（如最大需量及其发生时间）的完整显示值，逗号分隔
            dlt645_display = getattr(point, "_dlt645_display_extra", None)
            if dlt645_display is not None:
                real_val = str(dlt645_display)
            elif point_fc == "DC":
                real_val = str(point.name)
            else:
                real_val = str(point.real_value)

        # 获取 IEC104 类型标识（发 type_id，前端用 i18n key 翻译）
        iec_type_label = str(point.iec_type_id) if point.iec_type_id else ""

        return [
            str(point.address),
            str(point.hex_address),
            "",
            str(point.func_code),
            str(point.decode),
            str(point.name),
            str(point.code),
            reg_val,
            real_val,
            str(point.mul_coe),
            str(point.add_coe),
            str(frame_type_dict.get(point.frame_type, "")),
            iec_type_label,
            status,
            str(getattr(point, "fc", "") or ""),
        ]

    def _format_yx_row(self, point: Yx, frame_type_dict: dict[int, str], mask_error: bool = True) -> list[str]:
        """格式化遥信/遥控行"""
        bit = point.bit
        is_valid = point.is_valid

        status = "未知"
        if is_valid is True:
            status = "成功"
        elif is_valid is False:
            status = "失败"

        if mask_error and (is_valid is None or is_valid is False):
            reg_val = ""
            real_val = ""
        else:
            reg_val = str(point.hex_value)
            # IEC61850: FC=DC 的 DA 为描述/元数据 (如 dU, d, cDCnam), 真实值返回描述文本
            point_fc = getattr(point, "fc", "") or ""
            if point_fc == "DC":
                real_val = str(point.name)
            else:
                real_val = str(int(point.value))

        # 获取 IEC104 类型标识（发 type_id，前端用 i18n key 翻译）
        iec_type_label = str(point.iec_type_id) if point.iec_type_id else ""

        return [
            str(point.address),
            str(point.hex_address),
            str(bit),
            str(point.func_code),
            str(point.decode),
            str(point.name),
            str(point.code),
            reg_val,
            real_val,
            "1.0",
            "0",
            str(frame_type_dict.get(point.frame_type, "")),
            iec_type_label,
            status,
            str(getattr(point, "fc", "") or ""),
        ]

    def export_csv(self, file_path: str) -> None:
        """导出到 CSV 文件"""
        from src.tools.export_point import PointExporter

        # 创建兼容的设备对象
        class CompatDevice:
            def __init__(self, pm: PointManager):
                self.yc_dict = pm.yc_dict
                self.yx_dict = pm.yx_dict
                self.slave_id_list = pm.slave_id_list

        compat_device = CompatDevice(self._point_manager)
        exporter = PointExporter(device=compat_device, file_path=file_path)
        exporter.exportDataPointCsv(file_path)

    def export_xlsx(self, file_path: str) -> None:
        """导出到 Excel 文件"""
        from src.tools.export_point import PointExporter

        class CompatDevice:
            def __init__(self, pm: PointManager):
                self.yc_dict = pm.yc_dict
                self.yx_dict = pm.yx_dict
                self.slave_id_list = pm.slave_id_list

        compat_device = CompatDevice(self._point_manager)
        exporter = PointExporter(device=compat_device, file_path=file_path)
        exporter.exportDataPointXlsx(file_path)

    def import_csv(self, file_path: str) -> None:
        """从 CSV 文件导入"""
        from src.tools.import_point import PointImporter

        class CompatDevice:
            def __init__(self, pm: PointManager):
                self.yc_dict = pm.yc_dict
                self.yx_dict = pm.yx_dict
                self.slave_id_list = pm.slave_id_list
                self.codeToDataPointMap = pm.code_map

        compat_device = CompatDevice(self._point_manager)
        importer = PointImporter(device=compat_device, file_name=file_path)
        importer.importDataPointCsv()
