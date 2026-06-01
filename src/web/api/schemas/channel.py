from typing import Optional

from pydantic import BaseModel, Field

from src.config.config import Config


class ChannelCreateRequest(BaseModel):
    code: str
    name: str
    protocol_type: int = 1
    conn_type: int = 2
    ip: str = Config.DEFAULT_IP
    port: int = Config.DEFAULT_PORT
    com_port: Optional[str] = None
    baud_rate: int = 9600
    data_bits: int = 8
    stop_bits: int = 1
    parity: str = "N"
    rtu_addr: str = "1"
    group_id: Optional[int] = None
    model_name: Optional[str] = None  # IEC61850 IED 模型名称


class ChannelUpdateRequest(BaseModel):
    channel_id: int = Field(..., description="通道ID")
    name: Optional[str] = None
    protocol_type: Optional[int] = None
    conn_type: Optional[int] = None
    ip: Optional[str] = None
    port: Optional[int] = None
    com_port: Optional[str] = None
    baud_rate: Optional[int] = None
    data_bits: Optional[int] = None
    stop_bits: Optional[int] = None
    parity: Optional[str] = None
    rtu_addr: Optional[str] = None
    model_name: Optional[str] = None  # IEC61850 IED 模型名称


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
    ip_start_offset: int = Field(1, ge=1, description="IP起始偏移量")
    prefix: Optional[str] = Field(None, description="编码前缀")
    suffix: Optional[str] = Field(None, description="编码后缀")
    port_offset: int = Field(0, description="端口偏移量")
