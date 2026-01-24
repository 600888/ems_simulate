"""
通道管理 API 控制器
提供通道的创建、删除、点表导入等接口
"""

import os
import tempfile
from typing import Optional

from fastapi import APIRouter, Request, File, UploadFile, Form
from fastapi.responses import JSONResponse

from src.data.service.channel_service import ChannelService
from src.data.service.yc_service import YcService
from src.data.service.yx_service import YxService
from src.data.service.yk_service import YkService
from src.data.service.yt_service import YtService
from src.tools.excel_point_importer import ExcelPointImporter
from src.web.log import get_logger
from src.config.config import Config
from src.device.factory.general_device_builder import GeneralDeviceBuilder
from src.device.types.general_device import GeneralDevice
from src.device.types.pcs import Pcs
from src.device.types.circuit_breaker import CircuitBreaker
from src.enums.modbus_def import ProtocolType
from src.web.schemas import (
    BaseResponse, ChannelCreateRequest, ChannelUpdateRequest,
    CreateAndStartDeviceRequest
)

log = get_logger()

# 创建路由对象
channel_router = APIRouter(prefix="/channel", tags=["channel"])


# 协议类型映射
PROTOCOL_OPTIONS = [
    {"value": 0, "label": "Modbus RTU", "conn_types": [0, 3]},
    {"value": 1, "label": "Modbus TCP", "conn_types": [1, 2]},
    {"value": 2, "label": "IEC 104", "conn_types": [1, 2]},
    {"value": 3, "label": "DL/T645-2007", "conn_types": [0, 1, 2, 3]},
]

# 连接类型映射
CONN_TYPE_OPTIONS = [
    {"value": 0, "label": "RTU主站"},
    {"value": 1, "label": "TCP客户端"},
    {"value": 2, "label": "TCP服务端"},
    {"value": 3, "label": "RTU从站"},
]


@channel_router.get("/protocols", response_model=BaseResponse)
async def get_protocols():
    """获取支持的协议列表"""
    try:
        return BaseResponse(
            message="获取协议列表成功",
            data={
                "protocols": PROTOCOL_OPTIONS,
                "conn_types": CONN_TYPE_OPTIONS,
            }
        )
    except Exception as e:
        log.error(f"获取协议列表失败: {e}")
        return BaseResponse(code=500, message=f"获取协议列表失败: {e}", data={})


@channel_router.get("/serial_ports", response_model=BaseResponse)
async def get_serial_ports():
    """获取可用的串口列表"""
    try:
        from src.tools.serial_port_detector import SerialPortDetector
        ports = SerialPortDetector.get_available_ports()
        return BaseResponse(message="获取串口列表成功", data=ports)
    except Exception as e:
        log.error(f"获取串口列表失败: {e}")
        return BaseResponse(code=500, message=f"获取串口列表失败: {e}", data=[])


@channel_router.post("/create", response_model=BaseResponse)
async def create_channel(req: ChannelCreateRequest, request: Request):
    """创建通道/设备"""
    try:
        # 检查通道编码是否已存在
        existing = ChannelService.get_channel_by_code(req.code)
        if existing:
            return BaseResponse(code=400, message=f"设备编码 '{req.code}' 已存在，请使用其他编码")
        
        # 检查端口是否已被其他服务端通道占用（仅对服务端模式检查）
        if req.conn_type == 2:  # TCP 服务端
            all_channels = ChannelService.get_all_channels()
            for ch in all_channels:
                # 仅检查启用的服务端通道
                if ch.get("conn_type") == 2 and ch.get("port") == req.port:
                    return BaseResponse(
                        code=400, 
                        message=f"端口 {req.port} 已被设备 '{ch.get('name')}' 占用，请使用其他端口"
                    )
        
        # 1. 首先创建 Device 记录
        from src.data.service.device_service import DeviceService
        device_id = DeviceService.create_device(
            code=req.code,
            name=req.name,
            device_type=0,  # 默认类型
            group_id=req.group_id,  # 设备组ID
        )
        
        if device_id <= 0:
            return BaseResponse(code=500, message="创建设备记录失败")
        
        # 2. 创建通道，关联到设备
        channel_id = ChannelService.create_channel(
            code=req.code,
            name=req.name,
            device_id=device_id,  # 关联设备ID
            protocol_type=req.protocol_type,
            conn_type=req.conn_type,
            ip=req.ip,
            port=req.port,
            com_port=req.com_port,
            baud_rate=req.baud_rate,
            data_bits=req.data_bits,
            stop_bits=req.stop_bits,
            parity=req.parity,
            rtu_addr=req.rtu_addr,
        )
        
        if channel_id > 0:
            return BaseResponse(
                message="创建通道成功", 
                data={
                    "channel_id": channel_id,
                    "device_id": device_id,
                }
            )
        else:
            return BaseResponse(code=500, message="创建通道失败")
            
    except Exception as e:
        log.error(f"创建通道失败: {e}")
        return BaseResponse(code=500, message=f"创建通道失败: {e}")


