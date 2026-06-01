"""设备管理 - 设备操作路由"""

from copy import deepcopy

from fastapi import APIRouter, Depends, Request

from src.data.dao.channel_dao import ChannelDao
from src.device.core.device import Device
from src.enums.modbus_def import ProtocolType
from src.web.api.schemas import (
    BaseResponse,
    CurrentTableRequest,
    DeviceInfoRequest,
    DeviceResetRequest,
    DeviceStartRequest,
    DeviceStopRequest,
    DeviceTableRequest,
    ExportModelRequest,
    ManualReadRequest,
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
    return request.app.state.device_controller.device_map[device_name]


@device_router.post("/list", response_model=BaseResponse)
async def get_device_name_list(request: Request):
    """获取设备名列表"""
    try:
        sorted_devices = sorted(
            request.app.state.device_controller.device_list,
            key=lambda d: getattr(d, "device_id", 0),
        )
        device_name_list = [deepcopy(device.name) for device in sorted_devices]
        return BaseResponse(data=device_name_list)
    except Exception as e:
        log.error(f"获取设备名列表失败: {e}")
        return BaseResponse(code=500, message="获取设备名列表失败!", data=[])


@device_router.post("/info", response_model=BaseResponse)
async def get_device_info(req: DeviceInfoRequest, request: Request):
    """获取设备信息"""
    try:
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
        }

        channels = ChannelDao.get_all_channels()
        channel = next((c for c in channels if c.get("name") == req.device_name), None)

        if channel:
            info_dict["ip"] = channel.get("ip")
            info_dict["port"] = channel.get("port")
            info_dict["conn_type"] = channel.get("conn_type", 2)
            info_dict["channel_id"] = channel.get("id")
        else:
            info_dict["conn_type"] = 2

        info_dict["server_status"] = device.is_protocol_running()
        return BaseResponse(message="获取设备信息成功!", data=info_dict)
    except Exception as e:
        log.error(f"获取设备信息失败: {e}")
        return BaseResponse(code=500, message=f"获取设备信息失败: {e}!", data={})


@device_router.post("/slave-id-list", response_model=BaseResponse)
async def get_slave_id_list(req: DeviceInfoRequest, request: Request):
    """获取从机ID列表"""
    try:
        device = _get_device(req.device_name, request)
        return BaseResponse(data=sorted(device.slave_id_list))
    except Exception as e:
        log.error(f"获取从机id列表失败: {e}")
        return BaseResponse(code=500, message=f"获取从机id列表失败: {e}!", data=[])


@device_router.post("/table", response_model=BaseResponse)
async def get_table_by_slave_id(req: DeviceTableRequest, request: Request):
    """获取设备表格数据"""
    try:
        device = _get_device(req.device_name, request)
        table_data, total = device.get_table_data(
            req.slave_id,
            req.point_name,
            req.page_index,
            req.page_size,
            req.point_types,
            req.order_by,
            req.order_direction,
        )
        data_dict = {"total": total, "table_data": table_data}
        return BaseResponse(message="获取从机信息成功!", data=data_dict)
    except Exception as e:
        log.error(f"获取从机信息失败: {e}")
        return BaseResponse(code=500, message=f"获取从机信息失败: {e}!", data={})


@device_router.post("/start-simulation", response_model=BaseResponse)
async def start_simulation(req: SimulationStartRequest, request: Request):
    """启动模拟"""
    try:
        device = _get_device(req.device_name, request)
        device.setAllPointSimulateMethod(req.simulate_method)
        device.startSimulation()
        return BaseResponse(message="启动模拟程序成功!", data=True)
    except Exception as e:
        log.error(f"启动模拟程序失败: {e}")
        return BaseResponse(code=500, message=f"启动模拟程序失败: {e}!", data=False)


@device_router.post("/stop-simulation", response_model=BaseResponse)
async def stop_simulation(req: SimulationStopRequest, request: Request):
    """停止模拟"""
    try:
        device = _get_device(req.device_name, request)
        device.stopSimulation()
        return BaseResponse(message="停止模拟程序成功!", data=True)
    except Exception as e:
        log.error(f"停止模拟程序失败: {e}")
        return BaseResponse(code=500, message=f"停止模拟程序失败: {e}!", data=False)


