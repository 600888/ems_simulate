import os
from copy import deepcopy

from fastapi import APIRouter, Request, File, UploadFile
from fastapi.responses import JSONResponse

from src.config.global_config import UPLOAD_PLAN_DIR
from src.device.device import Device
from src.enums.modbus_def import ProtocolType
from src.enums.point_data import Yc
from src.web.log import get_logger

log = get_logger()

# 创建路由对象
device_router = APIRouter(prefix="/device", tags=["device"])


@device_router.post("/get_device_list")
async def get_device_name_list(request: Request):
    try:
        device_name_list = []
        for device in request.app.state.device_controller.device_list:
            device_name_list.append(deepcopy(device.name))
        return JSONResponse(
            {
                "code": 200,
                "message": "获取设备名列表成功!",
                "data": device_name_list,
            }
        )
    except Exception as e:
        return JSONResponse(
            {
                "code": 500,
                "message": "获取设备名列表失败!",
                "data": [],
            }
        )


# 获取设备信息接口
@device_router.post("/get_device_info")
async def get_device_info(request: Request):
    try:
        data = await request.json()
        device_name = data["device_name"]
        info_dict = {}
        device: Device = request.app.state.device_controller.device_map[device_name]
        if device.protocol_type == ProtocolType.Iec104Client:
            info_dict["ip"] = device.ip
            info_dict["port"] = device.port
            info_dict["server_status"] = device.client.is_connected()
        elif device.protocol_type == ProtocolType.Dlt645Server:
            info_dict["ip"] = device.ip
            info_dict["port"] = device.port
            info_dict["server_status"] = device.server.server.is_running()
        elif device.protocol_type == ProtocolType.ModbusTcpClient:
            info_dict["ip"] = device.ip
            info_dict["port"] = device.port
            info_dict["server_status"] = device.client.is_connected()
        else:
            info_dict["ip"] = device.ip
            info_dict["port"] = device.port
            info_dict["server_status"] = device.server.isRunning()
        info_dict["type"] = device.protocol_type.value
        info_dict["simulation_status"] = True if device.isSimulationRunning() else False
        info_dict["plan_status"] = True if device.plan.isRunning() else False
        return JSONResponse(
            {
                "code": 200,
                "message": "获取设备信息成功!",
                "data": info_dict,
            }
        )
    except Exception as e:
        raise e


@device_router.post("/get_slave_id_list")
async def get_slave_id_list(request: Request):
    try:
        data = await request.json()
        device_name = data["device_name"]
        device = request.app.state.device_controller.device_map[device_name]
        slave_id_list = device.slave_id_list
        return JSONResponse(
            {
                "code": 200,
                "message": "获取从机id列表成功!",
                "data": slave_id_list,
            }
        )
    except Exception as e:
        return JSONResponse(
            {
                "code": 500,
                "message": "获取从机id列表失败!",
                "data": 0,
            }
        )


@device_router.post("/get_device_table")
async def get_table_by_slave_id(request: Request):
    try:
        data = await request.json()
        device_name = data["device_name"]
        slave_id = data["slave_id"]
        point_name = data["point_name"]
        page_index = data["page_index"]
        page_size = data["page_size"]
        point_types = data["point_types"]
        device = request.app.state.device_controller.device_map[device_name]
        head_data = device.get_table_head()
        table_data, total = device.get_table_data(
            slave_id, point_name, page_index, page_size, point_types
        )
        data_dict = {"total": total, "head_data": head_data, "table_data": table_data}
        return JSONResponse(
            {
                "code": 200,
                "message": "获取从机信息成功!",
                "data": data_dict,
            }
        )
    except Exception as e:
        log.error(e)
        return JSONResponse(
            {
                "code": 500,
                "message": "获取从机信息失败!",
                "data": {},
            }
        )


@device_router.post("/start_simulation")
async def start_simulation(request: Request):
    try:
        data = await request.json()
        device_name = data["device_name"]
        simulate_method = data["simulate_method"]
        device = request.app.state.device_controller.device_map[device_name]
        device.setAllPointSimulateMethod(simulate_method)
        device.startSimulation()
        return JSONResponse(
            {
                "code": 200,
                "message": "启动模拟程序成功!",
                "data": True,
            }
        )
    except Exception as e:
        log.error(e)
        return JSONResponse(
            {
                "code": 500,
                "message": "启动模拟程序失败!",
                "data": False,
            }
        )


