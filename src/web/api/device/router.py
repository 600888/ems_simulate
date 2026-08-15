"""设备管理 - 设备操作路由"""

import asyncio
import atexit
from copy import deepcopy

from fastapi import APIRouter, Request

from src.config.storage import get_storage_path
from src.data.dao.channel_dao import ChannelDao
from src.device.core.device import Device
from src.enums.modbus_def import ProtocolType
from src.web.api.exceptions import NotFoundError, OperationError, ValidationError
from src.web.api.schemas import (
    BaseResponse,
    DeviceInfoRequest,
    DeviceStartRequest,
    DeviceStopRequest,
    DeviceTableRequest,
    DLT645CommandRequest,
    DLT645DiInfoRequest,
    ExportModelRequest,
    IEC61850ImportModelRequest,
    ManualReadRequest,
    MessageDetailRequest,
    MessageListRequest,
    SimulationStartRequest,
    SimulationStopRequest,
    SlaveAddRequest,
    SlaveDeleteRequest,
    SlaveEditRequest,
)
from src.web.log import log

# from src.web.ws.manager import manager  # TODO: WebSocket 模块尚未实现

device_router = APIRouter(prefix="/api/devices", tags=["设备管理"])


def _get_device(device_name: str, request: Request) -> Device:
    """获取设备，不存在时抛出 NotFoundError（由全局异常处理器统一返回 404）"""
    try:
        return request.app.state.device_controller.device_map[device_name]
    except KeyError as exc:
        log.warning(f"设备 {device_name} 不存在")
        raise NotFoundError(f"设备 {device_name} 不存在") from exc


@device_router.post("/list", response_model=BaseResponse)
async def get_device_name_list(request: Request):
    """获取设备名列表"""
    sorted_devices = sorted(
        request.app.state.device_controller.device_list,
        key=lambda d: getattr(d, "device_id", 0),
    )
    device_name_list = [deepcopy(device.name) for device in sorted_devices]
    return BaseResponse(data=device_name_list)


@device_router.post("/info", response_model=BaseResponse)
async def get_device_info(req: DeviceInfoRequest, request: Request):
    """获取设备信息"""
    device = _get_device(req.device_name, request)
    info_dict = {
        "ip": device.ip,
        "port": device.port,
        "type": device.protocol_type.value,
        "simulation_status": device.isSimulationRunning(),
        "serial_port": getattr(device, "serial_port", None),
        "baudrate": getattr(device, "baudrate", 9600),
        "databits": getattr(device, "databits", 8),
        "stopbits": getattr(device, "stopbits", 1),
        "parity": getattr(device, "parity", "N"),
        "meter_address": getattr(device, "meter_address", None),
    }

    channels = await asyncio.to_thread(ChannelDao.get_all_channels)
    channel = next((c for c in channels if c.get("name") == req.device_name), None)

    if channel:
        info_dict["ip"] = channel.get("ip")
        info_dict["port"] = channel.get("port")
        info_dict["conn_type"] = channel.get("conn_type", 2)
        info_dict["channel_id"] = channel.get("id")
    else:
        info_dict["conn_type"] = 2

    info_dict["server_status"] = device.is_protocol_running()
    info_dict["iec61850_model_loaded"] = device.iec61850_model_loaded
    return BaseResponse(message="获取设备信息成功!", data=info_dict)


@device_router.post("/slave-id-list", response_model=BaseResponse)
async def get_slave_id_list(req: DeviceInfoRequest, request: Request):
    """获取从机ID列表"""
    device = _get_device(req.device_name, request)
    return BaseResponse(data=sorted(device.slave_id_list))


