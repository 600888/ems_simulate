"""通道管理 - IEC 61850 Reports 报告控制块路由

提供 RCB 发现、使能/禁用、GI 触发、数据查询等 RESTful API。
"""

from typing import Any

from fastapi import APIRouter, Request

from src.data.service.channel_service import ChannelService
from src.web.api.schemas import BaseResponse
from src.web.api.schemas.report import (
    RcbDetailRequest,
    RcbDisableRequest,
    RcbEnableRequest,
    RcbGiRequest,
    RcbListRequest,
    ReportDataRequest,
)
from src.web.log import log

router = APIRouter(tags=["channel"])


def _get_reports_plugin(channel_id: int, request: Request) -> Any | None:
    """获取设备对应的 Reports 管理对象

    客户端模式: 返回 ReportsPlugin (支持 discover_rcbs/enable/disable/GI)
    服务端模式: 返回 ReportManager (支持 browse_rcbs, RCB 在本地注册)
    """
    channel = ChannelService.get_channel_by_id(channel_id)
    if not channel:
        return None

    protocol_type = channel.get("protocol_type", -1)
    if protocol_type != 4:
        return None

    device_controller = request.app.state.device_controller
    device = device_controller.get_device_by_channel_id(channel_id)
    if not device:
        return None

    protocol_handler = getattr(device, "protocol_handler", None)
    if not protocol_handler:
        return None

    from src.device.protocol.iec61850_handler import IEC61850ClientHandler, IEC61850ServerHandler

    if isinstance(protocol_handler, IEC61850ClientHandler):
        client = getattr(protocol_handler, "_client", None)
        if client and hasattr(client, "reports"):
            return client.reports
    elif isinstance(protocol_handler, IEC61850ServerHandler):
        server = getattr(protocol_handler, "_server", None)
        if server and hasattr(server, "reports"):
            return server.reports

    return None


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

        # entry_id: 支持 bytes 和 hex 字符串两种格式
        entry_id_val = rcb.get("entry_id", None)
        if isinstance(entry_id_val, bytes):
            entry_id_val = entry_id_val.hex()
        elif entry_id_val and not isinstance(entry_id_val, str):
            entry_id_val = str(entry_id_val) if entry_id_val else None

        # time_of_entry: 支持 int (ms) 或 datetime 字符串
        time_of_entry_val = rcb.get("time_of_entry", None)

        # purge_buf: 仅 BRCB 有意义
        purge_buf_val = rcb.get("purge_buf", False) if rcb_type == "BRCB" else False

        rcbs.append(
            {
                "name": rcb_name,
                "ref": f"{ld_inst}/{ld_inst}.{rcb_name}" if ld_inst else rcb_name,
                "rcb_type": rcb_type,
                "ld": ld_inst,
                "ln": "LLN0",
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


@router.post("/iec61850/reports/list", response_model=BaseResponse)
async def list_rcbs(body: RcbListRequest, request: Request):
    """列出 IEC61850 设备的报告控制块 (RCB)"""
    try:
        reports = _get_reports_plugin(body.channel_id, request)
        if not reports:
            return BaseResponse(code=400, message="设备未就绪或 Reports 插件不可用", data={"rcbs": []})

        rcbs = _discover_rcbs(reports, body.channel_id, _get_client_handler(body.channel_id, request))
        return BaseResponse(message="获取 RCB 列表成功", data={"rcbs": rcbs})
    except Exception as e:
        log.error(f"获取 RCB 列表失败: {e}")
        return BaseResponse(code=500, message=f"获取 RCB 列表失败: {e}", data={"rcbs": []})


@router.post("/iec61850/reports/enable", response_model=BaseResponse)
async def enable_report(body: RcbEnableRequest, request: Request):
    """使能报告控制块

    注意: 服务端模式 (ReportManager) 不支持 enable/disable/GI 操作，
    这些操作仅对客户端模式 (ReportsPlugin) 有效。
    """
    try:
        reports = _get_reports_plugin(body.channel_id, request)
        if not reports:
            return BaseResponse(code=400, message="Reports 插件不可用", data={"success": False})

        if _is_server_mode(reports):
            return BaseResponse(code=400, message="服务端模式不支持远程使能操作", data={"success": False})

        success = reports.enable_report(
            rcb_ref=body.rcb_ref,
            gi=body.gi,
            trg_ops=body.trg_ops,
            opt_fields=body.opt_fields,
        )
        if success:
            return BaseResponse(message="报告使能成功", data={"success": True})
        else:
            return BaseResponse(code=500, message="报告使能失败", data={"success": False})
    except Exception as e:
        log.error(f"使能报告失败: {e}")
        return BaseResponse(code=500, message=f"使能报告失败: {e}", data={"success": False})


@router.post("/iec61850/reports/disable", response_model=BaseResponse)
async def disable_report(body: RcbDisableRequest, request: Request):
    """禁用报告控制块"""
    try:
        reports = _get_reports_plugin(body.channel_id, request)
        if not reports:
            return BaseResponse(code=400, message="Reports 插件不可用", data={"success": False})

        if _is_server_mode(reports):
            return BaseResponse(code=400, message="服务端模式不支持远程禁用操作", data={"success": False})

        success = reports.disable_report(rcb_ref=body.rcb_ref)
        if success:
            return BaseResponse(message="报告禁用成功", data={"success": True})
        else:
            return BaseResponse(code=500, message="报告禁用失败", data={"success": False})
    except Exception as e:
        log.error(f"禁用报告失败: {e}")
        return BaseResponse(code=500, message=f"禁用报告失败: {e}", data={"success": False})


@router.post("/iec61850/reports/gi", response_model=BaseResponse)
async def trigger_gi(body: RcbGiRequest, request: Request):
    """触发报告通用查询 (GI)"""
    try:
        reports = _get_reports_plugin(body.channel_id, request)
        if not reports:
            return BaseResponse(code=400, message="Reports 插件不可用", data={"success": False})

        if _is_server_mode(reports):
            return BaseResponse(code=400, message="服务端模式不支持远程 GI 操作", data={"success": False})

        success = reports.trigger_gi(rcb_ref=body.rcb_ref)
        if success:
            return BaseResponse(message="GI 触发成功", data={"success": True})
        else:
            return BaseResponse(code=500, message="GI 触发失败", data={"success": False})
    except Exception as e:
        log.error(f"触发 GI 失败: {e}")
        return BaseResponse(code=500, message=f"触发 GI 失败: {e}", data={"success": False})


@router.post("/iec61850/reports/data", response_model=BaseResponse)
async def get_report_data(body: ReportDataRequest, request: Request):
    """获取报告数据 (仅客户端模式支持)"""
    try:
        reports = _get_reports_plugin(body.channel_id, request)
        if not reports:
            return BaseResponse(code=400, message="Reports 插件不可用", data={"data": [], "total": 0})

        if _is_server_mode(reports):
            return BaseResponse(code=400, message="服务端模式不支持报告数据查询", data={"data": [], "total": 0})

        data = reports.get_report_data(rcb_ref=body.rcb_ref, limit=body.limit)
        return BaseResponse(
            message="获取报告数据成功",
            data={
                "data": data,
                "total": len(data),
            },
        )
    except Exception as e:
        log.error(f"获取报告数据失败: {e}")
        return BaseResponse(code=500, message=f"获取报告数据失败: {e}", data={"data": [], "total": 0})


@router.post("/iec61850/reports/detail", response_model=BaseResponse)
async def get_rcb_detail(body: RcbDetailRequest, request: Request):
    """获取单个 RCB 详细信息"""
    try:
        reports = _get_reports_plugin(body.channel_id, request)
        if not reports:
            return BaseResponse(code=400, message="Reports 插件不可用", data={})

        if _is_server_mode(reports):
            rcbs = _server_rcbs_to_discovery_format(reports)
            for rcb in rcbs:
                if rcb.get("ref") == body.rcb_ref or rcb.get("name") == body.rcb_ref.split(".")[-1]:
                    return BaseResponse(message="获取 RCB 详情成功", data=rcb)
            return BaseResponse(code=404, message="RCB 未找到", data={})
        else:
            detail = reports.get_rcb_detail(rcb_ref=body.rcb_ref)
            if detail:
                return BaseResponse(message="获取 RCB 详情成功", data=detail)
            else:
                return BaseResponse(code=404, message="RCB 未找到", data={})
    except Exception as e:
        log.error(f"获取 RCB 详情失败: {e}")
        return BaseResponse(code=500, message=f"获取 RCB 详情失败: {e}", data={})


@router.post("/iec61850/reports/active", response_model=BaseResponse)
async def list_active_reports(body: RcbListRequest, request: Request):
    """列出当前活跃的报告订阅"""
    try:
        reports = _get_reports_plugin(body.channel_id, request)
        if not reports:
            return BaseResponse(code=400, message="Reports 插件不可用", data={"active_reports": []})

        if _is_server_mode(reports):
            return BaseResponse(message="服务端模式无活跃报告信息", data={"active_reports": []})

        active = reports.list_active_reports()
        return BaseResponse(message="获取活跃报告列表成功", data={"active_reports": active})
    except Exception as e:
        log.error(f"获取活跃报告列表失败: {e}")
        return BaseResponse(code=500, message=f"获取活跃报告列表失败: {e}", data={"active_reports": []})