@device_router.post("/current-table", response_model=BaseResponse)
async def get_current_table(req: CurrentTableRequest, request: Request):
    """获取当前表数据"""
    try:
        device = _get_device(req.device_name, request)
        data_list, hex_data_list, real_data_list, max_limit_list, min_limit_list = device.getSlaveValueList(
            req.slave_id, req.point_name
        )
        data_dict = {
            "data_list": data_list,
            "hex_data_list": hex_data_list,
            "real_data_list": real_data_list,
            "max_limit_list": max_limit_list,
            "min_limit_list": min_limit_list,
        }
        return BaseResponse(message="获取当前表数据成功!", data=data_dict)
    except Exception as e:
        log.error(f"获取当前表数据失败: {e}")
        return BaseResponse(code=500, message="获取当前表数据失败!", data={})


@device_router.post("/start", response_model=BaseResponse)
async def start_device(req: DeviceStartRequest, request: Request):
    """启动设备"""
    try:
        device = _get_device(req.device_name, request)
        success = await device.start()
        if success:
            return BaseResponse(message="设备启动成功!", data=True)
        else:
            return BaseResponse(code=500, message="设备启动失败! (连接被拒绝或超时)", data=False)
    except KeyError:
        return BaseResponse(code=404, message=f"设备 {req.device_name} 不存在!", data=False)
    except Exception as e:
        log.error(f"设备启动失败: {e}")
        return BaseResponse(code=500, message=f"设备启动失败: {e}!", data=False)


@device_router.post("/stop", response_model=BaseResponse)
async def stop_device(req: DeviceStopRequest, request: Request):
    """停止设备"""
    try:
        device = _get_device(req.device_name, request)
        success = await device.stop()
        if success:
            return BaseResponse(message="设备停止成功!", data=True)
        else:
            return BaseResponse(code=500, message="设备停止失败!", data=False)
    except KeyError:
        return BaseResponse(code=404, message=f"设备 {req.device_name} 不存在!", data=False)
    except Exception as e:
        log.error(f"设备停止失败: {e}")
        return BaseResponse(code=500, message=f"设备停止失败: {e}!", data=False)


@device_router.post("/iec61850-connect-progress", response_model=BaseResponse)
async def get_iec61850_connect_progress(req: DeviceInfoRequest, request: Request):
    """获取 IEC61850 客户端连接进度"""
    try:
        device = _get_device(req.device_name, request)
        progress = device.get_iec61850_connect_progress()
        return BaseResponse(data=progress)
    except KeyError:
        return BaseResponse(code=404, message=f"设备 {req.device_name} 不存在!", data={})
    except Exception as e:
        log.error(f"获取连接进度失败: {e}")
        return BaseResponse(code=500, message=f"获取连接进度失败: {e}", data={})


# ===== 自动读取控制 =====


@device_router.post("/auto-read-status", response_model=BaseResponse)
async def get_auto_read_status(req: DeviceInfoRequest, request: Request):
    """获取自动读取状态"""
    try:
        device = _get_device(req.device_name, request)
        is_running = device.is_auto_read_running()
        return BaseResponse(message="获取自动读取状态成功!", data=is_running)
    except KeyError:
        return BaseResponse(code=404, message=f"设备 {req.device_name} 不存在!", data=False)
    except Exception as e:
        log.error(f"获取自动读取状态失败: {e}")
        return BaseResponse(code=500, message=f"获取自动读取状态失败: {e}!", data=False)


@device_router.post("/start-auto-read", response_model=BaseResponse)
async def start_auto_read(req: DeviceInfoRequest, request: Request):
    """启动自动读取"""
    try:
        device = _get_device(req.device_name, request)
        success = device.start_auto_read()
        if success:
            return BaseResponse(message="启动自动读取成功!", data=True)
        else:
            return BaseResponse(code=400, message="自动读取已在运行中!", data=False)
    except KeyError:
        return BaseResponse(code=404, message=f"设备 {req.device_name} 不存在!", data=False)
    except Exception as e:
        log.error(f"启动自动读取失败: {e}")
        return BaseResponse(code=500, message=f"启动自动读取失败: {e}!", data=False)


