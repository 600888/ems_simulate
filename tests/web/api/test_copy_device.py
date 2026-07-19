"""Regression tests for copying devices with unchanged client endpoints."""

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import ValidationError
import pytest

from src.web.api.channel.device_manage import copy_device
from src.web.api.schemas.channel import CopyDeviceRequest


@pytest.fixture(autouse=True)
def copy_configuration():
    with (
        patch("src.web.api.channel.device_manage.ChannelConfigurationService.clone_for_channel") as clone,
        patch("src.data.service.device_service.DeviceService.update_device"),
        patch("src.web.api.channel.device_manage.log"),
    ):
        yield clone


def _fake_builder():
    return SimpleNamespace(
        makeGeneralDevice=lambda **_kwargs: SimpleNamespace(name=""),
    )


def test_copy_device_request_accepts_unchanged_ip_and_port():
    request = CopyDeviceRequest(
        channel_id=1,
        count=2,
        ip_start_offset=0,
        port_offset=0,
    )

    assert request.ip_start_offset == 0
    assert request.port_offset == 0


def test_copy_device_request_rejects_negative_ip_offset():
    with pytest.raises(ValidationError):
        CopyDeviceRequest(channel_id=1, ip_start_offset=-1)


@pytest.mark.parametrize(
    ("target_group", "expected_group"),
    [
        (42, 42),
        (None, None),
        ("omitted", 7),
    ],
)
def test_copy_device_uses_selected_group_and_preserves_legacy_default(
    target_group: int | None | str,
    expected_group: int | None,
):
    request_data = {"channel_id": 1, "count": 1, "ip_start_offset": 0}
    if target_group != "omitted":
        request_data["target_group_id"] = target_group
    request = CopyDeviceRequest(**request_data)
    source_channel = {
        "id": 1,
        "device_id": 10,
        "code": "SOURCE",
        "name": "Source",
        "protocol_type": 1,
        "conn_type": 1,
        "ip": "127.0.0.1",
        "port": 502,
    }
    app_request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                device_controller=SimpleNamespace(device_list=[], device_map={}),
            ),
        ),
    )

    with (
        patch(
            "src.web.api.channel.device_manage.ChannelService.get_channel_by_id",
            return_value=source_channel,
        ),
        patch(
            "src.web.api.channel.device_manage.ChannelService.get_channel_by_code",
            return_value=None,
        ),
        patch(
            "src.web.api.channel.device_manage.ChannelService.create_channel",
            return_value=30,
        ),
        patch(
            "src.data.service.device_service.DeviceService.get_device_by_id",
            return_value={"id": 10, "group_id": 7},
        ),
        patch(
            "src.data.service.device_service.DeviceService.create_device",
            return_value=20,
        ) as create_device,
        patch(
            "src.data.service.device_group_service.DeviceGroupService.get_group_by_id",
            return_value={"id": 42},
        ),
        patch("src.data.dao.point_dao.PointDao.get_points_by_channel", return_value=[]),
        patch(
            "src.web.api.channel.device_manage.get_device_builder",
            return_value=_fake_builder(),
        ),
    ):
        asyncio.run(copy_device(request, app_request))

    assert create_device.call_args.kwargs["group_id"] == expected_group


def test_zero_ip_offset_keeps_source_ip_for_every_copy():
    request = CopyDeviceRequest(channel_id=1, count=3, ip_start_offset=0)
    source_channel = {
        "id": 1,
        "device_id": 10,
        "code": "SOURCE",
        "name": "Source",
        "protocol_type": 1,
        "conn_type": 1,
        "ip": "127.0.0.1",
        "port": 2404,
    }
    app_request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                device_controller=SimpleNamespace(device_list=[], device_map={}),
            ),
        ),
    )

    with (
        patch(
            "src.web.api.channel.device_manage.ChannelService.get_channel_by_id",
            return_value=source_channel,
        ),
        patch(
            "src.web.api.channel.device_manage.ChannelService.get_channel_by_code",
            return_value=None,
        ),
        patch(
            "src.web.api.channel.device_manage.ChannelService.create_channel",
            side_effect=[31, 32, 33],
        ) as create_channel,
        patch(
            "src.data.service.device_service.DeviceService.get_device_by_id",
            return_value={"id": 10, "group_id": None},
        ),
        patch(
            "src.data.service.device_service.DeviceService.create_device",
            side_effect=[21, 22, 23],
        ),
        patch("src.data.dao.point_dao.PointDao.get_points_by_channel", return_value=[]),
        patch(
            "src.web.api.channel.device_manage.get_device_builder",
            return_value=_fake_builder(),
        ),
    ):
        asyncio.run(copy_device(request, app_request))

    assert [item.kwargs["ip"] for item in create_channel.call_args_list] == [
        "127.0.0.1",
        "127.0.0.1",
        "127.0.0.1",
    ]


def test_copy_loads_runtime_and_security_from_new_channel(copy_configuration):
    request = CopyDeviceRequest(channel_id=2, count=1, ip_start_offset=0)
    source_channel = {
        "id": 2,
        "device_id": 10,
        "code": "PCS2",
        "name": "PCS2",
        "protocol_type": 2,
        "conn_type": 1,
        "ip": "127.0.0.1",
        "port": 2404,
    }
    app_request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                device_controller=SimpleNamespace(device_list=[], device_map={}),
            ),
        ),
    )
    builder = _fake_builder()

    with (
        patch(
            "src.web.api.channel.device_manage.ChannelService.get_channel_by_id",
            return_value=source_channel,
        ),
        patch(
            "src.web.api.channel.device_manage.ChannelService.get_channel_by_code",
            return_value=None,
        ),
        patch(
            "src.web.api.channel.device_manage.ChannelService.create_channel",
            return_value=30,
        ),
        patch(
            "src.data.service.device_service.DeviceService.get_device_by_id",
            return_value={"id": 10, "group_id": None},
        ),
        patch(
            "src.data.service.device_service.DeviceService.create_device",
            return_value=20,
        ),
        patch("src.data.dao.point_dao.PointDao.get_points_by_channel", return_value=[]),
        patch("src.web.api.channel.device_manage.get_device_builder", return_value=builder),
        patch("src.web.api.channel.device_manage.configure_builder_network") as configure_network,
    ):
        asyncio.run(copy_device(request, app_request))

    copied_channel_data = configure_network.call_args.args[5]
    copy_configuration.assert_called_once_with(2, 30, 2, 1)
    assert copied_channel_data["id"] == 30
    assert copied_channel_data["device_id"] == 20
    assert copied_channel_data["id"] != source_channel["id"]