@channel_router.post("/import_points", response_model=BaseResponse)
async def import_points(
    channel_id: int = Form(...),
    file: UploadFile = File(...)
):
    """导入 Excel 点表"""
    try:
        if not file.filename.endswith(('.xlsx', '.xls')):
            return BaseResponse(code=400, message="请上传 Excel 文件 (.xlsx 或 .xls)")
        
        # 保存上传的文件到临时目录
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name
        
        try:
            # 先删除该通道的现有点表（支持重新导入）
            from src.data.dao.point_dao import PointDao
            deleted_count = PointDao.delete_points_by_channel(channel_id)
            if deleted_count > 0:
                log.info(f"重新导入前已删除 {deleted_count} 个旧测点")
            
            # 使用导入器导入点表
            importer = ExcelPointImporter(channel_id=channel_id)
            yc_count, yx_count, yk_count, yt_count = importer.import_from_excel(tmp_path)
            
            return BaseResponse(
                message="导入点表成功",
                data={
                    "yc_count": yc_count,
                    "yx_count": yx_count,
                    "yk_count": yk_count,
                    "yt_count": yt_count,
                    "total": yc_count + yx_count + yk_count + yt_count
                }
            )
        finally:
            # 清理临时文件
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
                
    except Exception as e:
        log.error(f"导入点表失败: {e}")
        return BaseResponse(code=500, message=f"导入点表失败: {e}")


@channel_router.post("/create_and_start", response_model=BaseResponse)
async def create_and_start_device(req: CreateAndStartDeviceRequest, request: Request):
    """创建通道并启动设备"""
    try:
        # 获取通道信息
        channel = ChannelService.get_channel_by_id(req.channel_id)
        if not channel:
            return BaseResponse(code=404, message="通道不存在")
        
        channel_code = channel["code"]
        channel_name = channel["name"]
        ip = channel.get("ip", Config.DEFAULT_IP)
        port = channel.get("port", Config.DEFAULT_PORT)
        
        # 获取协议类型枚举
        channel_protocol_type = ChannelService.get_protocol_type(channel)
        
        # 根据设备名称选择设备类型
        if channel_code.upper().find("PCS") != -1:
            general_device_builder = GeneralDeviceBuilder(
                channel_id=req.channel_id, device=Pcs()
            )
        elif channel_code.upper().find("BREAKER") != -1:
            general_device_builder = GeneralDeviceBuilder(
                channel_id=req.channel_id, device=CircuitBreaker()
            )
        else:
            general_device_builder = GeneralDeviceBuilder(
                channel_id=req.channel_id, device=GeneralDevice()
            )
        
        # 设置网络/串口配置
        conn_type = channel.get("conn_type", 1)
        if conn_type in [0, 3]:  # 串口连接（主站或0，从站或3）
            general_device_builder.setDeviceSerialConfig(
                serial_port=channel.get("com_port", ""),
                baudrate=channel.get("baud_rate", 9600),
                databits=channel.get("data_bits", 8),
                stopbits=channel.get("stop_bits", 1),
                parity=channel.get("parity", "E")
            )
        elif (
            channel_protocol_type == ProtocolType.Iec104Client
            or channel_protocol_type == ProtocolType.ModbusTcpClient
        ):
            general_device_builder.setDeviceNetConfig(port=port, ip=ip)
        else:
            # 服务端默认监听配置
            general_device_builder.setDeviceNetConfig(port=port, ip=Config.DEFAULT_IP)
        
        # 创建设备
        general_device = general_device_builder.makeGeneralDevice(
            device_id=req.channel_id,
            device_name=channel_name,
            protocol_type=channel_protocol_type,
            is_start=True,
        )
        general_device.name = channel_name
        general_device.data_update_thread.start()
        
        # 添加到设备控制器
        device_controller = request.app.state.device_controller
        device_controller.device_list.append(general_device)
        device_controller.device_map[general_device.name] = general_device
        
        log.info(f"设备 {channel_name} 创建并启动成功")
        
        return BaseResponse(message="设备创建并启动成功", data={"device_name": channel_name})
        
    except Exception as e:
        log.error(f"创建并启动设备失败: {e}")
        return BaseResponse(code=500, message=f"创建并启动设备失败: {e}")


