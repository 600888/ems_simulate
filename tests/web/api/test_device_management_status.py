from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.enums.modbus_def import ProtocolType
from src.web.api.device.router import get_management_status


def device(channel_id, protocol=ProtocolType.ModbusTcpServer, **overrides):
    values = dict(
        device_id=channel_id,
        name=f"device-{channel_id}",
        protocol_type=protocol,
        is_protocol_running=Mock(return_value=True),
        isSimulationRunning=Mock(return_value=False),
        iec61850_model_loaded=False,
        protocol_handler=SimpleNamespace(last_error=None),
    )
    return SimpleNamespace(**(values | overrides))


async def statuses(*devices):
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                device_controller=SimpleNamespace(device_list=list(devices)),
            )
        )
    )
    return (await get_management_status(request)).data


@pytest.mark.asyncio
async def test_snapshot_reports_runtime_roles_and_real_power_state():
    server, client, stopped = await statuses(
        device(10),
        device(20, ProtocolType.ModbusTcpClient),
        device(
            30,
            is_protocol_running=Mock(return_value=False),
            protocol_handler=SimpleNamespace(last_error="connection refused"),
        ),
    )
    assert server["channel_id"] == 10
    assert server["running"] is True
    assert server["simulation_supported"] is True
    assert client["simulation_supported"] is False
    assert client["simulation_reason"] == "clientNoSim"
    assert stopped["running"] is False
    assert stopped["error"] == "connection refused"


@pytest.mark.asyncio
async def test_opcua_uses_its_plugin_state_instead_of_generic_simulator():
    capabilities = Mock(
        return_value=[
            {
                "name": "simulation",
                "running": True,
                "details": {"rules": [{"node_id": "a", "paused": False, "error": None}]},
            }
        ]
    )
    ua = device(
        7,
        ProtocolType.OpcUaServer,
        protocol_handler=SimpleNamespace(
            last_error=None,
            server=SimpleNamespace(capabilities=capabilities),
        ),
    )
    result = (await statuses(ua))[0]
    assert result["simulating"] is True
    assert result["simulation_supported"] is True
    capabilities.return_value[0]["details"]["rules"][0]["paused"] = True
    assert (await statuses(ua))[0]["simulating"] is False
    capabilities.return_value[0]["details"]["rules"] = []
    assert (await statuses(ua))[0]["simulation_reason"] == "noSimulationRules"


@pytest.mark.asyncio
async def test_one_broken_device_does_not_hide_other_devices():
    broken, healthy = await statuses(
        device(1, is_protocol_running=Mock(side_effect=RuntimeError("offline"))), device(2)
    )
    assert broken["status_available"] is False
    assert broken["error"] == "offline"
    assert healthy["status_available"] is True


@pytest.mark.asyncio
async def test_opcua_stopped_transport_never_reports_active_simulation():
    ua = device(
        7,
        ProtocolType.OpcUaServer,
        is_protocol_running=Mock(return_value=False),
        protocol_handler=SimpleNamespace(
            last_error=None,
            server=SimpleNamespace(
                capabilities=Mock(
                    return_value=[
                        {
                            "name": "simulation",
                            "running": True,
                            "details": {"rules": [{"paused": False}]},
                        }
                    ]
                )
            ),
        ),
    )
    assert (await statuses(ua))[0]["simulating"] is False
