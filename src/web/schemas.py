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
