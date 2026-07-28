from src.device.core.data.data_exporter import DataExporter
from src.device.core.point.point_manager import PointManager
from src.enums.point_data import Yc


def _point(address: int) -> Yc:
    return Yc(
        rtu_addr=1,
        address=address,
        name=f"DI {address:08X}",
        code=f"0x{address:08X}",
        value=0,
        frame_type=0,
    )


def test_dlt645_prefix_and_settlement_filters():
    manager = PointManager()
    for address in (0x00000000, 0x00000001, 0x01010000, 0x01010001, 0x02010100):
        manager.add_point(1, _point(address))
    exporter = DataExporter(manager)

    assert exporter.get_table_data(1, page_index=None, page_size=None, dlt645_prefix=0)[1] == 2
    assert (
        exporter.get_table_data(
            1,
            page_index=None,
            page_size=None,
            dlt645_prefix=1,
            dlt645_settlement=1,
        )[1]
        == 1
    )
    assert exporter.get_table_data(1, page_index=None, page_size=None, dlt645_prefix=2)[1] == 1
