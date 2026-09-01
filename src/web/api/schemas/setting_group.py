"""IEC 61850 setting-group API request models."""

from typing import Any

from pydantic import BaseModel, Field


class SettingGroupListRequest(BaseModel):
    channel_id: int


class SettingGroupDetailRequest(SettingGroupListRequest):
    sgcb_ref: str = Field(min_length=1)


class SettingGroupSelectRequest(SettingGroupDetailRequest):
    group: int = Field(ge=1, le=65535)


class SettingValueWrite(BaseModel):
    address: str = Field(min_length=1)
    value: Any


class SettingValuesWriteRequest(SettingGroupDetailRequest):
    values: list[SettingValueWrite] = Field(min_length=1)
