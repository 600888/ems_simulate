import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import ValidationError
import pytest

from src.web.api.channel.import_points import import_dlt645_standard_points
from src.web.api.channel.router import _runtime_configuration_changed
from src.web.api.schemas.channel import ChannelCreateRequest, ChannelUpdateRequest


def test_channel_requests_validate_dlt645_point_mode():
    request = ChannelCreateRequest(code="DLT", name="DLT", dlt645_point_mode="standard")
    update = ChannelUpdateRequest(channel_id=1, dlt645_point_mode="import")

    assert request.dlt645_point_mode == "standard"
    assert update.dlt645_point_mode == "import"
    with pytest.raises(ValidationError):
        ChannelCreateRequest(code="DLT", name="DLT", dlt645_point_mode="unknown")


def test_metadata_only_edit_does_not_rebuild_runtime_device():
    existing = {
        "name": "old-name",
        "protocol_type": 3,
        "conn_type": 1,
        "ip": "127.0.0.1",
        "port": 645,
        "rtu_addr": "000000000001",
    }
    request = ChannelUpdateRequest(channel_id=1, name="new-name", dlt645_point_mode="standard")

    assert not _runtime_configuration_changed(existing, request, None, None)


def test_connection_or_protocol_parameter_edit_rebuilds_runtime_device():
    existing = {"protocol_type": 3, "conn_type": 1, "ip": "127.0.0.1", "port": 645}

    assert _runtime_configuration_changed(
        existing,
        ChannelUpdateRequest(channel_id=1, port=646),
        None,
        None,
    )
    assert _runtime_configuration_changed(
        existing,
        ChannelUpdateRequest(channel_id=1),
        {"timeout": 2},
        {"timeout": 1},
    )


def test_standard_import_records_standard_source():
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                device_controller=SimpleNamespace(get_device_by_id=lambda _channel_id: None),
            )
        )
    )

    with (
        patch(
            "src.web.api.channel.import_points.ChannelService.get_channel_by_id",
            return_value={"id": 7, "protocol_type": 3},
        ),
        patch(
            "src.tools.dlt645_standard_importer.Dlt645StandardPointImporter.import_points",
            return_value=123,
        ),
        patch(
            "src.web.api.channel.import_points.ChannelService.update_channel",
            return_value=True,
        ) as update_channel,
    ):
        response = asyncio.run(import_dlt645_standard_points(request, channel_id=7))

    assert response.data["total"] == 123
    update_channel.assert_called_once_with(7, dlt645_point_mode="standard")
