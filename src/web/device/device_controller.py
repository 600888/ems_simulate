from fastapi import APIRouter, Request, File, UploadFile, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from copy import deepcopy
from typing import List, Dict, Optional

from src.config.global_config import UPLOAD_PLAN_DIR
from src.device.core.device import Device
from src.enums.modbus_def import ProtocolType
from src.enums.point_data import Yc, SimulateMethod
from src.web.log import log
from src.web.schemas import (
    BaseModel, BaseResponse, DeviceNameListResponse, DeviceInfoRequest, DeviceInfoResponse,
    SlaveIdListRequest, SlaveIdListResponse, DeviceTableRequest,
    PointEditDataRequest, PointLimitEditRequest, PointMetadataEditRequest,
    PointInfoRequest, SimulationStartRequest, SimulationStopRequest,
    SimulateMethodSetRequest, SimulateStepSetRequest, SimulateRangeSetRequest,
    DeviceStartRequest, DeviceStopRequest, DeviceResetRequest,
    MessageListRequest, PointCreateRequest, PointDeleteRequest, SlaveAddRequest, SlaveDeleteRequest,
    SlaveEditRequest,
    ClearPointsRequest, PointsBatchCreateRequest, CurrentTableRequest, PointLimitGetRequest
)
from src.data.dao.channel_dao import ChannelDao

# WebSocket 连接管理器
class ConnectionManager:
    def __init__(self):
        # device_name -> List[WebSocket]
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, device_name: str):
        await websocket.accept()
        if device_name not in self.active_connections:
            self.active_connections[device_name] = []
        self.active_connections[device_name].append(websocket)

    def disconnect(self, websocket: WebSocket, device_name: str):
        if device_name in self.active_connections:
            if websocket in self.active_connections[device_name]:
                self.active_connections[device_name].remove(websocket)
            if not self.active_connections[device_name]:
                del self.active_connections[device_name]

    async def broadcast(self, message: dict, device_name: str):
        if device_name in self.active_connections:
            for connection in self.active_connections[device_name]:
                try:
                    await connection.send_json(message)
                except Exception:
                    # 连接可能断开
                    pass

manager = ConnectionManager()

# 创建路由对象
device_router = APIRouter(prefix="/device", tags=["device"]) 

# 测试日志接口
@device_router.get("/test_log")
async def test_log():
    """测试日志是否正常工作"""
    log.info("测试日志 - INFO")
    log.error("测试日志 - ERROR")
    return {"message": "日志测试完成，请检查控制台和 web.log 文件"}

# @device_router.websocket("/ws/{device_name}")
# async def websocket_endpoint(websocket: WebSocket, device_name: str):
#     await manager.connect(websocket, device_name)
#     try:
#         while True:
#             await websocket.receive_text()
#     except WebSocketDisconnect:
#         manager.disconnect(websocket, device_name)

def get_device(device_name: str, request: Request) -> Device:
    return request.app.state.device_controller.device_map[device_name]


@device_router.post("/get_device_list", response_model=DeviceNameListResponse)
async def get_device_name_list(request: Request):
    try:
        # 按 device_id 排序，确保顺序稳定
        sorted_devices = sorted(
            request.app.state.device_controller.device_list,
            key=lambda d: getattr(d, 'device_id', 0)
        )
        device_name_list = [deepcopy(device.name) for device in sorted_devices]
        return DeviceNameListResponse(data=device_name_list)
    except Exception as e:
        log.error(f"获取设备名列表失败: {e}")
        return DeviceNameListResponse(code=500, message="获取设备名列表失败!", data=[])


