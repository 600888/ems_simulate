import asyncio
from unittest.mock import AsyncMock, Mock

from src.device.protocol.modbus_handler import ModbusClientHandler


def test_zero_disables_reconnect_and_minus_one_allows_it():
    handler = ModbusClientHandler()
    handler._max_reconnect_attempts = 0
    handler.disconnect = AsyncMock()
    handler.initialize = Mock()
    handler.connect = AsyncMock(return_value=False)

    assert asyncio.run(handler._try_reconnect()) is False
    handler.disconnect.assert_not_awaited()
    handler.connect.assert_not_awaited()

    handler._max_reconnect_attempts = -1
    assert asyncio.run(handler._try_reconnect()) is False
    handler.disconnect.assert_awaited_once()
    handler.connect.assert_awaited_once()
