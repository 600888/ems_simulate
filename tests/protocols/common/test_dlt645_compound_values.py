import asyncio
from datetime import datetime
import struct
from types import SimpleNamespace

from dlt645.common.transform import string_to_bcd
from dlt645.model.types.dlt645_type import Demand
from dlt645.protocol.frame import Frame

from src.device.core.data.data_exporter import DataExporter
from src.device.core.point.point_manager import PointManager
from src.device.core.point.point_operator import _read_result
from src.device.protocol.dlt645_compat import AsyncMeterClientService, _decode_demand_time
from src.device.protocol.dlt645_handler import DLT645ClientHandler, _data_item_display, _primary_numeric
from src.enums.point_data import Yc


def _point() -> Yc:
    return Yc(
        rtu_addr=1,
        address=0x01010000,
        name="最大需量及发生时间",
        code="0x01010000",
        value=0,
        mul_coe=2,
        add_coe=1,
        frame_type=0,
    )


def test_demand_display_keeps_value_and_time_without_double_scaling():
    point = _point()
    item = SimpleNamespace(value=Demand(11.0, datetime(2026, 8, 2, 11, 30, 0)))

    assert _data_item_display(item, point) == "11.0, 2026-08-02 11:30:00"

    # The point model still receives the inverse-scaled register value so that
    # its real_value resolves to the decoded value returned by dlt645.
    point.value = _primary_numeric(item, point)
    assert point.value == 5
    assert point.real_value == 11.0


def test_compound_display_is_exported_as_the_real_value():
    point = _point()
    point.is_valid = True
    point._dlt645_display_extra = "11.0, 2026-08-02 11:30:00"
    manager = PointManager()
    manager.add_point(1, point)

    rows, total = DataExporter(manager).get_table_data(
        1,
        page_index=None,
        page_size=None,
        mask_error=False,
    )

    assert total == 1
    assert rows[0][8] == "11.0, 2026-08-02 11:30:00"
    assert _read_result(point) == "11.0, 2026-08-02 11:30:00"


def test_demand_occurrence_time_uses_dlt645_little_endian_order():
    # On-wire order is minute, hour, day, month, year.
    raw = bytes([0x41, 0x11, 0x02, 0x08, 0x26])
    assert _decode_demand_time(raw) == datetime(2026, 8, 2, 11, 41)


def test_demand_response_is_corrected_before_upstream_date_parsing():
    client = AsyncMeterClientService(None)
    client.address = string_to_bcd("000000000033", "little")
    raw_time = bytes([0x17, 0x21, 0x02, 0x08, 0x26])
    frame = Frame(
        addr=client.address,
        ctrl_code=0x91,
        data=struct.pack("<I", 0x01010001) + bytes([0x00, 0x00, 0x00]) + raw_time,
    )

    item = client.handle_response(frame)

    assert item is not None
    assert item.value.value == 0.0
    assert item.value.time == datetime(2026, 8, 2, 21, 17)
    assert bytes(frame.data[7:12]) == raw_time


def test_client_read_failure_is_not_reported_as_zero_success():
    class FailedClient:
        async def read_01(self, _di):
            return None

    handler = DLT645ClientHandler()
    handler._client = FailedClient()

    assert asyncio.run(handler.read_value_async(_point())) is None


def test_client_read_preserves_demand_value_and_occurrence_time():
    class DemandClient:
        async def read_01(self, _di):
            return SimpleNamespace(value=Demand(11.0, datetime(2026, 8, 2, 11, 41)))

    handler = DLT645ClientHandler()
    handler._client = DemandClient()
    point = _point()

    assert asyncio.run(handler.read_value_async(point)) == 5
    assert point._dlt645_display_extra == "11.0, 2026-08-02 11:41:00"
