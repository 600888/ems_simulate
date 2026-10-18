"""Real package boundary tests; no second implementation of the protocol."""

import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from dlt698 import ConnectionProfile, encode_data
from dlt698.common import ErrorCode
from dlt698.errors import RequestTimeoutError, ResourceLimitError
import pytest

from src.device.core.message.message_capture import MessageCapture
from src.device.protocol.runtime_config import normalize_protocol_params
from src.proto.dlt698.catalog import catalog, standard_definition
from src.proto.dlt698.codec import from_native, oad, to_native
from src.proto.dlt698.runtime import Dlt698Runtime, record_query, record_result
from src.proto.dlt698.schema import Data, Dlt698Config, Operation, Point, RecordQuery


def point(code="frequency", oad="200F0200", kind="UInt16", value="5000", standard=True):
    return Point(
        code=code, name=code, oad=oad, data_type=kind, standard=standard, initial_value=Data(type=kind, value=value)
    ).model_dump(exclude_none=True)


@pytest.mark.parametrize(
    "kind,value",
    [
        ("UInt64", "18446744073709551615"),
        ("Int64", "-9223372036854775808"),
        ("Boolean", True),
        ("Null", None),
        ("BitString", "101011001"),
        ("OctetString", "6800FF16"),
        ("Utf8String", "测试"),
        ("Date", "2026-10-14"),
        ("Time", "23:59:58"),
        ("DateTime", "2026-10-14T23:59:58"),
        ("DateTimeS", "2026-10-14T23:59:58"),
        (
            "Structure",
            [
                {"type": "UInt64", "value": "9007199254740993"},
                {"type": "Array", "value": [{"type": "UInt8", "value": "255"}]},
            ],
        ),
    ],
)
def test_json_round_trip_preserves_library_encoding(kind, value):
    original = to_native(Data(type=kind, value=value))
    result = from_native(original)
    assert result["type"] == kind
    assert result["value"] == value
    assert encode_data(to_native(result)) == encode_data(original)


@pytest.mark.parametrize("value", [9007199254740993, True, "18446744073709551616", "1.2", "NaN"])
def test_precise_integer_rejects_json_numbers_and_overflow(value):
    with pytest.raises(ValueError):
        Data(type="UInt64", value=value)


def test_standard_catalog_and_permissions_are_delegated_to_library():
    rows = catalog(Dlt698Config(), limit=5000)
    frequency = next(row for row in rows if row["oad"] == "200F0200")
    assert frequency["data_type"] == "UInt16"
    assert frequency["scaler"] == -2
    assert frequency["unit"] == "Hz"
    bad = Point.model_validate({**point(), "writable": True})
    with pytest.raises(ValueError, match="只读"):
        standard_definition(bad, Dlt698Config())
    with pytest.raises(ValueError):
        normalize_protocol_params(8, 1, {"role": "server"})
    assert normalize_protocol_params(8, 2, None)["role"] == "server"


