"""
数据导出器模块
处理测点数据的导入导出和表格格式化
"""

from typing import Any, Dict, List, Optional, Tuple

from src.device.core.point_manager import PointManager
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
        ]

    def get_table_data(
        self,
        slave_id: int,
        name: Optional[str] = None,
        page_index: Optional[int] = 1,
        page_size: Optional[int] = 10,
        point_types: Optional[List[int]] = None,
    ) -> Tuple[List[List[str]], int]:
        """获取表格数据
        
        Args:
            slave_id: 从机 ID
            name: 名称筛选
            page_index: 页码
            page_size: 每页大小
            point_types: 点类型列表
            
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
                    table_data.append(self._format_yc_row(yc, frame_type_dict))

        # 处理遥信数据
        if 1 in point_types:
            for yx in yx_list:
                if name is None or name in str(yx.name):
                    table_data.append(self._format_yx_row(yx, frame_type_dict))

        # 处理遥控数据
        if 2 in point_types:
            for yk in yk_list:
                if name is None or name in str(yk.name):
                    table_data.append(self._format_yx_row(yk, frame_type_dict))

        # 处理遥调数据
        if 3 in point_types:
            for yt in yt_list:
                if name is None or name in str(yt.name):
                    table_data.append(self._format_yc_row(yt, frame_type_dict))

        total = len(table_data)

        if page_index is None or page_size is None:
            return table_data, total

        # 分页
        start = (page_index - 1) * page_size
        end = start + page_size
        return table_data[start:end], total

    def _format_yc_row(
        self, point: Yc, frame_type_dict: Dict[int, str]
    ) -> List[str]:
        """格式化遥测/遥调行"""
        return [
            str(point.address),
            str(point.hex_address),
            "",
            str(point.func_code),
            str(point.decode),
            str(point.name),
            str(point.code),
            str(point.hex_value),
            str(point.real_value),
            str(point.mul_coe),
            str(point.add_coe),
            str(frame_type_dict.get(point.frame_type, "")),
        ]

    def _format_yx_row(
        self, point: Yx, frame_type_dict: Dict[int, str]
    ) -> List[str]:
        """格式化遥信/遥控行"""
        bit = point.bit if hasattr(point, "bit") else 0
        return [
            str(point.address),
            str(point.hex_address),
            str(bit),
            str(point.func_code),
            str(point.decode),
            str(point.name),
            str(point.code),
            str(point.hex_value),
            str(int(point.value)),
            "1.0",
            "0",
            str(frame_type_dict.get(point.frame_type, "")),
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
