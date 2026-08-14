"""设备组管理路由"""

import asyncio

from fastapi import APIRouter, Request

from src.data.service.device_group_service import DeviceGroupService
from src.web.api.exceptions import NotFoundError, OperationError, ValidationError
from src.web.api.schemas import (
    BaseResponse,
    BatchDeviceOperationRequest,
    DeviceGroupCreateRequest,
    DeviceGroupDeleteRequest,
    DeviceGroupIdRequest,
    DeviceGroupStatusRequest,
    DeviceGroupUpdateRequest,
    DevicesToGroupRequest,
    DeviceToGroupRequest,
    RemoveDeviceRequest,
)
from src.web.log import log

device_group_router = APIRouter(prefix="/api/device-groups", tags=["设备组管理"])


@device_group_router.post("/tree")
async def get_device_group_tree():
    """获取设备组树形结构（包含未分组设备）"""
    tree = await asyncio.to_thread(DeviceGroupService.get_group_tree)
    return BaseResponse(data=tree)


@device_group_router.post("/list")
async def get_all_groups():
    """获取所有设备组（扁平列表）"""
    groups = await asyncio.to_thread(DeviceGroupService.get_all_groups)
    return BaseResponse(data=groups)


@device_group_router.post("/root")
async def get_root_groups():
    """获取顶级设备组"""
    groups = await asyncio.to_thread(DeviceGroupService.get_root_groups)
    return BaseResponse(data=groups)


@device_group_router.post("/ungrouped")
async def get_ungrouped_devices():
    """获取未分组设备"""
    devices = await asyncio.to_thread(DeviceGroupService.get_ungrouped_devices)
    return BaseResponse(data=devices)


@device_group_router.post("/detail")
async def get_group_by_id(body: DeviceGroupIdRequest):
    """根据ID获取设备组详情"""
    group = await asyncio.to_thread(DeviceGroupService.get_group_by_id, body.group_id)
    if not group:
        raise NotFoundError("设备组不存在")
    return BaseResponse(data=group)


@device_group_router.post("/devices")
async def get_group_devices(body: DeviceGroupIdRequest):
    """获取设备组内的设备列表"""
    devices = await asyncio.to_thread(DeviceGroupService.get_devices_by_group, body.group_id)
    return BaseResponse(data=devices)


@device_group_router.post("/children")
async def get_children_groups(body: DeviceGroupIdRequest):
    """获取子设备组"""
    groups = await asyncio.to_thread(DeviceGroupService.get_children_groups, body.group_id)
    return BaseResponse(data=groups)


@device_group_router.post("/create")
async def create_group(request: DeviceGroupCreateRequest):
    """创建设备组"""
    existing = await asyncio.to_thread(DeviceGroupService.get_group_by_code, request.code)
    if existing:
        raise ValidationError(f"设备组编码 '{request.code}' 已存在")

    group_id = await asyncio.to_thread(
        DeviceGroupService.create_group,
        code=request.code,
        name=request.name,
        parent_id=request.parent_id,
        description=request.description,
    )
    if group_id <= 0:
        raise OperationError("创建设备组失败")
    return BaseResponse(data={"group_id": group_id}, message="设备组创建成功")


@device_group_router.post("/update")
async def update_group(body: DeviceGroupUpdateRequest):
    """更新设备组"""
    # exclude_unset 区分"未传"与"显式传 null"：parent_id 显式传 null 表示提升为顶层
    update_data = {k: v for k, v in body.model_dump(exclude_unset=True).items() if k != "group_id"}
    if not update_data:
        raise ValidationError("没有提供更新数据")

    success = await asyncio.to_thread(DeviceGroupService.update_group, body.group_id, **update_data)
    if not success:
        raise NotFoundError("设备组不存在")
    return BaseResponse(message="设备组更新成功")


@device_group_router.post("/delete")
async def delete_group(body: DeviceGroupDeleteRequest, request: Request):
    """删除设备组"""
    if body.cascade:
        device_controller = request.app.state.device_controller
        channel_ids = await asyncio.to_thread(
            DeviceGroupService.get_channel_ids_for_group_tree,
            body.group_id,
        )
        for channel_id in channel_ids:
            try:
                await device_controller.remove_device_by_id(channel_id)
            except Exception as e:
                log.warning(f"级联删除分组时停止设备失败: channel_id={channel_id}, error={e}")
    success = await asyncio.to_thread(
        DeviceGroupService.delete_group,
        body.group_id,
        body.cascade,
    )
    if not success:
        raise NotFoundError("设备组不存在")
    return BaseResponse(message="设备组删除成功")


@device_group_router.post("/add-device")
async def add_device_to_group(request: DeviceToGroupRequest):
    """将设备添加到设备组"""
    success = await asyncio.to_thread(
        DeviceGroupService.add_device_to_group,
        device_id=request.device_id,
        group_id=request.group_id,
    )
    if not success:
        raise NotFoundError("设备不存在")
    return BaseResponse(message="设备已添加到设备组")


@device_group_router.post("/remove-device")
async def remove_device_from_group(body: RemoveDeviceRequest):
    """将设备从设备组移除"""
    success = await asyncio.to_thread(DeviceGroupService.remove_device_from_group, body.device_id)
    if not success:
        raise NotFoundError("设备不存在")
    return BaseResponse(message="设备已从设备组移除")


@device_group_router.post("/move-devices")
async def move_devices_to_group(request: DevicesToGroupRequest):
    """批量移动设备到指定设备组"""
    count = await asyncio.to_thread(
        DeviceGroupService.move_devices_to_group,
        device_ids=request.device_ids,
        group_id=request.group_id,
    )
    return BaseResponse(data={"moved_count": count}, message=f"成功移动 {count} 个设备")


@device_group_router.post("/batch-operation")
async def batch_device_operation(body: BatchDeviceOperationRequest, req: Request):
    """批量操作设备组内的设备"""
    device_controller = req.app.state.device_controller

    if body.group_id == 0:
        devices = await asyncio.to_thread(DeviceGroupService.get_ungrouped_devices)
    else:
        devices = await asyncio.to_thread(DeviceGroupService.get_devices_by_group, body.group_id)

    if not devices:
        raise NotFoundError("设备组内没有设备")

    success_count = 0
    fail_count = 0

    for device_dict in devices:
        device_name = device_dict.get("name")
        device = device_controller.device_map.get(device_name)

        if not device:
            fail_count += 1
            continue

        try:
            result = False
            if body.operation == "start":
                result = await device.start()
            elif body.operation == "stop":
                result = await device.stop()
            elif body.operation == "reset":
                await asyncio.to_thread(device.resetPointValues)
                result = True

            if result:
                success_count += 1
            else:
                log.error(f"操作设备 {device_name} 失败: {body.operation} 返回 False")
                fail_count += 1
        except Exception as e:
            log.error(f"操作设备 {device_name} 失败: {e}")
            fail_count += 1

    return BaseResponse(
        data={"success_count": success_count, "fail_count": fail_count},
        message=f"操作完成: 成功 {success_count} 个, 失败 {fail_count} 个",
    )


@device_group_router.post("/update-status")
async def update_group_status(body: DeviceGroupStatusRequest):
    """更新设备组状态"""
    success = await asyncio.to_thread(
        DeviceGroupService.update_group_status,
        body.group_id,
        body.status,
    )
    if not success:
        raise NotFoundError("设备组不存在")
    return BaseResponse(message="设备组状态更新成功")