@device_router.post("/start_plan")
async def start_plan(request: Request):
    try:
        data = await request.json()
        device_name = data["device_name"]
        plan_name = data["plan_name"]
        device = request.app.state.device_controller.device_map[device_name]
        device.plan.thread.clear()
        device.plan.current_plan_name = plan_name
        device.plan.start()
        return JSONResponse(
            {
                "code": 200,
                "message": "启动计划模拟成功!",
                "data": True,
            }
        )
    except KeyError as e:
        error_str = str(e)
        error_str = error_str.replace("'", "")
        return JSONResponse({"code": 404, "message": error_str, "data": {}})
    except Exception as e:
        return JSONResponse(
            {
                "code": 500,
                "message": f"启动计划模拟失败: {e}",
                "data": False,
            }
        )


@device_router.post("/stop_plan")
async def stop_plan(request: Request):
    try:
        data = await request.json()
        device_name = data["device_name"]
        device = request.app.state.device_controller.device_map[device_name]
        device.plan.thread.clear()
        device.plan.stop()
        return JSONResponse(
            {
                "code": 200,
                "message": "停止计划模拟成功!",
                "data": True,
            }
        )
    except Exception as e:
        return JSONResponse(
            {
                "code": 500,
                "message": "停止计划模拟失败!",
                "data": False,
            }
        )


@device_router.post("/stop_simulation")
async def stop_simulation(request: Request):
    try:
        data = await request.json()
        device_name = data["device_name"]
        device = request.app.state.device_controller.device_map[device_name]
        device.stopSimulation()
        return JSONResponse(
            {
                "code": 200,
                "message": "停止模拟程序成功!",
                "data": True,
            }
        )
    except Exception as e:
        log.error(e)
        return JSONResponse(
            {
                "code": 500,
                "message": "停止模拟程序失败!",
                "data": False,
            }
        )


@device_router.get("/current_table/")
async def get_current_table(request: Request):
    try:
        device_name = str(request.query_params.get("device_name"))
        slave_id = int(request.query_params.get("slave_id"))
        point_name = str(request.query_params.get("point_name"))
        device = request.app.state.device_controller.device_map[device_name]
        data_list, hex_data_list, real_data_list, max_limit_list, min_limit_list = (
            device.getSlaveValueList(slave_id, point_name)
        )
        data_dict = {
            "data_list": data_list,
            "hex_data_list": hex_data_list,
            "real_data_list": real_data_list,
            "max_limit_list": max_limit_list,
            "min_limit_list": min_limit_list,
        }
        return JSONResponse(
            {
                "code": 200,
                "message": "获取当前表数据成功!",
                "data": data_dict,
            }
        )
    except Exception as e:
        log.error(e)
        return JSONResponse(
            {
                "code": 500,
                "message": "获取当前表数据失败!",
                "data": {},
            }
        )


# 接收计划json文件
@device_router.post("/import_plan/")
async def get_plan_json(device_name: str, file: UploadFile = File(...)):
    try:
        if file:
            save_path = os.path.join(UPLOAD_PLAN_DIR, file.filename)
            log.debug(f"file.save(save_path) = {save_path}")
            with open(save_path, "wb") as buffer:
                buffer.write(await file.read())
            device = request.app.state.device_controller.device_map[device_name]
            device.plan.importPlanJson(
                file.filename, os.path.join(UPLOAD_PLAN_DIR, file.filename)
            )
            return JSONResponse(
                {
                    "code": 200,
                    "message": "获取计划json数据成功!",
                    "data": True,
                }
            )
        else:
            return JSONResponse(
                {
                    "code": 404,
                    "message": "获取计划json数据失败!",
                    "data": False,
                }
            )
    except Exception as e:
        log.error(e)
        return JSONResponse(
            {
                "code": 500,
                "message": "获取计划json数据失败!",
                "data": False,
            }
        )


# 获取计划列表
@device_router.get("/get_plan_list/")
async def get_plan_list(request: Request):
    try:
        device_name = str(request.query_params.get("device_name"))
        plan_name = str(request.query_params.get("plan_name"))
        point_name = str(request.query_params.get("point_name"))
        device = request.app.state.device_controller.device_map[device_name]
        head_data = device.plan.getTableHead()
        table_data = device.plan.getTableData(plan_name, point_name)
        data_dict = {"head_data": head_data, "table_data": table_data}
        return JSONResponse(
            {
                "code": 200,
                "message": "获取计划列表成功!",
                "data": data_dict,
            }
        )
    except KeyError as e:
        error_str = str(e)
        error_str = error_str.replace("'", "")
        return JSONResponse({"code": 404, "message": error_str, "data": {}})
    except Exception as e:
        log.error(e)
        return JSONResponse({"code": 500, "message": "获取计划列表失败!", "data": {}})


