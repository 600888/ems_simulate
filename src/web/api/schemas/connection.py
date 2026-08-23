"""Connection monitoring API request schemas."""

import ipaddress

from pydantic import BaseModel, Field, field_validator

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
