"""通道管理 - 通道 CRUD 路由"""

import asyncio

from fastapi import APIRouter, Request

from src.config.config import Config
from src.data.dao.point_dao import PointDao
from src.data.service.channel_configuration_service import ChannelConfigurationService
from src.data.service.channel_service import ChannelService
from src.device.protocol.runtime_config import normalize_protocol_params
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

_RUNTIME_CHANNEL_FIELDS = (
    "ip",
    "port",
    "com_port",
    "baud_rate",
    "data_bits",
    "stop_bits",
    "parity",
    "rtu_addr",
    "model_name",
)


def _runtime_configuration_changed(
    existing: dict,
    req: ChannelUpdateRequest,
    normalized_params: dict | None,
    existing_params: dict | None,
) -> bool:
    """Return whether an edit requires replacing the in-memory device."""
    protocol_type = req.protocol_type if req.protocol_type is not None else existing.get("protocol_type", 1)
    conn_type = req.conn_type if req.conn_type is not None else existing.get("conn_type", 1)
    if protocol_type != existing.get("protocol_type", 1) or conn_type != existing.get("conn_type", 1):
        return True

    for field in _RUNTIME_CHANNEL_FIELDS:
        value = getattr(req, field)
        if value is None:
            continue
        old_value = existing.get(field)
        if field == "rtu_addr":
            if str(value) != str(old_value):
                return True
        elif value != old_value:
            return True

    return normalized_params is not None and normalized_params != existing_params


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

    ports = await asyncio.to_thread(SerialPortDetector.get_available_ports)
    return BaseResponse(message="获取串口列表成功", data=ports)