@device_router.get("/load_plan_list/")
async def load_plan_list(request: Request):
    try:
        device_name = str(request.query_params.get("device_name"))
        device = request.app.state.device_controller.device_map[device_name]
        device.plan.clearAllPlan()
        device.plan.importAllPlan()
        plan_list = list(device.plan.is_set_plan_dict.keys())
        return JSONResponse(
            {
                "code": 200,
                "message": "加载计划列表成功!",
                "data": plan_list,
            }
        )
    except Exception as e:
        log.error(e)
        return JSONResponse({"code": 500, "message": "加载计划列表失败!", "data": {}})


# 修改测点数据接口
@device_router.post("/edit_point_data/")
async def edit_point_data(request: Request):
    try:
        data = await request.json()
        device_name = data["device_name"]
        point_code = data["point_code"]
        point_value = data["point_value"]
        device: Device = request.app.state.device_controller.device_map[device_name]
        if device.editPointData(point_code, point_value):
            return JSONResponse(
                {"code": 200, "message": "编辑测点数据成功!", "data": True}
            )
        else:
            return JSONResponse(
                {"code": 400, "message": "编辑测点数据失败!", "data": False}
            )
    except Exception as e:
        log.error(e)
        return JSONResponse(
            {"code": 500, "message": f"编辑测点数据失败: {e}!", "data": False}
        )


# 修改测点数据接口
@device_router.post("/edit_point_limit/")
async def edit_point_limit(request: Request):
    try:
        data = await request.json()
        device_name = data["device_name"]
        point_code = data["point_code"]
        max_value_limit = data["max_value_limit"]
        min_value_limit = data["min_value_limit"]
        device: Device = request.app.state.device_controller.device_map[device_name]
        if device.edit_point_limit(point_code, min_value_limit, max_value_limit):
            return JSONResponse(
                {"code": 200, "message": "编辑测点限制值数据成功!", "data": True}
            )
        else:
            return JSONResponse(
                {"code": 400, "message": "编辑测点限制值数据失败!", "data": False}
            )
    except Exception as e:
        log.error(e)
        return JSONResponse(
            {"code": 500, "message": f"编辑测点限制值数据失败: {e}!", "data": False}
        )


# 修改测点数据接口
@device_router.post("/get_point_limit/")
async def get_point_limit(request: Request):
    try:
        data = await request.json()
        device_name = data["device_name"]
        point_code = data["point_code"]
        device: Device = request.app.state.device_controller.device_map[device_name]
        point = device.get_point_data([point_code])
        min_value_limit = 0
        max_value_limit = 1
        if isinstance(point, Yc):
            max_value_limit = point.max_value_limit
            min_value_limit = point.min_value_limit
        return JSONResponse(
            {
                "code": 200,
                "message": "获取测点限制值数据成功!",
                "data": {
                    "min_value_limit": min_value_limit,
                    "max_value_limit": max_value_limit,
                },
            }
        )
    except Exception as e:
        log.error(e)
        return JSONResponse(
            {"code": 500, "message": "获取测点限制值数据失败!", "data": False}
        )


# 一键重置测点数据
@device_router.post("/reset_point_data/")
async def reset_point_data(request: Request):
    try:
        data = await request.json()
        device_name = data["device_name"]
        device = request.app.state.device_controller.device_map[device_name]
        device.resetPointValues()
        return JSONResponse({"code": 200, "message": "重置测点数据成功!", "data": True})
    except Exception as e:
        log.error(e)
        return JSONResponse(
            {"code": 500, "message": "重置测点数据失败!", "data": False}
        )


# 保存模板
@device_router.post("/save_template/")
async def save_template(request: Request):
    try:
        data = await request.json()
        device_name = data["device_name"]
        template_name = data["template_name"]
        table_data = data["table_data"]
        device = request.app.state.device_controller.device_map.get(device_name)
        is_success = device.save_template(template_name, table_data)
        if is_success:
            return JSONResponse({"code": 200, "msg": "保存模板成功!", "data": True})
        else:
            return JSONResponse({"code": 404, "msg": "保存模板失败!", "data": False})
    except Exception as e:
        log.error(e)
        return JSONResponse({"code": 500, "msg": "保存模板失败", "data": False})


# 获取模板
@device_router.post("/get_template")
async def get_template(request: Request):
    try:
        data = await request.json()
        device_name = data["device_name"]
        device = request.app.state.device_controller.device_map.get(device_name)
        template_list = device.get_template_list()
        return JSONResponse(
            {"code": 200, "msg": "获取模板成功!", "data": template_list}
        )
    except Exception as e:
        log.error(e)
        return JSONResponse({"code": 500, "msg": "获取模板失败!", "data": []})


# 删除模板
@device_router.post("/delete_template")
async def delete_template(request: Request):
    try:
        data = await request.json()
        device_name = data["device_name"]
        template_name = data["template_name"]
        device = request.app.state.device_controller.device_map.get(device_name)
        if is_success := device.delete_template(template_name):
            return JSONResponse({"code": 200, "msg": "删除模板成功!"})
        else:
            return JSONResponse({"code": 404, "msg": "删除模板失败!"})
    except Exception as e:
        log.error(e)
        return JSONResponse({"code": 500, "msg": "删除模板失败!"})


