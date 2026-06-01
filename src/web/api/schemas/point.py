from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from src.enums.point_data import SimulateMethod


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
    metadata: dict[str, Any]


class Iec104MetadataEditRequest(BaseModel):
    """IEC104协议专属测点属性编辑请求"""

    device_name: str
    point_code: str
    iec_type_id: str | None = Field(None, description="IEC104 ASDU类型标识（如M_ME_NC_1）", max_length=16)
    iec_quality: int | None = Field(0, description="IEC104品质描述符(位标志: OV=0x01 BL=0x02 SB=0x04 NT=0x08 IV=0x10)")


class PointInfoRequest(BaseModel):
    device_name: str
    point_code: str


class PointLimitGetRequest(BaseModel):
    device_name: str
    point_code: str


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
    bit: int | None = Field(None, description="位偏移")
    mul_coe: float = Field(1.0, description="乘系数（仅遥测/遥调）")
    add_coe: float = Field(0.0, description="加系数（仅遥测/遥调）")
    iec_type_id: str | None = Field(None, description="IEC104 ASDU类型标识（如M_ME_NC_1）", max_length=16)
    iec_quality: int | None = Field(0, description="IEC104品质描述符(位标志: OV=0x01 BL=0x02 SB=0x04 NT=0x08 IV=0x10)")


class PointDeleteRequest(BaseModel):
    """删除测点请求"""

    device_name: str = Field(..., description="设备名称")
    point_code: str = Field(..., description="测点编码")


class PointItem(BaseModel):
    code: str = Field(..., description="测点编码", max_length=64)
    name: str = Field(..., description="测点名称", max_length=64)
    rtu_addr: int = Field(1, description="从机地址")
    reg_addr: str = Field(..., description="寄存器地址")
    func_code: int = Field(3, description="功能码")
    decode_code: str = Field("0x41", description="解析码")
    bit: int | None = Field(None, description="位偏移")
    mul_coe: float = Field(1.0, description="乘系数（仅遥测/遥调）")
    add_coe: float = Field(0.0, description="加系数（仅遥测/遥调）")
    iec_type_id: str | None = Field(None, description="IEC104 ASDU类型标识（如M_ME_NC_1）", max_length=16)
    iec_quality: int | None = Field(0, description="IEC104品质描述符(位标志: OV=0x01 BL=0x02 SB=0x04 NT=0x08 IV=0x10)")


class PointsBatchCreateRequest(BaseModel):
    """批量创建测点请求"""

    device_name: str = Field(..., description="设备名称")
    frame_type: int = Field(..., description="测点类型: 0=遥测, 1=遥信, 2=遥控, 3=遥调")
    points: list[PointItem] = Field(..., description="测点数据列表")


class ClearPointsRequest(BaseModel):
    """清空从机测点请求"""

    device_name: str = Field(..., description="设备名称")
    slave_id: int = Field(..., description="从机地址")


class PointChangeHistoryRequest(BaseModel):
    """查询测点变更历史请求"""

    device_name: str = Field(..., description="设备名称")
    point_code: str = Field(..., description="测点编码")


class ChangeTrackingConfigRequest(BaseModel):
    """变更追溯配置请求"""

    device_name: str = Field(..., description="设备名称")
    point_code: str | None = Field(None, description="测点编码，若不传则应用到设备所有测点")
    enabled: bool = Field(..., description="是否启用变更追溯")
    maxlen: int | None = Field(None, description="历史记录最大条数（1-100），不传则不修改")
