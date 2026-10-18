"""Opt-in native serial regression: set EMS_TEST_DLT698_SERIAL_PAIR=COM10,COM11."""

import asyncio
import os

import pytest

from src.device.core.message.message_capture import MessageCapture
from src.proto.dlt698.runtime import Dlt698Runtime
from src.proto.dlt698.schema import Dlt698Config
from tests.protocols.dlt698.test_adapter import point


@pytest.mark.parametrize("association", ["public", "preestablished"])
@pytest.mark.asyncio
async def test_serial_batches_wrap_piid_cancel_release_and_restart(association):
    pair = os.environ.get("EMS_TEST_DLT698_SERIAL_PAIR", "")
    if not pair:
        pytest.skip("requires an explicitly selected virtual serial pair")
    server_port, client_port = pair.split(",")
    published = [point(), point("counter", "FFFF0200", "UInt64", "9007199254740993", False)]
    templates = [published[0], point("missing", "FFFF0300", standard=False), published[1], published[0]]
    points = [{**templates[i % 4], "code": f"p{i}"} for i in range(256)]
    network = {"baudrate": 9600, "databits": 8, "stopbits": 1, "parity": "E"}
    capture = MessageCapture(2000)
    server = Dlt698Runtime(
        Dlt698Config(role="server", association=association),
        {**network, "conn_type": 3, "serial_port": server_port},
        published,
    )
    client = Dlt698Runtime(
        Dlt698Config(association=association),
        {**network, "conn_type": 0, "serial_port": client_port},
        points,
        capture,
    )
    try:
        await asyncio.wait_for(server.start(), 5)
        await asyncio.wait_for(client.start(), 5)
        original = client.client
        for _ in range(5):
            results = await asyncio.wait_for(client.read([p["oad"] for p in points], [p["code"] for p in points]), 15)
            assert [r["index"] for r in results] == list(range(256))
            assert [r["kind"] for r in results] == ["data", "dar", "data", "data"] * 64
            assert results[2]["data"]["value"] == "9007199254740993"
            assert client.client is original
        task = asyncio.create_task(client.read([p["oad"] for p in points]))
        await asyncio.sleep(0.05)
        assert not task.done()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)
        assert not client.auto_read.read_lock.locked()
        assert client.state == "associated"
        assert client.client is original
        assert (await asyncio.wait_for(client.read(["200F0200"]), 5))[0]["data"]["value"] == "5000"
        await asyncio.wait_for(client.stop(), 2)
        # 预设关联不重新发送 CONNECT；关闭后需重建串口两端的会话。
        await asyncio.wait_for(server.stop(), 2)
        # Windows 虚拟串口驱动在 CloseHandle 后异步完成取消 I/O。
        await asyncio.sleep(0.05)
        await asyncio.wait_for(server.start(), 5)
        await asyncio.wait_for(client.start(), 5)
        assert (await asyncio.wait_for(client.read(["200F0200"]), 5))[0]["data"]["value"] == "5000"
    finally:
        await client.stop()
        await server.stop()
        await asyncio.sleep(0.05)
