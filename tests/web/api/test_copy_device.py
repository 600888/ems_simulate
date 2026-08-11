"""Regression tests for copying devices with unchanged client endpoints."""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pydantic import ValidationError
import pytest

from src.data.service.iec61850_copy_service import Iec61850CopyResult
from src.web.api.channel.device_manage import copy_device, copy_single_device
from src.web.api.schemas.channel import CopyDeviceRequest, CopySingleDeviceRequest


@pytest.fixture(autouse=True)
def copy_configuration():
    with (
        patch("src.web.api.channel.device_manage.ChannelConfigurationService.clone_for_channel") as clone,
        patch("src.web.api.channel.device_manage.PointMappingService.clone_for_device"),
        patch("src.web.api.channel.device_manage.PointMappingService.get_all_mappings", return_value=[]),
        patch("src.data.service.device_service.DeviceService.update_device"),
        patch("src.web.api.channel.device_manage.log"),
    ):
        yield clone


def _fake_builder(device=None):
    runtime_device = device or SimpleNamespace(name="", set_device_provider=MagicMock())
    return SimpleNamespace(
        makeGeneralDevice=lambda **_kwargs: runtime_device,
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


def test_single_copy_uses_explicit_target_identity_and_endpoint():
    request = CopySingleDeviceRequest(
        channel_id=1,
        target_name="Target device",
        target_code="TARGET",
        target_ip="192.168.10.20",
        target_port=1502,
    )
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
        ) as create_channel,
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
            return_value={"id": 7},
        ),
        patch("src.data.dao.point_dao.PointDao.get_points_by_channel", return_value=[]),
        patch(
            "src.web.api.channel.device_manage.get_device_builder",
            return_value=_fake_builder(),
        ),
    ):
        response = asyncio.run(copy_single_device(request, app_request))

    assert create_device.call_args.kwargs == {
        "code": "TARGET",
        "name": "Target device",
        "device_type": 0,
        "group_id": 7,
    }
    assert create_channel.call_args.kwargs["ip"] == "192.168.10.20"
    assert create_channel.call_args.kwargs["port"] == 1502
    assert response.data["copied_count"] == 1


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
    device_controller = SimpleNamespace(device_list=[], device_map={})
    app_request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(device_controller=device_controller)))
    runtime_device = SimpleNamespace(name="", set_device_provider=MagicMock())
    builder = _fake_builder(runtime_device)

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
    runtime_device.set_device_provider.assert_called_once_with(device_controller, [])