@device_router.post("/table", response_model=BaseResponse)
async def get_table_by_slave_id(req: DeviceTableRequest, request: Request):
    """获取设备表格数据"""
    device = _get_device(req.device_name, request)
    table_data, total = await asyncio.to_thread(
        device.get_table_data,
        slave_id=req.slave_id,
        name=req.point_name,
        page_index=req.page_index,
        page_size=req.page_size,
        point_types=req.point_types,
        order_by=req.order_by,
        order_direction=req.order_direction,
        iec104_types=req.iec104_types,
        dlt645_prefix=req.dlt645_prefix,
        dlt645_settlement=req.dlt645_settlement,
    )
    data_dict = {"total": total, "table_data": table_data}
    return BaseResponse(message="获取从机信息成功!", data=data_dict)


@device_router.post("/start-simulation", response_model=BaseResponse)
async def start_simulation(req: SimulationStartRequest, request: Request):
    """启动模拟"""
    device = _get_device(req.device_name, request)
    await asyncio.to_thread(device.setAllPointSimulateMethod, req.simulate_method)
    device.startSimulation()
    return BaseResponse(message="启动模拟程序成功!", data=True)


@device_router.post("/stop-simulation", response_model=BaseResponse)
async def stop_simulation(req: SimulationStopRequest, request: Request):
    """停止模拟"""
    device = _get_device(req.device_name, request)
    await asyncio.to_thread(device.stopSimulation)
    return BaseResponse(message="停止模拟程序成功!", data=True)


@device_router.post("/start", response_model=BaseResponse)
async def start_device(req: DeviceStartRequest, request: Request):
    """启动设备"""
    device = _get_device(req.device_name, request)
    success = await device.start()
    if not success:
        log.error(f"设备 {req.device_name} 启动失败 (连接被拒绝或超时)")
        raise OperationError("设备启动失败! (连接被拒绝或超时)", data=False)
    return BaseResponse(message="设备启动成功!", data=True)


@device_router.post("/stop", response_model=BaseResponse)
async def stop_device(req: DeviceStopRequest, request: Request):
    """停止设备"""
    device = _get_device(req.device_name, request)
    success = await device.stop()
    if not success:
        log.error(f"设备 {req.device_name} 停止失败")
        raise OperationError("设备停止失败!", data=False)
    return BaseResponse(message="设备停止成功!", data=True)


@device_router.post("/iec61850-connect-progress", response_model=BaseResponse)
async def get_iec61850_connect_progress(req: DeviceInfoRequest, request: Request):
    """获取 IEC61850 客户端连接、发现或 DataSet 批读进度。"""
    device = _get_device(req.device_name, request)
    progress = device.get_iec61850_connect_progress()
    return BaseResponse(data=progress)


@device_router.post("/iec61850/import_model", response_model=BaseResponse)
async def import_iec61850_model(req: IEC61850ImportModelRequest, request: Request):
    """导入 IEC61850 ICD 模型（从指定的 ICD 文件路径加载）

    用户手动在界面点击"导入模型"后调用。
    ICD 文件必须已通过 SCL 导入功能上传到服务器。

    Args:
        req: {device_name, icd_path}
    """
    device = _get_device(req.device_name, request)
    success = await asyncio.to_thread(device.load_iec61850_model, req.icd_path)
    if not success:
        log.error(f"设备 {req.device_name} IEC61850 模型导入失败: {req.icd_path}")
        raise OperationError("IEC61850 模型导入失败!", data=False)
    return BaseResponse(message="IEC61850 模型导入成功!", data=True)