@pytest.mark.parametrize("conn", [0, 1, 2, 3])
@pytest.mark.parametrize("association", ["public", "preestablished"])
@pytest.mark.asyncio
async def test_start_selects_local_serial_or_remote_tcp_association(monkeypatch, conn, association):
    role = "client" if conn in (0, 1) else "server"
    runtime = Dlt698Runtime(
        Dlt698Config(role=role, association=association),
        {"conn_type": conn, "serial_port": "COM_TEST", "ip": "127.0.0.1", "port": 698},
    )
    endpoint = SimpleNamespace(
        open_serial_configured=AsyncMock(),
        connect_tcp=AsyncMock(),
        start_serial_configured=AsyncMock(),
        start_tcp=AsyncMock(),
        aclose=AsyncMock(),
    )
    monkeypatch.setattr("src.proto.dlt698.runtime.AsyncClient", Mock(return_value=endpoint))
    monkeypatch.setattr("src.proto.dlt698.runtime.AsyncServer", Mock(return_value=endpoint))
    expected = (
        ConnectionProfile.local_preset
        if association == "preestablished"
        else ConnectionProfile.local_public
        if conn in (0, 3)
        else ConnectionProfile.remote_public
    )
    try:
        assert await runtime.start()
        method = (
            endpoint.open_serial_configured
            if conn == 0
            else endpoint.connect_tcp
            if conn == 1
            else endpoint.start_tcp
            if conn == 2
            else endpoint.start_serial_configured
        )
        assert method.await_count == 1
        assert method.await_args.args[-1] == expected
        assert runtime.state == ("associated" if role == "client" else "listening")
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_empty_serial_start_timeout_retains_diagnostic_and_closes_client(monkeypatch):
    runtime = Dlt698Runtime(Dlt698Config(), {"conn_type": 0, "serial_port": "COM_TEST"})
    client = SimpleNamespace(open_serial_configured=AsyncMock(side_effect=TimeoutError()), aclose=AsyncMock())
    monkeypatch.setattr("src.proto.dlt698.runtime.AsyncClient", Mock(return_value=client))
    with pytest.raises(TimeoutError, match="COM_TEST.*关联超时"):
        await runtime.start()
    assert "5000 ms" in runtime.error
    assert "TimeoutError" in runtime.error
    assert not runtime.running
    assert not runtime.sessions
    client.aclose.assert_awaited_once()


@pytest.mark.parametrize("association", ["public", "preestablished"])
@pytest.mark.asyncio
async def test_managed_tcp_read_local_publish_partial_dar_restart_and_capture(association):
    points = [point(), point("counter", "FFFF0200", "UInt64", "9007199254740993", False)]
    capture = MessageCapture()
    server = Dlt698Runtime(
        Dlt698Config(role="server", association=association), {"conn_type": 2, "ip": "127.0.0.1", "port": 0}, points
    )
    client = Dlt698Runtime(
        Dlt698Config(association=association), {"conn_type": 1, "ip": "127.0.0.1", "port": 0}, points, capture
    )
    try:
        await server.start()
        client.network["port"] = server.actual_port
        await client.start()
        results = await client.probe(["FFFF0200", "FFFF0300", "FFFF0200"])
        assert [item["index"] for item in results] == [0, 1, 2]
        assert results[0]["data"]["value"] == results[2]["data"]["value"] == "9007199254740993"
        assert results[1]["kind"] == "dar"
        await client.read(["200F0200"], ["frequency"])
        last_good = deepcopy(client.snapshots["frequency"]["last_good"])
        dar = await client.operate(
            Operation(service="set", items=[{"oad": "200F0200", "data": {"type": "UInt16", "value": "1234"}}])
        )
        assert dar[0]["kind"] == "dar" and dar[0]["dar"] != 0
        await server.operate(
            Operation(service="local_values", items=[{"oad": "200F0200", "data": {"type": "UInt16", "value": "4998"}}])
        )
        assert (await client.read(["200F0200"]))[0]["data"]["value"] == "4998"
        assert capture.get_messages()
        assert {item["direction"] for item in capture.get_messages()} == {"TX", "RX"}
        await client.set_auto(True, 100, ["frequency"])
        await asyncio.sleep(0.15)
        assert client.auto_read.status()["cycle_count"] >= 1
        await client.set_auto(False)
        assert not client.auto_read.is_running()
        await server.stop()
        failed = await client.read(["200F0200"], ["frequency"])
        assert failed[0]["kind"] == "transport_error"
        assert client.snapshots["frequency"]["last_good"]["value"] in (last_good["value"], "4998")
        await client.stop()
        await server.start()
        client.network["port"] = server.actual_port
        await client.start()
        assert (await client.read(["200F0200"]))[0]["data"]["value"] == "4998"
    finally:
        await client.stop()
        await server.stop()
    assert not client.running and not server.running


