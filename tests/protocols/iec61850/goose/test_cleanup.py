import asyncio
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.proto.iec61850.plugins.goose.cleanup import clear_channel_goose_resources
from src.web.api.device.router import discover_iec61850_model
from src.web.api.schemas import DeviceInfoRequest


def test_clear_channel_goose_resources_clears_database_and_runtime():
    manager = Mock()
    manager.delete_publishers_by_channel.return_value = 2
    manager.delete_receivers_by_channel.return_value = 1

    with (
        patch(
            "src.proto.iec61850.plugins.goose.cleanup.GoosePublisherDao.delete_by_channel",
            return_value=3,
        ) as delete_publishers,
        patch(
            "src.proto.iec61850.plugins.goose.cleanup.GooseReceiverDao.delete_by_channel",
            return_value=1,
        ) as delete_receivers,
    ):
        result = clear_channel_goose_resources(7, manager)

    delete_publishers.assert_called_once_with(7, raise_on_error=True)
    delete_receivers.assert_called_once_with(7)
    manager.delete_publishers_by_channel.assert_called_once_with(7, delete_from_db=False)
    manager.delete_receivers_by_channel.assert_called_once_with(7, delete_from_db=False)
    assert result == {
        "publishers": 3,
        "receivers": 1,
        "runtime_publishers": 2,
        "runtime_receivers": 1,
    }


def test_online_rediscovery_clears_channel_goose_before_discovery():
    device = Mock(device_id=7)
    device.iec61850_remote_discover_model.return_value = True
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                device_controller=SimpleNamespace(device_map={"remote": device}),
                goose_manager=Mock(),
            )
        )
    )
    cleanup_result = {
        "publishers": 1,
        "receivers": 1,
        "runtime_publishers": 1,
        "runtime_receivers": 1,
    }

    with patch(
        "src.proto.iec61850.plugins.goose.cleanup.clear_channel_goose_resources",
        return_value=cleanup_result,
    ) as cleanup:
        response = asyncio.run(discover_iec61850_model(DeviceInfoRequest(device_name="remote"), request))

    cleanup.assert_called_once_with(7, request.app.state.goose_manager)
    device.iec61850_remote_discover_model.assert_called_once_with()
    assert response.data is True
