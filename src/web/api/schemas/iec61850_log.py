"""IEC 61850 log API request models."""

from pydantic import BaseModel, Field


class Iec61850LogListRequest(BaseModel):
    channel_id: int


class Iec61850LogControlRequest(Iec61850LogListRequest):
    lcb_ref: str = Field(min_length=1)


class Iec61850LogEnableRequest(Iec61850LogControlRequest):
    enabled: bool


class Iec61850LogQueryRequest(Iec61850LogListRequest):
    log_ref: str = Field(min_length=1)
    start_time_ms: int = Field(ge=0)
    end_time_ms: int = Field(ge=0)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=500)
    keyword: str = ""
    level: str = ""
    service: str = ""
