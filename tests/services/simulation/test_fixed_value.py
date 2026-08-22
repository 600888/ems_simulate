from types import SimpleNamespace

from src.device.simulator.point_simulator import PointSimulator
from src.device.simulator.simulation_controller import SimulationController
from src.enums.modbus_def import ProtocolType
from src.enums.point_data import SimulateMethod
from src.enums.points.yc import Yc
from src.enums.points.yx import Yx
from src.web.api.schemas.device import SimulationConfigItem


def test_fixed_value_simulation_restores_configured_value():
    point = Yx(code="switch", value=0)
    simulator = PointSimulator(point, SimulateMethod.FixedValue, 1)
    simulator.fixed_value = 1

    simulator.simulate()
    assert point.value == 1

    point.value = 0
    simulator.simulate()
    assert point.value == 1


def test_apply_configuration_sets_fixed_value():
    device = SimpleNamespace(protocol_type=ProtocolType.ModbusTcpServer)
    controller = SimulationController(device)
    point = Yx(code="switch", value=0)
    controller.add_point(point, SimulateMethod.Random, 1)

    applied, failed = controller.apply_configuration(
        [
            {
                "point_code": "switch",
                "simulate_method": "FixedValue",
                "fixed_value": 1,
                "enabled": True,
            }
        ]
    )

    simulator = controller.points[point]
    assert applied == ["switch"]
    assert failed == []
    assert simulator.simulate_method is SimulateMethod.FixedValue
    assert simulator.fixed_value == 1
    assert simulator.is_running is True


def test_fractional_step_is_accepted_and_applied():
    config = SimulationConfigItem(
        point_code="power",
        simulate_method=SimulateMethod.AutoIncrement,
        step=0.25,
    )
    assert config.step == 0.25

    point = Yc(
        code="power",
        value=1,
        decode="0x42",
        min_value_limit=0,
        max_value_limit=10,
    )
    simulator = PointSimulator(point, SimulateMethod.AutoIncrement, config.step)
    simulator.simulate()

    assert point.real_value == 1.25
