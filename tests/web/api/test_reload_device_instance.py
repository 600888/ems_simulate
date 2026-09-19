"""reload_device_instance 原子替换时序测试。

验证修复：构建新实例完成前不移除旧实例，避免删除-重建空窗期内
接口报"设备不存在"；启动场景仍先停旧实例再启动新实例。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.device.simulator.simulation_controller import SimulationController
from src.enums.modbus_def import ProtocolType
from src.enums.point_data import SimulateMethod
from src.enums.points.yc import Yc
from src.web.api.channel import helpers


def _channel(name: str = "dlt645-server", protocol: str = "Dlt645Server"):
    return {
        "id": 1,
        "name": name,
        "code": "DLT645-SRV",
        "protocol_type": protocol,
        "conn_type": 2,
        "ip": "0.0.0.0",
        "port": 8899,
        "rtu_addr": "000000000001",
    }


def _controller(remove_side_effect=None):
    controller = SimpleNamespace(
        device_list=[],
        device_map={},
        remove_device_by_id=AsyncMock(side_effect=remove_side_effect or (lambda _id: True)),
    )
    return controller


def _new_device(name: str = "dlt645-server"):
    return SimpleNamespace(
        name=name,
        device_id=1,
        start=AsyncMock(return_value=True),
        set_device_provider=Mock(),
    )


@pytest.mark.asyncio
async def test_reload_non_start_removes_old_after_build():
    """非启动场景：先构建新实例，构建完成后再移除旧实例（无空窗）。"""
    controller = _controller()
    mappings = [{"id": 7}]
    with (
        patch.object(
            helpers.asyncio,
            "to_thread",
            side_effect=[_channel(), _new_device(), mappings, None],
        ) as to_thread,
        patch.object(helpers, "log", SimpleNamespace(info=lambda *a, **k: None)),
    ):
        result = await helpers.reload_device_instance(controller, 1, is_start=False)

    assert result.name == "dlt645-server"
    assert controller.device_map["dlt645-server"] is result
    # remove 只调用一次，且发生在新实例构建完成之后
    assert controller.remove_device_by_id.await_count == 1
    assert to_thread.await_args_list[-1].args == (result.set_device_provider, controller, mappings)


@pytest.mark.asyncio
async def test_reload_non_start_build_failure_keeps_old_device():
    """构建失败时旧设备不被移除（设备继续可用）。"""
    controller = _controller()
    controller.device_list.append(_new_device("old"))
    controller.device_map["dlt645-server"] = controller.device_list[0]

    def _raise(*args, **kwargs):
        raise RuntimeError("build failed")

    with (
        patch.object(helpers.asyncio, "to_thread", _raise),
        patch.object(helpers, "log", SimpleNamespace(info=lambda *a, **k: None)),
    ):
        with pytest.raises(RuntimeError):
            await helpers.reload_device_instance(controller, 1, is_start=False)

    # 旧实例未被移除
    assert controller.remove_device_by_id.await_count == 0
    assert controller.device_map["dlt645-server"] is controller.device_list[0]


@pytest.mark.asyncio
async def test_reload_client_start_stops_old_before_start():
    """启动场景（客户端）：先停止旧实例，再启动新实例。"""
    controller = _controller()
    new_device = _new_device()

    with (
        patch.object(
            helpers.asyncio,
            "to_thread",
            side_effect=[_channel(protocol="Dlt645Client"), new_device, [], None],
        ),
        patch.object(helpers, "log", SimpleNamespace(info=lambda *a, **k: None)),
    ):
        result = await helpers.reload_device_instance(controller, 1, is_start=True)

    assert result is new_device
    assert controller.device_map["dlt645-server"] is new_device
    # 启动场景同样只移除一次
    assert controller.remove_device_by_id.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("is_start", "was_simulating", "protocol_running", "resume"),
    [(False, True, False, False), (True, True, True, True), (True, False, True, False), (True, True, False, False)],
)
async def test_reload_migrates_simulation_settings_before_replacing_device(
    is_start, was_simulating, protocol_running, resume
):
    old_device = _new_device("before-rename")
    old_device.protocol_type = ProtocolType.Dnp3Server
    old_device.get_auto_read_status = Mock(return_value={})
    old_device.isSimulationRunning = Mock(return_value=was_simulating)
    old_device.simulation_controller = SimulationController(old_device)
    old_point = Yc(code="power", min_value_limit=-5, max_value_limit=30)
    old_device.simulation_controller.add_point(old_point, SimulateMethod.FixedValue, 0.25, is_running=False)
    old_device.simulation_controller.points[old_point].fixed_value = 17
    expected = old_device.simulation_controller.snapshot_configuration()

    new_device = _new_device("after-rename")
    new_device.protocol_type = ProtocolType.Dnp3Server
    new_device.simulation_controller = SimulationController(new_device)
    new_device.simulation_controller.add_point(Yc(code="power"), SimulateMethod.Random, 1, is_running=True)
    new_device.is_protocol_running = Mock(return_value=protocol_running)
    new_device.startSimulation = Mock()

    def remove_old(_id):
        # 替换之前就已恢复设置；旧实例可安全停止，且其设置没有被修改。
        assert new_device.simulation_controller.snapshot_configuration() == expected
        assert old_device.simulation_controller.snapshot_configuration() == expected
        controller.device_list.remove(old_device)
        controller.device_map.pop(old_device.name)

    controller = _controller(remove_old)
    controller.get_device_by_id = lambda _id: old_device
    controller.device_list.append(old_device)
    controller.device_map[old_device.name] = old_device
    with (
        patch.object(helpers.ChannelService, "get_channel_by_id", return_value=_channel("after-rename")),
        patch.object(helpers.ChannelService, "get_protocol_type", return_value=ProtocolType.Dnp3Server),
        patch.object(
            helpers, "get_device_builder", return_value=SimpleNamespace(makeGeneralDevice=Mock(return_value=new_device))
        ),
        patch.object(helpers, "configure_builder_network"),
        patch.object(helpers.PointMappingService, "get_all_mappings", return_value=[]),
    ):
        result = await helpers.reload_device_instance(controller, 1, is_start=is_start)

    assert result is new_device
    assert controller.device_list == [new_device]
    assert controller.device_map == {"after-rename": new_device}
    assert new_device.startSimulation.call_count == int(resume)
    assert new_device.start.await_count == int(is_start)


@pytest.mark.asyncio
@pytest.mark.parametrize("same_protocol", [True, False])
async def test_reload_defers_iec61850_settings_until_model_load_only_for_same_protocol(same_protocol):
    old = _new_device()
    old.protocol_type = ProtocolType.Iec61850Server if same_protocol else ProtocolType.ModbusTcpServer
    old.get_auto_read_status = Mock(return_value={})
    old.isSimulationRunning = Mock(return_value=False)
    old.simulation_controller = SimulationController(old)
    old.simulation_controller.add_point(Yc(code="power"), SimulateMethod.Pulse, 0.5, is_running=False)
    new = _new_device()
    new.protocol_type = ProtocolType.Iec61850Server
    new.simulation_controller = SimulationController(new)
    controller = _controller()
    controller.get_device_by_id = lambda _id: old
    with (
        patch.object(helpers.ChannelService, "get_channel_by_id", return_value=_channel()),
        patch.object(helpers.ChannelService, "get_protocol_type", return_value=ProtocolType.Iec61850Server),
        patch.object(
            helpers, "get_device_builder", return_value=SimpleNamespace(makeGeneralDevice=Mock(return_value=new))
        ),
        patch.object(helpers, "configure_builder_network"),
        patch.object(helpers.PointMappingService, "get_all_mappings", return_value=[]),
    ):
        await helpers.reload_device_instance(controller, 1, is_start=False)

    assert not new.simulation_controller.points
    loaded_point = Yc(code="power")
    new.simulation_controller.add_point(loaded_point, SimulateMethod.Random, 1, is_running=True)
    simulator = new.simulation_controller.points[loaded_point]
    assert simulator.simulate_method is (SimulateMethod.Pulse if same_protocol else SimulateMethod.Random)
    assert simulator.is_running is not same_protocol
