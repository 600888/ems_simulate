"""Real package boundary tests; no second implementation of the protocol."""

import asyncio
from copy import deepcopy

from dlt698 import encode_data
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
