import asyncio
from importlib import import_module
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI, HTTPException
import pytest

from src.proto.dlt698.schema import ReadRequest
from src.web.api.dlt698.router import _locks, read
from src.web.app import initialization_guard

router_module = import_module("src.web.api.dlt698.router")


def connected_request(disconnected=None):
    event = disconnected if disconnected is not None else asyncio.Event()

    async def receive():
        await event.wait()
        return {"type": "http.disconnect"}

    return SimpleNamespace(receive=receive)


@pytest.mark.asyncio
async def test_disconnect_cancels_read_and_releases_both_channel_locks(monkeypatch):
    started, cancelled, disconnected = asyncio.Event(), asyncio.Event(), asyncio.Event()
    read_lock = asyncio.Lock()

    async def blocked_read(*args):
        async with read_lock:
            started.set()
            try:
                await asyncio.Future()
            finally:
                cancelled.set()

    runtime = SimpleNamespace(definitions={"p": {"oad": "200F0200"}}, read=blocked_read)
    handler = SimpleNamespace(get_runtime=lambda: runtime)
    monkeypatch.setattr(router_module, "get_handler", AsyncMock(return_value=handler))
    request = connected_request(disconnected)
    task = asyncio.create_task(read(9876, ReadRequest(codes=["p"]), request))
    await asyncio.wait_for(started.wait(), 1)
    disconnected.set()
    with pytest.raises(HTTPException) as raised:
        await asyncio.wait_for(task, 1)
    assert raised.value.status_code == 499
    assert cancelled.is_set()
    assert not read_lock.locked()
    assert not _locks[9876].locked()
    runtime.read = AsyncMock(return_value=[{"index": 0, "oad": "200F0200", "kind": "dar", "dar": 4}])
    disconnected.clear()
    response = await asyncio.wait_for(read(9876, ReadRequest(codes=["p"]), request), 1)
    assert response.data[0]["dar"] == 4


@pytest.mark.asyncio
async def test_disconnected_request_does_not_wait_for_another_channels_read_lock(monkeypatch):
    handler = AsyncMock()
    monkeypatch.setattr(router_module, "get_handler", handler)
    async with _locks[9877]:
        disconnected = asyncio.Event()
        disconnected.set()
        request = connected_request(disconnected)
        with pytest.raises(HTTPException) as raised:
            await asyncio.wait_for(read(9877, ReadRequest(codes=["p"]), request), 1)
        assert raised.value.status_code == 499
        handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_read_error_is_propagated_and_releases_channel_lock(monkeypatch):
    runtime = SimpleNamespace(
        definitions={"p": {"oad": "200F0200"}}, read=AsyncMock(side_effect=ConnectionError("lost"))
    )
    monkeypatch.setattr(
        router_module, "get_handler", AsyncMock(return_value=SimpleNamespace(get_runtime=lambda: runtime))
    )
    request = connected_request()
    with pytest.raises(ConnectionError, match="lost"):
        await read(9878, ReadRequest(codes=["p"]), request)
    assert not _locks[9878].locked()


@pytest.mark.asyncio
async def test_http_disconnect_reaches_native_read_through_application_middleware(monkeypatch):
    started, cancelled = asyncio.Event(), asyncio.Event()

    async def blocked_read(*args):
        started.set()
        try:
            await asyncio.Future()
        finally:
            cancelled.set()

    runtime = SimpleNamespace(definitions={"p": {"oad": "200F0200"}}, read=blocked_read)
    monkeypatch.setattr(
        router_module, "get_handler", AsyncMock(return_value=SimpleNamespace(get_runtime=lambda: runtime))
    )
    app = FastAPI()
    app.state.device_controller = SimpleNamespace()
    app.middleware("http")(initialization_guard)
    app.include_router(router_module.router)
    messages = asyncio.Queue()
    await messages.put({"type": "http.request", "body": json.dumps({"codes": ["p"]}).encode(), "more_body": False})
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "method": "POST",
        "scheme": "http",
        "path": "/api/dlt698/channels/9879/read",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"content-type", b"application/json")],
        "server": ("127.0.0.1", 80),
        "client": ("127.0.0.1", 1234),
        "http_version": "1.1",
    }
    dispatch = asyncio.create_task(app(scope, messages.get, AsyncMock()))
    await asyncio.wait_for(started.wait(), 1)
    await messages.put({"type": "http.disconnect"})
    await asyncio.wait_for(cancelled.wait(), 1)
    await asyncio.wait_for(dispatch, 1)
    assert not _locks[9879].locked()
