"""Subnet discovery validation, result accuracy, cancellation and API contracts."""

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.tools import subnet_scan
from src.tools.subnet_scan import SubnetScanner, parse_subnet, ping_host
from src.web.api.exceptions import NotFoundError, ValidationError
from src.web.api.tools import SubnetScanRequest, get_subnet_scan, start_subnet_scan, stop_subnet_scan


@pytest.mark.parametrize(
    ("value", "expected", "count"),
    [
        ("192.168.1", "192.168.1.0/24", 254),
        (" 10.0.0.99/30 ", "10.0.0.96/30", 2),
        ("127.0.0.1/32", "127.0.0.1/32", 1),
        ("10.0.0.0/31", "10.0.0.0/31", 2),
    ],
)
def test_subnet_ranges(value, expected, count):
    network = parse_subnet(value)
    assert str(network) == expected
    assert len(list(network.hosts())) == count


@pytest.mark.parametrize(
    "value",
    [
        "",
        "192.168.300",
        "example.com",
        "10.0.0.0/16",
        "::1/128",
        "224.0.0.0/24",
        "0.0.0.0/24",
        "192.168.1;whoami",
        "10.0.0.0/33",
    ],
)
def test_invalid_subnet(value):
    with pytest.raises(ValueError):
        parse_subnet(value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("output", "returncode", "reachable", "latency"),
    [
        (b"Reply from 192.168.1.1: bytes=32 time<1ms TTL=64", 0, True, 1.0),
        (b"64 bytes from 10.0.0.1: icmp_seq=1 ttl=64 time=0.125 ms", 0, True, 0.125),
        (b"Reply from 192.168.1.1: Destination host unreachable.", 0, False, None),
        (b"Request timed out.", 1, False, None),
    ],
)
async def test_echo_reply_detection(monkeypatch, output, returncode, reachable, latency):
    process = SimpleNamespace(
        returncode=returncode, communicate=Mock(return_value=(output, b"")), poll=lambda: returncode
    )
    spawn = Mock(return_value=process)
    monkeypatch.setattr(subnet_scan.subprocess, "Popen", spawn)
    result = await ping_host("192.168.1.1", 1000)
    assert result == {"ip": "192.168.1.1", "reachable": reachable, "latency_ms": latency}
    assert spawn.call_args.args[0][-1] == "192.168.1.1"


@pytest.mark.asyncio
async def test_cancel_terminates_ping_process(monkeypatch):
    started = threading.Event()
    killed = threading.Event()

    def communicate(**kwargs):
        started.set()
        if process.returncode is None:
            killed.wait(timeout=5)
        return b"", b""

    def kill():
        process.returncode = 1
        killed.set()

    process = SimpleNamespace(returncode=None, communicate=communicate, kill=kill, poll=lambda: process.returncode)
    monkeypatch.setattr(subnet_scan.subprocess, "Popen", Mock(return_value=process))
    task = asyncio.create_task(ping_host("192.168.1.1", 1000))
    await asyncio.to_thread(started.wait, 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert process.returncode == 1


@pytest.mark.asyncio
async def test_scan_counts_sorts_and_excludes_network_broadcast(monkeypatch):
    async def probe(ip, timeout):
        await asyncio.sleep(0)
        return {"ip": ip, "reachable": ip.endswith(".1"), "latency_ms": None}

    monkeypatch.setattr(subnet_scan, "ping_host", probe)
    scanner = SubnetScanner()
    scan = scanner.start("192.168.1", 1000)
    await scan.task
    result = scan.snapshot()
    assert result["status"] == "completed"
    assert (result["total"], result["completed"], result["reachable"], result["unreachable"]) == (254, 254, 1, 253)
    assert result["results"][0]["ip"] == "192.168.1.1"
    assert result["results"][-1]["ip"] == "192.168.1.254"


@pytest.mark.asyncio
async def test_concurrency_limit_and_shutdown(monkeypatch):
    started = asyncio.Event()
    active = 0
    peak = 0

    async def probe(ip, timeout):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        if active == 32:
            started.set()
        try:
            await asyncio.Event().wait()
        finally:
            active -= 1

    monkeypatch.setattr(subnet_scan, "ping_host", probe)
    scanner = SubnetScanner()
    scan = scanner.start("192.168.1", 1000)
    await started.wait()
    await scanner.close()
    assert peak == 32
    assert active == 0
    assert scan.status == "cancelled"
    assert scan.task.done()


@pytest.mark.asyncio
async def test_missing_ping_is_failed_scan(monkeypatch):
    monkeypatch.setattr(subnet_scan, "ping_host", AsyncMock(side_effect=FileNotFoundError("ping unavailable")))
    scanner = SubnetScanner()
    scan = scanner.start("127.0.0.1/32", 1000)
    await scan.task
    assert scan.status == "failed"
    assert "ping unavailable" in scan.error
    assert scan.snapshot()["unreachable"] == 0


@pytest.mark.asyncio
async def test_invalid_api_request_starts_no_scan():
    scanner = SubnetScanner()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(subnet_scanner=scanner)))
    with pytest.raises(ValidationError):
        await start_subnet_scan(SubnetScanRequest(subnet="10.0.0.0/8"), request)
    assert scanner.scans == {}


@pytest.mark.asyncio
async def test_api_start_progress_and_stop(monkeypatch):
    async def probe(ip, timeout):
        await asyncio.Event().wait()

    monkeypatch.setattr(subnet_scan, "ping_host", probe)
    scanner = SubnetScanner()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(subnet_scanner=scanner)))
    response = await start_subnet_scan(SubnetScanRequest(subnet="192.168.1"), request)
    result = response.model_dump()["data"]
    assert result["total"] == 254
    assert (await get_subnet_scan(result["id"], request)).data["status"] == "running"
    stopped = (await stop_subnet_scan(result["id"], request)).data
    assert stopped["status"] == "cancelled"
    assert stopped["completed"] == 0
    with pytest.raises(NotFoundError):
        await get_subnet_scan("missing", request)


@pytest.mark.asyncio
async def test_immediate_cancel_and_task_limit(monkeypatch):
    monkeypatch.setattr(subnet_scan, "ping_host", AsyncMock())
    scanner = SubnetScanner()
    scans = [scanner.start("192.168.1", 1000) for _ in range(4)]
    with pytest.raises(ValueError, match="4"):
        scanner.start("192.168.2", 1000)
    await scanner.close()
    assert all(scan.status == "cancelled" for scan in scans)