# 获取设备信息接口
@device_router.post("/get_device_info", response_model=DeviceInfoResponse)
async def get_device_info(req: DeviceInfoRequest, request: Request):
    try:
        device = get_device(req.device_name, request)
        info_dict = {
            "ip": device.ip,
            "port": device.port,
            "type": device.protocol_type.value,
            "simulation_status": device.isSimulationRunning(),
            # 串口配置
            "serial_port": getattr(device, 'serial_port', None),
            "baudrate": getattr(device, 'baudrate', 9600),
            "databits": getattr(device, 'databits', 8),
            "stopbits": getattr(device, 'stopbits', 1),
            "parity": getattr(device, 'parity', 'N'),
        }
        
        # 获取 conn_type（服务端/客户端判断需要）
        channels = ChannelDao.get_all_channels()
        channel = next((c for c in channels if c.get("name") == req.device_name), None)
        
        # 优先使用数据库中的 IP 和 Port，因为 Device 对象中的可能是 0.0.0.0 (服务端绑定)
        if channel:
             info_dict["ip"] = channel.get("ip")
             info_dict["port"] = channel.get("port")
             info_dict["conn_type"] = channel.get("conn_type", 2)
        else:
             info_dict["conn_type"] = 2
        
        info_dict["server_status"] = device.is_protocol_running()
        return DeviceInfoResponse(message="获取设备信息成功!", data=info_dict)
    except Exception as e:
        log.error(f"获取设备信息失败: {e}")
        return DeviceInfoResponse(code=500, message=f"获取设备信息失败: {e}!", data={})


@device_router.post("/get_slave_id_list", response_model=SlaveIdListResponse)
async def get_slave_id_list(req: SlaveIdListRequest, request: Request):
    try:
        device = get_device(req.device_name, request)
        return SlaveIdListResponse(data=sorted(device.slave_id_list))
    except Exception as e:
        log.error(f"获取从机id列表失败: {e}")
        return SlaveIdListResponse(code=500, message=f"获取从机id列表失败: {e}!", data=[])


@device_router.post("/get_device_table", response_model=BaseResponse)
async def get_table_by_slave_id(req: DeviceTableRequest, request: Request):
    try:
        device = get_device(req.device_name, request)
        head_data = device.get_table_head()
        table_data, total = device.get_table_data(
            req.slave_id, req.point_name, req.page_index, req.page_size, req.point_types
        )
        data_dict = {"total": total, "head_data": head_data, "table_data": table_data}
        return BaseResponse(message="获取从机信息成功!", data=data_dict)
    except Exception as e:
        log.error(f"获取从机信息失败: {e}")
        return BaseResponse(code=500, message=f"获取从机信息失败: {e}!", data={})


@device_router.post("/start_simulation", response_model=BaseResponse)
async def start_simulation(req: SimulationStartRequest, request: Request):
    try:
        device = get_device(req.device_name, request)
        device.setAllPointSimulateMethod(req.simulate_method)
        device.startSimulation()
        return BaseResponse(message="启动模拟程序成功!", data=True)
    except Exception as e:
        log.error(f"启动模拟程序失败: {e}")
        return BaseResponse(code=500, message=f"启动模拟程序失败: {e}!", data=False)

@device_router.post("/stop_simulation", response_model=BaseResponse)
async def stop_simulation(req: SimulationStopRequest, request: Request):
    try:
        device = get_device(req.device_name, request)
        device.stopSimulation()
        return BaseResponse(message="停止模拟程序成功!", data=True)
    except Exception as e:
        log.error(f"停止模拟程序失败: {e}")
        return BaseResponse(code=500, message=f"停止模拟程序失败: {e}!", data=False)


@device_router.get("/current_table/", response_model=BaseResponse)
async def get_current_table(req: CurrentTableRequest = Depends(), request: Request = None):
    try:
        device = get_device(req.device_name, request)
        data_list, hex_data_list, real_data_list, max_limit_list, min_limit_list = (
            device.getSlaveValueList(req.slave_id, req.point_name)
        )
        data_dict = {
            "data_list": data_list,
            "hex_data_list": hex_data_list,
            "real_data_list": real_data_list,
            "max_limit_list": max_limit_list,
            "min_limit_list": min_limit_list,
        }
        return BaseResponse(
            message="获取当前表数据成功!",
            data=data_dict,
        )
    except Exception as e:
        log.error(f"获取当前表数据失败: {e}")
        return BaseResponse(
            code=500,
            message="获取当前表数据失败!",
            data={},
        )


