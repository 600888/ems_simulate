import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.device.core.data.data_reader import DataReader
from src.device.protocol.dnp3_handler import DNP3ClientHandler


def _device(handler):
    return SimpleNamespace(
        protocol_handler=handler,
        serial_port="",
        ip="127.0.0.1",
        port=20000,
        _logger=Mock(),
        log=Mock(),
    )


@pytest.mark.asyncio
async def test_dnp3_data_reader_uses_protocol_batch_path():
    handler = DNP3ClientHandler()
    handler.read_points_batch_async = AsyncMock(return_value={"AI-1": 10.5, "BI-2": 1})
    analog = SimpleNamespace(code="AI-1", address=1, frame_type=0, value=None, is_valid=False)
    binary = SimpleNamespace(code="BI-2", address=2, frame_type=1, value=None, is_valid=False)
    progress = []

    result = await DataReader(_device(handler)).get_slave_values_async(
        [analog],
        [binary],
        interval_ms=500,
        progress_callback=lambda *args: progress.append(args),
    )

    handler.read_points_batch_async.assert_awaited_once_with([analog, binary])
    assert result == (2, 0)
    assert (analog.value, binary.value) == (10.5, 1)
    assert progress == [(1, 2, 1, 0), (2, 2, 2, 0)]


@pytest.mark.asyncio
async def test_single_read_fallback_honors_interval_between_requests(monkeypatch):
    handler = DNP3ClientHandler()
    handler.read_value_async = AsyncMock(side_effect=[1, 2])
    reader = DataReader(_device(handler))
    points = [
        SimpleNamespace(code="P-1", value=None, is_valid=False),
        SimpleNamespace(code="P-2", value=None, is_valid=False),
    ]
    sleep = AsyncMock()
    monkeypatch.setattr(asyncio, "sleep", sleep)

    result = await reader._single_read_async(points, interval_ms=75)

    assert result == (2, 0)
    sleep.assert_awaited_once_with(0.075)