def test_copy_iec104_preserves_protocol_metadata_for_all_point_types():
    request = CopyDeviceRequest(channel_id=2, count=1, ip_start_offset=0, suffix="_COPY")
    source_channel = {
        "id": 2,
        "device_id": 10,
        "code": "IEC104",
        "name": "IEC104",
        "protocol_type": 2,
        "conn_type": 2,
        "ip": "127.0.0.1",
        "port": 2404,
    }
    source_points = [
        {
            "id": 101,
            "code": "YC",
            "name": "YC",
            "rtu_addr": 1,
            "reg_addr": "0x4001",
            "frame_type": 0,
            "mul_coe": 0.1,
            "add_coe": 5,
            "iec_common_address": 1,
            "iec_cot": 3,
            "iec_quality": 0x11,
            "iec_type_id": "M_ME_NB_1",
        },
        {
            "id": 102,
            "code": "YX",
            "name": "YX",
            "rtu_addr": 1,
            "reg_addr": "0x0001",
            "frame_type": 1,
            "iec_common_address": 1,
            "iec_cot": 20,
            "iec_quality": 0x10,
            "iec_type_id": "M_DP_TB_1",
            "reverse": True,
        },
        {
            "id": 103,
            "code": "YK",
            "name": "YK",
            "rtu_addr": 1,
            "reg_addr": "0x6001",
            "frame_type": 2,
            "iec_common_address": 1,
            "iec_cot": 6,
            "iec_quality": 0,
            "iec_type_id": "C_DC_TA_1",
            "command_type": 1,
            "related_yx_id": 102,
        },
        {
            "id": 104,
            "code": "YT",
            "name": "YT",
            "rtu_addr": 1,
            "reg_addr": "0x6201",
            "frame_type": 3,
            "mul_coe": 0.1,
            "add_coe": 0,
            "iec_common_address": 1,
            "iec_cot": 6,
            "iec_quality": 1,
            "iec_type_id": "C_SE_NC_1",
            "related_yc_id": 101,
        },
    ]
    app_request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(device_controller=SimpleNamespace(device_list=[], device_map={})),
        ),
    )

    with (
        patch("src.web.api.channel.device_manage.ChannelService.get_channel_by_id", return_value=source_channel),
        patch("src.web.api.channel.device_manage.ChannelService.get_channel_by_code", return_value=None),
        patch(
            "src.web.api.channel.device_manage.ChannelService.get_all_channels",
            return_value=[],
        ),
        patch("src.web.api.channel.device_manage.ChannelService.create_channel", return_value=30),
        patch("src.data.service.device_service.DeviceService.get_device_by_id", return_value={"id": 10}),
        patch("src.data.service.device_service.DeviceService.create_device", return_value=20),
        patch("src.data.dao.point_dao.PointDao.get_points_by_channel", return_value=source_points),
        patch(
            "src.data.dao.point_dao.PointDao.create_point",
            side_effect=[{"id": 201}, {"id": 202}, {"id": 203}, {"id": 204}],
        ) as create_point,
        patch("src.web.api.channel.device_manage.get_device_builder", return_value=_fake_builder()),
    ):
        asyncio.run(copy_device(request, app_request))

    assert create_point.call_count == 4
    copied_by_frame = {call.args[1]: call.args[2] for call in create_point.call_args_list}
    for frame_type, source in enumerate(source_points):
        copied = copied_by_frame[frame_type]
        assert copied["code"] == source["code"]
        assert copied["iec_type_id"] == source["iec_type_id"]
        assert copied["iec_quality"] == source["iec_quality"]
        assert copied["iec_common_address"] == source["iec_common_address"]
        assert copied["iec_cot"] == source["iec_cot"]
    assert copied_by_frame[1]["reverse"] is True
    assert copied_by_frame[2]["command_type"] == 1
    assert copied_by_frame[2]["related_yx_id"] == 202
    assert copied_by_frame[3]["related_yc_id"] == 201


def test_copy_iec61850_deep_copies_model_resources_and_fc():
    request = CopyDeviceRequest(channel_id=4, count=1, ip_start_offset=0, suffix="_COPY")
    source_channel = {
        "id": 4,
        "device_id": 10,
        "code": "IED",
        "name": "IED",
        "protocol_type": 4,
        "conn_type": 2,
        "ip": "127.0.0.1",
        "port": 102,
        "model_name": "SOURCE_IED",
        "icd_path": "D:/models/source.icd",
        "icd_file_hash": "abc",
    }
    new_channel = {
        **source_channel,
        "id": 30,
        "device_id": 20,
        "code": "IED_COPY1",
        "name": "IED_COPY1",
        "icd_path": "D:/models/IED_COPY1/source.icd",
    }
    app_request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(device_controller=SimpleNamespace(device_list=[], device_map={})),
        ),
    )
    point = {
        "code": "MMXU1.TotW",
        "name": "Total active power",
        "rtu_addr": 1,
        "reg_addr": "SOURCE_IEDLD0/MMXU1.TotW.mag.f",
        "func_code": 3,
        "decode_code": "0x41",
        "mul_coe": 1.0,
        "add_coe": 0.0,
        "frame_type": 0,
        "fc": "MX",
    }
    copy_result = Iec61850CopyResult(
        model_copied=True,
        model_path=new_channel["icd_path"],
        model_hash="def",
        publisher_count=1,
        dataset_count=2,
        receiver_count=1,
        subscription_count=3,
    )

    with (
        patch(
            "src.web.api.channel.device_manage.ChannelService.get_channel_by_id",
            side_effect=[source_channel, new_channel],
        ),
        patch("src.web.api.channel.device_manage.ChannelService.get_channel_by_code", return_value=None),
        patch(
            "src.web.api.channel.device_manage.ChannelService.get_all_channels",
            return_value=[],
        ),
        patch("src.web.api.channel.device_manage.ChannelService.create_channel", return_value=30) as create_channel,
        patch("src.data.service.device_service.DeviceService.get_device_by_id", return_value={"id": 10}),
        patch("src.data.service.device_service.DeviceService.create_device", return_value=20),
        patch("src.data.dao.point_dao.PointDao.get_points_by_channel", return_value=[point]),
        patch("src.data.dao.point_dao.PointDao.create_point") as create_point,
        patch(
            "src.web.api.channel.device_manage.Iec61850CopyService.clone_for_channel",
            return_value=copy_result,
        ) as clone,
        patch("src.web.api.channel.device_manage.get_device_builder", return_value=_fake_builder()),
        patch("src.web.api.channel.device_manage.configure_builder_network") as configure_network,
    ):
        response = asyncio.run(copy_device(request, app_request))

    assert create_channel.call_args.kwargs["icd_path"] is None
    assert create_channel.call_args.kwargs["icd_file_hash"] is None
    clone.assert_called_once_with(source_channel, 30, 20, "IED_COPY1")
    assert create_point.call_args.args[2]["code"] == point["code"]
    assert create_point.call_args.args[2]["fc"] == "MX"
    assert configure_network.call_args.args[5]["icd_path"] == new_channel["icd_path"]
    assert response.data["devices"][0]["iec61850"]["dataset_count"] == 2


