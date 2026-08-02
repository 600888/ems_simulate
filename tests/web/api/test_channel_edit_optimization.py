import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src.web.api.channel.security import upload_security_config
from src.web.api.schemas.channel import ChannelUpdateRequest


def test_update_request_can_defer_reload_to_security_save():
    request = ChannelUpdateRequest(channel_id=1, defer_runtime_reload=True)

    assert request.defer_runtime_reload is True


def test_unchanged_security_does_not_save_or_reload_device():
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(device_controller=object())))
    public_security = {
        "tls_enabled": False,
        "tls_mode": "mutual",
        "certificate_configured": False,
        "certificate_filename": None,
        "private_key_configured": False,
        "private_key_filename": None,
        "ca_certificate_configured": False,
        "ca_certificate_filename": None,
    }
    runtime_security = {
        "tls_enabled": False,
        "tls_mode": "mutual",
        "certificate_path": None,
        "private_key_path": None,
        "ca_certificate_path": None,
    }

    with (
        patch(
            "src.web.api.channel.security.ChannelService.get_channel_by_id",
            return_value={"id": 1, "protocol_type": 1, "conn_type": 1},
        ),
        patch(
            "src.web.api.channel.security.ChannelConfigurationService.get_runtime_security",
            return_value=runtime_security,
        ),
        patch(
            "src.web.api.channel.security.ChannelConfigurationService.get_security_config",
            return_value=public_security,
        ),
        patch(
            "src.web.api.channel.security.ChannelConfigurationService.save_security_config",
        ) as save_security,
        patch(
            "src.web.api.channel.security.reload_device_instance",
            new_callable=AsyncMock,
        ) as reload_device,
    ):
        response = asyncio.run(
            upload_security_config(
                request=request,
                channel_id=1,
                tls_enabled=False,
                tls_mode="mutual",
                certificate=None,
                private_key=None,
                ca_certificate=None,
            )
        )

    assert response.message == "TLS 配置未变化"
    save_security.assert_not_called()
    reload_device.assert_not_awaited()
