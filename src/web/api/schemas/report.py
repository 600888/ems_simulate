"""IEC 61850 Reports Pydantic 数据模型"""

from typing import Any

from pydantic import BaseModel, Field


class RcbListRequest(BaseModel):
    channel_id: int = Field(..., description="通道ID")


class RcbApplyConfigRequest(BaseModel):
    channel_id: int = Field(..., description="通道ID")
    rcb_ref: str = Field(..., description="RCB 引用路径")
    rpt_ena: bool = Field(..., description="报告使能目标状态")
    trg_ops: dict[str, bool] | None = Field(None, description="触发选项")
    opt_fields: dict[str, bool] | None = Field(None, description="可选字段")


class RcbBatchApplyConfigItem(BaseModel):
    rcb_ref: str = Field(..., description="RCB 引用路径")


class RcbBatchApplyConfigRequest(BaseModel):
    channel_id: int = Field(..., description="通道ID")
    items: list[RcbBatchApplyConfigItem] = Field(..., description="要批量应用的 RCB 列表")
    rpt_ena: bool = Field(..., description="报告使能目标状态")
    trg_ops: dict[str, bool] | None = Field(None, description="触发选项")
    opt_fields: dict[str, bool] | None = Field(None, description="可选字段")


class RcbGiRequest(BaseModel):
    channel_id: int = Field(..., description="通道ID")
    rcb_ref: str = Field(..., description="RCB 引用路径")


class ReportDataRequest(BaseModel):
    channel_id: int = Field(..., description="通道ID")
    rcb_ref: str = Field(..., description="RCB 引用路径")
    limit: int = Field(100, description="最多返回条数", ge=1, le=10000)
    known_latest_uid: int | None = Field(None, description="前端已知的最新报告 uid，用于无变化短路")


class ReportTreeDataRequest(BaseModel):
    channel_id: int = Field(..., description="通道ID")
    rcb_ref: str = Field(..., description="RCB 引用路径")
    entry_key: str | None = Field(None, description="报告条目 key，不传则按 latest 选择")
    latest: bool = Field(True, description="是否返回最新一条报告")
    known_latest_uid: int | None = Field(None, description="前端已知的最新报告 uid，用于无变化短路")


class RcbListResponse(BaseModel):
    channel_id: int = Field(..., description="通道ID")
    rcbs: list[dict[str, Any]] = Field(default_factory=list, description="RCB 列表")


class ReportDataResponse(BaseModel):
    channel_id: int = Field(..., description="通道ID")
    rcb_ref: str = Field(..., description="RCB 引用路径")
    data: list[dict[str, Any]] = Field(default_factory=list, description="报告数据列表")
    total: int = Field(0, description="总条数")


class ReportTreeNode(BaseModel):
    id: str = Field(..., description="节点唯一 ID")
    label: str = Field(..., description="显示名称")
    node_type: str = Field(..., description="节点类型: ld/ln/do/da/bda/group/value")
    fc: str | None = Field(None, description="功能约束")
    reason: str | None = Field(None, description="报告包含原因")
    value: Any = Field(None, description="显示值")
    raw_ref: str | None = Field(None, description="原始数据引用")
    children: list["ReportTreeNode"] = Field(default_factory=list, description="子节点")


class ReportTreeDataResponse(BaseModel):
    rcb_ref: str = Field(..., description="RCB 引用路径")
    entry: dict[str, Any] | None = Field(None, description="报告条目摘要")
    tree_items: list[ReportTreeNode] = Field(default_factory=list, description="树形报告数据")


class ActiveReportsResponse(BaseModel):
    channel_id: int = Field(..., description="通道ID")
    active_reports: list[dict[str, Any]] = Field(default_factory=list, description="活跃报告列表")


class RcbDetailRequest(BaseModel):
    channel_id: int = Field(..., description="通道ID")
    rcb_ref: str = Field(..., description="RCB 引用路径")