@pytest.mark.parametrize("association", ["public", "preestablished"])
@pytest.mark.asyncio
async def test_large_batch_reads_preserve_order_dar_snapshots_and_auto_read(association):
    published = [point(), point("counter", "FFFF0200", "UInt64", "9007199254740993", False)]
    templates = [published[0], point("missing", "FFFF0300", standard=False), published[1], published[0]]
    points = [{**templates[i % 4], "code": f"p{i}"} for i in range(1000)]
    capture = MessageCapture(max_size=2000)
    server = Dlt698Runtime(
        Dlt698Config(role="server", association=association), {"conn_type": 2, "ip": "127.0.0.1", "port": 0}, published
    )
    client = Dlt698Runtime(
        Dlt698Config(association=association), {"conn_type": 1, "ip": "127.0.0.1", "port": 0}, points, capture
    )
    codes = [p["code"] for p in points]
    try:
        await server.start()
        client.network["port"] = server.actual_port
        await client.start()
        native_client = client.client
        client.snapshots["p1"] = {"last_good": {"type": "UInt16", "value": "42"}}
        for round_number in range(4):
            value = str(5000 + round_number)
            server.publish("200F0200", Data(type="UInt16", value=value))
            results = await asyncio.wait_for(client.read([p["oad"] for p in points], codes), timeout=5)
            assert client.client is native_client
            assert [r["index"] for r in results] == list(range(1000))
            assert [r["oad"] for r in results] == [p["oad"] for p in points]
            assert [r["kind"] for r in results] == ["data", "dar", "data", "data"] * 250
            assert results[0]["data"]["value"] == value
            assert results[2]["data"]["value"] == "9007199254740993"
            assert client.snapshots["p1"]["last_good"]["value"] == "42"
            assert client.snapshots["p999"]["last_good"]["value"] == value
        client.auto_codes = codes
        cycle = await asyncio.wait_for(client._read_cycle(None, asyncio.Event(), lambda *args: None), timeout=5)
        assert (cycle.success, cycle.fail, cycle.total) == (750, 250, 1000)
        assert client.client is native_client
        # All five passes use list GETs and preserve the original association.
        assert sum(m["direction"] == "TX" for m in capture.get_messages(2000)) < 330
    finally:
        await client.stop()
        await server.stop()


@pytest.mark.asyncio
async def test_single_reads_reuse_piid_on_same_connection():
    server = Dlt698Runtime(Dlt698Config(role="server"), {"conn_type": 2, "ip": "127.0.0.1", "port": 0}, [point()])
    client = Dlt698Runtime(Dlt698Config(), {"conn_type": 1, "ip": "127.0.0.1", "port": 0}, [point()])
    try:
        await server.start()
        client.network["port"] = server.actual_port
        await client.start()
        native_client = client.client
        async with asyncio.timeout(10):
            for _ in range(1000):
                assert (await client.read(["200F0200"]))[0]["data"]["value"] == "5000"
                assert client.client is native_client
    finally:
        await client.stop()
        await server.stop()


@pytest.mark.asyncio
async def test_shutdown_after_piid_wraparound():
    server = Dlt698Runtime(Dlt698Config(role="server"), {"conn_type": 2, "ip": "127.0.0.1", "port": 0}, [point()])
    client = Dlt698Runtime(Dlt698Config(), {"conn_type": 1, "ip": "127.0.0.1", "port": 0}, [point()])
    try:
        await server.start()
        client.network["port"] = server.actual_port
        await client.start()
        for _ in range(65):
            await client.client.get(oad("200F0200"))
        native_client = client.client
        await client.stop()
        assert native_client._closed
        assert not client.running
        assert client.state == "stopped"
    finally:
        await client.stop()
        await server.stop()


@pytest.mark.parametrize(
    "error",
    [
        RequestTimeoutError(ErrorCode.timeout, 0, "request timeout"),
        ResourceLimitError(ErrorCode.resource_limit, 0, "APDU limit"),
        ResourceLimitError(ErrorCode.resource_limit, 0, "PIID quarantine"),
    ],
)
@pytest.mark.asyncio
async def test_failed_reads_do_not_retry_wait_or_replace_connection(error):
    runtime = Dlt698Runtime(Dlt698Config(), {})
    client = SimpleNamespace(get=AsyncMock(side_effect=error))
    runtime.client = client
    runtime.sessions["1"] = {"associated": True}
    result = await asyncio.wait_for(runtime.read(["200F0200"]), timeout=0.5)
    assert result[0]["kind"] == "transport_error"
    assert error.context in result[0]["message"]
    client.get.assert_awaited_once()
    assert runtime.client is client