@router.post("/create", response_model=BaseResponse)
async def create_channel(req: ChannelCreateRequest, request: Request):
    """创建通道/设备"""
    _validate_protocol_connection(req.protocol_type, req.conn_type)

    existing = await asyncio.to_thread(ChannelService.get_channel_by_code, req.code)
    if existing:
        raise ValidationError(f"设备编码 '{req.code}' 已存在，请使用其他编码")

    if req.conn_type == 2:
        all_channels = await asyncio.to_thread(ChannelService.get_all_channels)
        for ch in all_channels:
            if ch.get("conn_type") == 2 and ch.get("port") == req.port:
                raise ValidationError(f"端口 {req.port} 已被设备 '{ch.get('name')}' 占用，请使用其他端口")

    params = req.protocol_params
    try:
        normalize_protocol_params(
            req.protocol_type,
            req.conn_type,
            params.values if params else None,
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc

    device_id, channel_id = await asyncio.to_thread(
        ChannelService.provision_channel,
        code=req.code,
        name=req.name,
        group_id=req.group_id,
        protocol_type=req.protocol_type,
        conn_type=req.conn_type,
        protocol_params=params.values if params else None,
        protocol_schema_version=params.schema_version if params else 1,
        ip=req.ip,
        port=req.port,
        com_port=req.com_port,
        baud_rate=req.baud_rate,
        data_bits=req.data_bits,
        stop_bits=req.stop_bits,
        parity=req.parity,
        rtu_addr=req.rtu_addr if req.protocol_type == 3 else "1",
        dlt645_point_mode=req.dlt645_point_mode if req.protocol_type == 3 else "import",
        model_name=req.model_name if req.protocol_type == 4 else None,
    )

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

        runtime_config = await asyncio.to_thread(
            ChannelConfigurationService.get_protocol_params,
            channel_id,
            req.protocol_type,
            req.conn_type,
        )
        builder.setDeviceRuntimeConfig(runtime_config["values"])
        security_config = await asyncio.to_thread(
            ChannelConfigurationService.get_runtime_security,
            channel_id,
        )
        builder.setDeviceSecurityConfig(security_config)

        new_device = await asyncio.to_thread(
            builder.makeGeneralDevice,
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
    await asyncio.to_thread(ChannelConfigurationService.delete_for_channel, req.channel_id)
    success = await asyncio.to_thread(ChannelService.delete_channel, req.channel_id)
    if not success:
        raise NotFoundError("通道不存在", data=False)
    return BaseResponse(message="删除通道成功", data=True)


@router.post("/list", response_model=BaseResponse)
async def get_channel_list():
    """获取所有通道列表"""
    channels = await asyncio.to_thread(ChannelService.get_all_channels)
    return BaseResponse(message="获取通道列表成功", data=channels)


@router.post("/detail", response_model=BaseResponse)
async def get_channel_by_id(req: ChannelDetailRequest):
    """获取单个通道详情"""
    channel = await asyncio.to_thread(ChannelService.get_channel_by_id, req.channel_id)
    if channel:
        channel["protocol_params"] = await asyncio.to_thread(
            ChannelConfigurationService.get_protocol_params,
            req.channel_id,
            channel.get("protocol_type", 1),
            channel.get("conn_type", 1),
        )
        channel["security_config"] = await asyncio.to_thread(
            ChannelConfigurationService.get_security_config,
            req.channel_id,
        )
    if not channel:
        raise NotFoundError("通道不存在")
    return BaseResponse(message="获取通道详情成功", data=channel)


@router.post("/update", response_model=BaseResponse)
async def update_channel(req: ChannelUpdateRequest, request: Request):
    """更新通道配置"""
    channel_id = req.channel_id
    existing = await asyncio.to_thread(ChannelService.get_channel_by_id, channel_id)
    if not existing:
        raise NotFoundError("通道不存在")

    protocol_to_use = req.protocol_type if req.protocol_type is not None else existing.get("protocol_type", 1)
    conn_type_to_use = req.conn_type if req.conn_type is not None else existing.get("conn_type", 1)
    dlt645_point_mode_to_use = (
        req.dlt645_point_mode if req.dlt645_point_mode is not None else existing.get("dlt645_point_mode", "import")
    )
    _validate_protocol_connection(protocol_to_use, conn_type_to_use)

    old_protocol = existing.get("protocol_type", 1)
    if protocol_to_use != old_protocol:
        point_count = await asyncio.to_thread(PointDao.count_points_by_channel, channel_id)
        has_iec61850_model = bool(existing.get("icd_path") or existing.get("model_name"))
        if point_count or has_iec61850_model:
            raise ConflictError(
                "通道已有测点或 IEC 61850 模型，不能直接切换协议；请先显式清理原协议数据",
                data={"point_count": point_count, "has_iec61850_model": has_iec61850_model},
            )

    params = req.protocol_params
    normalized_params = None
    existing_params = None
    protocol_combination_changed = protocol_to_use != existing.get(
        "protocol_type", 1
    ) or conn_type_to_use != existing.get("conn_type", 1)
    if params is not None:
        try:
            normalized_params = normalize_protocol_params(protocol_to_use, conn_type_to_use, params.values)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        current_protocol_params = await asyncio.to_thread(
            ChannelConfigurationService.get_protocol_params,
            channel_id,
            existing.get("protocol_type", 1),
            existing.get("conn_type", 1),
        )
        existing_params = current_protocol_params["values"]

    runtime_configuration_changed = _runtime_configuration_changed(
        existing,
        req,
        normalized_params,
        existing_params,
    )

    requested_updates = {
        field: value
        for field in (
            "name",
            "protocol_type",
            "conn_type",
            "ip",
            "port",
            "com_port",
            "baud_rate",
            "data_bits",
            "stop_bits",
            "parity",
        )
        if (value := getattr(req, field)) is not None
    }
    if protocol_to_use == 3:
        if req.rtu_addr is not None:
            requested_updates["rtu_addr"] = req.rtu_addr
        requested_updates["dlt645_point_mode"] = dlt645_point_mode_to_use
    else:
        if protocol_combination_changed:
            requested_updates["rtu_addr"] = "1"
        requested_updates["dlt645_point_mode"] = "import"
    if protocol_to_use == 4:
        if req.model_name is not None:
            requested_updates["model_name"] = req.model_name
    elif protocol_combination_changed:
        requested_updates["model_name"] = None

    channel_updates = {
        field: value
        for field, value in requested_updates.items()
        if (str(value) != str(existing.get(field)) if field == "rtu_addr" else value != existing.get(field))
    }
    success = True
    if channel_updates:
        success = await asyncio.to_thread(
            ChannelService.update_channel,
            channel_id=channel_id,
            **channel_updates,
        )

    if not success:
        raise OperationError("更新通道失败", data=False)

    protocol_params_changed = normalized_params is not None and normalized_params != existing_params
    if protocol_params_changed or protocol_combination_changed:
        await asyncio.to_thread(
            ChannelConfigurationService.save_protocol_params,
            channel_id,
            protocol_to_use,
            conn_type_to_use,
            normalized_params if params else None,
            params.schema_version if params else 1,
        )

    try:
        device_controller = request.app.state.device_controller
        if runtime_configuration_changed and not req.defer_runtime_reload:
            old_device = device_controller.get_device_by_id(channel_id)
            was_running = bool(old_device and old_device.is_protocol_running())
            await reload_device_instance(device_controller, channel_id, is_start=was_running)
        elif "name" in channel_updates:
            # A display-name-only edit does not require rebuilding the protocol stack.
            device = device_controller.get_device_by_id(channel_id)
            if device is not None:
                old_keys = [key for key, value in device_controller.device_map.items() if value is device]
                for key in old_keys:
                    device_controller.device_map.pop(key, None)
                device.name = req.name
                device_controller.device_map[req.name] = device
    except Exception as e:
        log.error(f"更新配置后同步运行时设备失败: {e}")
    return BaseResponse(message="更新通道成功", data=True)