# ---------------------------------------------------------------- 复制：服务端 IP+端口 唯一性


def _server_source(**overrides) -> dict:
    ch = {
        "id": 1,
        "device_id": 10,
        "code": "SOURCE",
        "name": "Source",
        "protocol_type": 1,
        "conn_type": 2,
        "ip": "192.168.0.1",
        "port": 502,
    }
    ch.update(overrides)
    return ch


def _copy_state():
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                device_controller=SimpleNamespace(device_list=[], device_map={}),
            ),
        ),
    )


def test_batch_copy_server_skips_conflicting_endpoint():
    """批量复制服务端：目标端点与已有服务端冲突时跳过，不创建通道。"""
    request = CopyDeviceRequest(channel_id=1, count=2, ip_start_offset=0, port_offset=0)
    source_channel = _server_source()
    occupied = {"id": 9, "name": "Occupied", "conn_type": 2, "ip": "192.168.0.1", "port": 502}
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
            "src.web.api.channel.device_manage.ChannelService.get_all_channels",
            return_value=[occupied],
        ),
        patch(
            "src.web.api.channel.device_manage.ChannelService.create_channel",
            return_value=30,
        ) as create_channel,
        patch(
            "src.data.service.device_service.DeviceService.get_device_by_id",
            return_value={"id": 10, "group_id": None},
        ),
        patch(
            "src.data.service.device_service.DeviceService.create_device",
            return_value=20,
        ),
        patch("src.data.dao.point_dao.PointDao.get_points_by_channel", return_value=[]),
        patch(
            "src.web.api.channel.device_manage.get_device_builder",
            return_value=_fake_builder(),
        ),
    ):
        response = asyncio.run(copy_device(request, _copy_state()))

    assert response.data["copied_count"] == 0
    create_channel.assert_not_called()


def test_batch_copy_server_skips_wildcard_conflict():
    """批量复制服务端：目标 0.0.0.0 与已有具体 IP 同端口冲突时跳过。"""
    request = CopyDeviceRequest(channel_id=1, count=1, ip_start_offset=0, port_offset=0)
    source_channel = _server_source(ip="0.0.0.0")
    occupied = {"id": 9, "name": "Occupied", "conn_type": 2, "ip": "192.168.0.1", "port": 502}
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
            "src.web.api.channel.device_manage.ChannelService.get_all_channels",
            return_value=[occupied],
        ),
        patch(
            "src.web.api.channel.device_manage.ChannelService.create_channel",
            return_value=30,
        ) as create_channel,
        patch(
            "src.data.service.device_service.DeviceService.get_device_by_id",
            return_value={"id": 10, "group_id": None},
        ),
        patch(
            "src.data.service.device_service.DeviceService.create_device",
            return_value=20,
        ),
        patch("src.data.dao.point_dao.PointDao.get_points_by_channel", return_value=[]),
        patch(
            "src.web.api.channel.device_manage.get_device_builder",
            return_value=_fake_builder(),
        ),
    ):
        response = asyncio.run(copy_device(request, _copy_state()))

    assert response.data["copied_count"] == 0
    create_channel.assert_not_called()


