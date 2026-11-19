"""Connection monitoring API request schemas."""

import ipaddress

from pydantic import BaseModel, Field, field_validator, model_validator

from src.device.core.connection import DisconnectReason


class ConnectionHistoryRequest(BaseModel):
    device_name: str
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
    disconnect_reason: DisconnectReason | None = None
    remote_ip: str | None = Field(None, max_length=45)

    @field_validator("remote_ip")
    @classmethod
    def validate_remote_ip(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return str(ipaddress.ip_address(value.strip()))


class ConnectionDetailRequest(BaseModel):
    device_name: str
    session_id: str = Field(..., min_length=1, max_length=36)


class ConnectionHistoryClearRequest(BaseModel):
    device_name: str | None = Field(None, min_length=1)
    channel_id: int | None = Field(None, gt=0)

    @model_validator(mode="after")
    def validate_target(self):
        if (self.device_name is None) == (self.channel_id is None):
            raise ValueError("请指定设备名称或通道ID，且只能指定其中一项")
        return self