# 设置单个点的模拟方法
@device_router.post("/set_single_point_simulate_method")
async def set_single_point_simulate_method(request: Request):
    try:
        data = await request.json()
        device_name = data["device_name"]
        point_code = data["point_code"]
        simulate_method = data["simulate_method"]
        device: Device = request.app.state.device_controller.device_map[device_name]
        result = device.setSinglePointSimulateMethod(point_code, simulate_method)
        if result:
            return JSONResponse(
                {"code": 200, "message": "设置单点模拟方法成功!", "data": True}
            )
        else:
            return JSONResponse(
                {"code": 400, "message": "设置单点模拟方法失败!", "data": False}
            )
    except Exception as e:
        log.error(e)
        return JSONResponse(
            {"code": 500, "message": f"设置单点模拟方法失败: {e}!", "data": False}
        )


# 设置单个点的模拟步长
@device_router.post("/set_single_point_step")
async def set_single_point_step(request: Request):
    try:
        data = await request.json()
        device_name = data["device_name"]
        point_code = data["point_code"]
        step = data["step"]
        device: Device = request.app.state.device_controller.device_map[device_name]
        result = device.setSinglePointStep(point_code, step)
        if result:
            return JSONResponse(
                {"code": 200, "message": "设置单点模拟步长成功!", "data": True}
            )
        else:
            return JSONResponse(
                {"code": 400, "message": "设置单点模拟步长失败!", "data": False}
            )
    except Exception as e:
        log.error(e)
        return JSONResponse(
            {"code": 500, "message": f"设置单点模拟步长失败: {e}!", "data": False}
        )


# 获取点信息
@device_router.post("/get_point_info")
async def get_point_info(request: Request):
    try:
        data = await request.json()
        device_name = data["device_name"]
        point_code = data["point_code"]
        device: Device = request.app.state.device_controller.device_map[device_name]
        point_info = device.getPointInfo(point_code)
        if point_info:
            return JSONResponse(
                {"code": 200, "message": "获取点信息成功!", "data": point_info}
            )
        else:
            return JSONResponse(
                {"code": 400, "message": "获取点信息失败!", "data": None}
            )
    except Exception as e:
        log.error(e)
        return JSONResponse(
            {"code": 500, "message": f"获取点信息失败: {e}!", "data": None}
        )


# 设置点的模拟范围
@device_router.post("/set_point_simulation_range")
async def set_point_simulation_range(request: Request):
    try:
        data = await request.json()
        device_name = data["device_name"]
        point_code = data["point_code"]
        min_value = data["min_value"]
        max_value = data["max_value"]
        device: Device = request.app.state.device_controller.device_map[device_name]
        result = device.setPointSimulationRange(point_code, min_value, max_value)
        if result:
            return JSONResponse(
                {"code": 200, "message": "设置点模拟范围成功!", "data": True}
            )
        else:
            return JSONResponse(
                {"code": 400, "message": "设置点模拟范围失败!", "data": False}
            )
    except Exception as e:
        log.error(e)
        return JSONResponse(
            {"code": 500, "message": f"设置点模拟范围失败: {e}!", "data": False}
        )


# 启动设备接口
@device_router.post("/start")
async def start_device(request: Request):
    try:
        data = await request.json()
        device_name = data["device_name"]
        device: Device = request.app.state.device_controller.device_map[device_name]
        success = await device.start()
        return JSONResponse(
            {
                "code": 200,
                "message": "设备启动成功!" if success else "设备启动失败!",
                "data": success,
            }
        )
    except KeyError:
        return JSONResponse(
            {"code": 404, "message": f"设备 {device_name} 不存在!", "data": False}
        )
    except Exception as e:
        log.error(e)
        return JSONResponse(
            {"code": 500, "message": f"设备启动失败: {e}!", "data": False}
        )


# 停止设备接口
@device_router.post("/stop")
async def stop_device(request: Request):
    try:
        data = await request.json()
        device_name = data["device_name"]
        device: Device = request.app.state.device_controller.device_map[device_name]
        success = await device.stop()
        return JSONResponse(
            {
                "code": 200,
                "message": "设备停止成功!" if success else "设备停止失败!",
                "data": success,
            }
        )
    except KeyError:
        return JSONResponse(
            {"code": 404, "message": f"设备 {device_name} 不存在!", "data": False}
        )
    except Exception as e:
        log.error(e)
        return JSONResponse(
            {"code": 500, "message": f"设备停止失败: {e}!", "data": False}
        )
