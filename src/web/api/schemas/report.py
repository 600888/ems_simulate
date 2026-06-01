"""IEC 61850 Reports Pydantic 数据模型"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RcbListRequest(BaseModel):
    channel_id: int = Field(..., description="通道ID")


class RcbEnableRequest(BaseModel):
    channel_id: int = Field(..., description="通道ID")
    rcb_ref: str = Field(..., description="RCB 引用路径")
    gi: bool = Field(True, description="是否同时触发 GI")
    trg_ops: dict[str, bool] | None = Field(None, description="触发选项")
    opt_fields: dict[str, bool] | None = Field(None, description="可选字段")


class RcbDisableRequest(BaseModel):
    channel_id: int = Field(..., description="通道ID")
    rcb_ref: str = Field(..., description="RCB 引用路径")


class RcbGiRequest(BaseModel):
    channel_id: int = Field(..., description="通道ID")
    rcb_ref: str = Field(..., description="RCB 引用路径")


class ReportDataRequest(BaseModel):
    channel_id: int = Field(..., description="通道ID")
    rcb_ref: str = Field(..., description="RCB 引用路径")
    limit: int = Field(100, description="最多返回条数", ge=1, le=10000)


class RcbListResponse(BaseModel):
    channel_id: int = Field(..., description="通道ID")
    rcbs: list[dict[str, Any]] = Field(default_factory=list, description="RCB 列表")


class ReportDataResponse(BaseModel):
    channel_id: int = Field(..., description="通道ID")
    rcb_ref: str = Field(..., description="RCB 引用路径")
    data: list[dict[str, Any]] = Field(default_factory=list, description="报告数据列表")
    total: int = Field(0, description="总条数")


class ActiveReportsResponse(BaseModel):
    channel_id: int = Field(..., description="通道ID")
    active_reports: list[dict[str, Any]] = Field(default_factory=list, description="活跃报告列表")


class RcbDetailRequest(BaseModel):
    channel_id: int = Field(..., description="通道ID")
    rcb_ref: str = Field(..., description="RCB 引用路径")
