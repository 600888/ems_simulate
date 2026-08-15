from pydantic import BaseModel, Field

from src.enums.point_data import SimulateMethod


class DeviceNameListResponse:
    pass  # 使用 BaseResponse 统一返回


class DeviceInfoRequest(BaseModel):
    device_name: str


class DLT645CommandRequest(BaseModel):
    """DL/T645 特殊命令请求（主站/从站功能）"""

    device_name: str
    command: str
    params: dict | None = None


class DLT645DiInfoRequest(BaseModel):
    """DL/T645 数据标识（DI）元信息请求"""

    device_name: str
    di: str


class DeviceInfoResponse:
    pass  # 使用 BaseResponse 统一返回


class SlaveIdListRequest(BaseModel):
    device_name: str


class DeviceTableRequest(BaseModel):
    """获取表格数据请求"""

    device_name: str
    slave_id: int
    point_name: str | None = None
    page_index: int | None = Field(1, ge=1, description="当前页码")
    page_size: int | None = Field(10, ge=1, description="每页条数")
    point_types: list[int] | None = None  # 为空表示全部
    order_by: str | None = None
    order_direction: str | None = None
    iec104_types: list[str] | None = None  # 为空表示全部 IEC104 ASDU 类型
    dlt645_prefix: int | None = Field(None, ge=0, le=4)
    dlt645_settlement: int | None = Field(None, ge=0, le=12)


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
    point_name: str | None = ""


class DeviceGroupStatusRequest(BaseModel):
    """设备组状态更新请求"""

    group_id: int = Field(..., description="设备组ID")
    status: int = Field(..., description="设备组状态")


class ManualReadRequest(BaseModel):
    device_name: str
    interval: int | None = 0


class MessageListRequest(BaseModel):
    """获取报文列表请求"""

    device_name: str = Field(..., description="设备名称")
    limit: int | None = Field(100, description="最大返回数量")


class MessageDetailRequest(BaseModel):
    device_name: str
    sequence_id: int = Field(..., ge=1)


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
    """导出 IEC61850 模型请求"""

    device_name: str = Field(..., description="设备名称")
    export_type: str = Field(..., description="导出格式: icd/json/xml/csv/tree")
    ied_name: str | None = Field(None, description="IED 名称 (导出 ICD 时使用)")


class IEC61850LoadModelRequest(BaseModel):
    """加载 IEC61850 模型请求"""

    device_name: str = Field(..., description="设备名称")
    source: str = Field(..., description="模型来源: 'icd' 从ICD文件加载, 'discovery' 远程发现")


class IEC61850ImportModelRequest(BaseModel):
    """导入 ICD 模型请求"""

    device_name: str = Field(..., description="设备名称")
    icd_path: str = Field(..., description="ICD 文件路径")


class IEC61850ModelStatusResponse(BaseModel):
    """IEC61850 模型状态响应"""

    model_loaded: bool = Field(..., description="模型是否已加载")
    loaded_icd_path: str | None = Field(None, description="已加载的 ICD 文件路径")
    model_name: str | None = Field(None, description="模型名称")
