"""批量复制：起始IP + 各段独立偏移 的回归测试。

新能力：批量复制时输入起始 IP 与 4 个段各自的偏移量，
第 n 台设备第 k 段 = 起始IP[k] + 偏移[k] × (n-1)，溢出按 256 进制进位。
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pydantic import ValidationError
import pytest

from src.web.api.channel.device_manage import copy_device
from src.web.api.channel.helpers import apply_ip_offsets
from src.web.api.schemas.channel import CopyDeviceRequest

# ---------------------------------------------------------------- apply_ip_offsets


@pytest.mark.parametrize(
    ("start_ip", "offsets", "index", "expected"),
    [
        # 最后一段 +1，逐台递增
        ("192.168.0.1", [0, 0, 0, 1], 1, "192.168.0.1"),
        ("192.168.0.1", [0, 0, 0, 1], 2, "192.168.0.2"),
        ("192.168.0.1", [0, 0, 0, 1], 10, "192.168.0.10"),
        # 第三段偏移（192.168.X.1，X 递增，末段固定）
        ("192.168.1.10", [0, 0, 1, 0], 3, "192.168.3.10"),
        # 第二段偏移
        ("10.1.0.5", [0, 1, 0, 0], 4, "10.4.0.5"),
        # 第一段偏移
        ("1.2.3.4", [1, 0, 0, 0], 3, "3.2.3.4"),
        # 末段溢出进位到第三段（256 进制）
        ("192.168.0.254", [0, 0, 0, 2], 2, "192.168.1.0"),
        ("192.168.0.255", [0, 0, 0, 1], 2, "192.168.1.0"),
        # 跨多段进位
        ("192.168.255.255", [0, 0, 0, 1], 2, "192.169.0.0"),
        # 偏移为 0：所有设备同 IP
        ("10.0.0.1", [0, 0, 0, 0], 5, "10.0.0.1"),
    ],
)
def test_apply_ip_offsets(start_ip, offsets, index, expected):
    assert apply_ip_offsets(start_ip, offsets, index) == expected


def test_apply_ip_offsets_rejects_invalid_start_ip():
    with pytest.raises(ValueError, match="起始IP"):
        apply_ip_offsets("192.168.0", [0, 0, 0, 1], 1)
    with pytest.raises(ValueError, match="起始IP"):
        apply_ip_offsets("192.168.0.300", [0, 0, 0, 1], 1)
    with pytest.raises(ValueError, match="起始IP"):
        apply_ip_offsets("not-an-ip", [0, 0, 0, 1], 1)


def test_apply_ip_offsets_rejects_wrong_offset_length():
    with pytest.raises(ValueError, match="4个段"):
        apply_ip_offsets("192.168.0.1", [0, 0, 1], 1)


def test_apply_ip_offsets_rejects_first_segment_overflow():
    # 第一段溢出无法进位，视为超出 IPv4 范围
    with pytest.raises(ValueError, match="超出 IPv4 范围"):
        apply_ip_offsets("255.255.255.254", [0, 0, 0, 2], 2)


# ---------------------------------------------------------------- CopyDeviceRequest 校验


def test_copy_request_accepts_start_ip_and_offsets():
    req = CopyDeviceRequest(
        channel_id=1,
        count=2,
        ip_start="192.168.0.1",
        ip_offsets=[0, 0, 0, 1],
    )
    assert req.ip_start == "192.168.0.1"
    assert req.ip_offsets == [0, 0, 0, 1]


def test_copy_request_rejects_offsets_without_start_ip():
    with pytest.raises(ValidationError, match="ip_start"):
        CopyDeviceRequest(channel_id=1, count=2, ip_offsets=[0, 0, 0, 1])


def test_copy_request_rejects_start_ip_without_offsets():
    with pytest.raises(ValidationError, match="ip_offsets"):
        CopyDeviceRequest(channel_id=1, count=2, ip_start="192.168.0.1")


def test_copy_request_rejects_wrong_offsets_length():
    with pytest.raises(ValidationError, match="4个段"):
        CopyDeviceRequest(
            channel_id=1,
            count=2,
            ip_start="192.168.0.1",
            ip_offsets=[0, 0, 1],
        )


def test_copy_request_rejects_offsets_out_of_range():
    with pytest.raises(ValidationError, match="0-255"):
        CopyDeviceRequest(
            channel_id=1,
            count=2,
            ip_start="192.168.0.1",
            ip_offsets=[0, 0, 0, 256],
        )


# ---------------------------------------------------------------- 复制集成


def _source_channel(conn_type=1) -> dict:
    return {
        "id": 1,
        "device_id": 10,
        "code": "SOURCE",
        "name": "Source",
        "protocol_type": 1,
        "conn_type": conn_type,
        "ip": "192.168.0.1",
        "port": 502,
    }


def _fake_builder():
    return SimpleNamespace(makeGeneralDevice=lambda **_kwargs: SimpleNamespace(name=""))


def _copy_state():
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                device_controller=SimpleNamespace(
                    device_list=[],
                    device_map={},
                ),
            ),
        ),
    )


def test_copy_uses_start_ip_and_per_segment_offsets():
    request = CopyDeviceRequest(
        channel_id=1,
        count=3,
        ip_start="10.0.0.1",
        ip_offsets=[0, 0, 1, 0],
    )
    with (
        patch(
            "src.web.api.channel.device_manage.ChannelService.get_channel_by_id",
            return_value=_source_channel(),
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
        patch("src.web.api.channel.device_manage.PointMappingService.clone_for_device"),
        patch("src.web.api.channel.device_manage.PointMappingService.get_all_mappings", return_value=[]),
        patch("src.data.service.device_service.DeviceService.update_device"),
        patch("src.web.api.channel.device_manage.log"),
    ):
        response = asyncio.run(copy_device(request, _copy_state()))

    # 第三段偏移 +1：10.0.0.1 / 10.0.1.1 / 10.0.2.1
    assert [item.kwargs["ip"] for item in create_channel.call_args_list] == [
        "10.0.0.1",
        "10.0.1.1",
        "10.0.2.1",
    ]
    assert response.data["copied_count"] == 3


def test_copy_offsets_carry_to_previous_segment():
    request = CopyDeviceRequest(
        channel_id=1,
        count=2,
        ip_start="192.168.0.254",
        ip_offsets=[0, 0, 0, 2],
    )
    with (
        patch(
            "src.web.api.channel.device_manage.ChannelService.get_channel_by_id",
            return_value=_source_channel(),
        ),
        patch(
            "src.web.api.channel.device_manage.ChannelService.get_channel_by_code",
            return_value=None,
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
        patch("src.web.api.channel.device_manage.PointMappingService.clone_for_device"),
        patch("src.web.api.channel.device_manage.PointMappingService.get_all_mappings", return_value=[]),
        patch("src.data.service.device_service.DeviceService.update_device"),
        patch("src.web.api.channel.device_manage.log"),
    ):
        response = asyncio.run(copy_device(request, _copy_state()))

    # 末段 +2：254 → 256 进位到第三段
    assert [item.kwargs["ip"] for item in create_channel.call_args_list] == [
        "192.168.0.254",
        "192.168.1.0",
    ]
    assert response.data["copied_count"] == 2
