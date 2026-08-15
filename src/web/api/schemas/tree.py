from typing import Any

from pydantic import BaseModel, Field


class PointLeaf(BaseModel):
    """测点叶子节点"""

    code: str = Field(..., description="测点编码")
    name: str = Field(..., description="测点名称")
    value: Any = Field(None, description="测点值")
    rtu_addr: int = Field(..., description="从机地址")
    reg_addr: str = Field(..., description="寄存器地址")
    type: str = Field(..., description="测点类型 (YC/YX/YT/YK)")


class GroupNode(BaseModel):
    """分组节点 (可嵌套)，用于 DLT645 数据标识前缀 / 结算日分组"""

    label: str = Field(..., description="分组标签")
    dlt645_prefix: int | None = Field(None, description="DLT645 数据标识前缀 (0-4)，非 DLT645 分组为空")
    dlt645_settlement: int | None = Field(
        None, description="DLT645 结算日 (0=当前, 1-12=上N结算日)，无结算日分组时为空"
    )
    children: list["GroupNode | PointLeaf"] = Field(default_factory=list, description="子节点 (测点或更深层分组)")


class TypeNode(BaseModel):
    """类型节点 (遥测/遥信等)"""

    label: str = Field(..., description="类型标签")
    children: list["GroupNode | PointLeaf"] = Field(default_factory=list, description="子节点 (测点列表或分组)")


class DeviceNode(BaseModel):
    """设备节点"""

    label: str = Field(..., description="设备名称")
    children: list[TypeNode] = Field(default_factory=list, description="子节点 (类型列表)")


class TreeResponse(BaseModel):
    """树形结构响应"""

    data: list[DeviceNode] = Field(..., description="设备列表")


# 解析递归前向引用
GroupNode.model_rebuild()
TypeNode.model_rebuild()
