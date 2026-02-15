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
    page_size: int = 10
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


# ========== 报文捕获相关请求 ==========

class MessageListRequest(BaseModel):
    """获取报文列表请求"""
    device_name: str = Field(..., description="设备名称")
    limit: Optional[int] = Field(100, description="最大返回数量")


# ========== 动态测点/从机管理请求 ==========

class PointCreateRequest(BaseModel):
    """创建测点请求"""
    device_name: str = Field(..., description="设备名称")
    frame_type: int = Field(..., description="测点类型: 0=遥测, 1=遥信, 2=遥控, 3=遥调")
    code: str = Field(..., description="测点编码", max_length=64)
    name: str = Field(..., description="测点名称", max_length=64)
    rtu_addr: int = Field(1, description="从机地址")
    reg_addr: str = Field(..., description="寄存器地址")
    func_code: int = Field(3, description="功能码")
    decode_code: str = Field("0x41", description="解析码")
    mul_coe: float = Field(1.0, description="乘系数（仅遥测/遥调）")
    add_coe: float = Field(0.0, description="加系数（仅遥测/遥调）")


class PointDeleteRequest(BaseModel):
    """删除测点请求"""
    device_name: str = Field(..., description="设备名称")
    point_code: str = Field(..., description="测点编码")


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

class ClearPointsRequest(BaseModel):
    """清空从机测点请求"""
    device_name: str = Field(..., description="设备名称")
    slave_id: int = Field(..., description="从机地址")


class PointItem(BaseModel):
    code: str = Field(..., description="测点编码", max_length=64)
    name: str = Field(..., description="测点名称", max_length=64)
    rtu_addr: int = Field(1, description="从机地址")
    reg_addr: str = Field(..., description="寄存器地址")
    func_code: int = Field(3, description="功能码")
    decode_code: str = Field("0x41", description="解析码")
    mul_coe: float = Field(1.0, description="乘系数（仅遥测/遥调）")
    add_coe: float = Field(0.0, description="加系数（仅遥测/遥调）")


class PointsBatchCreateRequest(BaseModel):
    """批量创建测点请求"""
    device_name: str = Field(..., description="设备名称")
    frame_type: int = Field(..., description="测点类型: 0=遥测, 1=遥信, 2=遥控, 3=遥调")
    points: List[PointItem] = Field(..., description="测点数据列表")