@device_router.post("/stop-auto-read", response_model=BaseResponse)
async def stop_auto_read(req: DeviceInfoRequest, request: Request):
    """停止自动读取"""
    try:
        device = _get_device(req.device_name, request)
        device.stop_auto_read()
        return BaseResponse(message="停止自动读取成功!", data=True)
    except KeyError:
        return BaseResponse(code=404, message=f"设备 {req.device_name} 不存在!", data=False)
    except Exception as e:
        log.error(f"停止自动读取失败: {e}")
        return BaseResponse(code=500, message=f"停止自动读取失败: {e}!", data=False)


@device_router.post("/manual-read", response_model=BaseResponse)
async def manual_read(req: ManualReadRequest, request: Request):
    """手动读取"""
    try:
        device = _get_device(req.device_name, request)

        async def event_emitter(data):
            # await manager.broadcast(data, req.device_name)  # TODO: ws 模块未实现
            pass

        stats = await device.single_read(event_emitter=event_emitter, interval_ms=req.interval)
        return BaseResponse(message="手动读取成功!", data=stats)
    except KeyError:
        return BaseResponse(code=404, message=f"设备 {req.device_name} 不存在!", data=False)
    except Exception as e:
        log.error(f"手动读取失败: {e}")
        return BaseResponse(code=500, message=f"手动读取失败: {e}!", data=False)


# ===== 报文捕获 =====


@device_router.post("/messages", response_model=BaseResponse)
async def get_messages(req: MessageListRequest, request: Request):
    """获取设备报文历史"""
    try:
        device = _get_device(req.device_name, request)
        messages = device.get_messages(limit=req.limit)
        return BaseResponse(message="获取报文历史成功!", data={"messages": messages, "count": len(messages)})
    except KeyError:
        return BaseResponse(code=404, message=f"设备 {req.device_name} 不存在!", data=None)
    except Exception as e:
        log.error(f"获取报文历史失败: {e}")
        return BaseResponse(code=500, message=f"获取报文历史失败: {e}!", data=None)


@device_router.post("/clear-messages", response_model=BaseResponse)
async def clear_messages(req: DeviceInfoRequest, request: Request):
    """清空设备报文历史"""
    try:
        device = _get_device(req.device_name, request)
        device.clear_messages()
        return BaseResponse(message="清空报文历史成功!", data=True)
    except KeyError:
        return BaseResponse(code=404, message=f"设备 {req.device_name} 不存在!", data=False)
    except Exception as e:
        log.error(f"清空报文历史失败: {e}")
        return BaseResponse(code=500, message=f"清空报文历史失败: {e}!", data=False)


@device_router.post("/avg-time", response_model=BaseResponse)
async def get_avg_time(req: DeviceInfoRequest, request: Request):
    """获取报文平均收发时间"""
    try:
        device = _get_device(req.device_name, request)
        stats = device.get_avg_time()
        return BaseResponse(message="获取平均收发时间成功!", data=stats)
    except KeyError:
        return BaseResponse(code=404, message=f"设备 {req.device_name} 不存在!", data=None)
    except Exception as e:
        log.error(f"获取平均收发时间失败: {e}")
        return BaseResponse(code=500, message=f"获取平均收发时间失败: {e}!", data=None)


# ===== 从机管理 =====


@device_router.post("/add-slave", response_model=BaseResponse)
async def add_slave(req: SlaveAddRequest, request: Request):
    """添加从机"""
    try:
        device = _get_device(req.device_name, request)
        success = device.add_slave_dynamic(req.slave_id)
        if success:
            return BaseResponse(message="添加从机成功!", data=True)
        else:
            return BaseResponse(code=400, message="添加从机失败，请检查从机地址是否有效或已存在!", data=False)
    except KeyError:
        return BaseResponse(code=404, message=f"设备 {req.device_name} 不存在!", data=False)
    except Exception as e:
        log.error(f"添加从机失败: {e}")
        return BaseResponse(code=500, message=f"添加从机失败: {e}!", data=False)