@device_router.post("/iec61850/load_model", response_model=BaseResponse)
async def load_iec61850_model(req: DeviceInfoRequest, request: Request):
    """从数据库存储的 ICD 路径加载 IEC61850 模型

    查询通道配置中记录的 icd_path，若存在且文件有效则加载模型到内存。
    如果没有记录或文件不存在则返回错误提示。

    Args:
        req: {device_name}
    """
    import os

    from src.data.service.channel_service import ChannelService

    device = _get_device(req.device_name, request)

    # 查询数据库中的 icd_path
    channels = await asyncio.to_thread(ChannelService.get_all_channels)
    channel = next((c for c in channels if c.get("name") == req.device_name), None)

    if not channel:
        log.warning(f"设备 {req.device_name} 的通道配置不存在")
        raise NotFoundError(f"设备 {req.device_name} 的通道通道配置不存在")

    icd_path = channel.get("icd_path")
    if not icd_path:
        log.warning(f"设备 {req.device_name} 未存储 ICD 模型路径")
        raise OperationError("数据库中未存储 ICD 模型路径，请先导入模型!", data=False)

    if not os.path.exists(icd_path):
        log.error(f"设备 {req.device_name} 的 ICD 文件不存在: {icd_path}")
        raise OperationError(f"ICD 文件不存在: {icd_path}，请重新导入模型!", data=False)

    success = await asyncio.to_thread(device.load_iec61850_model, icd_path)
    if not success:
        log.error(f"设备 {req.device_name} IEC61850 模型加载失败: {icd_path}")
        raise OperationError("IEC61850 模型加载失败!", data=False)
    return BaseResponse(
        message=f"IEC61850 模型加载成功! 路径: {icd_path}",
        data={"icd_path": icd_path},
    )


@device_router.post("/iec61850/model-cache-status", response_model=BaseResponse)
async def check_iec61850_model_cache(req: DeviceInfoRequest, request: Request):
    """检查 IEC61850 远程模型缓存是否存在

    在点击"发现模型"前调用，如果缓存已存在，前端可提示用户
    选择使用缓存或重新发现。

    Args:
        req: {device_name}
    """
    device = _get_device(req.device_name, request)
    cache_info = await asyncio.to_thread(device.check_iec61850_model_cache)
    return BaseResponse(data=cache_info)


@device_router.post("/iec61850/load-model-from-cache", response_model=BaseResponse)
async def load_iec61850_model_from_cache(req: DeviceInfoRequest, request: Request):
    """从缓存加载 IEC61850 模型（不进行 MMS 在线发现）

    仅在模型缓存存在时有效，直接从 ModelCache 恢复 IedModel 和 PointRegistry。

    Args:
        req: {device_name}
    """
    device = _get_device(req.device_name, request)
    success = await asyncio.to_thread(device.iec61850_load_model_from_cache)
    if not success:
        log.warning(f"设备 {req.device_name} IEC61850 模型缓存不存在或无法读取")
        raise OperationError("IEC61850 模型缓存不存在或无法读取!", data=False)
    return BaseResponse(message="IEC61850 模型从缓存加载成功!", data=True)


@device_router.post("/iec61850/discover-model", response_model=BaseResponse)
async def discover_iec61850_model(req: DeviceInfoRequest, request: Request):
    """远程发现 IEC61850 模型（通过 MMS 在线遍历）

    如果客户端未连接，自动先连接再发现。
    connect() 是 C 扩展同步调用，通过 to_thread 避免阻塞事件循环。

    Args:
        req: {device_name}
    """
    device = _get_device(req.device_name, request)
    channel_id = int(getattr(device, "device_id", 0) or 0)
    if channel_id > 0:
        from src.proto.iec61850.plugins.goose.cleanup import clear_channel_goose_resources

        goose_manager = getattr(request.app.state, "goose_manager", None)
        cleanup = await asyncio.to_thread(clear_channel_goose_resources, channel_id, goose_manager)
        if any(cleanup.values()):
            log.info(
                f"设备 {req.device_name} 在线重发现前已清理旧 GOOSE 配置: "
                f"Publisher/DataSet={cleanup['publishers']}, Receiver={cleanup['receivers']}, "
                f"运行时 Publisher={cleanup['runtime_publishers']}, "
                f"运行时 Receiver={cleanup['runtime_receivers']}"
            )
    else:
        log.warning(f"设备 {req.device_name} 缺少有效 channel_id，在线重发现无法清理旧 GOOSE 配置")
    success = await asyncio.to_thread(device.iec61850_remote_discover_model)
    if not success:
        log.error(f"设备 {req.device_name} IEC61850 远程模型发现失败")
        raise OperationError("IEC61850 远程模型发现失败!", data=False)
    return BaseResponse(message="IEC61850 远程模型发现成功!", data=True)


