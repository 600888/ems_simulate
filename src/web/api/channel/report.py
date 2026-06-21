"""通道管理 - IEC 61850 Reports 报告控制块路由

提供 RCB 发现、使能/禁用、GI 触发、数据查询等 RESTful API。
"""

import asyncio
from typing import Any

from fastapi import APIRouter, Request

from src.data.service.channel_service import ChannelService
from src.web.api.exceptions import NotFoundError, OperationError, ValidationError
from src.web.api.schemas import BaseResponse
from src.web.api.schemas.report import (
    RcbApplyConfigRequest,
    RcbDetailRequest,
    RcbGiRequest,
    RcbListRequest,
    ReportDataRequest,
)
from src.web.log import log

router = APIRouter(tags=["channel"])


def _get_reports_plugin(channel_id: int, request: Request) -> Any:
    """获取设备对应的 Reports 管理对象

    客户端模式: 返回 ReportsPlugin (支持 discover_rcbs/enable/disable/GI)
    服务端模式: 返回 ReportManager (支持 browse_rcbs, RCB 在本地注册)

    Raises:
        NotFoundError: 通道或设备不存在
        ValidationError: 协议不匹配或插件不可用
    """
    channel = ChannelService.get_channel_by_id(channel_id)
    if not channel:
        raise NotFoundError("通道不存在")

    protocol_type = channel.get("protocol_type", -1)
    if protocol_type != 4:
        raise ValidationError("该通道不是 IEC61850 协议")

    device_controller = request.app.state.device_controller
    device = device_controller.get_device_by_channel_id(channel_id)
    if not device:
        raise NotFoundError("设备未找到")

    protocol_handler = getattr(device, "protocol_handler", None)
    if not protocol_handler:
        raise ValidationError("协议处理器未初始化")

    from src.device.protocol.iec61850_handler import IEC61850ClientHandler, IEC61850ServerHandler

    if isinstance(protocol_handler, IEC61850ClientHandler):
        client = getattr(protocol_handler, "_client", None)
        if client and hasattr(client, "reports"):
            return client.reports
    elif isinstance(protocol_handler, IEC61850ServerHandler):
        server = getattr(protocol_handler, "_server", None)
        if server and hasattr(server, "reports"):
            return server.reports

    raise ValidationError("Reports 插件不可用")


def _server_rcbs_to_discovery_format(report_manager: Any) -> list:
    """将服务端 ReportManager 的 RCB 列表转为前端标准格式

    与 ReportsPlugin.discover_rcbs() 返回格式一致，
    便于前端统一渲染。
    """
    rcbs = []
    for rcb in report_manager.browse_rcbs():
        trg = rcb.get("trg_ops", {})
        opt = rcb.get("opt_fields", {})
        ld_inst = rcb.get("ld_inst", "")
        rcb_name = rcb.get("name", "")
        rcb_type = rcb.get("rcb_type", "BRCB")
        ln_name = rcb.get("ln_name", "LLN0")  # 取实际 LN 名，非硬编码

        # entry_id: 支持 bytes 和 hex 字符串两种格式
        entry_id_val = rcb.get("entry_id", None)
        if isinstance(entry_id_val, bytes):
            entry_id_val = entry_id_val.hex()
        elif entry_id_val and not isinstance(entry_id_val, str):
            entry_id_val = str(entry_id_val) if entry_id_val else None

        # time_of_entry: 后端已格式化为 "YYYY-MM-DD HH:mm:ss" 字符串
        time_of_entry_val = rcb.get("time_of_entry", "")

        # purge_buf: 仅 BRCB 有意义
        purge_buf_val = rcb.get("purge_buf", False) if rcb_type == "BRCB" else False

        rcbs.append(
            {
                "name": rcb_name,
                "ref": f"{ld_inst}/{ln_name}.{rcb_name}" if ld_inst else rcb_name,
                "rcb_type": rcb_type,
                "ld": ld_inst,
                "ln": ln_name,
                "rpt_id": rcb.get("rpt_id", ""),
                "rpt_ena": rcb.get("rpt_ena", False),
                "data_set_ref": rcb.get("data_set_ref", ""),
                "conf_rev": rcb.get("conf_rev", 1),
                "buf_time": rcb.get("buf_time", 0),
                "intg_period": rcb.get("intg_period", 0),
                "sq_num": rcb.get("sq_num", 0),
                "purge_buf": purge_buf_val,
                "entry_id": entry_id_val,
                "time_of_entry": time_of_entry_val,
                "owner": rcb.get("owner", ""),
                "resv": rcb.get("resv", False),
                "trg_ops": {
                    "dchg": trg.get("dchg", True),
                    "qchg": trg.get("qchg", False),
                    "dupd": trg.get("dupd", False),
                    "period": trg.get("period", False),
                    "gi": trg.get("gi", True),
                },
                "opt_fields": {
                    "seq_num": opt.get("seq_num", True),
                    "time_stamp": opt.get("time_stamp", True),
                    "data_set": opt.get("data_set", True),
                    "reason_code": opt.get("reason_code", True),
                    "data_ref": opt.get("data_ref", False),
                    "entry_id": opt.get("entry_id", True),
                    "config_ref": opt.get("config_ref", False),
                    "buf_ovfl": opt.get("buf_ovfl", False),
                },
                "active": False,
            }
        )
    return rcbs


