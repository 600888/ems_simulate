from types import SimpleNamespace

from src.device.protocol.iec61850_handler import IEC61850ServerHandler
from src.device.protocol.iec61850_report_coordination import (
    pause_matching_local_server_simulations,
    resume_local_server_simulations,
)


class _FakeSimulation:
    def __init__(self, running: bool = True):
        self.running = running
        self.events: list[str] = []

    def is_simulation_running(self) -> bool:
        return self.running

    def stop_simulation(self, timeout: float = 1.0) -> bool:
        self.events.append("stop")
        self.running = False
        return True

    def start_simulation(self) -> None:
        self.events.append("start")
        self.running = True


def _server_device(name: str, port: int, simulation: _FakeSimulation):
    handler = IEC61850ServerHandler()
    handler._server = SimpleNamespace(port=port)
    return SimpleNamespace(
        name=name,
        protocol_handler=handler,
        simulation_controller=simulation,
    )


def _request(*devices):
    controller = SimpleNamespace(device_list=list(devices))
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(device_controller=controller)))


class _FakeLog:
    def info(self, *_args, **_kwargs):
        pass

    def error(self, *_args, **_kwargs):
        pass


LOG = _FakeLog()


def test_batch_enable_pauses_only_the_matching_loopback_server_and_resumes_it():
    matching = _FakeSimulation()
    unrelated = _FakeSimulation()
    stopped = _FakeSimulation(running=False)
    request = _request(
        _server_device("matching", 10102, matching),
        _server_device("unrelated", 10103, unrelated),
        _server_device("already-stopped", 10102, stopped),
    )
    reports = SimpleNamespace(_client=SimpleNamespace(ip="127.0.0.1", port=10102))

    paused = pause_matching_local_server_simulations(reports, request, LOG)

    assert paused == [matching]
    assert matching.events == ["stop"]
    assert unrelated.events == []
    assert stopped.events == []

    resume_local_server_simulations(paused, LOG)
    assert matching.events == ["stop", "start"]


def test_external_report_client_does_not_pause_local_server_simulation():
    simulation = _FakeSimulation()
    request = _request(_server_device("local", 102, simulation))
    reports = SimpleNamespace(_client=SimpleNamespace(ip="192.0.2.10", port=102))

    assert pause_matching_local_server_simulations(reports, request, LOG) == []
    assert simulation.events == []