# ===== 自动读取控制 =====


@device_router.post("/auto-read-status", response_model=BaseResponse)
async def get_auto_read_status(req: DeviceInfoRequest, request: Request):
    """获取自动读取状态"""
    device = _get_device(req.device_name, request)
    is_running = device.is_auto_read_running()
    return BaseResponse(message="获取自动读取状态成功!", data=is_running)


@device_router.post("/start-auto-read", response_model=BaseResponse)
async def start_auto_read(req: DeviceInfoRequest, request: Request):
    """启动自动读取"""
    device = _get_device(req.device_name, request)
    success = device.start_auto_read()
    if not success:
        log.warning(f"设备 {req.device_name} 自动读取已在运行中")
        raise ValidationError("自动读取已在运行中!", data=False)
    return BaseResponse(message="启动自动读取成功!", data=True)


@device_router.post("/stop-auto-read", response_model=BaseResponse)
async def stop_auto_read(req: DeviceInfoRequest, request: Request):
    """停止自动读取"""
    device = _get_device(req.device_name, request)
    device.stop_auto_read()
    return BaseResponse(message="停止自动读取成功!", data=True)


@device_router.post("/manual-read", response_model=BaseResponse)
async def manual_read(req: ManualReadRequest, request: Request):
    """手动读取"""
    device = _get_device(req.device_name, request)

    async def event_emitter(data):
        # await manager.broadcast(data, req.device_name)  # TODO: ws 模块未实现
        pass

    stats = await device.single_read(event_emitter=event_emitter, interval_ms=req.interval)
    return BaseResponse(message="手动读取成功!", data=stats)


@device_router.post("/iec104-interrogation", response_model=BaseResponse)
async def iec104_interrogation(req: DeviceInfoRequest, request: Request):
    """触发 IEC104 总召唤(C_IC_NA_1)，刷新所有测点数据"""
    device = _get_device(req.device_name, request)
    success = await device.send_iec104_interrogation()
    if not success:
        raise OperationError("总召唤失败，请检查设备是否已连接且为 IEC104 客户端", data=False)
    return BaseResponse(message="总召唤已触发，数据同步中!", data=True)


@device_router.post("/dlt645-command", response_model=BaseResponse)
async def send_dlt645_command(req: DLT645CommandRequest, request: Request):
    """发送 DL/T645 特殊命令（读/写通讯地址、广播校时、冻结、改速率、改密码、清零等）

    主站（Dlt645Client）与从站（Dlt645Server）设备均支持，
    具体可用命令由 handler 侧按角色分发。
    """
    device = _get_device(req.device_name, request)
    result = await device.send_dlt645_command(req.command, req.params)
    if not result.get("ok"):
        message = result.get("message", "DLT645 命令执行失败")
        log.error(f"设备 {req.device_name} DLT645 命令失败: {message}")
        raise OperationError(message, data=False)
    return BaseResponse(
        message=result.get("message", "命令执行成功"),
        data=result.get("detail") if result.get("detail") is not None else True,
    )


@device_router.post("/dlt645-di-info", response_model=BaseResponse)
async def get_dlt645_di_info(req: DLT645DiInfoRequest):
    """获取 DL/T645 数据标识（DI）的元信息：名称、数据格式、是否列表及子项格式。"""
    import dlt645  # noqa: F401
    from dlt645.model.data.define import DIMap

    di_str = req.di.strip()
    try:
        di = int(di_str, 16)
    except ValueError:
        raise ValidationError("数据标识格式错误，请输入十六进制，如 0x00000000") from None
    item = DIMap.get(di)
    if item is None:
        raise ValidationError(f"数据标识 0x{di:08X} 不存在")

    def _range(it: object) -> tuple:
        min_v = getattr(it, "min_value", None)
        max_v = getattr(it, "max_value", None)
        return min_v, max_v

    if isinstance(item, list):
        min_v, max_v = _range(item[0])
        for child in item[1:]:
            child_min, child_max = _range(child)
            if child_min is not None:
                min_v = child_min if min_v is None else min(min_v, child_min)
            if child_max is not None:
                max_v = child_max if max_v is None else max(max_v, child_max)
        info = {
            "di": f"0x{di:08X}",
            "name": " / ".join(str(getattr(child, "name", "")) for child in item if getattr(child, "name", "")),
            "is_list": True,
            "data_format": None,
            "list_formats": [getattr(child, "data_format", "") for child in item],
            "min_value": min_v,
            "max_value": max_v,
        }
    else:
        min_v, max_v = _range(item)
        info = {
            "di": f"0x{di:08X}",
            "name": str(getattr(item, "name", "")),
            "is_list": False,
            "data_format": getattr(item, "data_format", ""),
            "list_formats": None,
            "min_value": min_v,
            "max_value": max_v,
        }
    return BaseResponse(data=info)