@channel_router.post("/restart/{channel_id}", response_model=BaseResponse)
async def restart_device(channel_id: int, request: Request):
    """重启设备（用于配置更新后）"""
    try:
        channel = ChannelService.get_channel_by_id(channel_id)
        if not channel:
            return BaseResponse(code=404, message="通道不存在")
        
        device_controller = request.app.state.device_controller
        device_name = channel["name"]
        
        # 1. 找到旧设备在列表中的位置
        original_index = -1
        for i, device in enumerate(device_controller.device_list):
            if getattr(device, 'device_id', None) == channel_id:
                original_index = i
                break
        
        # 2. 停止并移除旧设备（使用 ID 查找，确保名称变更也能找到）
        await device_controller.remove_device_by_id(channel_id)
        log.info(f"已停止旧设备 ID: {channel_id} (原索引: {original_index})")
        
        # 3. 使用更新后的配置创建新设备
        channel_code = channel["code"]
        # 获取协议类型枚举
        channel_protocol_type = ChannelService.get_protocol_type(channel)
        port = channel.get("port", Config.DEFAULT_PORT)
        ip = channel.get("ip", Config.DEFAULT_IP)
        
        # 根据设备名称选择设备类型
        if channel_code.upper().find("PCS") != -1:
            general_device_builder = GeneralDeviceBuilder(
                channel_id=channel_id, device=Pcs()
            )
        elif channel_code.upper().find("BREAKER") != -1:
            general_device_builder = GeneralDeviceBuilder(
                channel_id=channel_id, device=CircuitBreaker()
            )
        else:
            general_device_builder = GeneralDeviceBuilder(
                channel_id=channel_id, device=GeneralDevice()
            )
        
        # 设置网络/串口配置
        conn_type = channel.get("conn_type", 1)
        if conn_type in [0, 3]:  # 串口连接（主站或0，从站或3）
            general_device_builder.setDeviceSerialConfig(
                serial_port=channel.get("com_port", ""),
                baudrate=channel.get("baud_rate", 9600),
                databits=channel.get("data_bits", 8),
                stopbits=channel.get("stop_bits", 1),
                parity=channel.get("parity", "E")
            )
        elif (
            channel_protocol_type == ProtocolType.Iec104Client
            or channel_protocol_type == ProtocolType.ModbusTcpClient
        ):
            general_device_builder.setDeviceNetConfig(port=port, ip=ip)
        else:
            # 服务端默认监听配置
            general_device_builder.setDeviceNetConfig(port=port, ip=Config.DEFAULT_IP)
        
        # 创建设备
        general_device = general_device_builder.makeGeneralDevice(
            device_id=channel_id,
            device_name=device_name,
            protocol_type=channel_protocol_type,
            is_start=True,
        )
        general_device.name = device_name
        general_device.data_update_thread.start()
        
        # 4. 在原位置插入新设备（保持列表顺序）
        if original_index >= 0 and original_index <= len(device_controller.device_list):
            device_controller.device_list.insert(original_index, general_device)
        else:
            device_controller.device_list.append(general_device)
        device_controller.device_map[general_device.name] = general_device
        
        log.info(f"设备 {device_name} 重启成功")
        
        return BaseResponse(message=f"设备 {device_name} 重启成功", data={"device_name": device_name})
        
    except Exception as e:
        log.error(f"重启设备失败: {e}")
        return BaseResponse(code=500, message=f"重启设备失败: {e}")


