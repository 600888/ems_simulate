import asyncio
from importlib import import_module
import json
import threading
from types import SimpleNamespace

from fastapi import FastAPI

import src.device_controller as controller_module


def test_concurrent_controller_requests_share_one_initialization(monkeypatch):
    calls = 0

    async def fake_import_device(self):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)

    monkeypatch.setattr(controller_module.DeviceController, "import_device", fake_import_device)
    monkeypatch.setattr(controller_module, "device_controller", None)
    monkeypatch.setattr(controller_module, "_device_controller_init_task", None)

    async def scenario():
        controllers = await asyncio.gather(*(controller_module.get_device_controller() for _ in range(12)))
        assert len({id(controller) for controller in controllers}) == 1
        assert calls == 1
        await controller_module.shutdown_device_controller()

    asyncio.run(scenario())


def test_database_device_import_does_not_block_event_loop(monkeypatch):
    controller = controller_module.DeviceController()
    worker_started = threading.Event()
    release_worker = threading.Event()

    def blocking_import():
        worker_started.set()
        assert release_worker.wait(timeout=2)

    monkeypatch.setattr(controller, "_import_device_from_db", blocking_import)

    async def scenario():
        import_task = asyncio.create_task(controller.import_device_from_db())
        await asyncio.to_thread(worker_started.wait, 1)

        # If import runs on the event loop, this coroutine cannot make progress.
        await asyncio.sleep(0)
        assert not import_task.done()

        release_worker.set()
        await import_task
        await controller.shutdown()

    asyncio.run(scenario())


def test_failed_background_initialization_stays_unhealthy(monkeypatch):
    app_module = import_module("src.web.app")
    application = FastAPI()
    application.state.initialized = False
    application.state.initialization_error = None

    async def failing_controller():
        raise RuntimeError("broken startup")

    monkeypatch.setattr(app_module, "_init_device_controller", failing_controller)

    asyncio.run(app_module._background_init(application))

    assert application.state.initialized is False
    assert isinstance(application.state.initialization_error, RuntimeError)


def test_lifespan_tracks_initialization_and_always_shuts_down(monkeypatch):
    app_module = import_module("src.web.app")
    application = FastAPI()
    events = []

    async def fake_background_init(app):
        events.append("initialized")
        app.state.initialized = True

    async def fake_shutdown(app):
        events.append("shutdown")
        app.state.initialized = False

    monkeypatch.setattr(app_module, "_background_init", fake_background_init)
    monkeypatch.setattr(app_module, "_shutdown_application", fake_shutdown)

    async def scenario():
        async with app_module.lifespan(application):
            await asyncio.sleep(0)
            assert application.state.initialized is True
        assert application.state.initialized is False

    asyncio.run(scenario())
    assert events == ["initialized", "shutdown"]


def test_api_request_waits_for_background_initialization():
    app_module = import_module("src.web.app")
    application = FastAPI()
    application.state.device_controller = None
    application.state.initialization_error = None
    request = SimpleNamespace(
        method="POST",
        url=SimpleNamespace(path="/api/devices/slave-id-list"),
        app=application,
    )

    async def scenario():
        async def initialize():
            await asyncio.sleep(0)
            application.state.device_controller = object()

        application.state.init_task = asyncio.create_task(initialize())

        async def call_next(_request):
            return "served"

        response = await app_module.initialization_guard(request, call_next)
        assert response == "served"

    asyncio.run(scenario())


def test_api_request_returns_503_after_initialization_failure():
    app_module = import_module("src.web.app")
    application = FastAPI()
    application.state.device_controller = None
    application.state.init_task = None
    application.state.initialization_error = RuntimeError("broken startup")
    request = SimpleNamespace(
        method="POST",
        url=SimpleNamespace(path="/api/devices/slave-id-list"),
        app=application,
    )

    async def scenario():
        async def call_next(_request):
            raise AssertionError("uninitialized API must not reach the route")

        response = await app_module.initialization_guard(request, call_next)
        assert response.status_code == 503
        assert json.loads(response.body)["code"] == 503

    asyncio.run(scenario())
