"""通道管理 - 通道 CRUD 路由"""

from fastapi import APIRouter, Request

from src.config.config import Config
from src.data.dao.point_dao import PointDao
from src.data.service.channel_service import ChannelService
from src.enums.modbus_def import ProtocolType
from src.web.api.channel.helpers import (
    get_device_builder,
    reload_device_instance,
)
from src.web.api.exceptions import ConflictError, NotFoundError, OperationError, ValidationError
from src.web.api.schemas import (
    BaseResponse,
    ChannelCreateRequest,
    ChannelDeleteRequest,
    ChannelDetailRequest,
    ChannelUpdateRequest,
)
from src.web.log import log

router = APIRouter(tags=["channel"])


# 协议类型映射
PROTOCOL_OPTIONS = [
    {"value": 0, "label": "Modbus RTU", "conn_types": [0, 3]},
    {"value": 1, "label": "Modbus TCP", "conn_types": [1, 2]},
    {"value": 2, "label": "IEC 104", "conn_types": [1, 2]},
    {"value": 3, "label": "DL/T645-2007", "conn_types": [0, 1, 2, 3]},
    {"value": 4, "label": "IEC 61850", "conn_types": [1, 2]},
]

# 连接类型映射
CONN_TYPE_OPTIONS = [
    {"value": 0, "label": "RTU主站"},
    {"value": 1, "label": "TCP客户端"},
    {"value": 2, "label": "TCP服务端"},
    {"value": 3, "label": "RTU从站"},
]


def _validate_protocol_connection(protocol_type: int, conn_type: int) -> None:
    option = next((item for item in PROTOCOL_OPTIONS if item["value"] == protocol_type), None)
    if not option:
        raise ValidationError(f"不支持的协议类型: {protocol_type}")
    if conn_type not in option["conn_types"]:
        raise ValidationError(f"协议 {option['label']} 不支持连接类型 {conn_type}")


@router.post("/protocols", response_model=BaseResponse)
async def get_protocols():
    """获取支持的协议列表"""
    return BaseResponse(
        message="获取协议列表成功",
        data={"protocols": PROTOCOL_OPTIONS, "conn_types": CONN_TYPE_OPTIONS},
    )


@router.post("/serial-ports", response_model=BaseResponse)
async def get_serial_ports():
    """获取可用的串口列表"""
    from src.tools.serial_port_detector import SerialPortDetector

    ports = SerialPortDetector.get_available_ports()
    return BaseResponse(message="获取串口列表成功", data=ports)


@router.post("/create", response_model=BaseResponse)
async def create_channel(req: ChannelCreateRequest, request: Request):
    """创建通道/设备"""
    _validate_protocol_connection(req.protocol_type, req.conn_type)

    existing = ChannelService.get_channel_by_code(req.code)
    if existing:
        raise ValidationError(f"设备编码 '{req.code}' 已存在，请使用其他编码")

    if req.conn_type == 2:
        all_channels = ChannelService.get_all_channels()
        for ch in all_channels:
            if ch.get("conn_type") == 2 and ch.get("port") == req.port:
                raise ValidationError(f"端口 {req.port} 已被设备 '{ch.get('name')}' 占用，请使用其他端口")

    from src.data.service.device_service import DeviceService

    device_id = DeviceService.create_device(
        code=req.code,
        name=req.name,
        device_type=0,
        group_id=req.group_id,
    )
    if device_id <= 0:
        raise OperationError("创建设备记录失败")

    channel_id = ChannelService.create_channel(
        code=req.code,
        name=req.name,
        device_id=device_id,
        protocol_type=req.protocol_type,
        conn_type=req.conn_type,
        ip=req.ip,
        port=req.port,
        com_port=req.com_port,
        baud_rate=req.baud_rate,
        data_bits=req.data_bits,
        stop_bits=req.stop_bits,
        parity=req.parity,
        rtu_addr=req.rtu_addr if req.protocol_type == 3 else "1",
        model_name=req.model_name if req.protocol_type == 4 else None,
    )

    if channel_id <= 0:
        raise OperationError("创建通道失败")

    try:
        device_controller = request.app.state.device_controller
        builder = get_device_builder(channel_id, req.code)

        channel_data_mock = {"protocol_type": req.protocol_type, "conn_type": req.conn_type}
        protocol_enum = ChannelService.get_protocol_type(channel_data_mock)

        if req.conn_type in [0, 3]:
            builder.setDeviceSerialConfig(
                serial_port=req.com_port or "",
                baudrate=req.baud_rate or 9600,
                databits=req.data_bits or 8,
                stopbits=req.stop_bits or 1,
                parity=req.parity or "E",
            )
        else:
            if protocol_enum in [
                ProtocolType.ModbusTcpClient,
                ProtocolType.Iec104Client,
                ProtocolType.Dlt645Client,
                ProtocolType.Iec61850Client,
            ]:
                builder.setDeviceNetConfig(port=req.port, ip=req.ip)
            else:
                builder.setDeviceNetConfig(port=req.port, ip=Config.DEFAULT_IP)

        # 传递 IEC61850 IED 模型名称
        if protocol_enum in (ProtocolType.Iec61850Server, ProtocolType.Iec61850Client):
            if req.model_name:
                builder.setDeviceModelName(req.model_name)

        new_device = builder.makeGeneralDevice(
            device_id=channel_id,
            device_name=req.name,
            protocol_type=protocol_enum,
            is_start=False,
        )
        new_device.name = req.name
        device_controller.device_list.append(new_device)
        device_controller.device_map[new_device.name] = new_device
        log.info(f"设备 {req.name} (ID: {channel_id}) 已在内存中动态创建")
    except Exception as e:
        log.error(f"内存同步创建设备失败: {e}")

    return BaseResponse(
        message="创建通道成功",
        data={"channel_id": channel_id, "device_id": device_id},
    )