def _is_server_mode(reports_obj: Any) -> bool:
    """判断 reports 对象是否为服务端模式 (ReportManager)"""
    return hasattr(reports_obj, "browse_rcbs") and not hasattr(reports_obj, "discover_rcbs")


def _get_client_handler(channel_id: int, request: Request) -> Any | None:
    """获取客户端协议处理器 (用于读取连接时缓存的 RCB)"""
    device_controller = request.app.state.device_controller
    device = device_controller.get_device_by_channel_id(channel_id)
    if not device:
        return None
    protocol_handler = getattr(device, "protocol_handler", None)
    from src.device.protocol.iec61850_handler import IEC61850ClientHandler

    if isinstance(protocol_handler, IEC61850ClientHandler):
        return protocol_handler
    return None


def _discover_rcbs(reports: Any, channel_id: int = 0, handler: Any = None) -> list:
    """统一获取 RCB 列表，兼容客户端和服务端模式

    客户端模式: 优先用连接时缓存的 RCB，缓存为空再现场 MMS 发现
    服务端模式: 直接从本地 ReportManager 获取
    """
    if _is_server_mode(reports):
        return _server_rcbs_to_discovery_format(reports)

    if handler is not None and hasattr(handler, "get_discovered_rcbs"):
        cached = handler.get_discovered_rcbs()
        if cached:
            return cached
    rcbs = reports.discover_rcbs()
    # 现场发现成功则回写缓存，供后续及侧边栏结构接口复用
    if rcbs and handler is not None and hasattr(handler, "set_discovered_rcbs"):
        handler.set_discovered_rcbs(rcbs)
    return rcbs


def _refresh_single_rcb(reports: Any, rcb_ref: str, channel_id: int, request: Request) -> dict[str, Any] | None:
    """读取单个 RCB 最新状态并更新缓存中对应记录

    用于使能/GI 等操作后局部刷新，避免全部重新发现。

    Returns:
        更新后的 RCB 字典，失败返回 None
    """
    try:
        if _is_server_mode(reports):
            # 服务端模式: 从本地 ReportManager 重新获取
            rcbs = _server_rcbs_to_discovery_format(reports)
            for rcb in rcbs:
                if rcb.get("ref") == rcb_ref or rcb.get("name") == rcb_ref.split(".")[-1]:
                    return rcb
            return None

        # 客户端模式: 重新读取单个 RCB 详情
        detail = reports.get_rcb_detail(rcb_ref=rcb_ref)
        if not detail:
            return None

        # 更新缓存中对应的那条记录
        handler = _get_client_handler(channel_id, request)
        if handler and hasattr(handler, "update_discovered_rcb"):
            handler.update_discovered_rcb(rcb_ref, detail)
        return detail
    except Exception as e:
        log.warning(f"刷新单个 RCB 状态失败: ref={rcb_ref}, {e}")
        return None


def _mark_rcb_disabled(channel_id: int, rcb_ref: str, request: Request) -> dict[str, Any] | None:
    """禁用报告后直接从缓存更新 rpt_ena=False

    不调用 get_rcb_detail 读取服务器状态，避免注销回调后紧接着读 RCB
    触发 C 层竞争崩溃。

    Returns:
        更新后的 RCB 字典，失败返回 None
    """
    handler = _get_client_handler(channel_id, request)
    if not handler or not hasattr(handler, "get_discovered_rcbs"):
        return None

    for rcb in handler.get_discovered_rcbs():
        if rcb.get("ref") == rcb_ref:
            rcb["rpt_ena"] = False
            if hasattr(handler, "update_discovered_rcb"):
                handler.update_discovered_rcb(rcb_ref, rcb)
            return rcb
    return None


@router.post("/iec61850/reports/list", response_model=BaseResponse)
async def list_rcbs(body: RcbListRequest, request: Request):
    """列出 IEC61850 设备的报告控制块 (RCB)"""
    reports = _get_reports_plugin(body.channel_id, request)
    rcbs = _discover_rcbs(reports, body.channel_id, _get_client_handler(body.channel_id, request))
    return BaseResponse(message="获取 RCB 列表成功", data={"rcbs": rcbs})


