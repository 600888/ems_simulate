from ipaddress import IPv4Address
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

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
    dlt645_point_mode: Literal["standard", "import"] = "import"


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
    group_id: int | None = Field(None, description="设备组ID，NULL表示未分组")
    protocol_params: ProtocolParamsRequest | None = None
    model_name: str | None = None  # IEC61850 IED 模型名称
    dlt645_point_mode: Literal["standard", "import"] | None = None
    defer_runtime_reload: bool = False


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
    count: int = Field(2, ge=1, le=256, description="复制数量（1-256）")
    ip_start_offset: int = Field(1, ge=0, description="IP起始偏移量（仅作用于最后一段，兼容旧逻辑）")
    prefix: str | None = Field(None, description="编码前缀")
    suffix: str | None = Field(None, description="编码后缀")
    port_offset: int = Field(0, description="端口偏移量")
    target_group_id: int | None = Field(None, description="目标设备组ID，NULL表示未分组")
    ip_start: str | None = Field(None, description="批量复制起始IP，提供时按各段偏移生成IP")
    ip_offsets: list[int] | None = Field(None, description="各段独立偏移量（长度4，0-255），与 ip_start 配合使用")

    @model_validator(mode="after")
    def validate_ip_offsets(self):
        if self.ip_offsets is not None:
            if len(self.ip_offsets) != 4:
                raise ValueError("ip_offsets 必须包含4个段的偏移量")
            if any(not (0 <= v <= 255) for v in self.ip_offsets):
                raise ValueError("ip_offsets 每段偏移量必须在 0-255 之间")
            if self.ip_start is None:
                raise ValueError("提供 ip_offsets 时必须同时提供 ip_start")
        elif self.ip_start is not None:
            raise ValueError("提供 ip_start 时必须同时提供 ip_offsets")
        return self


class CopySingleDeviceRequest(BaseModel):
    """单个复制设备请求。"""

    channel_id: int = Field(..., description="源通道ID")
    target_name: str = Field(..., description="目标设备名称")
    target_code: str = Field(..., description="目标设备编码")
    target_ip: IPv4Address = Field(..., description="目标设备IP地址")
    target_port: int = Field(..., ge=1, le=65535, description="目标设备端口")

    @model_validator(mode="after")
    def validate_target_identity(self):
        self.target_name = self.target_name.strip()
        self.target_code = self.target_code.strip()
        if not self.target_name:
            raise ValueError("目标设备名称不能为空")
        if not self.target_code:
            raise ValueError("目标设备编码不能为空")
        return self
