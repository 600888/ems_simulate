"""编辑通道时更新设备分组（group_id）的回归测试。

历史 bug：ChannelUpdateRequest 缺少 group_id 字段，前端编辑设备时提交的
group_id 被 Pydantic 静默丢弃，导致编辑设备修改分组无效。
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.web.api.channel.router import update_channel
from src.web.api.exceptions import OperationError, ValidationError
from src.web.api.schemas.channel import ChannelUpdateRequest


def _existing(device_id=10, group_id=1) -> dict:
    return {
        "id": 1,
        "device_id": device_id,
        "code": "DEV1",
        "name": "dev1",
        "protocol_type": 1,
        "conn_type": 2,
        "ip": "0.0.0.0",
        "port": 502,
        "com_port": None,
        "baud_rate": 9600,
        "data_bits": 8,
        "stop_bits": 1,
        "parity": "N",
        "rtu_addr": "1",
        "dlt645_point_mode": "import",
        "model_name": None,
        "group_id": group_id,
    }


def _run(req: ChannelUpdateRequest, existing: dict) -> None:
    state = SimpleNamespace(device_controller=object())
    asyncio.run(update_channel(req, SimpleNamespace(app=SimpleNamespace(state=state))))


def test_update_channel_moves_device_to_new_group():
    existing = _existing()
    with (
        patch(
            "src.web.api.channel.router.ChannelService.get_channel_by_id",
            return_value=existing,
        ),
        patch(
            "src.web.api.channel.router.DeviceGroupService.get_group_by_id",
            return_value={"id": 2},
        ),
        patch(
            "src.web.api.channel.router.DeviceGroupService.move_devices_to_group",
            return_value=1,
        ) as move,
    ):
        _run(ChannelUpdateRequest(channel_id=1, group_id=2), existing)
    move.assert_called_once_with([10], 2)


def test_update_channel_moves_device_to_ungrouped():
    existing = _existing()
    with (
        patch(
            "src.web.api.channel.router.ChannelService.get_channel_by_id",
            return_value=existing,
        ),
        patch(
            "src.web.api.channel.router.DeviceGroupService.get_group_by_id",
        ),
        patch(
            "src.web.api.channel.router.DeviceGroupService.move_devices_to_group",
            return_value=1,
        ) as move,
    ):
        _run(ChannelUpdateRequest(channel_id=1, group_id=None), existing)
    move.assert_called_once_with([10], None)


def test_update_channel_skips_move_when_group_unchanged():
    existing = _existing(group_id=2)
    with (
        patch(
            "src.web.api.channel.router.ChannelService.get_channel_by_id",
            return_value=existing,
        ),
        patch(
            "src.web.api.channel.router.DeviceGroupService.get_group_by_id",
        ),
        patch(
            "src.web.api.channel.router.DeviceGroupService.move_devices_to_group",
        ) as move,
    ):
        _run(ChannelUpdateRequest(channel_id=1, group_id=2), existing)
    move.assert_not_called()


def test_update_channel_skips_move_when_group_not_submitted():
    # 只修改名称、未显式提交 group_id 时，不应触发分组移动
    existing = _existing()
    with (
        patch(
            "src.web.api.channel.router.ChannelService.get_channel_by_id",
            return_value=existing,
        ),
        patch(
            "src.web.api.channel.router.DeviceGroupService.get_group_by_id",
        ),
        patch(
            "src.web.api.channel.router.DeviceGroupService.move_devices_to_group",
        ) as move,
        patch(
            "src.web.api.channel.router.ChannelService.update_channel",
            return_value=True,
        ),
    ):
        _run(ChannelUpdateRequest(channel_id=1, name="new-name"), existing)
    move.assert_not_called()


def test_update_channel_raises_when_group_move_fails():
    existing = _existing()
    with (
        patch(
            "src.web.api.channel.router.ChannelService.get_channel_by_id",
            return_value=existing,
        ),
        patch(
            "src.web.api.channel.router.DeviceGroupService.get_group_by_id",
            return_value={"id": 2},
        ),
        patch(
            "src.web.api.channel.router.DeviceGroupService.move_devices_to_group",
            return_value=0,
        ),
    ):
        with pytest.raises(OperationError):
            _run(ChannelUpdateRequest(channel_id=1, group_id=2), existing)


def test_update_channel_rejects_nonexistent_group():
    existing = _existing()
    with (
        patch(
            "src.web.api.channel.router.ChannelService.get_channel_by_id",
            return_value=existing,
        ),
        patch(
            "src.web.api.channel.router.DeviceGroupService.get_group_by_id",
            return_value=None,
        ),
        patch(
            "src.web.api.channel.router.DeviceGroupService.move_devices_to_group",
        ),
    ):
        with pytest.raises(ValidationError):
            _run(ChannelUpdateRequest(channel_id=1, group_id=99), existing)