def test_batch_copy_server_allows_different_ip_same_port():
    """批量复制服务端：IP 递增后端点不同（192.168.0.2/3:502），不与 192.168.0.1:502 冲突。"""
    request = CopyDeviceRequest(channel_id=1, count=2, ip_start_offset=1, port_offset=0)
    source_channel = _server_source()
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
            "src.web.api.channel.device_manage.ChannelService.get_all_channels",
            return_value=[source_channel],
        ),
        patch(
            "src.web.api.channel.device_manage.ChannelService.create_channel",
            side_effect=[31, 32],
        ) as create_channel,
        patch(
            "src.data.service.device_service.DeviceService.get_device_by_id",
            return_value={"id": 10, "group_id": None},
        ),
        patch(
            "src.data.service.device_service.DeviceService.create_device",
            side_effect=[21, 22],
        ),
        patch("src.data.dao.point_dao.PointDao.get_points_by_channel", return_value=[]),
        patch(
            "src.web.api.channel.device_manage.get_device_builder",
            return_value=_fake_builder(),
        ),
    ):
        response = asyncio.run(copy_device(request, _copy_state()))

    assert response.data["copied_count"] == 2
    assert [item.kwargs["ip"] for item in create_channel.call_args_list] == [
        "192.168.0.2",
        "192.168.0.3",
    ]


def test_single_copy_server_rejects_conflicting_endpoint():
    """单个复制服务端：目标端点与已有服务端冲突时报错。"""
    from src.web.api.exceptions import ConflictError

    request = CopySingleDeviceRequest(
        channel_id=1,
        target_name="Target",
        target_code="TARGET",
        target_ip="192.168.0.2",
        target_port=502,
    )
    source_channel = _server_source(port=1502)
    occupied = {"id": 9, "name": "Occupied", "conn_type": 2, "ip": "192.168.0.2", "port": 502}
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
            "src.web.api.channel.device_manage.ChannelService.get_all_channels",
            return_value=[occupied],
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
        patch(
            "src.web.api.channel.device_manage.get_device_builder",
            return_value=_fake_builder(),
        ),
    ):
        with pytest.raises(ConflictError, match="Occupied"):
            asyncio.run(copy_single_device(request, _copy_state()))


def test_single_copy_server_allows_different_ip_same_port():
    """单个复制服务端：不同 IP 同端口（192.168.0.2:502 vs 192.168.0.3:502）不冲突。"""
    request = CopySingleDeviceRequest(
        channel_id=1,
        target_name="Target",
        target_code="TARGET",
        target_ip="192.168.0.2",
        target_port=502,
    )
    source_channel = _server_source()
    other = {"id": 9, "name": "Other", "conn_type": 2, "ip": "192.168.0.3", "port": 502}
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
            "src.web.api.channel.device_manage.ChannelService.get_all_channels",
            return_value=[other],
        ),
        patch(
            "src.web.api.channel.device_manage.ChannelService.create_channel",
            return_value=30,
        ) as create_channel,
        patch(
            "src.data.service.device_service.DeviceService.get_device_by_id",
            return_value={"id": 10, "group_id": None},
        ),
        patch(
            "src.data.service.device_service.DeviceService.create_device",
            return_value=20,
        ),
        patch("src.data.dao.point_dao.PointDao.get_points_by_channel", return_value=[]),
        patch(
            "src.web.api.channel.device_manage.get_device_builder",
            return_value=_fake_builder(),
        ),
    ):
        response = asyncio.run(copy_single_device(request, _copy_state()))

    assert response.data["copied_count"] == 1
    assert create_channel.call_args.kwargs["ip"] == "192.168.0.2"
    assert create_channel.call_args.kwargs["port"] == 502


def test_copy_client_device_skips_server_endpoint_check():
    """客户端（conn_type=1）复制不触发服务端端点检测。"""
    request = CopySingleDeviceRequest(
        channel_id=1,
        target_name="Target",
        target_code="TARGET",
        target_ip="192.168.0.2",
        target_port=502,
    )
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
            "src.web.api.channel.device_manage.ChannelService.get_all_channels",
            return_value=[{"id": 9, "name": "Occupied", "conn_type": 2, "ip": "192.168.0.2", "port": 502}],
        ) as get_all,
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
        patch(
            "src.web.api.channel.device_manage.get_device_builder",
            return_value=_fake_builder(),
        ),
    ):
        response = asyncio.run(copy_single_device(request, _copy_state()))

    assert response.data["copied_count"] == 1
    get_all.assert_not_called()
