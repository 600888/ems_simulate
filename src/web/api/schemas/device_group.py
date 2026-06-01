from typing import List, Optional

from pydantic import BaseModel, Field


class DeviceGroupCreateRequest(BaseModel):
    """创建设备组请求"""

    code: str = Field(..., description="设备组编码", max_length=32)
    name: str = Field(..., description="设备组名称", max_length=64)
    parent_id: int | None = Field(None, description="父设备组ID，NULL表示顶级")
    description: str | None = Field(None, description="设备组描述", max_length=256)


class DeviceGroupIdRequest(BaseModel):
    """通用设备组ID请求"""

    group_id: int = Field(..., description="设备组ID")


class DeviceGroupUpdateRequest(BaseModel):
    """更新设备组请求"""

    group_id: int = Field(..., description="设备组ID")
    name: str | None = Field(None, description="设备组名称", max_length=64)
    parent_id: int | None = Field(None, description="父设备组ID")
    description: str | None = Field(None, description="设备组描述", max_length=256)
    status: int | None = Field(None, description="设备组状态")


class DeviceGroupDeleteRequest(BaseModel):
    """删除设备组请求"""

    group_id: int = Field(..., description="设备组ID")
    cascade: bool = Field(False, description="是否级联删除子组，False时将子组和设备移至未分组")


class DeviceToGroupRequest(BaseModel):
    """将设备添加到设备组请求"""

    device_id: int = Field(..., description="设备ID")
    group_id: int = Field(..., description="目标设备组ID")


class RemoveDeviceRequest(BaseModel):
    """将设备从设备组移除请求"""

    device_id: int = Field(..., description="设备ID")


class DevicesToGroupRequest(BaseModel):
    """批量移动设备到设备组请求"""

    device_ids: list[int] = Field(..., description="设备ID列表")
    group_id: int | None = Field(None, description="目标设备组ID，NULL表示移至未分组")


class BatchDeviceOperationRequest(BaseModel):
    """批量设备操作请求"""

    group_id: int = Field(..., description="设备组ID")
    operation: str = Field(..., description="操作类型: start/stop/reset")
