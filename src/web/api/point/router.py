"""测点管理 - 测点操作路由"""

from fastapi import APIRouter, Request

from src.data.dao.channel_dao import ChannelDao
from src.device.core.device import Device
from src.enums.modbus_def import ProtocolType
from src.enums.point_data import Yc, Yt
from src.web.api.schemas import (
    BaseResponse,
    ChangeTrackingConfigRequest,
    ClearPointsRequest,
    DeviceResetRequest,
    Iec104MetadataEditRequest,
    PointChangeHistoryRequest,
    PointCreateRequest,
    PointDeleteRequest,
    PointEditDataRequest,
    PointInfoRequest,
    PointLimitEditRequest,
    PointLimitGetRequest,
    PointMetadataEditRequest,
    PointsBatchCreateRequest,
    SimulateMethodSetRequest,
    SimulateRangeSetRequest,
    SimulateStepSetRequest,
)
from src.web.log import log

point_router = APIRouter(prefix="/api/points", tags=["测点管理"])


def _get_device(device_name: str, request: Request) -> Device:
    return request.app.state.device_controller.device_map[device_name]


@point_router.post("/edit-data", response_model=BaseResponse)
async def edit_point_data(req: PointEditDataRequest, request: Request):
    """修改测点数据"""
    try:
        device = _get_device(req.device_name, request)
        if device.protocol_type in (
            ProtocolType.ModbusRtu,
            ProtocolType.ModbusRtuClient,
            ProtocolType.ModbusRtuServer,
            ProtocolType.ModbusRtuOverTcp,
        ):
            client_info = device.serial_port or "未知串口"
        else:
            client_info = f"{device.ip}:{device.port}"
        from src.enums.points.change_tracker import change_client_info_ctx

        token = change_client_info_ctx.set(client_info)
        try:
            success = await device.edit_point_data_async(req.point_code, req.point_value, slave_id=req.slave_id)
        finally:
            change_client_info_ctx.reset(token)
        if success:
            return BaseResponse(message="编辑测点数据成功!", data=True)
        else:
            return BaseResponse(code=400, message="编辑测点数据失败!", data=False)
    except Exception as e:
        log.error(f"编辑测点数据失败: {e}")
        return BaseResponse(code=500, message=f"编辑测点数据失败: {e}!", data=False)


@point_router.post("/edit-limit", response_model=BaseResponse)
async def edit_point_limit(req: PointLimitEditRequest, request: Request):
    """修改测点限制值"""
    try:
        device = _get_device(req.device_name, request)
        success = device.edit_point_limit(req.point_code, req.min_value_limit, req.max_value_limit)
        if success:
            return BaseResponse(message="编辑测点限制值数据成功!", data=True)
        else:
            return BaseResponse(code=400, message="编辑测点限制值数据失败!", data=False)
    except Exception as e:
        log.error(f"编辑测点限制值数据失败: {e}")
        return BaseResponse(code=500, message=f"编辑测点限制值数据失败: {e}!", data=False)


@point_router.post("/get-limit", response_model=BaseResponse)
async def get_point_limit(req: PointLimitGetRequest, request: Request):
    """获取测点限制值"""
    try:
        device = _get_device(req.device_name, request)
        point = device.get_point_data([req.point_code])
        min_value_limit = 0
        max_value_limit = 1
        if isinstance(point, (Yc, Yt)):
            max_value_limit = point.max_value_limit
            min_value_limit = point.min_value_limit
        return BaseResponse(
            message="获取测点限制值数据成功!",
            data={"min_value_limit": min_value_limit, "max_value_limit": max_value_limit},
        )
    except Exception as e:
        log.error(f"获取测点限制值数据失败: {e}")
        return BaseResponse(code=500, message="获取测点限制值数据失败!", data=False)


@point_router.post("/set-simulate-method", response_model=BaseResponse)
async def set_single_point_simulate_method(req: SimulateMethodSetRequest, request: Request):
    """设置单个点的模拟方法"""
    try:
        device = _get_device(req.device_name, request)
        success = device.setSinglePointSimulateMethod(req.point_code, req.simulate_method)
        if success:
            return BaseResponse(message="设置单点模拟方法成功!", data=True)
        else:
            return BaseResponse(code=400, message="设置单点模拟方法失败!", data=False)
    except Exception as e:
        log.error(f"设置单点模拟方法失败: {e}")
        return BaseResponse(code=500, message=f"设置单点模拟方法失败: {e}!", data=False)