@router.post("/iec61850/reports/apply", response_model=BaseResponse)
async def apply_report_config(body: RcbApplyConfigRequest, request: Request):
    """应用报告配置 (一次性写入 RptEna + TrgOps + OptFields)

    根据 rpt_ena 决定使能或禁用:
    - rpt_ena=True: 设置 RptEna=True + TrgOps + OptFields，安装报告回调
    - rpt_ena=False: 设置 RptEna=False，注销报告回调

    注意: 服务端模式 (ReportManager) 不支持此操作，
    仅对客户端模式 (ReportsPlugin) 有效。
    """
    reports = _get_reports_plugin(body.channel_id, request)

    if _is_server_mode(reports):
        raise ValidationError("服务端模式不支持远程配置操作", data={"success": False})

    loop = asyncio.get_event_loop()
    success = await loop.run_in_executor(
        None,
        lambda: reports.apply_config(
            rcb_ref=body.rcb_ref,
            rpt_ena=body.rpt_ena,
            trg_ops=body.trg_ops,
            opt_fields=body.opt_fields,
        ),
    )
    if not success:
        action = "使能" if body.rpt_ena else "禁用"
        raise OperationError(f"报告{action}失败", data={"success": False})

    if body.rpt_ena:
        # 使能成功: 读取单个 RCB 最新状态并更新缓存
        updated = _refresh_single_rcb(reports, body.rcb_ref, body.channel_id, request)
    else:
        # 禁用成功: 不立即调用 get_rcb_detail (可能触发 C 层竞争崩溃)
        # 直接从缓存更新 rpt_ena=False
        updated = _mark_rcb_disabled(body.channel_id, body.rcb_ref, request)
    return BaseResponse(message="报告配置应用成功", data={"success": True, "rcb": updated})


@router.post("/iec61850/reports/gi", response_model=BaseResponse)
async def trigger_gi(body: RcbGiRequest, request: Request):
    """触发报告通用查询 (GI)"""
    reports = _get_reports_plugin(body.channel_id, request)

    if _is_server_mode(reports):
        raise ValidationError("服务端模式不支持远程 GI 操作", data={"success": False})

    loop = asyncio.get_event_loop()
    success = await loop.run_in_executor(
        None,
        lambda: reports.trigger_gi(rcb_ref=body.rcb_ref),
    )
    if not success:
        raise OperationError("GI 触发失败", data={"success": False})
    return BaseResponse(message="GI 触发成功", data={"success": True})


@router.post("/iec61850/reports/refresh", response_model=BaseResponse)
async def refresh_rcb(body: RcbDetailRequest, request: Request):
    """刷新单个 RCB 状态 (从服务器重新读取并更新缓存)"""
    reports = _get_reports_plugin(body.channel_id, request)
    updated = _refresh_single_rcb(reports, body.rcb_ref, body.channel_id, request)
    if not updated:
        raise NotFoundError("RCB 未找到或刷新失败")
    return BaseResponse(message="刷新 RCB 成功", data=updated)


@router.post("/iec61850/reports/data", response_model=BaseResponse)
async def get_report_data(body: ReportDataRequest, request: Request):
    """获取报告数据 (仅客户端模式支持)"""
    reports = _get_reports_plugin(body.channel_id, request)

    if _is_server_mode(reports):
        raise ValidationError("服务端模式不支持报告数据查询，正在开发中", data={"data": [], "total": 0})

    data = reports.get_report_data(rcb_ref=body.rcb_ref, limit=body.limit)
    return BaseResponse(
        message="获取报告数据成功",
        data={
            "data": data,
            "total": len(data),
        },
    )


@router.post("/iec61850/reports/detail", response_model=BaseResponse)
async def get_rcb_detail(body: RcbDetailRequest, request: Request):
    """获取单个 RCB 详细信息"""
    reports = _get_reports_plugin(body.channel_id, request)

    if _is_server_mode(reports):
        rcbs = _server_rcbs_to_discovery_format(reports)
        for rcb in rcbs:
            if rcb.get("ref") == body.rcb_ref or rcb.get("name") == body.rcb_ref.split(".")[-1]:
                return BaseResponse(message="获取 RCB 详情成功", data=rcb)
        raise NotFoundError("RCB 未找到")
    else:
        detail = reports.get_rcb_detail(rcb_ref=body.rcb_ref)
        if not detail:
            raise NotFoundError("RCB 未找到")
        return BaseResponse(message="获取 RCB 详情成功", data=detail)


@router.post("/iec61850/reports/active", response_model=BaseResponse)
async def list_active_reports(body: RcbListRequest, request: Request):
    """列出当前活跃的报告订阅"""
    reports = _get_reports_plugin(body.channel_id, request)

    if _is_server_mode(reports):
        return BaseResponse(message="服务端模式无活跃报告信息", data={"active_reports": []})

    active = reports.list_active_reports()
    return BaseResponse(message="获取活跃报告列表成功", data={"active_reports": active})
