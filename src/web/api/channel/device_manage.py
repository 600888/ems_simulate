"""通道管理 - 设备管理路由（创建启动/重启/重载/复制）"""

from fastapi import APIRouter, Request

from src.config.config import Config
from src.data.service.channel_configuration_service import ChannelConfigurationService
from src.data.service.channel_service import ChannelService
from src.data.service.iec61850_copy_service import Iec61850CopyResult, Iec61850CopyService
from src.enums.modbus_def import ProtocolType
from src.web.api.channel.helpers import (
    configure_builder_network,
    get_device_builder,
    increment_ip,
    is_client_protocol,
    reload_device_instance,
)
from src.web.api.exceptions import NotFoundError
from src.web.api.schemas import BaseResponse, ChannelIdRequest, CopyDeviceRequest
from src.web.log import log

router = APIRouter(tags=["channel"])


@router.post("/create-and-start", response_model=BaseResponse)
async def create_and_start_device(req: ChannelIdRequest, request: Request):
    """创建通道并启动设备"""
    channel = ChannelService.get_channel_by_id(req.channel_id)
    if not channel:
        raise NotFoundError("通道不存在")

    channel_code = channel["code"]
    channel_name = channel["name"]
    ip = channel.get("ip", Config.DEFAULT_IP)
    port = channel.get("port", Config.DEFAULT_PORT)
    channel_protocol_type = ChannelService.get_protocol_type(channel)

    builder = get_device_builder(req.channel_id, channel_code)
    conn_type = channel.get("conn_type", 1)
    configure_builder_network(builder, conn_type, channel_protocol_type, ip, port, channel)

    general_device = builder.makeGeneralDevice(
        device_id=req.channel_id,
        device_name=channel_name,
        protocol_type=channel_protocol_type,
        is_start=True,
    )
    general_device.name = channel_name

    if is_client_protocol(channel_protocol_type):
        # 客户端协议：先连接服务器，再启动数据更新线程
        await general_device.start()
        general_device.data_update_thread.start()
    elif channel_protocol_type == ProtocolType.Iec61850Server:
        # IEC61850 服务端: 显式启动 MMS 服务器
        await general_device.start()
        log.info(f"IEC 61850 服务端已启动: {channel_name}")

    device_controller = request.app.state.device_controller
    device_controller.device_list.append(general_device)
    device_controller.device_map[general_device.name] = general_device

    log.info(f"设备 {channel_name} 创建并启动成功")
    return BaseResponse(message="设备创建并启动成功", data={"device_name": channel_name})


@router.post("/restart", response_model=BaseResponse)
async def restart_device(req: ChannelIdRequest, request: Request):
    """重启设备"""
    device_controller = request.app.state.device_controller
    new_device = await reload_device_instance(device_controller, req.channel_id, is_start=True)
    return BaseResponse(message=f"设备 {new_device.name} 重启成功", data={"device_name": new_device.name})


@router.post("/reload-config", response_model=BaseResponse)
async def reload_device_config(req: ChannelIdRequest, request: Request):
    """重新加载设备配置（不自动启动服务）"""
    device_controller = request.app.state.device_controller
    new_device = await reload_device_instance(device_controller, req.channel_id, is_start=False)
    return BaseResponse(message=f"设备 {new_device.name} 配置已重新加载", data={"device_name": new_device.name})