# 修改测点数据接口
@device_router.post("/edit_point_data/", response_model=BaseResponse)
async def edit_point_data(req: PointEditDataRequest, request: Request):
    try:
        device = get_device(req.device_name, request)
        success = await device.edit_point_data_async(req.point_code, req.point_value)
        return BaseResponse(
            message="编辑测点数据成功!" if success else "编辑测点数据失败!",
            data=success
        )
    except Exception as e:
        log.error(f"编辑测点数据失败: {e}")
        return BaseResponse(code=500, message=f"编辑测点数据失败: {e}!", data=False)


# 修改测点限制值接口
@device_router.post("/edit_point_limit/", response_model=BaseResponse)
async def edit_point_limit(req: PointLimitEditRequest, request: Request):
    try:
        device = get_device(req.device_name, request)
        success = device.edit_point_limit(req.point_code, req.min_value_limit, req.max_value_limit)
        return BaseResponse(
            message="编辑测点限制值数据成功!" if success else "编辑测点限制值数据失败!",
            data=success
        )
    except Exception as e:
        log.error(f"编辑测点限制值数据失败: {e}")
        return BaseResponse(code=500, message=f"编辑测点限制值数据失败: {e}!", data=False)


# 获取测点限制值接口
@device_router.post("/get_point_limit/", response_model=BaseResponse)
async def get_point_limit(req: PointLimitGetRequest, request: Request):
    try:
        device = get_device(req.device_name, request)
        point = device.get_point_data([req.point_code])
        min_value_limit = 0
        max_value_limit = 1
        if isinstance(point, Yc):
            max_value_limit = point.max_value_limit
            min_value_limit = point.min_value_limit
        return BaseResponse(
            message="获取测点限制值数据成功!",
            data={
                "min_value_limit": min_value_limit,
                "max_value_limit": max_value_limit,
            }
        )
    except Exception as e:
        log.error(f"获取测点限制值数据失败: {e}")
        return BaseResponse(code=500, message="获取测点限制值数据失败!", data=False)


# 一键重置测点数据
@device_router.post("/reset_point_data/", response_model=BaseResponse)
async def reset_point_data(req: DeviceResetRequest, request: Request):
    try:
        device = get_device(req.device_name, request)
        device.resetPointValues()
        return BaseResponse(message="重置测点数据成功!", data=True)
    except Exception as e:
        log.error(f"重置测点数据失败: {e}")
        return BaseResponse(code=500, message="重置测点数据失败!", data=False)

# 设置单个点的模拟方法
@device_router.post("/set_single_point_simulate_method", response_model=BaseResponse)
async def set_single_point_simulate_method(req: SimulateMethodSetRequest, request: Request):
    try:
        device = get_device(req.device_name, request)
        success = device.setSinglePointSimulateMethod(req.point_code, req.simulate_method)
        return BaseResponse(
            message="设置单点模拟方法成功!" if success else "设置单点模拟方法失败!",
            data=success
        )
    except Exception as e:
        log.error(f"设置单点模拟方法失败: {e}")
        return BaseResponse(code=500, message=f"设置单点模拟方法失败: {e}!", data=False)


# 设置单个点的模拟步长
@device_router.post("/set_single_point_step", response_model=BaseResponse)
async def set_single_point_step(req: SimulateStepSetRequest, request: Request):
    try:
        device = get_device(req.device_name, request)
        success = device.setSinglePointStep(req.point_code, req.step)
        return BaseResponse(
            message="设置单点模拟步长成功!" if success else "设置单点模拟步长失败!",
            data=success
        )
    except Exception as e:
        log.error(f"设置单点模拟步长失败: {e}")
        return BaseResponse(code=500, message=f"设置单点模拟步长失败: {e}!", data=False)


# 获取点信息
@device_router.post("/get_point_info", response_model=BaseResponse)
async def get_point_info(req: PointInfoRequest, request: Request):
    try:
        device = get_device(req.device_name, request)
        point_info = device.getPointInfo(req.point_code)
        if point_info:
            return BaseResponse(message="获取点信息成功!", data=point_info)
        else:
            return BaseResponse(code=400, message="获取点信息失败!", data=None)
    except Exception as e:
        log.error(f"获取点信息失败: {e}")
        return BaseResponse(code=500, message=f"获取点信息失败: {e}!", data=None)


