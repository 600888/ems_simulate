from types import SimpleNamespace

from src.device.simulator.simulation_controller import SimulationController
from src.enums.modbus_def import ProtocolType
from src.enums.point_data import SimulateMethod
from src.enums.points.yc import Yc
from src.enums.points.yx import Yx


def _controller(protocol=ProtocolType.ModbusTcpServer):
    return SimulationController(SimpleNamespace(protocol_type=protocol))


def test_restore_preserves_parameters_and_selection_without_reusing_points():
    old = _controller()
    power = Yc(code="power", decode="0x42", min_value_limit=-10, max_value_limit=50)
    switch = Yx(code="switch")
    old.add_point(power, SimulateMethod.FixedValue, 0.25, is_running=True)
    old.add_point(switch, SimulateMethod.NoSimulation, 2, is_running=False)
    old.points[power].fixed_value = 12.5
    old.points[power].cycle = 30
    old.points[power].phase = 0.5
    old.points[power].ramp_time = 8

    new = _controller()
    new_power, new_switch = Yc(code="power", decode="0x42"), Yx(code="switch")
    new.add_point(new_power, SimulateMethod.Random, 1, is_running=True)
    new.add_point(new_switch, SimulateMethod.Random, 1, is_running=True)
    new.restore_configuration(old.snapshot_configuration())

    assert new.snapshot_configuration() == old.snapshot_configuration()
    assert new.points[new_power].point is new_power
    assert new.points[new_power] is not old.points[power]
    assert new.points[new_switch].is_running is False
    new.points[new_power].simulate()
    assert new_power.real_value == 12.5
    assert power.real_value == 0


def test_restore_does_not_confuse_same_codes_in_different_slaves_or_point_types():
    old = _controller()
    point = Yc(code="same", rtu_addr="1")
    old.add_point(point, SimulateMethod.AutoIncrement, 0.5, is_running=False)
    new = _controller()
    matching = Yc(code="same", rtu_addr="1")
    other_slave = Yc(code="same", rtu_addr="2")
    other_type = Yx(code="same", rtu_addr="1")
    for item in (matching, other_slave, other_type):
        new.add_point(item, SimulateMethod.Random, 1, is_running=True)
    new.restore_configuration(old.snapshot_configuration())

    assert new.points[matching].simulate_method is SimulateMethod.AutoIncrement
    assert new.points[matching].is_running is False
    for item in (other_slave, other_type):
        assert new.points[item].simulate_method is SimulateMethod.Random
        assert new.points[item].is_running is True


def test_restore_discards_deleted_points_and_leaves_new_points_at_defaults():
    old, new = _controller(), _controller()
    deleted, added = Yx(code="deleted"), Yx(code="added")
    old.add_point(deleted, SimulateMethod.FixedValue, 2)
    new.add_point(added, SimulateMethod.Random, 1, is_running=True)
    new.restore_configuration(old.snapshot_configuration())
    assert new.points[added].is_running is True
    assert len(new.snapshot_configuration()) == 1
    recreated = Yx(code="deleted")
    new.add_point(recreated, SimulateMethod.Random, 1, is_running=True)
    assert new.points[recreated].simulate_method is SimulateMethod.Random


def test_deferred_model_configuration_survives_repeated_reload_and_preserves_disabled_points():
    old = _controller(ProtocolType.Iec61850Server)
    point = Yc(code="LD0/GGIO1.AnIn1.mag.f", min_value_limit=5, max_value_limit=20)
    old.add_point(point, SimulateMethod.SineWave, 0.5, is_running=False)
    pending = _controller(ProtocolType.Iec61850Server)
    pending.restore_configuration(old.snapshot_configuration(), defer_missing=True)
    assert not pending.points

    reloaded = _controller(ProtocolType.Iec61850Server)
    reloaded.restore_configuration(pending.snapshot_configuration(), defer_missing=True)
    loaded_point = Yc(code=point.code)
    reloaded.add_point(loaded_point, SimulateMethod.Random, 1, is_running=True)
    assert reloaded.snapshot_configuration() == old.snapshot_configuration()
    assert reloaded.points[loaded_point].is_running is False


def test_empty_simulation_selection_stays_empty_after_reload():
    old, new = _controller(), _controller()
    for controller in (old, new):
        controller.add_point(Yx(code="switch"), SimulateMethod.Random, 1, is_running=True)
    old.apply_configuration([])
    new.restore_configuration(old.snapshot_configuration())
    assert all(not simulator.is_running for simulator in new.points.values())
