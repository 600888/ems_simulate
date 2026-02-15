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
from src.web.log import log
from src.config.config import Config
from src.device.factory.general_device_builder import GeneralDeviceBuilder
from src.device.types.general_device import GeneralDevice
from src.device.types.pcs import Pcs
from src.device.types.circuit_breaker import CircuitBreaker
from src.enums.modbus_def import ProtocolType
from src.web.schemas.schemas import (
    BaseResponse, ChannelCreateRequest, ChannelUpdateRequest,
    CreateAndStartDeviceRequest
)


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
            # ==========================================
            # 新增：立即在内存中创建设备对象，无需重启
            # ==========================================
            try:
                device_controller = request.app.state.device_controller
                
                # 1. 准备构建器
                if req.code.upper().find("PCS") != -1:
                    builder = GeneralDeviceBuilder(channel_id=channel_id, device=Pcs())
                elif req.code.upper().find("BREAKER") != -1:
                    builder = GeneralDeviceBuilder(channel_id=channel_id, device=CircuitBreaker())
                else:
                    builder = GeneralDeviceBuilder(channel_id=channel_id, device=GeneralDevice())
                
                # 2. 转换协议类型
                # 注意：ChannelService.get_protocol_type 需要 protocol_type (int) 和 conn_type (int)
                channel_data_mock = {
                    "protocol_type": req.protocol_type,
                    "conn_type": req.conn_type
                }
                protocol_enum = ChannelService.get_protocol_type(channel_data_mock)

                # 3. 配置通信参数
                if req.conn_type in [0, 3]:  # 串口
                    builder.setDeviceSerialConfig(
                        serial_port=req.com_port or "",
                        baudrate=req.baud_rate or 9600,
                        databits=req.data_bits or 8,
                        stopbits=req.stop_bits or 1,
                        parity=req.parity or "E"
                    )
                else: 
                    # 网络设备
                    # TCP客户端 和 IEC104客户端 需要连接到目标IP
                    # ProtocolType.ModbusTcpClient 等是枚举
                    if protocol_enum in [ProtocolType.ModbusTcpClient, ProtocolType.Iec104Client, ProtocolType.Dlt645Client]:
                        builder.setDeviceNetConfig(port=req.port, ip=req.ip)
                    else:
                        # 服务端，监听 0.0.0.0 (Config.DEFAULT_IP)
                        builder.setDeviceNetConfig(port=req.port, ip=Config.DEFAULT_IP)

                # 4. 创建设备实例
                new_device = builder.makeGeneralDevice(
                    device_id=channel_id,
                    device_name=req.name,
                    protocol_type=protocol_enum,
                    is_start=False 
                )
                new_device.name = req.name # 确保名字一致
                
                # 5. 注册到控制器
                device_controller.device_list.append(new_device)
                device_controller.device_map[new_device.name] = new_device
                
                log.info(f"设备 {req.name} (ID: {channel_id}) 已在内存中动态创建")

            except Exception as e:
                log.error(f"内存同步创建设备失败: {e}")
                # 即使内存同步失败，数据库已创建成功，不阻拦返回，但可能需要前端刷新或重启
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
    request: Request,
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
            
            # 4. 同步更新内存中的设备点表
            try:
                device_controller = request.app.state.device_controller
                device = device_controller.get_device_by_id(channel_id)
                if device:
                    # 重新从数据库加载点表
                    # 注意：importDataPointFromChannel 会清空现有 SimulationPointList 并重新初始化
                    # 我们需要确保 protocol_type 正确。Device 对象里应该存了。
                    device.importDataPointFromChannel(channel_id, device.protocol_type)
                    log.info(f"已同步更新设备 {device.name} (ID: {channel_id}) 的内存点表")
                else:
                    log.warning(f"导入点表后未找到内存设备 (ID: {channel_id})，需要手动加载或重启")
            except Exception as e:
                log.error(f"同步内存点表失败: {e}")

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
        device_controller = request.app.state.device_controller
        new_device = await _reload_device_instance(device_controller, channel_id, is_start=True)
        device_name = new_device.name
        
        return BaseResponse(message=f"设备 {device_name} 重启成功", data={"device_name": device_name})
        
    except Exception as e:
        log.error(f"重启设备失败: {e}")
        return BaseResponse(code=500, message=f"重启设备失败: {e}")


