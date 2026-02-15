from typing import List, Optional, Any
from pydantic import BaseModel, Field

class PointLeaf(BaseModel):
    """测点叶子节点"""
    code: str = Field(..., description="测点编码")
    name: str = Field(..., description="测点名称")
    value: Any = Field(None, description="测点值")
    rtu_addr: int = Field(..., description="从机地址")
    reg_addr: str = Field(..., description="寄存器地址")
    type: str = Field(..., description="测点类型 (YC/YX/YT/YK)")

class TypeNode(BaseModel):
    """类型节点 (遥测/遥信等)"""
    label: str = Field(..., description="类型标签")
    children: List[PointLeaf] = Field(default_factory=list, description="子节点 (测点列表)")

class DeviceNode(BaseModel):
    """设备节点"""
    label: str = Field(..., description="设备名称")
    children: List[TypeNode] = Field(default_factory=list, description="子节点 (类型列表)")

class TreeResponse(BaseModel):
    """树形结构响应"""
    data: List[DeviceNode] = Field(..., description="设备列表")