@point_router.post("/set-simulate-step", response_model=BaseResponse)
async def set_single_point_step(req: SimulateStepSetRequest, request: Request):
    """设置单个点的模拟步长"""
    try:
        device = _get_device(req.device_name, request)
        success = device.setSinglePointStep(req.point_code, req.step)
        if success:
            return BaseResponse(message="设置单点模拟步长成功!", data=True)
        else:
            return BaseResponse(code=400, message="设置单点模拟步长失败!", data=False)
    except Exception as e:
        log.error(f"设置单点模拟步长失败: {e}")
        return BaseResponse(code=500, message=f"设置单点模拟步长失败: {e}!", data=False)


@point_router.post("/info", response_model=BaseResponse)
async def get_point_info(req: PointInfoRequest, request: Request):
    """获取点信息"""
    try:
        device = _get_device(req.device_name, request)
        point_info = device.getPointInfo(req.point_code)
        if point_info:
            return BaseResponse(message="获取点信息成功!", data=point_info)
        else:
            return BaseResponse(code=400, message="获取点信息失败!", data=None)
    except Exception as e:
        log.error(f"获取点信息失败: {e}")
        return BaseResponse(code=500, message=f"获取点信息失败: {e}!", data=None)


@point_router.post("/set-simulation-range", response_model=BaseResponse)
async def set_point_simulation_range(req: SimulateRangeSetRequest, request: Request):
    """设置点的模拟范围"""
    try:
        device = _get_device(req.device_name, request)
        success = device.setPointSimulationRange(req.point_code, req.min_value, req.max_value)
        if success:
            return BaseResponse(message="设置点模拟范围成功!", data=True)
        else:
            return BaseResponse(code=400, message="设置点模拟范围失败!", data=False)
    except Exception as e:
        log.error(f"设置点模拟范围失败: {e}")
        return BaseResponse(code=500, message=f"设置点模拟范围失败: {e}!", data=False)


@point_router.post("/edit-metadata", response_model=BaseResponse)
async def edit_point_metadata(req: PointMetadataEditRequest, request: Request):
    """修改测点元数据"""
    try:
        device = _get_device(req.device_name, request)
        success = device.edit_point_metadata(req.point_code, req.metadata)
        if success:
            return BaseResponse(message="编辑测点属性成功!", data=True)
        else:
            return BaseResponse(code=400, message="编辑测点属性失败!", data=False)
    except Exception as e:
        log.error(f"编辑测点属性失败: {e}")
        return BaseResponse(code=500, message=f"编辑测点属性失败: {e}!", data=False)


@point_router.post("/edit-iec104-metadata", response_model=BaseResponse)
async def edit_iec104_metadata(req: Iec104MetadataEditRequest, request: Request):
    """修改IEC104协议专属测点属性（ASDU类型、品质描述符）"""
    try:
        device = _get_device(req.device_name, request)
        metadata = {
            "iec_type_id": req.iec_type_id,
            "iec_quality": req.iec_quality,
        }
        success = device.edit_point_metadata(req.point_code, metadata)
        if success:
            return BaseResponse(message="编辑IEC104属性成功!", data=True)
        else:
            return BaseResponse(code=400, message="编辑IEC104属性失败!", data=False)
    except Exception as e:
        log.error(f"编辑IEC104属性失败: {e}")
        return BaseResponse(code=500, message=f"编辑IEC104属性失败: {e}!", data=False)


@point_router.post("/read-single", response_model=BaseResponse)
async def read_single_point(req: PointInfoRequest, request: Request):
    """读取单个测点值"""
    try:
        device = _get_device(req.device_name, request)
        value = await device.read_single_point_async(req.point_code, slave_id=req.slave_id)
        if value is not None:
            return BaseResponse(message="读取成功!", data={"value": value})
        else:
            return BaseResponse(code=400, message="读取失败，请检查连接状态", data=None)
    except KeyError:
        return BaseResponse(code=404, message=f"设备 {req.device_name} 不存在!", data=None)
    except Exception as e:
        log.error(f"读取测点失败: {e}")
        return BaseResponse(code=500, message=f"读取测点失败: {e}!", data=None)


@point_router.post("/add", response_model=BaseResponse)
async def add_point(req: PointCreateRequest, request: Request):
    """添加测点"""
    try:
        device = _get_device(req.device_name, request)
        channel = ChannelDao.get_channel_by_code(req.device_name)
        if not channel:
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
            "bit": req.bit,
            "mul_coe": req.mul_coe,
            "add_coe": req.add_coe,
            "iec_type_id": req.iec_type_id,
            "iec_quality": req.iec_quality,
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


