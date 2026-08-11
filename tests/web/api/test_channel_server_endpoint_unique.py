"""TCP 服务端 IP+端口 唯一性校验的回归测试。

历史 bug：创建设备时只按端口号判重（不同 IP 的服务端使用相同端口被误判冲突），
编辑设备时完全没有服务端地址冲突检测。正确规则：TCP 服务端（conn_type=2）的
唯一标识是 IP+端口 组合，而非端口号本身。
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.web.api.channel.router import (
    _validate_server_endpoint_unique,
    create_channel,
    update_channel,
)
from src.web.api.exceptions import ValidationError
from src.web.api.schemas.channel import ChannelCreateRequest, ChannelUpdateRequest


def _server(**overrides) -> dict:
    ch = {
        "id": 9,
        "code": "SRV1",
        "name": "existing-server",
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
        "group_id": None,
    }
    ch.update(overrides)
    return ch


# ---------------------------------------------------------------- 纯函数


def test_same_ip_and_port_is_conflict():
    with patch(
        "src.web.api.channel.router.ChannelService.get_all_channels",
        return_value=[_server()],
    ):
        with pytest.raises(ValidationError, match="existing-server"):
            _validate_server_endpoint_unique("0.0.0.0", 502)


def test_same_port_different_ip_is_allowed():
    with patch(
        "src.web.api.channel.router.ChannelService.get_all_channels",
        return_value=[_server(ip="192.168.0.1")],
    ):
        # 同端口、不同具体 IP：不冲突（192.168.0.1:502 vs 192.168.0.2:502）
        _validate_server_endpoint_unique("192.168.0.2", 502)


def test_wildcard_zero_ip_conflicts_with_specific_ip():
    with patch(
        "src.web.api.channel.router.ChannelService.get_all_channels",
        return_value=[_server()],  # 已占用 0.0.0.0:502（监听所有 IP）
    ):
        # 0.0.0.0 通配监听，任何具体 IP 的同端口都冲突
        with pytest.raises(ValidationError, match="existing-server"):
            _validate_server_endpoint_unique("192.168.0.1", 502)


def test_wildcard_zero_ip_conflicts_with_specific_ip_reverse():
    # 反向：已占用具体 IP，新设备用 0.0.0.0 同端口同样冲突
    with patch(
        "src.web.api.channel.router.ChannelService.get_all_channels",
        return_value=[_server(ip="192.168.0.1")],
    ):
        with pytest.raises(ValidationError, match="existing-server"):
            _validate_server_endpoint_unique("0.0.0.0", 502)


def test_same_ip_different_port_is_allowed():
    with patch(
        "src.web.api.channel.router.ChannelService.get_all_channels",
        return_value=[_server()],
    ):
        _validate_server_endpoint_unique("0.0.0.0", 1502)


def test_non_server_channel_is_ignored():
    with patch(
        "src.web.api.channel.router.ChannelService.get_all_channels",
        return_value=[_server(id=1, name="client", conn_type=1, ip="192.168.1.10", port=502)],
    ):
        _validate_server_endpoint_unique("192.168.1.10", 502)


def test_exclude_self_allows_unchanged_endpoint():
    with patch(
        "src.web.api.channel.router.ChannelService.get_all_channels",
        return_value=[_server(id=1, name="myself", ip="192.168.0.1")],
    ):
        # 编辑自身时保留原 IP+端口，不应误报冲突
        _validate_server_endpoint_unique("192.168.0.1", 502, exclude_channel_id=1)


def test_empty_ip_treated_as_wildcard():
    # 历史数据 ip 可能为空，服务端兜底绑定 0.0.0.0，视为通配
    with patch(
        "src.web.api.channel.router.ChannelService.get_all_channels",
        return_value=[_server(ip=None)],
    ):
        with pytest.raises(ValidationError, match="existing-server"):
            _validate_server_endpoint_unique("192.168.0.1", 502)


def test_none_port_is_allowed():
    with patch(
        "src.web.api.channel.router.ChannelService.get_all_channels",
        return_value=[_server()],
    ):
        _validate_server_endpoint_unique("0.0.0.0", None)


# ---------------------------------------------------------------- 创建


def _create_req(**overrides) -> ChannelCreateRequest:
    data = dict(
        code="NEW1",
        name="new-device",
        protocol_type=1,
        conn_type=2,
        ip="0.0.0.0",
        port=502,
    )
    data.update(overrides)
    return ChannelCreateRequest(**data)


def _create_state():
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(device_controller=object())))


def test_create_rejects_same_ip_and_port():
    with (
        patch(
            "src.web.api.channel.router.ChannelService.get_channel_by_code",
            return_value=None,
        ),
        patch(
            "src.web.api.channel.router.ChannelService.get_all_channels",
            return_value=[_server()],
        ) as get_all,
        patch(
            "src.web.api.channel.router.ChannelService.provision_channel",
        ) as provision,
    ):
        with pytest.raises(ValidationError, match="existing-server"):
            asyncio.run(create_channel(_create_req(), _create_state()))
    provision.assert_not_called()
    get_all.assert_called_once()


def test_create_allows_same_port_different_ip():
    with (
        patch(
            "src.web.api.channel.router.ChannelService.get_channel_by_code",
            return_value=None,
        ),
        patch(
            "src.web.api.channel.router.ChannelService.get_all_channels",
            return_value=[_server(ip="192.168.0.1")],
        ),
        patch(
            "src.web.api.channel.router.ChannelService.provision_channel",
            return_value=(1, 2),
        ),
    ):
        asyncio.run(create_channel(_create_req(ip="192.168.0.2", port=502), _create_state()))


def test_create_allows_same_ip_different_port():
    with (
        patch(
            "src.web.api.channel.router.ChannelService.get_channel_by_code",
            return_value=None,
        ),
        patch(
            "src.web.api.channel.router.ChannelService.get_all_channels",
            return_value=[_server()],
        ),
        patch(
            "src.web.api.channel.router.ChannelService.provision_channel",
            return_value=(1, 2),
        ),
    ):
        asyncio.run(create_channel(_create_req(port=1502), _create_state()))


def test_create_client_skips_server_endpoint_check():
    with (
        patch(
            "src.web.api.channel.router.ChannelService.get_channel_by_code",
            return_value=None,
        ),
        patch(
            "src.web.api.channel.router.ChannelService.get_all_channels",
            return_value=[_server()],
        ) as get_all,
        patch(
            "src.web.api.channel.router.ChannelService.provision_channel",
            return_value=(1, 2),
        ),
    ):
        asyncio.run(create_channel(_create_req(conn_type=1), _create_state()))
    get_all.assert_not_called()


# ---------------------------------------------------------------- 编辑


def _existing(**overrides) -> dict:
    ch = _server(id=1, code="DEV1", name="dev1")
    ch.update(overrides)
    return ch


def _update_run(req: ChannelUpdateRequest, existing: dict) -> None:
    state = SimpleNamespace(device_controller=object())
    asyncio.run(update_channel(req, SimpleNamespace(app=SimpleNamespace(state=state))))


def test_update_rejects_conflicting_server_endpoint():
    # 已存在的服务端占用 192.168.1.50:502；自身当前是 0.0.0.0:1502
    existing = _existing(ip="0.0.0.0", port=1502)
    with (
        patch(
            "src.web.api.channel.router.ChannelService.get_channel_by_id",
            return_value=existing,
        ),
        patch(
            "src.web.api.channel.router.ChannelService.get_all_channels",
            return_value=[_server(ip="192.168.1.50", port=502), existing],
        ),
        patch(
            "src.web.api.channel.router.ChannelService.update_channel",
        ) as update,
    ):
        with pytest.raises(ValidationError, match="existing-server"):
            _update_run(
                ChannelUpdateRequest(channel_id=1, ip="192.168.1.50", port=502),
                existing,
            )
    update.assert_not_called()


def test_update_allows_same_port_different_ip():
    existing = _existing(ip="192.168.0.10", port=1502)
    with (
        patch(
            "src.web.api.channel.router.ChannelService.get_channel_by_id",
            return_value=existing,
        ),
        patch(
            "src.web.api.channel.router.ChannelService.get_all_channels",
            return_value=[_server(ip="192.168.0.20", port=502), existing],
        ),
        patch(
            "src.web.api.channel.router.ChannelService.update_channel",
            return_value=True,
        ),
    ):
        # 端口改为 502 但 IP 仍是 192.168.0.10，不与 192.168.0.20:502 冲突
        _update_run(ChannelUpdateRequest(channel_id=1, port=502), existing)


def test_update_rejects_wildcard_zero_ip_conflict():
    # 编辑改成 0.0.0.0 监听，与已占用的具体 IP 同端口冲突
    existing = _existing(ip="192.168.0.10", port=1502)
    with (
        patch(
            "src.web.api.channel.router.ChannelService.get_channel_by_id",
            return_value=existing,
        ),
        patch(
            "src.web.api.channel.router.ChannelService.get_all_channels",
            return_value=[_server(ip="192.168.0.20", port=502), existing],
        ),
        patch(
            "src.web.api.channel.router.ChannelService.update_channel",
        ) as update,
    ):
        with pytest.raises(ValidationError, match="existing-server"):
            _update_run(ChannelUpdateRequest(channel_id=1, ip="0.0.0.0", port=502), existing)
    update.assert_not_called()


def test_update_keeps_own_endpoint_is_allowed():
    existing = _existing(ip="192.168.0.10", port=1502)
    with (
        patch(
            "src.web.api.channel.router.ChannelService.get_channel_by_id",
            return_value=existing,
        ),
        patch(
            "src.web.api.channel.router.ChannelService.get_all_channels",
            return_value=[_server(ip="192.168.1.50", port=502), existing],
        ),
        patch(
            "src.web.api.channel.router.ChannelService.update_channel",
            return_value=True,
        ),
    ):
        # 仅改名称，IP+端口保持自身原值：排除自身后不应误报
        _update_run(ChannelUpdateRequest(channel_id=1, name="renamed"), existing)