@device_router.post("/delete-slave", response_model=BaseResponse)
async def delete_slave(req: SlaveDeleteRequest, request: Request):
    """删除从机"""
    try:
        device = _get_device(req.device_name, request)
        success = device.delete_slave_dynamic(req.slave_id)
        if success:
            return BaseResponse(message="删除从机成功!", data=True)
        else:
            return BaseResponse(code=500, message="删除从机失败!", data=False)
    except KeyError:
        return BaseResponse(code=404, message=f"设备 {req.device_name} 不存在!", data=False)
    except Exception as e:
        log.error(f"删除从机失败: {e}")
        return BaseResponse(code=500, message=f"删除从机失败: {e}!", data=False)


@device_router.post("/edit-slave", response_model=BaseResponse)
async def edit_slave(req: SlaveEditRequest, request: Request):
    """编辑从机"""
    try:
        device = _get_device(req.device_name, request)
        success = device.edit_slave_dynamic(req.old_slave_id, req.new_slave_id)
        if success:
            return BaseResponse(message="编辑从机成功!", data=True)
        else:
            return BaseResponse(code=400, message="编辑从机失败，请检查新从机地址是否有效或已存在!", data=False)
    except KeyError:
        return BaseResponse(code=404, message=f"设备 {req.device_name} 不存在!", data=False)
    except Exception as e:
        log.error(f"编辑从机失败: {e}")
        return BaseResponse(code=500, message=f"编辑从机失败: {e}!", data=False)


# ===== IEC 61850 模型导出 =====


@device_router.post("/export-model")
async def export_model(req: ExportModelRequest, request: Request):
    """导出 IEC 61850 服务器模型为指定格式文件

    支持: icd (SCL/ICD标准格式), json, xml, csv, tree
    """
    import os
    import tempfile

    from fastapi.responses import FileResponse

    try:
        device = _get_device(req.device_name, request)
    except KeyError:
        return BaseResponse(code=404, message=f"设备 {req.device_name} 不存在!", data=False)
    except Exception as e:
        return BaseResponse(code=500, message=f"获取设备失败: {e}!", data=False)

    # 仅支持 IEC 61850 客户端设备
    if device.protocol_type != ProtocolType.Iec61850Client:
        return BaseResponse(code=400, message="仅支持 IEC 61850 客户端设备导出模型!", data=False)

    # 检查客户端是否已连接
    client = device.client
    if not client or not client.is_connected:
        return BaseResponse(code=400, message="IEC 61850 客户端未连接，请先启动设备!", data=False)

    # 导出类型映射
    export_type = req.export_type.lower()
    type_config = {
        "icd": {"ext": ".icd", "media": "application/xml", "method": "export_icd"},
        "json": {"ext": ".json", "media": "application/json", "method": "export_json"},
        "xml": {"ext": ".xml", "media": "application/xml", "method": "export_xml"},
        "csv": {"ext": ".csv", "media": "text/csv", "method": "export_csv"},
        "tree": {"ext": ".txt", "media": "text/plain", "method": "export_tree_text"},
    }

    if export_type not in type_config:
        return BaseResponse(
            code=400, message=f"不支持的导出类型: {req.export_type}，支持: icd/json/xml/csv/tree", data=False
        )

    config = type_config[export_type]

    try:
        # 发现模型
        exporter = client.model_exporter
        model = exporter.discover_server_model()

        # 导出到临时文件
        tmp_dir = tempfile.mkdtemp(prefix="ems_export_")
        filename = f"{req.device_name}_model{config['ext']}"
        tmp_path = os.path.join(tmp_dir, filename)

        # 调用对应的导出方法
        method = getattr(exporter, config["method"])
        if export_type == "icd":
            method(model, tmp_path, ied_name=req.ied_name)
        else:
            method(model, tmp_path)

        # 返回文件下载
        return FileResponse(
            path=tmp_path,
            filename=filename,
            media_type=config["media"],
        )
    except Exception as e:
        log.error(f"导出模型失败: {e}")
        return BaseResponse(code=500, message=f"导出模型失败: {e}!", data=False)
