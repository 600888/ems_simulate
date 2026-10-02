"""Use the same add_reader-capable loop as the Windows backend for UA/MQTT."""

import asyncio


def pytest_asyncio_loop_factories():
    return {"selector": asyncio.SelectorEventLoop}