@pytest.mark.asyncio
async def test_inflight_read_can_be_cancelled():
    runtime = Dlt698Runtime(Dlt698Config(), {})
    started = asyncio.Event()

    async def operation(_address):
        started.set()
        await asyncio.Future()

    runtime.client = SimpleNamespace(get=operation)
    runtime.sessions["1"] = {"associated": True}
    task = asyncio.create_task(runtime.read(["200F0200"]))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert runtime.state == "cancelled"


@pytest.mark.asyncio
async def test_serial_cancel_finishes_current_transaction_and_preserves_association():
    runtime = Dlt698Runtime(Dlt698Config(request_timeout_ms=100), {"conn_type": 0})
    started, finish = asyncio.Event(), asyncio.Event()

    async def operation(_address):
        started.set()
        await finish.wait()
        return SimpleNamespace(data=to_native(Data(type="UInt16", value="5000")), dar=0)

    runtime.client = SimpleNamespace(get=operation)
    runtime.sessions["1"] = {"associated": True}
    task = asyncio.create_task(runtime.read(["200F0200"]))
    await started.wait()
    task.cancel()
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 1)
    assert runtime.state == "associated"
    assert runtime.sessions["1"]["associated"]
    assert not runtime.auto_read.read_lock.locked()
    assert (await runtime.read(["200F0200"]))[0]["data"]["value"] == "5000"


@pytest.mark.asyncio
async def test_serial_cancel_has_a_deadline_when_current_transaction_never_completes():
    runtime = Dlt698Runtime(Dlt698Config(request_timeout_ms=100), {"conn_type": 0})
    started, cancelled = asyncio.Event(), asyncio.Event()

    async def operation(_address):
        started.set()
        try:
            await asyncio.Future()
        finally:
            cancelled.set()

    runtime.client = SimpleNamespace(get=operation)
    runtime.sessions["1"] = {"associated": True}
    task = asyncio.create_task(runtime.read(["200F0200"]))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 0.5)
    assert cancelled.is_set()
    assert runtime.state == "cancelled"
    assert not runtime.sessions
    assert not runtime.auto_read.read_lock.locked()


@pytest.mark.asyncio
async def test_individual_standard_array_element_is_published_by_shared_device():
    server = Dlt698Runtime(
        Dlt698Config(role="server"),
        {"conn_type": 2, "ip": "127.0.0.1", "port": 0},
        [point("voltage", "20000201", "UInt16", "2301")],
    )
    try:
        await server.start()
        result = await server.read(["20000201", "20000200"])
        assert result[0]["data"]["value"] == "2301"
        assert result[1]["data"]["type"] == "Array"
        assert result[1]["data"]["value"][0]["value"] == "2301"
    finally:
        await server.stop()


def test_records_delegate_selectors_and_preserve_empty_and_dar():
    from dlt698.protocol import RecordResult

    query = RecordQuery(template="daily", oad="50040200", columns=["20230200", "20210200", "00100201"])
    request = record_query(query, Dlt698Config())
    empty = record_result(
        RecordResult(attribute=request.attribute, columns=[oad(value) for value in query.columns], result=[])
    )
    assert empty["rows"] == [] and "dar" not in empty and empty["blocks"] is None
    assert record_result(RecordResult(attribute=request.attribute, result=4))["dar"] == 4
    with pytest.raises(ValueError):
        RecordQuery(
            **{
                **query.model_dump(),
                "selector": "between",
                "start": "2026-01-02T00:00:00",
                "end": "2026-01-01T00:00:00",
            }
        )
