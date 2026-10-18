"""Shared point controls must update the typed publication without losing precision."""

import asyncio
from copy import deepcopy
import json
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch

from dlt698 import encode_data
import pytest

from src.device.core.device import Device
from src.device.protocol.dlt698_handler import Dlt698Handler
from src.enums.modbus_def import ProtocolType
from src.enums.point_data import SimulateMethod
from src.enums.points.change_tracker import ChangeSource, track_change
from src.proto.dlt698.codec import oad, to_native
from src.proto.dlt698.schema import Data, Dlt698Config, Operation, Point
from src.web.api.point.router import get_point_change_history, set_change_tracking
from src.web.api.schemas import ChangeTrackingConfigRequest, PointChangeHistoryRequest


def definition(code="frequency", address="200F0200", kind="UInt16", value="5000", scaler=-2):
    return Point(
        code=code,
        name=code,
        oad=address,
        data_type=kind,
        scaler=scaler,
        initial_value=Data(type=kind, value=value),
    ).model_dump(exclude_none=True)


def make_device(points, role="server"):
    device = Device(ProtocolType.Dlt698Server if role == "server" else ProtocolType.Dlt698Client)
    device.device_id, device.name = 7, "meter"
    device.runtime_config = Dlt698Config(role=role).model_dump()
    with patch("src.data.service.dlt698_service.Dlt698Service.points", return_value=points):
        device.initProtocol()
    return device


def test_shared_manual_simulation_and_mapping_writes_publish_typed_values():
    device = make_device([definition()])
    runtime = device.protocol_handler.get_runtime()
    point = device.point_manager.get_point_by_code("frequency")
    point.enable_change_tracking()
    assert device.editPointData("frequency", 49.98, source=ChangeSource.MANUAL)
    assert runtime.snapshots[point.code]["last_good"]["value"] == "4998"
    simulator = device.simulation_controller.points[point]
    simulator.simulate_method, simulator.fixed_value = SimulateMethod.FixedValue, 50.01
    with track_change(ChangeSource.SIMULATION):
        device.simulation_controller._perform_point_simulation(simulator)
    assert runtime.snapshots[point.code]["last_good"]["value"] == "5001"
    assert point.change_history[-1].source == ChangeSource.SIMULATION
    assert device.editPointData("frequency", 51.23, source=ChangeSource.MAPPING)
    assert runtime.device.get(oad("200F0200")).value == 5123
    assert point.change_history[-1].source == ChangeSource.MAPPING
    before = deepcopy(runtime.snapshots)
    assert not point.set_real_value(1000000)
    assert runtime.snapshots == before
    assert point.real_value == 51.23


def test_common_history_api_preserves_uint64_and_composite_values():
    device = make_device(
        [
            definition("counter", "FFFF0200", "UInt64", "9007199254740993", -4),
            definition("array", "FFFE0200", "Array", [{"type": "UInt64", "value": "9007199254740993"}], 0),
        ]
    )
    runtime = device.protocol_handler.get_runtime()
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(device_controller=SimpleNamespace(device_map={"meter": device})))
    )
    asyncio.run(set_change_tracking(ChangeTrackingConfigRequest(device_name="meter", enabled=True), request))
    asyncio.run(
        runtime.operate(
            Operation(
                service="local_values",
                items=[
                    {"oad": "FFFF0200", "data": {"type": "UInt64", "value": "18446744073709551615"}},
                    {
                        "oad": "FFFE0200",
                        "data": {"type": "Array", "value": [{"type": "UInt64", "value": "18446744073709551615"}]},
                    },
                ],
            )
        )
    )
    response = asyncio.run(
        get_point_change_history(PointChangeHistoryRequest(device_name="meter", point_code="counter"), request)
    )
    assert response.data["history"][0]["new_value"] == "18446744073709551615"
    assert response.data["history"][0]["new_real_value"] == "1844674407370955.1615"
    point = device.point_manager.get_point_by_code("array")
    assert "18446744073709551615" in point.change_history[-1].new_value
    assert not device.simulation_controller.points
    with pytest.raises(ValueError, match="64 位"):
        device.point_manager.get_point_by_code("counter").set_real_value(1)


def test_array_publication_updates_independent_element_history_and_snapshot():
    device = make_device(
        [
            definition("array", "20000200", "Array", [{"type": "UInt16", "value": "0"}] * 3, -1),
            definition("voltage", "20000201", "UInt16", "0", -1),
        ]
    )
    runtime = device.protocol_handler.get_runtime()
    point = runtime.point_states["voltage"]
    point.enable_change_tracking()
    runtime.publish("20000200", Data(type="Array", value=[{"type": "UInt16", "value": "2301"}] * 3))
    assert point.real_value == 230.1
    assert runtime.snapshots["voltage"]["last_good"]["value"] == "2301"
    assert len(point.change_history) == 1


def test_client_reads_feed_shared_history_but_do_not_enable_local_simulation():
    device = make_device([definition()], "client")
    runtime = device.protocol_handler.get_runtime()
    point = runtime.point_states["frequency"]
    point.enable_change_tracking()

    class Client:
        async def get(self, _address):
            return SimpleNamespace(data=to_native(Data(type="UInt16", value="4999")), dar=0)

    runtime.client = Client()
    runtime.state = "associated"
    runtime.sessions["1"] = {"id": "1", "associated": True}
    asyncio.run(runtime.read(["200F0200"], ["frequency"]))
    assert point.real_value == 49.99
    assert point.change_history[-1].source == ChangeSource.CLIENT_READ
    assert not device.simulation_controller.points
    assert not point.set_real_value(51)
    assert not device.protocol_handler.status()["features"]["simulation"]["supported"]


def test_wrong_typed_publish_does_not_change_wire_or_shared_state():
    device = make_device([definition()])
    runtime = device.protocol_handler.get_runtime()
    runtime.device = runtime._make_device()
    before = encode_data(runtime.device.get(oad("200F0200")))
    with pytest.raises(ValueError, match="类型"):
        runtime.publish("200F0200", Data(type="UInt32", value="5000"))
    assert encode_data(runtime.device.get(oad("200F0200"))) == before
    assert runtime.point_states["frequency"].real_value == 50


def test_shared_mapping_calculator_publishes_result_and_records_source():
    device = make_device([definition(), definition("target", "FFFF0200", "UInt16", "0", -1)])
    runtime = device.protocol_handler.get_runtime()
    target = runtime.point_states["target"]
    target.enable_change_tracking()
    completed = Event()

    def on_change(_sender, **_kwargs):
        completed.set()

    target.is_send_signal = True
    target.value_changed.connect(on_change)
    mapping = {
        "id": 1,
        "enable": True,
        "device_name": "meter",
        "target_point_code": "target",
        "formula": "frequency * 2",
        "source_point_codes": json.dumps([{"device_name": "meter", "point_code": "frequency", "alias": "frequency"}]),
    }
    try:
        device.set_device_provider(SimpleNamespace(device_map={"meter": device}), [mapping])
        assert completed.wait(2)
        assert runtime.device.get(oad("FFFF0200")).value == 1000
        assert target.change_history[-1].source == ChangeSource.MAPPING
    finally:
        device.point_calculator.stop()
