from types import SimpleNamespace

from src.device.protocol.iec61850_handler import IEC61850ServerHandler
from src.device.protocol.iec61850_report_coordination import (
    pause_matching_local_server_simulations,
    resume_local_server_simulations,
    trigger_gi_with_local_server_coordination,
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


def test_local_gi_keeps_matching_simulation_paused_until_report_is_cached():
    simulation = _FakeSimulation()
    request = _request(_server_device("local", 10102, simulation))
    events: list[object] = []

    class _FakeReports:
        _client = SimpleNamespace(ip="127.0.0.1", port=10102)

        @staticmethod
        def get_report_data_state(rcb_ref):
            events.append(("state", rcb_ref))
            return 4, 17

        @staticmethod
        def trigger_gi(*, rcb_ref):
            events.append(("trigger", rcb_ref, simulation.running))
            return True

        @staticmethod
        def wait_for_report_after(rcb_ref, after_uid, *, timeout):
            events.append(("wait", rcb_ref, after_uid, timeout, simulation.running))
            return True

    assert trigger_gi_with_local_server_coordination(
        _FakeReports(),
        "LD0/LLN0.rp01",
        request,
        LOG,
    )
    assert simulation.events == ["stop", "start"]
    assert events == [
        ("state", "LD0/LLN0.rp01"),
        ("trigger", "LD0/LLN0.rp01", False),
        ("wait", "LD0/LLN0.rp01", 17, 3.0, False),
    ]