@router.post("/copy", response_model=BaseResponse)
async def copy_device(req: CopyDeviceRequest, request: Request):
    """复制设备（包括点表）"""
    from src.data.dao.point_dao import PointDao
    from src.data.service.device_group_service import DeviceGroupService
    from src.data.service.device_service import DeviceService

    source_channel = ChannelService.get_channel_by_id(req.channel_id)
    if not source_channel:
        raise NotFoundError("源通道不存在")

    source_device_id = source_channel.get("device_id")
    source_device = DeviceService.get_device_by_id(source_device_id) if source_device_id else None
    source_group_id = source_device.get("group_id") if source_device else None
    target_group_id = req.target_group_id if "target_group_id" in req.model_fields_set else source_group_id
    if target_group_id is not None and not DeviceGroupService.get_group_by_id(target_group_id):
        raise NotFoundError(f"目标设备组 {target_group_id} 不存在")
    source_points = PointDao.get_points_by_channel(req.channel_id)
    source_ip = source_channel.get("ip", Config.DEFAULT_IP)
    source_port = source_channel.get("port", Config.DEFAULT_PORT)
    is_iec61850 = source_channel.get("protocol_type") == Iec61850CopyService.PROTOCOL_ID

    prefix = req.prefix or ""
    suffix = req.suffix or ""
    copied_channels = []

    for i in range(1, req.count + 1):
        ip_offset = 0 if req.ip_start_offset == 0 else req.ip_start_offset + i - 1
        new_ip = increment_ip(source_ip, ip_offset)
        new_port = source_port + req.port_offset * i if req.port_offset > 0 else source_port
        new_code = f"{prefix}{source_channel['code']}{suffix}{i}"
        new_name = f"{prefix}{source_channel['name']}{suffix}{i}"

        existing = ChannelService.get_channel_by_code(new_code)
        if existing:
            log.warning(f"通道编码 {new_code} 已存在，跳过")
            continue

        new_device_id = DeviceService.create_device(
            code=new_code,
            name=new_name,
            device_type=source_device.get("device_type", 0) if source_device else 0,
            group_id=target_group_id,
        )
        if new_device_id <= 0:
            log.error(f"创建设备记录失败: {new_code}")
            continue
        if source_device and not is_iec61850:
            DeviceService.update_device(
                new_device_id,
                icd_path=source_device.get("icd_path"),
                icd_file_hash=source_device.get("icd_file_hash"),
            )

        new_channel_id = ChannelService.create_channel(
            code=new_code,
            name=new_name,
            device_id=new_device_id,
            protocol_type=source_channel.get("protocol_type", 1),
            conn_type=source_channel.get("conn_type", 2),
            ip=new_ip,
            port=new_port,
            com_port=source_channel.get("com_port"),
            baud_rate=source_channel.get("baud_rate", 9600),
            data_bits=source_channel.get("data_bits", 8),
            stop_bits=source_channel.get("stop_bits", 1),
            parity=source_channel.get("parity", "N"),
            rtu_addr=source_channel.get("rtu_addr", "1"),
            timeout=source_channel.get("timeout", 5),
            dlt645_point_mode=source_channel.get("dlt645_point_mode", "import"),
            model_name=source_channel.get("model_name"),
            # IEC 61850 models are deep-copied after both ownership IDs exist.
            # Never leave a copied device pointing at the source device's file.
            icd_path=None if is_iec61850 else source_channel.get("icd_path"),
            icd_file_hash=None if is_iec61850 else source_channel.get("icd_file_hash"),
        )
        if new_channel_id <= 0:
            log.error(f"创建通道失败: {new_code}")
            continue

        iec61850_copy = Iec61850CopyResult()
        try:
            ChannelConfigurationService.clone_for_channel(
                req.channel_id,
                new_channel_id,
                source_channel.get("protocol_type", 1),
                source_channel.get("conn_type", 2),
            )
            iec61850_copy = Iec61850CopyService.clone_for_channel(
                source_channel,
                new_channel_id,
                new_device_id,
                new_name,
            )
        except Exception as e:
            log.error(f"复制通道配置失败: {new_code}: {e}")
            ChannelConfigurationService.delete_for_channel(new_channel_id)
            ChannelService.delete_channel(new_channel_id)
            continue

        for point in source_points:
            point_copy = {
                # Point codes only need to be unique within the copied device.
                # Device naming options must not change the point table identity.
                "code": point["code"],
                "name": point["name"],
                "rtu_addr": point.get("rtu_addr", 1),
                "reg_addr": point.get("reg_addr", "0"),
                "func_code": point.get("func_code", 3),
                "decode_code": point.get("decode_code", "0x41"),
                "iec_common_address": point.get("iec_common_address"),
                "iec_cot": point.get("iec_cot", 3),
                "iec_type_id": point.get("iec_type_id"),
                "iec_quality": point.get("iec_quality", 0),
                "fc": point.get("fc"),
            }
            frame_type = point.get("frame_type", 0)
            if frame_type in [0, 3]:
                point_copy["mul_coe"] = point.get("mul_coe", 1.0)
                point_copy["add_coe"] = point.get("add_coe", 0.0)
                point_copy["max_limit"] = point.get("max_limit")
                point_copy["min_limit"] = point.get("min_limit")
            if frame_type in [1, 2]:
                point_copy["bit"] = point.get("bit")
            try:
                PointDao.create_point(new_channel_id, frame_type, point_copy)
            except Exception as e:
                log.error(f"复制测点失败: {point.get('code')} -> {point_copy['code']}: {e}")

        try:
            device_controller = request.app.state.device_controller
            builder = get_device_builder(new_channel_id, new_code)
            channel_protocol_type = ChannelService.get_protocol_type(source_channel)
            conn_type = source_channel.get("conn_type", 1)
            new_channel_data = ChannelService.get_channel_by_id(new_channel_id)
            if not new_channel_data or new_channel_data.get("id") != new_channel_id:
                new_channel_data = {
                    **source_channel,
                    "id": new_channel_id,
                    "device_id": new_device_id,
                    "code": new_code,
                    "name": new_name,
                    "ip": new_ip,
                    "port": new_port,
                    "icd_path": iec61850_copy.model_path,
                    "icd_file_hash": iec61850_copy.model_hash,
                }
            configure_builder_network(builder, conn_type, channel_protocol_type, new_ip, new_port, new_channel_data)
            new_device = builder.makeGeneralDevice(
                device_id=new_channel_id,
                device_name=new_name,
                protocol_type=channel_protocol_type,
                is_start=False,
            )
            new_device.name = new_name
            device_controller.device_list.append(new_device)
            device_controller.device_map[new_device.name] = new_device
            log.info(f"复制设备 {new_name} (ID: {new_channel_id}) 已在内存中创建")
        except Exception as e:
            log.error(f"内存同步复制设备失败: {e}")

        if is_iec61850:
            try:
                Iec61850CopyService.hydrate_runtime_resources(
                    new_channel_id,
                    getattr(request.app.state, "goose_manager", None),
                )
            except Exception as e:
                # Persistence is already complete. Runtime hydration is a
                # recoverable convenience and must not invalidate the copy.
                log.warning(f"复制设备 GOOSE 运行态同步失败: {new_name}: {e}")

        copied_channels.append(
            {
                "channel_id": new_channel_id,
                "device_id": new_device_id,
                "name": new_name,
                "code": new_code,
                "ip": new_ip,
                "port": new_port,
                "iec61850": iec61850_copy.to_dict() if is_iec61850 else None,
            }
        )

    return BaseResponse(
        message=f"成功复制 {len(copied_channels)} 个设备",
        data={"copied_count": len(copied_channels), "devices": copied_channels},
    )
