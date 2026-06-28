"""Protocol-boundary validation for channel imports and mutations."""

from src.data.model.channel import ChannelDict
from src.data.service.channel_service import ChannelService
from src.web.api.exceptions import NotFoundError, ValidationError

IEC61850_PROTOCOL_ID = 4


def get_channel_or_raise(channel_id: int) -> ChannelDict:
    """Return a channel or raise a user-facing 404 error."""
    channel = ChannelService.get_channel_by_id(channel_id)
    if not channel:
        raise NotFoundError(f"通道 {channel_id} 不存在")
    return channel


def require_iec61850_channel(channel_id: int) -> ChannelDict:
    """Ensure an ICD/SCL operation targets an IEC 61850 channel."""
    channel = get_channel_or_raise(channel_id)
    if channel.get("protocol_type") != IEC61850_PROTOCOL_ID:
        raise ValidationError(f"通道 {channel.get('name') or channel_id} 不是 IEC 61850 通道，禁止导入 ICD/SCL 模型")
    return channel


def require_tabular_point_channel(channel_id: int) -> ChannelDict:
    """Ensure an Excel point-table import does not target IEC 61850."""
    channel = get_channel_or_raise(channel_id)
    if channel.get("protocol_type") == IEC61850_PROTOCOL_ID:
        raise ValidationError(f"通道 {channel.get('name') or channel_id} 是 IEC 61850 通道，请使用 ICD/SCL 模型导入")
    return channel