# ===== 报文捕获 =====


@device_router.post("/messages", response_model=BaseResponse)
async def get_messages(req: MessageListRequest, request: Request):
    """获取设备报文历史"""
    device = _get_device(req.device_name, request)
    messages = device.get_messages(limit=req.limit)
    return BaseResponse(message="获取报文历史成功!", data={"messages": messages, "count": len(messages)})


@device_router.post("/message-detail", response_model=BaseResponse)
async def get_message_detail(req: MessageDetailRequest, request: Request):
    device = _get_device(req.device_name, request)
    detail = device.get_message_detail(req.sequence_id)
    if detail is None:
        raise NotFoundError("报文不存在、已被缓存淘汰或该协议暂不支持详情解析")
    return BaseResponse(message="获取报文详情成功!", data=detail)


@device_router.post("/clear-messages", response_model=BaseResponse)
async def clear_messages(req: DeviceInfoRequest, request: Request):
    """清空设备报文历史"""
    device = _get_device(req.device_name, request)
    device.clear_messages()
    return BaseResponse(message="清空报文历史成功!", data=True)


@device_router.post("/avg-time", response_model=BaseResponse)
async def get_avg_time(req: DeviceInfoRequest, request: Request):
    """获取报文平均收发时间"""
    device = _get_device(req.device_name, request)
    stats = device.get_avg_time()
    return BaseResponse(message="获取平均收发时间成功!", data=stats)


# ===== 从机管理 =====


@device_router.post("/add-slave", response_model=BaseResponse)
async def add_slave(req: SlaveAddRequest, request: Request):
    """添加从机"""
    device = _get_device(req.device_name, request)
    success = device.add_slave_dynamic(req.slave_id)
    if not success:
        log.warning(f"设备 {req.device_name} 添加从机失败: slave_id={req.slave_id}")
        raise ValidationError("添加从机失败，请检查从机地址是否有效或已存在!", data=False)
    return BaseResponse(message="添加从机成功!", data=True)


@device_router.post("/delete-slave", response_model=BaseResponse)
async def delete_slave(req: SlaveDeleteRequest, request: Request):
    """删除从机"""
    device = _get_device(req.device_name, request)
    success = device.delete_slave_dynamic(req.slave_id)
    if not success:
        log.warning(f"设备 {req.device_name} 删除从机失败: slave_id={req.slave_id}")
        raise OperationError("删除从机失败!", data=False)
    return BaseResponse(message="删除从机成功!", data=True)


@device_router.post("/edit-slave", response_model=BaseResponse)
async def edit_slave(req: SlaveEditRequest, request: Request):
    """编辑从机"""
    device = _get_device(req.device_name, request)
    success = device.edit_slave_dynamic(req.old_slave_id, req.new_slave_id)
    if not success:
        log.warning(f"设备 {req.device_name} 编辑从机失败: {req.old_slave_id} -> {req.new_slave_id}")
        raise ValidationError("编辑从机失败，请检查新从机地址是否有效或已存在!", data=False)
    return BaseResponse(message="编辑从机成功!", data=True)