# 设置点的模拟范围
@device_router.post("/set_point_simulation_range", response_model=BaseResponse)
async def set_point_simulation_range(req: SimulateRangeSetRequest, request: Request):
    try:
        device = get_device(req.device_name, request)
        success = device.setPointSimulationRange(req.point_code, req.min_value, req.max_value)
        return BaseResponse(
            message="设置点模拟范围成功!" if success else "设置点模拟范围失败!",
            data=success
        )
    except Exception as e:
        log.error(f"设置点模拟范围失败: {e}")
        return BaseResponse(code=500, message=f"设置点模拟范围失败: {e}!", data=False)


# 启动设备接口
@device_router.post("/start", response_model=BaseResponse)
async def start_device(req: DeviceStartRequest, request: Request):
    try:
        device = get_device(req.device_name, request)
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


# 修改测点元数据接口
@device_router.post("/edit_point_metadata/", response_model=BaseResponse)
async def edit_point_metadata(req: PointMetadataEditRequest, request: Request):
    try:
        device = get_device(req.device_name, request)
        success = device.edit_point_metadata(req.point_code, req.metadata)
        return BaseResponse(
            message="编辑测点属性成功!" if success else "编辑测点属性失败!",
            data=success
        )
    except Exception as e:
        log.error(f"编辑测点属性失败: {e}")
        return BaseResponse(code=500, message=f"编辑测点属性失败: {e}!", data=False)


# 停止设备接口
@device_router.post("/stop", response_model=BaseResponse)
async def stop_device(req: DeviceStopRequest, request: Request):
    try:
        device = get_device(req.device_name, request)
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


# ===== 自动读取控制接口 =====

# 获取自动读取状态
@device_router.post("/get_auto_read_status", response_model=BaseResponse)
async def get_auto_read_status(req: DeviceInfoRequest, request: Request):
    try:
        device = get_device(req.device_name, request)
        is_running = device.is_auto_read_running()
        return BaseResponse(message="获取自动读取状态成功!", data=is_running)
    except KeyError:
        return BaseResponse(code=404, message=f"设备 {req.device_name} 不存在!", data=False)
    except Exception as e:
        log.error(f"获取自动读取状态失败: {e}")
        return BaseResponse(code=500, message=f"获取自动读取状态失败: {e}!", data=False)


# 启动自动读取
@device_router.post("/start_auto_read", response_model=BaseResponse)
async def start_auto_read(req: DeviceInfoRequest, request: Request):
    try:
        device = get_device(req.device_name, request)
        success = device.start_auto_read()
        return BaseResponse(
            message="启动自动读取成功!" if success else "自动读取已在运行中!",
            data=success
        )
    except KeyError:
        return BaseResponse(code=404, message=f"设备 {req.device_name} 不存在!", data=False)
    except Exception as e:
        log.error(f"启动自动读取失败: {e}")
        return BaseResponse(code=500, message=f"启动自动读取失败: {e}!", data=False)


# 停止自动读取
@device_router.post("/stop_auto_read", response_model=BaseResponse)
async def stop_auto_read(req: DeviceInfoRequest, request: Request):
    try:
        device = get_device(req.device_name, request)
        device.stop_auto_read()
        return BaseResponse(message="停止自动读取成功!", data=True)
    except KeyError:
        return BaseResponse(code=404, message=f"设备 {req.device_name} 不存在!", data=False)
    except Exception as e:
        log.error(f"停止自动读取失败: {e}")
        return BaseResponse(code=500, message=f"停止自动读取失败: {e}!", data=False)


class ManualReadRequest(BaseModel):
    device_name: str
    interval: Optional[int] = 0

