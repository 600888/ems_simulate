"""IEC 61850 Log Control Block and journal REST API."""

import asyncio
from typing import Any

from fastapi import APIRouter, Request

from src.web.api.exceptions import NotFoundError, OperationError, ValidationError
from src.web.api.schemas import BaseResponse
from src.web.api.schemas.iec61850_log import (
    Iec61850LogEnableRequest,
    Iec61850LogListRequest,
    Iec61850LogQueryRequest,
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
    plugin = getattr(protocol, "logs", None) if protocol else None
    if not plugin:
        raise ValidationError("Log 插件不可用")
    return plugin


@router.post("/iec61850/logs/controls", response_model=BaseResponse)
async def list_log_controls(body: Iec61850LogListRequest, request: Request):
    plugin = _get_plugin(body.channel_id, request)
    items = await asyncio.to_thread(plugin.discover)
    return BaseResponse(message="获取日志控制块成功", data={"items": items, "total": len(items)})


@router.post("/iec61850/logs/enable", response_model=BaseResponse)
async def set_log_control_enabled(body: Iec61850LogEnableRequest, request: Request):
    plugin = _get_plugin(body.channel_id, request)
    if not await asyncio.to_thread(plugin.set_enabled, body.lcb_ref, body.enabled):
        raise OperationError("更新日志控制块失败", data={"success": False})
    return BaseResponse(message="日志控制块已更新", data={"success": True, "enabled": body.enabled})


@router.post("/iec61850/logs/query", response_model=BaseResponse)
async def query_iec61850_logs(body: Iec61850LogQueryRequest, request: Request):
    if body.end_time_ms < body.start_time_ms:
        raise ValidationError("结束时间不能早于开始时间")
    plugin = _get_plugin(body.channel_id, request)
    entries, more_follows = await asyncio.to_thread(
        plugin.query,
        body.log_ref,
        body.start_time_ms,
        body.end_time_ms,
    )
    keyword = body.keyword.strip().lower()
    level = body.level.strip().lower()
    service = body.service.strip().lower()
    if keyword:
        entries = [
            item
            for item in entries
            if keyword
            in " ".join(str(item.get(key, "")) for key in ("entry_id", "object_ref", "message", "source")).lower()
        ]
    if level:
        entries = [item for item in entries if str(item.get("level", "")).lower() == level]
    if service:
        entries = [item for item in entries if str(item.get("service", "")).lower() == service]
    total = len(entries)
    start = (body.page - 1) * body.page_size
    page_entries = entries[start : start + body.page_size]
    return BaseResponse(
        message="查询 IEC 61850 日志成功",
        data={
            "entries": page_entries,
            "total": total,
            "page": body.page,
            "page_size": body.page_size,
            "more_follows": more_follows,
        },
    )