# ===== IEC 61850 模型导出 =====

# 临时目录安全网: atexit 时清理泄漏的临时目录
_temp_dirs: list[str] = []


def _cleanup_temp_dirs() -> None:
    """atexit 清理泄漏的临时目录"""
    import shutil

    for d in _temp_dirs:
        shutil.rmtree(d, ignore_errors=True)


atexit.register(_cleanup_temp_dirs)


@device_router.post("/export-model")
async def export_model(req: ExportModelRequest, request: Request):
    """导出 IEC 61850 服务器模型为指定格式文件

    支持: icd (SCL/ICD标准格式), json, xml, csv, tree
    使用缓存的 IedModel + Strategy 导出器。
    临时文件通过 BackgroundTask + atexit 双重清理。
    """
    import os
    import shutil
    import tempfile

    from fastapi.responses import FileResponse
    from starlette.background import BackgroundTask

    device = _get_device(req.device_name, request)

    # 仅支持 IEC 61850 客户端设备
    if device.protocol_type != ProtocolType.Iec61850Client:
        log.warning(f"设备 {req.device_name} 导出模型失败: 仅支持 IEC 61850 客户端, 当前类型={device.protocol_type}")
        raise ValidationError("仅支持 IEC 61850 客户端设备导出模型!", data=False)

    # 检查客户端是否已连接
    client = device.client
    if not client or not client.is_connected:
        log.warning(f"设备 {req.device_name} 导出模型失败: 客户端未连接")
        raise ValidationError("IEC 61850 客户端未连接，请先启动设备!", data=False)

    # 导出类型映射
    export_type = req.export_type.lower()
    type_config = {
        "icd": {"ext": ".icd", "media": "application/xml"},
        "json": {"ext": ".json", "media": "application/json"},
        "xml": {"ext": ".xml", "media": "application/xml"},
        "csv": {"ext": ".csv", "media": "text/csv"},
        "tree": {"ext": ".txt", "media": "text/plain"},
    }

    if export_type not in type_config:
        log.warning(f"设备 {req.device_name} 导出模型失败: 不支持的导出类型 {req.export_type}")
        raise ValidationError(f"不支持的导出类型: {req.export_type}，支持: icd/json/xml/csv/tree", data=False)

    config = type_config[export_type]
    tmp_dir = tempfile.mkdtemp(
        prefix="ems_export_",
        dir=get_storage_path("iec61850_temp_directory"),
    )
    _temp_dirs.append(tmp_dir)  # atexit 安全网

    try:
        # 使用 Strategy 导出器 + 缓存 IedModel
        exporter = client.model_exporter
        filename = f"{req.device_name}_model{config['ext']}"
        tmp_path = os.path.join(tmp_dir, filename)

        if export_type == "icd":
            exporter.export(export_type, output_path=tmp_path, ied_name=req.ied_name)
        else:
            exporter.export(export_type, output_path=tmp_path)

        # 返回文件下载，使用 BackgroundTask 在响应完成后清理临时文件
        def _cleanup():
            if tmp_dir in _temp_dirs:
                _temp_dirs.remove(tmp_dir)
            shutil.rmtree(tmp_dir, ignore_errors=True)

        return FileResponse(
            path=tmp_path,
            filename=filename,
            media_type=config["media"],
            background=BackgroundTask(_cleanup),
        )
    except RuntimeError as e:
        log.error(f"设备 {req.device_name} 导出模型失败 (模型未缓存): {e}")
        # IedModel 未缓存
        if tmp_dir in _temp_dirs:
            _temp_dirs.remove(tmp_dir)
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise ValidationError(str(e), data=False) from e
    except Exception as e:
        # 异常时立即清理临时文件
        if tmp_dir in _temp_dirs:
            _temp_dirs.remove(tmp_dir)
        shutil.rmtree(tmp_dir, ignore_errors=True)
        log.error(f"设备 {req.device_name} 导出模型失败: {e}")
        raise OperationError(f"导出模型失败: {e}", data=False) from e