# 手动读取
@device_router.post("/manual_read", response_model=BaseResponse)
async def manual_read(req: ManualReadRequest, request: Request):
    try:
        device = get_device(req.device_name, request)
        
        # 定义发送进度的回调函数
        async def event_emitter(data):
            await manager.broadcast(data, req.device_name)
            
        # 异步执行读取
        stats = await device.single_read(event_emitter=event_emitter, interval_ms=req.interval)
        
        return BaseResponse(message="手动读取成功!", data=stats)
    except KeyError:
        return BaseResponse(code=404, message=f"设备 {req.device_name} 不存在!", data=False)
    except Exception as e:
        log.error(f"手动读取失败: {e}")
        return BaseResponse(code=500, message=f"手动读取失败: {e}!", data=False)


# 读取单个测点值
@device_router.post("/read_single_point", response_model=BaseResponse)
async def read_single_point(req: PointInfoRequest, request: Request):
    try:
        device = get_device(req.device_name, request)
        # 使用异步方法读取，避免阻塞事件循环
        value = await device.read_single_point_async(req.point_code)
        
        if value is not None:
            return BaseResponse(message="读取成功!", data={"value": value})
        else:
            return BaseResponse(code=400, message="读取失败，请检查连接状态", data=None)
    except KeyError:
        return BaseResponse(code=404, message=f"设备 {req.device_name} 不存在!", data=None)
    except Exception as e:
        log.error(f"读取测点失败: {e}")
        return BaseResponse(code=500, message=f"读取测点失败: {e}!", data=None)


# ===== 报文捕获接口 =====

# 获取设备报文历史
@device_router.post("/get_messages", response_model=BaseResponse)
async def get_messages(req: MessageListRequest, request: Request):
    try:
        device = get_device(req.device_name, request)
        messages = device.get_messages(limit=req.limit)
        return BaseResponse(
            message="获取报文历史成功!",
            data={"messages": messages, "count": len(messages)}
        )
    except KeyError:
        return BaseResponse(code=404, message=f"设备 {req.device_name} 不存在!", data=None)
    except Exception as e:
        log.error(f"获取报文历史失败: {e}")
        return BaseResponse(code=500, message=f"获取报文历史失败: {e}!", data=None)


# 清空设备报文历史
@device_router.post("/clear_messages", response_model=BaseResponse)
async def clear_messages(req: DeviceInfoRequest, request: Request):
    try:
        device = get_device(req.device_name, request)
        device.clear_messages()
        return BaseResponse(message="清空报文历史成功!", data=True)
    except KeyError:
        return BaseResponse(code=404, message=f"设备 {req.device_name} 不存在!", data=False)
    except Exception as e:
        log.error(f"清空报文历史失败: {e}")
        return BaseResponse(code=500, message=f"清空报文历史失败: {e}!", data=False)


# 获取报文平均收发时间
@device_router.post("/get_avg_time", response_model=BaseResponse)
async def get_avg_time(req: DeviceInfoRequest, request: Request):
    try:
        device = get_device(req.device_name, request)
        stats = device.get_avg_time()
        return BaseResponse(message="获取平均收发时间成功!", data=stats)
    except KeyError:
        return BaseResponse(code=404, message=f"设备 {req.device_name} 不存在!", data=None)
    except Exception as e:
        log.error(f"获取平均收发时间失败: {e}")
        return BaseResponse(code=500, message=f"获取平均收发时间失败: {e}!", data=None)


# ===== 动态测点/从机管理接口 =====

# 添加测点
@device_router.post("/add_point", response_model=BaseResponse)
async def add_point(req: PointCreateRequest, request: Request):
    try:
        device = get_device(req.device_name, request)
        # 获取设备的 channel_id
        channel = ChannelDao.get_channel_by_code(req.device_name)
        if not channel:
            # 尝试通过设备名称查找
            channels = ChannelDao.get_all_channels()
            channel = next((c for c in channels if c["name"] == req.device_name), None)
        
        if not channel:
            return BaseResponse(code=404, message=f"找不到设备 {req.device_name} 的通道信息!", data=False)
        
        channel_id = channel["id"]
        point_data = {
            "code": req.code,
            "name": req.name,
            "rtu_addr": req.rtu_addr,
            "reg_addr": req.reg_addr,
            "func_code": req.func_code,
            "decode_code": req.decode_code,
            "mul_coe": req.mul_coe,
            "add_coe": req.add_coe,
        }
        success = device.add_point_dynamic(channel_id, req.frame_type, point_data)
        if success:
            return BaseResponse(message="添加测点成功!", data=True)
        else:
            return BaseResponse(code=500, message="添加测点失败!", data=False)
    except KeyError:
        return BaseResponse(code=404, message=f"设备 {req.device_name} 不存在!", data=False)
    except Exception as e:
        log.error(f"添加测点失败: {e}")
        return BaseResponse(code=500, message=f"添加测点失败: {e}!", data=False)


