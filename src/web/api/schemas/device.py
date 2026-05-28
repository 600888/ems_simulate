from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict
from src.enums.point_data import SimulateMethod


class DeviceNameListResponse:
    pass  # 使用 BaseResponse 统一返回


class DeviceInfoRequest(BaseModel):
    device_name: str


class DeviceInfoResponse:
    pass  # 使用 BaseResponse 统一返回


class SlaveIdListRequest(BaseModel):
    device_name: str


class SlaveIdListResponse:
    pass  # 使用 BaseResponse 统一返回


class DeviceTableRequest(BaseModel):
    device_name: str
    slave_id: int
    point_name: Optional[str] = None
    page_index: int = 1
    page_size: int = 10
    point_types: List[int] = Field(default_factory=list)
    order_by: Optional[str] = None
    order_direction: Optional[str] = None


class SimulationStartRequest(BaseModel):
    device_name: str
    simulate_method: SimulateMethod


class SimulationStopRequest(BaseModel):
    device_name: str


class DeviceStartRequest(BaseModel):
    device_name: str


class DeviceStopRequest(BaseModel):
    device_name: str


class DeviceResetRequest(BaseModel):
    device_name: str


class CurrentTableRequest(BaseModel):
    device_name: str
    slave_id: int
    point_name: Optional[str] = ""


class DeviceGroupStatusRequest(BaseModel):
    """设备组状态更新请求"""
    group_id: int = Field(..., description="设备组ID")
    status: int = Field(..., description="设备组状态")


class ManualReadRequest(BaseModel):
    device_name: str
    interval: Optional[int] = 0


class MessageListRequest(BaseModel):
    """获取报文列表请求"""
    device_name: str = Field(..., description="设备名称")
    limit: Optional[int] = Field(100, description="最大返回数量")


class SlaveAddRequest(BaseModel):
    """添加从机请求"""
    device_name: str = Field(..., description="设备名称")
    slave_id: int = Field(..., description="从机地址 (1-255)")


class SlaveDeleteRequest(BaseModel):
    """删除从机请求"""
    device_name: str = Field(..., description="设备名称")
    slave_id: int = Field(..., description="从机地址")


class SlaveEditRequest(BaseModel):
    """编辑从机请求"""
    device_name: str = Field(..., description="设备名称")
    old_slave_id: int = Field(..., description="旧从机地址")
    new_slave_id: int = Field(..., description="新从机地址 (1-255)")


class ExportModelRequest(BaseModel):
    """IEC 61850 模型导出请求"""
    device_name: str = Field(..., description="设备名称")
    export_type: str = Field("icd", description="导出类型: icd/json/xml/csv/tree")
    ied_name: str = Field("", description="IED 名称 (ICD 导出时使用，为空则自动推断)")
