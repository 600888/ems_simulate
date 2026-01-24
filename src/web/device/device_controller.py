from fastapi import APIRouter, Request, File, UploadFile, Depends
from fastapi.responses import JSONResponse
from copy import deepcopy

from src.config.global_config import UPLOAD_PLAN_DIR
from src.device.core.device import Device
from src.enums.modbus_def import ProtocolType
from src.enums.point_data import Yc, SimulateMethod
from src.web.log import get_logger
from src.web.schemas import (
    DeviceNameListResponse, DeviceInfoRequest, DeviceInfoResponse,
    SlaveIdListRequest, SlaveIdListResponse, DeviceTableRequest,
    PointEditDataRequest, PointLimitEditRequest, PointMetadataEditRequest,
    PointInfoRequest, SimulationStartRequest, SimulationStopRequest,
    SimulateMethodSetRequest, SimulateStepSetRequest, SimulateRangeSetRequest,
    DeviceStartRequest, DeviceStopRequest, DeviceResetRequest,
    PointLimitGetRequest, CurrentTableRequest, BaseResponse
)

log = get_logger()

# 创建路由对象
device_router = APIRouter(prefix="/device", tags=["device"])

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
            "simulation_status": bool(device.isSimulationRunning()),
            # 串口配置
            "serial_port": getattr(device, 'serial_port', None),
            "baudrate": getattr(device, 'baudrate', 9600),
            "databits": getattr(device, 'databits', 8),
            "stopbits": getattr(device, 'stopbits', 1),
            "parity": getattr(device, 'parity', 'E'),
        }
        
        # 使用统一接口获取协议运行状态
        info_dict["server_status"] = device.is_protocol_running()

        return DeviceInfoResponse(message="获取设备信息成功!", data=info_dict)
    except Exception as e:
        log.error(f"获取设备信息失败: {e}")
        return DeviceInfoResponse(code=500, message=f"获取设备信息失败: {e}!", data={})


@device_router.post("/get_slave_id_list", response_model=SlaveIdListResponse)
async def get_slave_id_list(req: SlaveIdListRequest, request: Request):
    try:
        device = get_device(req.device_name, request)
        return SlaveIdListResponse(data=device.slave_id_list)
    except Exception as e:
        log.error(f"获取从机id列表失败: {e}")
        return SlaveIdListResponse(code=500, message=f"获取从机id列表失败: {e}!", data=[])


@device_router.post("/get_device_table", response_model=BaseResponse)
async def get_table_by_slave_id(req: DeviceTableRequest, request: Request):
    try:
        device = get_device(req.device_name, request)
        head_data = device.get_table_head()
        table_data, total = device.get_table_data(
            req.slave_id, req.point_name, req.page_index, req.pageSize, req.point_types
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
        success = device.editPointData(req.point_code, req.point_value)
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
        return BaseResponse(
            message="设备启动成功!" if success else "设备启动失败!",
            data=success
        )
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
        return BaseResponse(
            message="设备停止成功!" if success else "设备停止失败!",
            data=success
        )
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


# 手动读取
@device_router.post("/manual_read", response_model=BaseResponse)
async def manual_read(req: DeviceInfoRequest, request: Request):
    try:
        device = get_device(req.device_name, request)
        device.single_read()
        return BaseResponse(message="手动读取成功!", data=True)
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
        value = device.read_single_point(req.point_code)
        if value is not None:
            return BaseResponse(message="读取成功!", data={"value": value})
        else:
            return BaseResponse(code=400, message="读取失败，请检查连接状态", data=None)
    except KeyError:
        return BaseResponse(code=404, message=f"设备 {req.device_name} 不存在!", data=None)
    except Exception as e:
        log.error(f"读取测点失败: {e}")
        return BaseResponse(code=500, message=f"读取测点失败: {e}!", data=None)

