import asyncio
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.device.core.point.point_calculator import PointCalculator
from src.device.core.point.point_manager import PointManager
from src.enums.points.yc import Yc
from src.web.api.channel.goose_websocket import WebSocketSessionManager


def _reset_websocket_manager() -> WebSocketSessionManager:
    manager = WebSocketSessionManager()
    with manager._lock:
        manager._connections.clear()
        manager._connection_channels.clear()
        manager._pending_packets.clear()
        manager._packet_batch_scheduled.clear()
    manager._send_timeout_seconds = 1.0
    return manager


def test_websocket_broadcast_sends_to_clients_concurrently():
    manager = _reset_websocket_manager()

    class FakeWebSocket:
        def __init__(self):
            self.messages = []

        async def send_text(self, payload):
            await asyncio.sleep(0.05)
            self.messages.append(payload)

    first = FakeWebSocket()
    second = FakeWebSocket()
    with manager._lock:
        manager._connections.update((first, second))
        manager._connection_channels[first] = 7
        manager._connection_channels[second] = 7

    async def scenario():
        started = time.perf_counter()
        await manager.broadcast({"type": "packet"}, channel_id=7)
        return time.perf_counter() - started

    elapsed = asyncio.run(scenario())

    assert elapsed < 0.09
    assert len(first.messages) == 1
    assert len(second.messages) == 1


def test_websocket_broadcast_does_not_hold_thread_lock_while_sending():
    manager = _reset_websocket_manager()
    send_started = asyncio.Event()
    release_send = asyncio.Event()

    class SlowWebSocket:
        async def send_text(self, _payload):
            send_started.set()
            await release_send.wait()

    websocket = SlowWebSocket()
    with manager._lock:
        manager._connections.add(websocket)

    async def scenario():
        broadcast_task = asyncio.create_task(manager.broadcast({"type": "packet"}))
        await send_started.wait()
        acquired = await asyncio.to_thread(manager._lock.acquire, True, 0.1)
        if acquired:
            manager._lock.release()
        release_send.set()
        await broadcast_task
        return acquired

    assert asyncio.run(scenario()) is True


def test_mapping_scheduler_coalesces_high_frequency_changes():
    point_manager = MagicMock()
    device = SimpleNamespace(name="target", point_manager=point_manager)
    calculator = PointCalculator(device)
    first_started = threading.Event()
    release_first = threading.Event()
    calls = 0

    def execute(_mapping_id, _context=None):
        nonlocal calls
        calls += 1
        if calls == 1:
            first_started.set()
            assert release_first.wait(timeout=2)

    calculator._execute_calculation = execute
    calculator._running = True
    calculator._ensure_executor()
    calculator._schedule_mapping(1)
    assert first_started.wait(timeout=1)

    for _ in range(100):
        calculator._schedule_mapping(1)
    release_first.set()

    deadline = time.monotonic() + 2
    while calculator._pending_mapping_ids and time.monotonic() < deadline:
        time.sleep(0.01)

    calculator.stop()
    assert calls == 2


def test_running_mapping_calculator_reloads_when_device_provider_is_attached():
    """重建设备先启动计算器时，后注入 Controller 也必须恢复映射订阅。"""
    device = SimpleNamespace(name="target", point_manager=MagicMock())
    calculator = PointCalculator(device)
    calculator._running = True
    calculator.reload_mappings = MagicMock()
    provider = SimpleNamespace(device_map={"target": device})
    mappings = [{"id": 1}]

    calculator.set_device_provider(provider, mappings)

    assert calculator._device_provider is provider
    calculator.reload_mappings.assert_called_once_with(mappings)


def test_mapping_reload_subscribes_points_added_after_calculator_start():
    """手工添加的新测点在保存映射后应立即进入订阅表并锁定目标点。"""
    point_manager = PointManager()
    device = SimpleNamespace(name="device-a", point_manager=point_manager)
    provider = SimpleNamespace(device_map={"device-a": device})
    calculator = PointCalculator(device)
    calculator._device_provider = provider
    calculator._running = True
    calculator._schedule_mapping = MagicMock()

    source = Yc(code="SOURCE", name="Source")
    target = Yc(code="NEW_TARGET", name="Target")
    point_manager.add_point(1, source)
    point_manager.add_point(1, target)
    mapping = {
        "id": 9,
        "device_name": "device-a",
        "target_point_code": "NEW_TARGET",
        "source_point_codes": '[{"device_name":"device-a","point_code":"SOURCE","alias":"source"}]',
        "formula": "source * 2",
        "enable": True,
    }

    calculator.reload_mappings([mapping])

    assert calculator._sender_map[id(source)] == [9]
    assert source.is_send_signal is True
    assert target.is_locked_by_mapping is True
