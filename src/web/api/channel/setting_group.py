"""IEC 61850 setting-group REST API."""

import asyncio
from typing import Any

from fastapi import APIRouter, Request

from src.web.api.exceptions import NotFoundError, OperationError, ValidationError
from src.web.api.schemas import BaseResponse
from src.web.api.schemas.setting_group import (
    SettingGroupDetailRequest,
    SettingGroupListRequest,
    SettingGroupSelectRequest,
    SettingValuesWriteRequest,
)

router = APIRouter(tags=["channel"])


def _get_plugin(channel_id: int, request: Request) -> Any:
    device = request.app.state.device_controller.get_device_by_channel_id(channel_id)
    if not device:
        raise NotFoundError("通道或设备不存在")
    handler = getattr(device, "protocol_handler", None)
    from src.device.protocol.iec61850_handler import IEC61850ClientHandler, IEC61850ServerHandler

    protocol = None
    if isinstance(handler, IEC61850ClientHandler):
        protocol = getattr(handler, "_client", None)
    elif isinstance(handler, IEC61850ServerHandler):
        protocol = getattr(handler, "_server", None)
    else:
        raise ValidationError("该设备不是 IEC 61850 客户端或服务端设备")
    plugin = getattr(protocol, "setting_groups", None) if protocol else None
    if not plugin:
        raise ValidationError("SettingGroups 插件不可用")
    return plugin


@router.post("/iec61850/setting-groups/list", response_model=BaseResponse)
async def list_setting_groups(body: SettingGroupListRequest, request: Request):
    plugin = _get_plugin(body.channel_id, request)
    items = await asyncio.to_thread(plugin.discover)
    return BaseResponse(message="获取定值组控制块成功", data={"items": items, "total": len(items)})


@router.post("/iec61850/setting-groups/detail", response_model=BaseResponse)
async def get_setting_group_detail(body: SettingGroupDetailRequest, request: Request):
    plugin = _get_plugin(body.channel_id, request)
    detail, settings = await asyncio.gather(
        asyncio.to_thread(plugin.get_detail, body.sgcb_ref),
        asyncio.to_thread(plugin.list_settings, body.sgcb_ref),
    )
    detail["settings"] = settings
    return BaseResponse(message="读取定值组成功", data=detail)


@router.post("/iec61850/setting-groups/select-edit", response_model=BaseResponse)
async def select_edit_group(body: SettingGroupSelectRequest, request: Request):
    plugin = _get_plugin(body.channel_id, request)
    if not await asyncio.to_thread(plugin.select_edit_group, body.sgcb_ref, body.group):
        raise OperationError("选择编辑定值组失败", data={"success": False})
    return BaseResponse(message="编辑定值组已选择", data={"success": True, "edit_sg": body.group})


@router.post("/iec61850/setting-groups/write", response_model=BaseResponse)
async def write_setting_values(body: SettingValuesWriteRequest, request: Request):
    plugin = _get_plugin(body.channel_id, request)
    results = await asyncio.to_thread(
        plugin.write_values,
        [item.model_dump() for item in body.values],
        body.sgcb_ref,
    )
    failed = [item for item in results if not item["success"]]
    if failed:
        raise OperationError("部分定值写入失败", data={"success": False, "results": results})
    return BaseResponse(message="定值写入成功", data={"success": True, "results": results})


@router.post("/iec61850/setting-groups/confirm", response_model=BaseResponse)
async def confirm_setting_group(body: SettingGroupDetailRequest, request: Request):
    plugin = _get_plugin(body.channel_id, request)
    if not await asyncio.to_thread(plugin.confirm_edit, body.sgcb_ref):
        raise OperationError("确认定值编辑失败", data={"success": False})
    return BaseResponse(message="定值编辑已确认", data={"success": True})


@router.post("/iec61850/setting-groups/activate", response_model=BaseResponse)
async def activate_setting_group(body: SettingGroupSelectRequest, request: Request):
    plugin = _get_plugin(body.channel_id, request)
    if not await asyncio.to_thread(plugin.activate, body.sgcb_ref, body.group):
        raise OperationError("激活定值组失败", data={"success": False})
    return BaseResponse(message="定值组已激活", data={"success": True, "act_sg": body.group})
