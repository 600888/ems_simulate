from types import SimpleNamespace
from unittest.mock import MagicMock

from src.device.core.data.data_exporter import DataExporter


def test_iec104_type_filter_is_applied_before_pagination() -> None:
    points = [
        SimpleNamespace(address=1, name="p1", iec_type_id="M_ME_NC_1"),
        SimpleNamespace(address=2, name="p2", iec_type_id="M_SP_NA_1"),
        SimpleNamespace(address=3, name="p3", iec_type_id="M_SP_NA_1"),
        SimpleNamespace(address=4, name="p4", iec_type_id="M_SP_NA_1"),
    ]
    point_manager = MagicMock()
    point_manager.get_points_by_slave.return_value = (points, [], [], [])
    exporter = DataExporter(point_manager)
    exporter._format_yc_row = MagicMock(side_effect=lambda point, _frame_types, _mask_error: [str(point.address)])

    rows, total = exporter.get_table_data(
        slave_id=1,
        page_index=1,
        page_size=2,
        point_types=[0],
        iec104_types=["M_SP_NA_1"],
    )

    assert rows == [["2"], ["3"]]
    assert total == 3