@point_router.post("/add-batch", response_model=BaseResponse)
async def add_points_batch(req: PointsBatchCreateRequest, request: Request):
    """批量添加测点"""
    try:
        device = _get_device(req.device_name, request)
        channel = ChannelDao.get_channel_by_code(req.device_name)
        if not channel:
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


@point_router.post("/delete", response_model=BaseResponse)
async def delete_point(req: PointDeleteRequest, request: Request):
    """删除测点"""
    try:
        device = _get_device(req.device_name, request)
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


@point_router.post("/clear-by-slave", response_model=BaseResponse)
async def clear_points(req: ClearPointsRequest, request: Request):
    """清空从机测点"""
    try:
        device = _get_device(req.device_name, request)
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


@point_router.post("/reset-data", response_model=BaseResponse)
async def reset_point_data(req: DeviceResetRequest, request: Request):
    """重置测点数据"""
    try:
        device = _get_device(req.device_name, request)
        device.resetPointValues()
        return BaseResponse(message="重置测点数据成功!", data=True)
    except KeyError:
        return BaseResponse(code=404, message=f"设备 {req.device_name} 不存在!", data=False)
    except Exception as e:
        log.error(f"重置测点数据失败: {e}")
        return BaseResponse(code=500, message=f"重置测点数据失败: {e}!", data=False)


# ===== 变更追溯 =====


@point_router.post("/change-history", response_model=BaseResponse)
async def get_point_change_history(req: PointChangeHistoryRequest, request: Request):
    """获取测点变更历史"""
    try:
        device = _get_device(req.device_name, request)
        point = device.point_manager.get_point_by_code(req.point_code, req.slave_id)
        if not point:
            return BaseResponse(code=404, message=f"测点 {req.point_code} 不存在!", data=[])

        history = [record.to_dict() for record in reversed(point.change_history)]
        return BaseResponse(
            message="获取变更历史成功!",
            data={
                "point_code": req.point_code,
                "tracking_enabled": point.change_tracking_enabled,
                "maxlen": getattr(point, "_change_history_maxlen", 50),
                "history": history,
                "count": len(history),
            },
        )
    except KeyError:
        return BaseResponse(code=404, message=f"设备 {req.device_name} 不存在!", data=[])
    except Exception as e:
        log.error(f"获取变更历史失败: {e}")
        return BaseResponse(code=500, message=f"获取变更历史失败: {e}!", data=[])


@point_router.post("/set-change-tracking", response_model=BaseResponse)
async def set_change_tracking(req: ChangeTrackingConfigRequest, request: Request):
    """设置测点的变更追溯开关和历史上限"""
    try:
        device = _get_device(req.device_name, request)

        points_to_update = []
        if req.point_code:
            point = device.point_manager.get_point_by_code(req.point_code, req.slave_id)
            if not point:
                return BaseResponse(code=404, message=f"测点 {req.point_code} 不存在!", data=False)
            points_to_update = [point]
        else:
            points_to_update = device.point_manager.get_all_points()

        for point in points_to_update:
            if req.enabled:
                point.enable_change_tracking()
            else:
                point.disable_change_tracking()
            if req.maxlen is not None:
                point.set_change_history_maxlen(req.maxlen)

        status = "启用" if req.enabled else "关闭"
        target = f"测点 {req.point_code}" if req.point_code else f"设备 {req.device_name} 的所有测点"
        msg = f"已{status}{target}的变更追溯"
        if req.maxlen is not None:
            msg += f"，历史上限设为 {min(max(1, req.maxlen), 100)} 条"
        return BaseResponse(message=msg, data=True)
    except KeyError:
        return BaseResponse(code=404, message=f"设备 {req.device_name} 不存在!", data=False)
    except Exception as e:
        log.error(f"设置变更追溯失败: {e}")
        return BaseResponse(code=500, message=f"设置变更追溯失败: {e}!", data=False)


@point_router.post("/clear-change-history", response_model=BaseResponse)
async def clear_point_change_history(req: PointChangeHistoryRequest, request: Request):
    """清空测点变更历史"""
    try:
        device = _get_device(req.device_name, request)
        point = device.point_manager.get_point_by_code(req.point_code, req.slave_id)
        if not point:
            return BaseResponse(code=404, message=f"测点 {req.point_code} 不存在!", data=False)

        point.clear_change_history()
        return BaseResponse(message="清空变更历史成功!", data=True)
    except KeyError:
        return BaseResponse(code=404, message=f"设备 {req.device_name} 不存在!", data=False)
    except Exception as e:
        log.error(f"清空变更历史失败: {e}")
        return BaseResponse(code=500, message=f"清空变更历史失败: {e}!", data=False)