# 批量添加测点
@device_router.post("/add_points_batch", response_model=BaseResponse)
async def add_points_batch(req: PointsBatchCreateRequest, request: Request):
    try:
        device = get_device(req.device_name, request)
        # 获取设备的 channel_id
        channel = ChannelDao.get_channel_by_code(req.device_name)
        if not channel:
            # 尝试通过设备名称查找
            channels = ChannelDao.get_all_channels()
            channel = next((c for c in channels if c["name"] == req.device_name), None)
        
        if not channel:
            return BaseResponse(code=404, message=f"找不到设备 {req.device_name} 的通道信息!", data=False)
        
        channel_id = channel["id"]
        points_data = [point.dict() for point in req.points]
            
        success = device.add_points_dynamic_batch(channel_id, req.frame_type, points_data)
        if success:
            return BaseResponse(message="批量添加测点成功!", data=True)
        else:
            return BaseResponse(code=500, message="批量添加测点失败!", data=False)
    except KeyError:
        return BaseResponse(code=404, message=f"设备 {req.device_name} 不存在!", data=False)
    except Exception as e:
        log.error(f"批量添加测点失败: {e}")
        return BaseResponse(code=500, message=f"批量添加测点失败: {e}!", data=False)


# 删除测点
@device_router.post("/delete_point", response_model=BaseResponse)
async def delete_point(req: PointDeleteRequest, request: Request):
    try:
        device = get_device(req.device_name, request)
        success = device.delete_point_dynamic(req.point_code)
        if success:
            return BaseResponse(message="删除测点成功!", data=True)
        else:
            return BaseResponse(code=500, message="删除测点失败!", data=False)
    except KeyError:
        return BaseResponse(code=404, message=f"设备 {req.device_name} 不存在!", data=False)
    except Exception as e:
        log.error(f"删除测点失败: {e}")
        return BaseResponse(code=500, message=f"删除测点失败: {e}!", data=False)


# 添加从机
@device_router.post("/add_slave", response_model=BaseResponse)
async def add_slave(req: SlaveAddRequest, request: Request):
    try:
        device = get_device(req.device_name, request)
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


# 删除从机
@device_router.post("/delete_slave", response_model=BaseResponse)
async def delete_slave(req: SlaveDeleteRequest, request: Request):
    try:
        device = get_device(req.device_name, request)
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


# 编辑从机
@device_router.post("/edit_slave", response_model=BaseResponse)
async def edit_slave(req: SlaveEditRequest, request: Request):
    try:
        device = get_device(req.device_name, request)
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



# 清空从机测点
@device_router.post("/clear_points", response_model=BaseResponse)
async def clear_points(req: ClearPointsRequest, request: Request):
    try:
        device = get_device(req.device_name, request)
        deleted_count = device.clear_points_by_slave(req.slave_id)
        if deleted_count >= 0:
            log.info(f"清空成功，共删除 {deleted_count} 个测点!")
            return BaseResponse(message=f"清空成功，共删除 {deleted_count} 个测点!", data=deleted_count)
        else:
            return BaseResponse(code=500, message="清空测点失败!", data=0)
    except KeyError:
        return BaseResponse(code=404, message=f"设备 {req.device_name} 不存在!", data=0)
    except Exception as e:
        log.error(f"清空测点失败: {e}")
        return BaseResponse(code=500, message=f"清空测点失败: {e}!", data=0)
