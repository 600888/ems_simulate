from typing import Any

from pydantic import BaseModel, Field

from src.config.config import Config


class ProtocolParamsRequest(BaseModel):
    schema_version: int = Field(1, ge=1)
    values: dict[str, Any] = Field(default_factory=dict)


class ChannelCreateRequest(BaseModel):
    code: str
    name: str
    protocol_type: int = 1
    conn_type: int = 2
    ip: str = Config.DEFAULT_IP
    port: int = Config.DEFAULT_PORT
    com_port: str | None = None
    baud_rate: int = 9600
    data_bits: int = 8
    stop_bits: int = 1
    parity: str = "N"
    rtu_addr: str = "1"
    group_id: int | None = None
    protocol_params: ProtocolParamsRequest | None = None
    model_name: str | None = None  # IEC61850 IED 模型名称


class ChannelUpdateRequest(BaseModel):
    channel_id: int = Field(..., description="通道ID")
    name: str | None = None
    protocol_type: int | None = None
    conn_type: int | None = None
    ip: str | None = None
    port: int | None = None
    com_port: str | None = None
    baud_rate: int | None = None
    data_bits: int | None = None
    stop_bits: int | None = None
    parity: str | None = None
    rtu_addr: str | None = None
    protocol_params: ProtocolParamsRequest | None = None
    model_name: str | None = None  # IEC61850 IED 模型名称


class ChannelDeleteRequest(BaseModel):
    channel_id: int = Field(..., description="通道ID")


class ChannelDetailRequest(BaseModel):
    channel_id: int = Field(..., description="通道ID")


class ChannelIdRequest(BaseModel):
    """通用通道ID请求"""

    channel_id: int = Field(..., description="通道ID")


class CreateAndStartDeviceRequest(BaseModel):
    channel_id: int


class CopyDeviceRequest(BaseModel):
    """复制设备请求"""

    channel_id: int = Field(..., description="源通道ID")
    count: int = Field(2, ge=1, le=100, description="复制数量（1-100）")
    ip_start_offset: int = Field(1, ge=0, description="IP起始偏移量")
    prefix: str | None = Field(None, description="编码前缀")
    suffix: str | None = Field(None, description="编码后缀")
    port_offset: int = Field(0, description="端口偏移量")
    target_group_id: int | None = Field(None, description="目标设备组ID，NULL表示未分组")
