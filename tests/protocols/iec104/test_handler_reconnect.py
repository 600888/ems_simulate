import asyncio

from src.device.protocol.iec104_handler import IEC104ClientHandler


class _FakeClient:
    def __init__(self, connect_results: list[bool]):
        self._connect_results = iter(connect_results)
        self.connect_calls = 0
        self.disconnect_calls = 0
        self.clock_sync_calls = 0
        self.interrogation_calls = 0
        self.counter_interrogation_calls = 0
        self.is_connected = False
        self.stations = {}

    async def connect(self, timeout: float) -> bool:
        self.connect_calls += 1
        self.is_connected = next(self._connect_results)
        return self.is_connected

    def disconnect(self) -> None:
        self.disconnect_calls += 1
        self.is_connected = False

    def send_clock_sync(self, common_address=None) -> bool:
        self.clock_sync_calls += 1
        return True

    def send_interrogation(self, common_address=None) -> bool:
        self.interrogation_calls += 1
        return True

    def send_counter_interrogation(self, common_address=None) -> bool:
        self.counter_interrogation_calls += 1
        return True


def test_reconnect_uses_exponential_backoff_and_resets_after_success():
    handler = IEC104ClientHandler()
    client = _FakeClient([False, True])
    handler._client = client
    handler._reconnect_initial_interval = 2
    handler._max_reconnect_interval = 30

    assert asyncio.run(handler._try_reconnect()) is False
    assert handler._reconnect_count == 1
    assert client.connect_calls == 1

    # The next access during the two-second cooldown must not reconnect again.
    assert asyncio.run(handler._try_reconnect()) is False
    assert client.connect_calls == 1

    handler._last_reconnect_attempt -= 4
    assert asyncio.run(handler._try_reconnect()) is True
    assert client.connect_calls == 2
    assert handler._reconnect_count == 0


def test_reconnect_honors_maximum_attempts():
    handler = IEC104ClientHandler()
    client = _FakeClient([False, False])
    handler._client = client
    handler._max_reconnect_attempts = 2

    assert asyncio.run(handler._try_reconnect()) is False
    handler._last_reconnect_attempt -= 4
    assert asyncio.run(handler._try_reconnect()) is False
    handler._last_reconnect_attempt -= 8
    assert asyncio.run(handler._try_reconnect()) is False
    assert client.connect_calls == 2


def test_zero_disables_reconnect_and_minus_one_keeps_retrying():
    handler = IEC104ClientHandler()
    client = _FakeClient([False])
    handler._client = client
    handler._max_reconnect_attempts = 0

    assert asyncio.run(handler._try_reconnect()) is False
    assert client.connect_calls == 0

    handler._max_reconnect_attempts = -1
    assert asyncio.run(handler._try_reconnect()) is False
    assert client.connect_calls == 1


def test_periodic_maintenance_commands_follow_configured_intervals():
    async def scenario():
        handler = IEC104ClientHandler()
        client = _FakeClient([True])
        handler._client = client
        handler._clock_sync_interval = 1
        handler._general_interrogation_interval = 1
        handler._counter_interrogation_interval = 1

        assert await handler.start() is True
        await asyncio.sleep(1.1)
        await handler.stop()
        return client

    client = asyncio.run(scenario())
    assert client.clock_sync_calls == 1
    assert client.interrogation_calls == 1
    assert client.counter_interrogation_calls == 2


def test_counter_interrogation_on_connect_can_be_disabled():
    async def scenario():
        handler = IEC104ClientHandler()
        client = _FakeClient([True])
        handler._client = client
        handler._counter_interrogation_on_connect = False

        assert await handler.start() is True
        await handler.stop()
        return client

    client = asyncio.run(scenario())
    assert client.counter_interrogation_calls == 0