@channel_router.post("/reload_config/{channel_id}", response_model=BaseResponse)
async def reload_device_config(channel_id: int, request: Request):
    """重新加载设备配置（不自动启动服务）"""
    try:
        channel = ChannelService.get_channel_by_id(channel_id)
        if not channel:
            return BaseResponse(code=404, message="通道不存在")
        
        device_controller = request.app.state.device_controller
        device_name = channel["name"]
        
        # 1. 找到旧设备在列表中的位置
        original_index = -1
        for i, device in enumerate(device_controller.device_list):
            if getattr(device, 'device_id', None) == channel_id:
                original_index = i
                break
        
        # 2. 停止并移除旧设备
        await device_controller.remove_device_by_id(channel_id)
        log.info(f"已停止旧设备 ID: {channel_id}")
        
        # 3. 使用更新后的配置创建新设备（不启动）
        channel_code = channel["code"]
        channel_protocol_type = ChannelService.get_protocol_type(channel)
        port = channel.get("port", Config.DEFAULT_PORT)
        ip = channel.get("ip", Config.DEFAULT_IP)
        
        if channel_code.upper().find("PCS") != -1:
            general_device_builder = GeneralDeviceBuilder(
                channel_id=channel_id, device=Pcs()
            )
        elif channel_code.upper().find("BREAKER") != -1:
            general_device_builder = GeneralDeviceBuilder(
                channel_id=channel_id, device=CircuitBreaker()
            )
        else:
            general_device_builder = GeneralDeviceBuilder(
                channel_id=channel_id, device=GeneralDevice()
            )
        
        # 设置网络/串口配置
        conn_type = channel.get("conn_type", 1)
        if conn_type in [0, 3]:  # 串口连接
            general_device_builder.setDeviceSerialConfig(
                serial_port=channel.get("com_port", ""),
                baudrate=channel.get("baud_rate", 9600),
                databits=channel.get("data_bits", 8),
                stopbits=channel.get("stop_bits", 1),
                parity=channel.get("parity", "E")
            )
        elif (
            channel_protocol_type == ProtocolType.Iec104Client
            or channel_protocol_type == ProtocolType.ModbusTcpClient
        ):
            general_device_builder.setDeviceNetConfig(port=port, ip=ip)
        else:
            general_device_builder.setDeviceNetConfig(port=port, ip=Config.DEFAULT_IP)
        
        # 创建设备（不启动服务）
        general_device = general_device_builder.makeGeneralDevice(
            device_id=channel_id,
            device_name=device_name,
            protocol_type=channel_protocol_type,
            is_start=False,  # 不自动启动
        )
        general_device.name = device_name
        # 不启动数据更新线程
        
        # 4. 在原位置插入新设备
        if original_index >= 0 and original_index <= len(device_controller.device_list):
            device_controller.device_list.insert(original_index, general_device)
        else:
            device_controller.device_list.append(general_device)
        device_controller.device_map[general_device.name] = general_device
        
        log.info(f"设备 {device_name} 配置已重新加载（未启动）")
        
        return BaseResponse(message=f"设备 {device_name} 配置已重新加载", data={"device_name": device_name})
        
    except Exception as e:
        log.error(f"重新加载设备配置失败: {e}")
        return BaseResponse(code=500, message=f"重新加载设备配置失败: {e}")


@channel_router.delete("/{channel_id}", response_model=BaseResponse)
async def delete_channel(channel_id: int, request: Request):
    """删除通道"""
    try:
        # 先从设备控制器中移除设备（使用 ID 查找，确保健壮性）
        device_controller = request.app.state.device_controller
        await device_controller.remove_device_by_id(channel_id)
        
        # 删除通道记录
        success = ChannelService.delete_channel(channel_id)
        
        if success:
            return BaseResponse(message="删除通道成功", data=True)
        else:
            return BaseResponse(code=404, message="通道不存在", data=False)
            
    except Exception as e:
        log.error(f"删除通道失败: {e}")
        return BaseResponse(code=500, message=f"删除通道失败: {e}", data=False)


@channel_router.get("/list", response_model=BaseResponse)
async def get_channel_list():
    """获取所有通道列表"""
    try:
        channels = ChannelService.get_all_channels()
        return BaseResponse(message="获取通道列表成功", data=channels)
    except Exception as e:
        log.error(f"获取通道列表失败: {e}")
        return BaseResponse(code=500, message=f"获取通道列表失败: {e}", data=[])


@channel_router.get("/{channel_id}", response_model=BaseResponse)
async def get_channel_by_id(channel_id: int):
    """获取单个通道详情"""
    try:
        channel = ChannelService.get_channel_by_id(channel_id)
        if channel:
            return BaseResponse(message="获取通道详情成功", data=channel)
        else:
            return BaseResponse(code=404, message="通道不存在")
    except Exception as e:
        log.error(f"获取通道详情失败: {e}")
        return BaseResponse(code=500, message=f"获取通道详情失败: {e}")


@channel_router.put("/{channel_id}", response_model=BaseResponse)
async def update_channel(channel_id: int, req: ChannelUpdateRequest, request: Request):
    """更新通道配置"""
    try:
        # 检查通道是否存在
        existing = ChannelService.get_channel_by_id(channel_id)
        if not existing:
            return BaseResponse(code=404, message="通道不存在")
        
        # 更新通道
        success = ChannelService.update_channel(
            channel_id=channel_id,
            name=req.name,
            protocol_type=req.protocol_type,
            conn_type=req.conn_type,
            ip=req.ip,
            port=req.port,
            com_port=req.com_port,
            baud_rate=req.baud_rate,
            data_bits=req.data_bits, stop_bits=req.stop_bits,
            parity=req.parity,
            rtu_addr=req.rtu_addr,
        )
        
        if success:
            return BaseResponse(message="更新通道成功", data=True)
        else:
            return BaseResponse(code=500, message="更新通道失败", data=False)
            
    except Exception as e:
        log.error(f"更新通道失败: {e}")
        return BaseResponse(code=500, message=f"更新通道失败: {e}", data=False)

