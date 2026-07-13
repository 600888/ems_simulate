from types import SimpleNamespace

from src.device.simulator.simulation_controller import SimulationController
from src.enums.modbus_def import ProtocolType
from src.enums.points.yx import Yx
from src.proto.iec61850 import iec61850_server as server_module


def test_iec61850_simulation_commits_changed_points_as_one_batch():
    controller = None
    batches = []

    class BatchHandler:
        def write_values_batch(self, values):
            batches.append(list(values))
            controller._stop_event.set()
            return True

    device = SimpleNamespace(
        protocol_type=ProtocolType.Iec61850Server,
        protocol_handler=BatchHandler(),
        ip="127.0.0.1",
        port=102,
        editPointData=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("IEC61850 batch path must not write points one by one")
        ),
    )
    controller = SimulationController(device)

    first = Yx(code="first", address="LD0/GGIO1.Ind1.stVal", value=0, fc="ST")
    second = Yx(code="second", address="LD0/GGIO1.Ind2.stVal", value=0, fc="ST")
    controller.points = {
        first: SimpleNamespace(point=first, is_running=True, simulate=lambda: setattr(first, "value", 1)),
        second: SimpleNamespace(point=second, is_running=True, simulate=lambda: setattr(second, "value", 1)),
    }

    controller._run_simulation()

    assert batches == [[(first, 1), (second, 1)]]


def test_server_batch_holds_data_model_lock_for_all_updates(monkeypatch):
    events = []
    native = SimpleNamespace(
        IedServer_lockDataModel=lambda server: events.append(("lock", server)),
        IedServer_unlockDataModel=lambda server: events.append(("unlock", server)),
    )
    monkeypatch.setattr(server_module, "iec61850", native)

    server = server_module.IEC61850Server.__new__(server_module.IEC61850Server)
    server._server = object()
    server._is_running = True
    server.set_point_value = lambda address, value, fc="": events.append(("write", address, value, fc))

    assert server.set_point_values([("LD0/A", 1, "ST"), ("LD0/B", 2.0, "MX")])
    assert events == [
        ("lock", server._server),
        ("write", "LD0/A", 1, "ST"),
        ("write", "LD0/B", 2.0, "MX"),
        ("unlock", server._server),
    ]
