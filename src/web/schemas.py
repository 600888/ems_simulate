from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict
from src.enums.modbus_def import ProtocolType
from src.enums.point_data import SimulateMethod, DeviceType
from src.config.config import Config

class BaseResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: Any = None

class DeviceNameListResponse(BaseResponse):
    data: List[str]

class DeviceInfoRequest(BaseModel):
    device_name: str

class DeviceInfoResponse(BaseResponse):
    data: Dict[str, Any]

class SlaveIdListRequest(BaseModel):
    device_name: str

class SlaveIdListResponse(BaseResponse):
    data: List[int]

class DeviceTableRequest(BaseModel):
    device_name: str
    slave_id: int
    point_name: Optional[str] = None
    page_index: int = 1
    pageSize: int = 10
    point_types: List[int] = Field(default_factory=list)

class PointEditDataRequest(BaseModel):
    device_name: str
    point_code: str
    point_value: float

class PointLimitEditRequest(BaseModel):
    device_name: str
    point_code: str
    min_value_limit: float
    max_value_limit: float

class PointMetadataEditRequest(BaseModel):
    device_name: str
    point_code: str
    metadata: Dict[str, Any]

class PointInfoRequest(BaseModel):
    device_name: str
    point_code: str

class SimulationStartRequest(BaseModel):
    device_name: str
    simulate_method: SimulateMethod

class SimulationStopRequest(BaseModel):
    device_name: str

class SimulateMethodSetRequest(BaseModel):
    device_name: str
    point_code: str
    simulate_method: SimulateMethod

class SimulateStepSetRequest(BaseModel):
    device_name: str
    point_code: str
    step: int

class SimulateRangeSetRequest(BaseModel):
    device_name: str
    point_code: str
    min_value: float
    max_value: float

class DeviceStartRequest(BaseModel):
    device_name: str

class DeviceStopRequest(BaseModel):
    device_name: str

class DeviceResetRequest(BaseModel):
    device_name: str

class PointLimitGetRequest(BaseModel):
    device_name: str
    point_code: str

class CurrentTableRequest(BaseModel):
    device_name: str
    slave_id: int
    point_name: Optional[str] = ""

class ChannelCreateRequest(BaseModel):
    code: str
    name: str
    protocol_type: int = 1
    conn_type: int = 2
    ip: str = Config.DEFAULT_IP
    port: int = Config.DEFAULT_PORT
    com_port: Optional[str] = None
    baud_rate: int = 9600
    data_bits: int = 8
    stop_bits: int = 1
    parity: str = "N"
    rtu_addr: str = "1"
    group_id: Optional[int] = None  # 所属设备组ID

class ChannelUpdateRequest(BaseModel):
    name: Optional[str] = None
    protocol_type: Optional[int] = None
    conn_type: Optional[int] = None
    ip: Optional[str] = None
    port: Optional[int] = None
    com_port: Optional[str] = None
    baud_rate: Optional[int] = None
    data_bits: Optional[int] = None
    stop_bits: Optional[int] = None
    parity: Optional[str] = None
    rtu_addr: Optional[str] = None

class CreateAndStartDeviceRequest(BaseModel):
    channel_id: int


# ========== 设备组相关请求 ==========

class DeviceGroupCreateRequest(BaseModel):
    """创建设备组请求"""
    code: str = Field(..., description="设备组编码", max_length=32)
    name: str = Field(..., description="设备组名称", max_length=64)
    parent_id: Optional[int] = Field(None, description="父设备组ID，NULL表示顶级")
    description: Optional[str] = Field(None, description="设备组描述", max_length=256)


class DeviceGroupUpdateRequest(BaseModel):
    """更新设备组请求"""
    name: Optional[str] = Field(None, description="设备组名称", max_length=64)
    parent_id: Optional[int] = Field(None, description="父设备组ID")
    description: Optional[str] = Field(None, description="设备组描述", max_length=256)
    status: Optional[int] = Field(None, description="设备组状态")


class DeviceGroupDeleteRequest(BaseModel):
    """删除设备组请求"""
    cascade: bool = Field(False, description="是否级联删除子组，False时将子组和设备移至未分组")


class DeviceToGroupRequest(BaseModel):
    """将设备添加到设备组请求"""
    device_id: int = Field(..., description="设备ID")
    group_id: int = Field(..., description="目标设备组ID")


class DevicesToGroupRequest(BaseModel):
    """批量移动设备到设备组请求"""
    device_ids: List[int] = Field(..., description="设备ID列表")
    group_id: Optional[int] = Field(None, description="目标设备组ID，NULL表示移至未分组")


class BatchDeviceOperationRequest(BaseModel):
    """批量设备操作请求"""
    group_id: int = Field(..., description="设备组ID")
    operation: str = Field(..., description="操作类型: start/stop/reset")