@channel_router.post("/reload_config/{channel_id}", response_model=BaseResponse)
async def reload_device_config(channel_id: int, request: Request):
    """重新加载设备配置（不自动启动服务）"""
    try:
        device_controller = request.app.state.device_controller
        new_device = await _reload_device_instance(device_controller, channel_id, is_start=False)
        device_name = new_device.name
        
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
            # ==========================================
            # 新增：更新成功后立即重载设备配置（不自动启动）
            # ==========================================
            try:
                device_controller = request.app.state.device_controller
                await _reload_device_instance(device_controller, channel_id, is_start=False)

            except Exception as e:
                log.error(f"更新配置后重载设备失败: {e}")
                # 不阻拦返回成功

            return BaseResponse(message="更新通道成功", data=True)
        else:
            return BaseResponse(code=500, message="更新通道失败", data=False)
            
    except Exception as e:
        log.error(f"更新通道失败: {e}")
        return BaseResponse(code=500, message=f"更新通道失败: {e}", data=False)


async def _reload_device_instance(device_controller, channel_id: int, is_start: bool = True):
    """
    内部辅助函数：重载/重启设备实例
    """
    # 1. 停止并移除旧设备
    await device_controller.remove_device_by_id(channel_id)
    
    # 2. 获取最新配置
    channel = ChannelService.get_channel_by_id(channel_id)
    if not channel:
        raise ValueError(f"通道 {channel_id} 不存在")
        
    device_name = channel["name"]
    channel_code = channel["code"]
    channel_protocol_type = ChannelService.get_protocol_type(channel)
    port = channel.get("port", Config.DEFAULT_PORT)
    ip = channel.get("ip", Config.DEFAULT_IP)
    
    # 3. 构建器
    # 引入必要的类 (避免循环导入，这里局部引入即可，或顶部引入)
    from src.device.factory.general_device_builder import GeneralDeviceBuilder
    from src.device.types.general_device import GeneralDevice
    from src.device.types.pcs import Pcs
    from src.device.types.circuit_breaker import CircuitBreaker
    
    if channel_code.upper().find("PCS") != -1:
        builder = GeneralDeviceBuilder(channel_id=channel_id, device=Pcs())
    elif channel_code.upper().find("BREAKER") != -1:
        builder = GeneralDeviceBuilder(channel_id=channel_id, device=CircuitBreaker())
    else:
        builder = GeneralDeviceBuilder(channel_id=channel_id, device=GeneralDevice())
    
    # 4. 通信配置
    conn_type = channel.get("conn_type", 1)
    
    log.info(f"Preparing to reload device {device_name}. Protocol: {channel_protocol_type}, ConnType: {conn_type}, IP: {ip}, Port: {port}")
    
    if conn_type in [0, 3]:  # 串口
        builder.setDeviceSerialConfig(
            serial_port=channel.get("com_port", ""),
            baudrate=channel.get("baud_rate", 9600),
            databits=channel.get("data_bits", 8),
            stopbits=channel.get("stop_bits", 1),
            parity=channel.get("parity", "E")
        )
    elif (
        channel_protocol_type == ProtocolType.Iec104Client
        or channel_protocol_type == ProtocolType.ModbusTcpClient
        or channel_protocol_type == ProtocolType.Dlt645Client
    ):
        log.info(f"Setting client net config: IP={ip}, Port={port}")
        builder.setDeviceNetConfig(port=port, ip=ip)
    else:
        log.info(f"Setting server net config: IP={Config.DEFAULT_IP}, Port={port}")
        builder.setDeviceNetConfig(port=port, ip=Config.DEFAULT_IP)
    
    # 5. 创建设备
    new_device = builder.makeGeneralDevice(
        device_id=channel_id,
        device_name=device_name,
        protocol_type=channel_protocol_type,
        is_start=is_start, 
    )
    new_device.name = device_name
    
    if is_start:
        new_device.data_update_thread.start()
    
    device_controller.device_list.append(new_device)
    device_controller.device_map[new_device.name] = new_device
    
    log.info(f"设备 {device_name} 实例已更新 (启动状态: {is_start})")
    
    return new_device

