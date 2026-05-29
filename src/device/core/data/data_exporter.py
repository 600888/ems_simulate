"""
数据导出器模块
处理测点数据的导入导出和表格格式化
"""

from typing import Any, Dict, List, Optional, Tuple

from src.device.core.point.point_manager import PointManager
from src.enums.point_data import Yc, Yx, Yt, Yk


class DataExporter:
    """数据导出器"""

    def __init__(self, point_manager: PointManager):
        self._point_manager = point_manager

    def get_table_head(self) -> List[str]:
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
        name: Optional[str] = None,
        page_index: Optional[int] = 1,
        page_size: Optional[int] = 10,
        point_types: Optional[List[int]] = None,
        mask_error: bool = True,
        order_by: Optional[str] = None,
        order_direction: Optional[str] = None,
    ) -> Tuple[List[List[str]], int]:
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
            
        Returns:
            (数据列表, 总数)
        """
        if point_types is None or len(point_types) == 0:
            point_types = [0, 1, 2, 3]

        yc_list, yx_list, yt_list, yk_list = self._point_manager.get_points_by_slave(
            slave_id
        )

        table_data: List[List[str]] = []
        frame_type_dict = PointManager.frame_type_dict()

        # 处理遥测数据
        if 0 in point_types:
            for yc in yc_list:
                if name is None or name in str(yc.name):
                    table_data.append(self._format_yc_row(yc, frame_type_dict, mask_error))

        # 处理遥信数据
        if 1 in point_types:
            for yx in yx_list:
                if name is None or name in str(yx.name):
                    table_data.append(self._format_yx_row(yx, frame_type_dict, mask_error))

        # 处理遥控数据
        if 2 in point_types:
            for yk in yk_list:
                if name is None or name in str(yk.name):
                    table_data.append(self._format_yx_row(yk, frame_type_dict, mask_error))

        # 处理遥调数据
        if 3 in point_types:
            for yt in yt_list:
                if name is None or name in str(yt.name):
                    table_data.append(self._format_yc_row(yt, frame_type_dict, mask_error))

        # Default sorting by address
        def default_sort_key(row):
            return int(row[0]) if row[0].isdigit() else 0

        # Optional custom sorting
        if order_by and order_direction:
            is_reverse = order_direction == "descending"
            if order_by == "地址":
                table_data.sort(key=default_sort_key, reverse=is_reverse)
            elif order_by == "功能码":
                table_data.sort(key=lambda row: int(row[3]) if row[3].isdigit() else 0, reverse=is_reverse)
            elif order_by == "解析码":
                table_data.sort(key=lambda row: row[4], reverse=is_reverse)
            else:
                table_data.sort(key=default_sort_key)
        else:
            # 默认按地址排序
            table_data.sort(key=default_sort_key)

        total = len(table_data)

        if page_index is None or page_size is None:
            return table_data, total

        # 分页
        start = (page_index - 1) * page_size
        end = start + page_size
        return table_data[start:end], total

    def _format_yc_row(
        self, point: Yc, frame_type_dict: Dict[int, str], mask_error: bool = True
    ) -> List[str]:
        """格式化遥测/遥调行"""
        is_valid = point.is_valid if hasattr(point, "is_valid") else None
        
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
            point_fc = getattr(point, 'fc', '') or ''
            if point_fc == 'DC':
                real_val = str(point.name)
            else:
                real_val = str(point.real_value)
        
        # 获取 IEC104 类型标识（发 type_id，前端用 i18n key 翻译）
        iec_type_label = ""
        if hasattr(point, "iec_type_id") and point.iec_type_id:
            iec_type_label = point.iec_type_id

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
            str(getattr(point, 'fc', '') or ''),
        ]

    def _format_yx_row(
        self, point: Yx, frame_type_dict: Dict[int, str], mask_error: bool = True
    ) -> List[str]:
        """格式化遥信/遥控行"""
        bit = point.bit if hasattr(point, "bit") else 0
        is_valid = point.is_valid if hasattr(point, "is_valid") else None
        
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
            point_fc = getattr(point, 'fc', '') or ''
            if point_fc == 'DC':
                real_val = str(point.name)
            else:
                real_val = str(int(point.value))

        # 获取 IEC104 类型标识（发 type_id，前端用 i18n key 翻译）
        iec_type_label = ""
        if hasattr(point, "iec_type_id") and point.iec_type_id:
            iec_type_label = point.iec_type_id

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
            str(getattr(point, 'fc', '') or ''),
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
