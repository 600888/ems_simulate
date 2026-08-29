import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src.web.api.channel import iec61850 as channel_metadata_api


def test_dnp3_channel_can_read_quality_and_timestamp_metadata():
    metadata = {
        "quality": {"online": True, "detailQuality": "flags=0x01"},
        "timestamp": {"unixTimestampMs": 1_725_000_000_123},
    }
    device = SimpleNamespace(read_point_metadata_async=AsyncMock(return_value=metadata))
    controller = SimpleNamespace(get_device_by_channel_id=lambda _channel_id: device)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(device_controller=controller)))
    body = channel_metadata_api.Iec61850ReadMetadataRequest(
        channel_id=9,
        point_code="YX_1",
    )

    with patch.object(
        channel_metadata_api.ChannelService,
        "get_channel_by_id",
        return_value={"protocol_type": 5},
    ):
        response = asyncio.run(channel_metadata_api.iec61850_read_metadata(body, request))

    device.read_point_metadata_async.assert_awaited_once_with("YX_1")
    assert response.data == {"point_code": "YX_1", **metadata}