@router.post("/delete", response_model=BaseResponse)
async def delete_channel(req: ChannelDeleteRequest, request: Request):
    """删除通道"""
    device_controller = request.app.state.device_controller
    await device_controller.remove_device_by_id(req.channel_id)
    success = ChannelService.delete_channel(req.channel_id)
    if not success:
        raise NotFoundError("通道不存在", data=False)
    return BaseResponse(message="删除通道成功", data=True)


@router.post("/list", response_model=BaseResponse)
async def get_channel_list():
    """获取所有通道列表"""
    channels = ChannelService.get_all_channels()
    return BaseResponse(message="获取通道列表成功", data=channels)


@router.post("/detail", response_model=BaseResponse)
async def get_channel_by_id(req: ChannelDetailRequest):
    """获取单个通道详情"""
    channel = ChannelService.get_channel_by_id(req.channel_id)
    if not channel:
        raise NotFoundError("通道不存在")
    return BaseResponse(message="获取通道详情成功", data=channel)


@router.post("/update", response_model=BaseResponse)
async def update_channel(req: ChannelUpdateRequest, request: Request):
    """更新通道配置"""
    channel_id = req.channel_id
    existing = ChannelService.get_channel_by_id(channel_id)
    if not existing:
        raise NotFoundError("通道不存在")

    protocol_to_use = req.protocol_type if req.protocol_type is not None else existing.get("protocol_type", 1)
    conn_type_to_use = req.conn_type if req.conn_type is not None else existing.get("conn_type", 1)
    _validate_protocol_connection(protocol_to_use, conn_type_to_use)

    old_protocol = existing.get("protocol_type", 1)
    if protocol_to_use != old_protocol:
        point_count = PointDao.count_points_by_channel(channel_id)
        has_iec61850_model = bool(existing.get("icd_path") or existing.get("model_name"))
        if point_count or has_iec61850_model:
            raise ConflictError(
                "通道已有测点或 IEC 61850 模型，不能直接切换协议；请先显式清理原协议数据",
                data={"point_count": point_count, "has_iec61850_model": has_iec61850_model},
            )

    success = ChannelService.update_channel(
        channel_id=channel_id,
        name=req.name,
        protocol_type=req.protocol_type,
        conn_type=req.conn_type,
        ip=req.ip,
        port=req.port,
        com_port=req.com_port,
        baud_rate=req.baud_rate,
        data_bits=req.data_bits,
        stop_bits=req.stop_bits,
        parity=req.parity,
        rtu_addr=req.rtu_addr if protocol_to_use == 3 else "1",
        model_name=req.model_name if protocol_to_use == 4 else None,
    )

    if not success:
        raise OperationError("更新通道失败", data=False)

    try:
        device_controller = request.app.state.device_controller
        await reload_device_instance(device_controller, channel_id, is_start=False)
    except Exception as e:
        log.error(f"更新配置后重载设备失败: {e}")
    return BaseResponse(message="更新通道成功", data=True)
