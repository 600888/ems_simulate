"""通道管理 - IEC 61850 Reports 报告控制块路由

提供 RCB 发现、使能/禁用、GI 触发、数据查询等 RESTful API。
"""

import asyncio
from typing import Any

from fastapi import APIRouter, Request

from src.device.protocol.iec61850_report_coordination import (
    pause_matching_local_server_simulations,
    resume_local_server_simulations,
)
from src.proto.iec61850.plugins.reports.report_tree import ReportTreeBuilder, make_entry_summary
from src.web.api.exceptions import NotFoundError, OperationError, ValidationError
from src.web.api.schemas import BaseResponse
from src.web.api.schemas.report import (
    RcbApplyConfigRequest,
    RcbBatchApplyConfigRequest,
    RcbDetailRequest,
    RcbGiRequest,
    RcbListRequest,
    ReportDataRequest,
    ReportTreeDataRequest,
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
    device_controller = request.app.state.device_controller
    device = device_controller.get_device_by_channel_id(channel_id)
    if not device:
        raise NotFoundError("通道或设备不存在")

    protocol_handler = getattr(device, "protocol_handler", None)
    if not protocol_handler:
        raise ValidationError("协议处理器未初始化")

    from src.device.protocol.iec61850_handler import IEC61850ClientHandler, IEC61850ServerHandler

    if isinstance(protocol_handler, IEC61850ClientHandler):
        client = getattr(protocol_handler, "_client", None)
        if client:
            return client.reports
    elif isinstance(protocol_handler, IEC61850ServerHandler):
        server = getattr(protocol_handler, "_server", None)
        if server:
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
        resv_val = bool(rcb.get("resv", False))
        resv_tms_val = int(rcb.get("resv_tms", 0) or 0)
        reserved_val = bool(resv_val or resv_tms_val != 0)
        rpt_ena_val = bool(rcb.get("rpt_ena", False))

        rcbs.append(
            {
                "name": rcb_name,
                "ref": f"{ld_inst}/{ln_name}.{rcb_name}" if ld_inst else rcb_name,
                "rcb_type": rcb_type,
                "ld": ld_inst,
                "ln": ln_name,
                "rpt_id": rcb.get("rpt_id", ""),
                "rpt_ena": rpt_ena_val,
                "data_set_ref": rcb.get("data_set_ref", ""),
                "conf_rev": rcb.get("conf_rev", 1),
                "buf_time": rcb.get("buf_time", 0),
                "intg_period": rcb.get("intg_period", 0),
                "sq_num": rcb.get("sq_num", 0),
                "purge_buf": purge_buf_val,
                "entry_id": entry_id_val,
                "time_of_entry": time_of_entry_val,
                "owner": rcb.get("owner", ""),
                "resv": resv_val,
                "resv_tms": resv_tms_val,
                "reserved": reserved_val,
                "locked": bool(reserved_val or rpt_ena_val),
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


def _fix_rpt_id_suffix(rcb: dict) -> dict:
    """修复 RCB 的 rpt_id 缺失 name 数字后缀的问题

    当远端 IED 的多个 RCB 共享相同 rptID（如 "rpRack1CellTemp"）
    而 name 带有数字后缀（如 "rpRack1CellTemp01"）时，将 name 的
    数字后缀继承到 rpt_id，确保前端能区分不同 RCB 的路由键。
    """
    name = rcb.get("name", "")
    rpt_id = rcb.get("rpt_id", "")
    if rpt_id and name != rpt_id and name.startswith(rpt_id):
        suffix = name[len(rpt_id) :]
        if suffix and suffix.isdigit():
            rcb["rpt_id"] = name
    return rcb


def _discover_rcbs(reports: Any, channel_id: int = 0, handler: Any = None) -> list:
    """统一获取 RCB 列表，兼容客户端和服务端模式

    客户端模式: 直接使用连接阶段已校验的 RCB 缓存，缓存为空才现场发现。
    列表接口不读取每个 RCB 的在线状态，避免进入页面时产生大量 MMS 请求。
    服务端模式: 直接从本地 ReportManager 获取
    """
    if _is_server_mode(reports):
        rcbs = _server_rcbs_to_discovery_format(reports)
        for rcb in rcbs:
            _fix_rpt_id_suffix(rcb)
        return rcbs

    if handler is not None and hasattr(handler, "get_discovered_rcbs"):
        cached = handler.get_discovered_rcbs()
        if cached:
            for rcb in cached:
                _fix_rpt_id_suffix(rcb)
            return cached
    rcbs = reports.discover_rcbs()
    # 现场发现成功则回写缓存，供后续及侧边栏结构接口复用
    if rcbs and handler is not None and hasattr(handler, "set_discovered_rcbs"):
        handler.set_discovered_rcbs(rcbs)
    for rcb in rcbs:
        _fix_rpt_id_suffix(rcb)
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
                    _fix_rpt_id_suffix(rcb)
                    return rcb
            return None

        # 优先走只刷新易变状态的安全路径；使用主浏览连接，避免与报告回调竞争。
        handler = _get_client_handler(channel_id, request)
        if handler and hasattr(reports, "refresh_rcb_states"):
            cached = handler.get_discovered_rcbs()
            current = next((item for item in cached if item.get("ref") == rcb_ref), None)
            if current is not None:
                refreshed = reports.refresh_rcb_states([current])
                if refreshed:
                    handler.update_discovered_rcb(rcb_ref, refreshed[0])
                    _fix_rpt_id_suffix(refreshed[0])
                    return refreshed[0]

        # 客户端模式: 重新读取单个 RCB 详情
        detail = reports.get_rcb_detail(rcb_ref=rcb_ref)
        if not detail:
            return None

        # 更新缓存中对应的那条记录
        handler = _get_client_handler(channel_id, request)
        if handler:
            handler.update_discovered_rcb(rcb_ref, detail)
        _fix_rpt_id_suffix(detail)
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


def _mark_rcb_enabled(channel_id: int, rcb_ref: str, request: Request) -> dict[str, Any] | None:
    """使能报告后直接从缓存更新 rpt_ena=True

    与 _mark_rcb_disabled 对称，不依赖 MMS 读取，
    避免读 RCB 与报告回调竞争导致的 C 层崩溃。

    Returns:
        更新后的 RCB 字典，失败返回 None
    """
    handler = _get_client_handler(channel_id, request)
    if not handler or not hasattr(handler, "get_discovered_rcbs"):
        return None

    for rcb in handler.get_discovered_rcbs():
        if rcb.get("ref") == rcb_ref:
            rcb["rpt_ena"] = True
            if hasattr(handler, "update_discovered_rcb"):
                handler.update_discovered_rcb(rcb_ref, rcb)
            return rcb
    return None


def _select_report_entry(
    data: list[dict[str, Any]], entry_key: str | None, latest: bool
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Select one report entry and return (entry, summary)."""
    if not data:
        return None, None

    summaries = [make_entry_summary(entry, index) for index, entry in enumerate(data)]
    if entry_key:
        for entry, summary in zip(data, summaries, strict=True):
            if summary.get("entry_key") == entry_key:
                return entry, summary
        return None, None

    index = len(data) - 1 if latest else 0
    return data[index], summaries[index]


def _uid_from_entry_key(entry_key: str | None) -> int | None:
    """从前端稳定 key 中提取报告 uid。"""
    if not entry_key or not entry_key.startswith("uid:"):
        return None
    try:
        return int(entry_key.removeprefix("uid:"))
    except ValueError:
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
        # 使能成功: 先直接更新缓存 rpt_ena=True（不依赖 MMS 避免竞争）
        updated = _mark_rcb_enabled(body.channel_id, body.rcb_ref, request)
        # 再最佳努力从 IED 刷新完整实时状态（MMS 失败不影响缓存一致性）
        _refresh_single_rcb(reports, body.rcb_ref, body.channel_id, request)
    else:
        # 禁用成功: 不立即调用 get_rcb_detail (可能触发 C 层竞争崩溃)
        # 直接从缓存更新 rpt_ena=False
        updated = _mark_rcb_disabled(body.channel_id, body.rcb_ref, request)
    return BaseResponse(message="报告配置应用成功", data={"success": True, "rcb": updated})


@router.post("/iec61850/reports/batch-apply", response_model=BaseResponse)
async def batch_apply_report_config(body: RcbBatchApplyConfigRequest, request: Request):
    """批量应用报告配置"""
    reports = _get_reports_plugin(body.channel_id, request)

    if _is_server_mode(reports):
        raise ValidationError("服务端模式不支持远程配置操作", data={"success": False})

    loop = asyncio.get_event_loop()
    success_count = 0
    fail_count = 0
    fail_details: list[dict] = []

    paused_simulations = (
        await loop.run_in_executor(
            None,
            lambda: pause_matching_local_server_simulations(reports, request, log),
        )
        if body.rpt_ena
        else []
    )
    try:
        results = await loop.run_in_executor(
            None,
            lambda: reports.apply_config_batch(
                [item.rcb_ref for item in body.items],
                rpt_ena=body.rpt_ena,
                trg_ops=body.trg_ops,
                opt_fields=body.opt_fields,
            ),
        )
    finally:
        await loop.run_in_executor(
            None,
            lambda: resume_local_server_simulations(paused_simulations, log),
        )

    for rcb_ref, ok, reason in results:
        if ok:
            success_count += 1
            if body.rpt_ena:
                _mark_rcb_enabled(body.channel_id, rcb_ref, request)
            else:
                _mark_rcb_disabled(body.channel_id, rcb_ref, request)
        else:
            fail_count += 1
            fail_details.append({"rcb_ref": rcb_ref, "reason": reason or "操作失败"})

    return BaseResponse(
        message=f"批量应用完成: 成功 {success_count} 个, 失败 {fail_count} 个",
        data={
            "success": fail_count == 0,
            "success_count": success_count,
            "fail_count": fail_count,
            "fail_details": fail_details,
        },
    )


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
        return BaseResponse(
            message="服务端无报告缓存数据",
            data={"data": [], "total": 0, "latest_uid": None, "unchanged": False},
        )

    cache_total, latest_uid = reports.get_report_data_state(body.rcb_ref)
    if body.known_latest_uid is not None and latest_uid == body.known_latest_uid:
        return BaseResponse(
            message="报告数据无变化",
            data={
                "data": [],
                "total": min(cache_total, body.limit),
                "latest_uid": latest_uid,
                "unchanged": True,
            },
        )

    data = reports.get_report_data(rcb_ref=body.rcb_ref, limit=body.limit)
    return BaseResponse(
        message="获取报告数据成功",
        data={
            "data": data,
            "total": len(data),
            "latest_uid": latest_uid,
            "unchanged": False,
        },
    )


@router.post("/iec61850/reports/state", response_model=BaseResponse)
async def get_report_state(body: RcbDetailRequest, request: Request):
    """获取报告缓存轻量状态，不序列化报告正文。"""
    reports = _get_reports_plugin(body.channel_id, request)

    if _is_server_mode(reports):
        return BaseResponse(
            message="服务端无报告缓存数据",
            data={"total": 0, "latest_uid": None},
        )

    total, latest_uid = reports.get_report_data_state(body.rcb_ref)
    return BaseResponse(
        message="获取报告缓存状态成功",
        data={"total": total, "latest_uid": latest_uid},
    )


@router.post("/iec61850/reports/history", response_model=BaseResponse)
async def get_report_history(body: ReportDataRequest, request: Request):
    """获取报告历史轻量摘要列表，不返回报告值。"""
    reports = _get_reports_plugin(body.channel_id, request)

    if _is_server_mode(reports):
        return BaseResponse(
            message="服务端无报告缓存数据",
            data={"entries": [], "total": 0, "latest_uid": None, "unchanged": False},
        )

    cache_total, latest_uid = reports.get_report_data_state(body.rcb_ref)
    if body.known_latest_uid is not None and latest_uid == body.known_latest_uid:
        return BaseResponse(
            message="报告历史无变化",
            data={
                "entries": [],
                "total": cache_total,
                "latest_uid": latest_uid,
                "unchanged": True,
            },
        )

    entries = reports.get_report_summaries(body.rcb_ref, body.limit)
    return BaseResponse(
        message="获取报告历史成功",
        data={
            "entries": entries,
            "total": cache_total,
            "latest_uid": latest_uid,
            "unchanged": False,
        },
    )


@router.post("/iec61850/reports/latest", response_model=BaseResponse)
async def get_latest_report(body: ReportTreeDataRequest, request: Request):
    """按需获取最新一条报告及其树形结构。"""
    reports = _get_reports_plugin(body.channel_id, request)

    if _is_server_mode(reports):
        return BaseResponse(
            message="服务端无报告缓存数据",
            data={
                "rcb_ref": body.rcb_ref,
                "entry": None,
                "tree_items": [],
                "latest_uid": None,
                "unchanged": False,
            },
        )

    _, latest_uid = reports.get_report_data_state(body.rcb_ref)
    if body.known_latest_uid is not None and latest_uid == body.known_latest_uid:
        return BaseResponse(
            message="最近报告无变化",
            data={
                "rcb_ref": body.rcb_ref,
                "entry": None,
                "tree_items": [],
                "latest_uid": latest_uid,
                "unchanged": True,
            },
        )

    entry = reports.get_report_entry(body.rcb_ref, latest=True)
    if entry is None:
        return BaseResponse(
            message="暂无报告数据",
            data={
                "rcb_ref": body.rcb_ref,
                "entry": None,
                "tree_items": [],
                "latest_uid": latest_uid,
                "unchanged": False,
            },
        )

    summary = make_entry_summary(entry, 0)
    tree_items = ReportTreeBuilder().build(entry)
    return BaseResponse(
        message="获取最近报告成功",
        data={
            "rcb_ref": body.rcb_ref,
            "entry": summary,
            "tree_items": tree_items,
            "latest_uid": latest_uid,
            "unchanged": False,
        },
    )


@router.post("/iec61850/reports/data-tree", response_model=BaseResponse)
async def get_report_data_tree(body: ReportTreeDataRequest, request: Request):
    """获取单条报告数据的 IEDScout 风格树形结构。"""
    reports = _get_reports_plugin(body.channel_id, request)

    if _is_server_mode(reports):
        return BaseResponse(
            message="服务端无报告缓存数据",
            data={"entry": None, "tree_items": []},
        )

    uid = _uid_from_entry_key(body.entry_key)
    if body.entry_key and uid is None:
        return BaseResponse(
            message="报告条目标识无效",
            data={"rcb_ref": body.rcb_ref, "entry": None, "tree_items": []},
        )
    entry = reports.get_report_entry(rcb_ref=body.rcb_ref, uid=uid, latest=body.latest)
    if entry is None:
        return BaseResponse(
            message="暂无报告数据",
            data={"rcb_ref": body.rcb_ref, "entry": None, "tree_items": []},
        )

    summary = make_entry_summary(entry, 0)
    tree_items = ReportTreeBuilder().build(entry)
    return BaseResponse(
        message="获取报告树形数据成功",
        data={"rcb_ref": body.rcb_ref, "entry": summary, "tree_items": tree_items},
    )


@router.post("/iec61850/reports/detail", response_model=BaseResponse)
async def get_rcb_detail(body: RcbDetailRequest, request: Request):
    """获取单个 RCB 详细信息"""
    reports = _get_reports_plugin(body.channel_id, request)

    if _is_server_mode(reports):
        rcbs = _server_rcbs_to_discovery_format(reports)
        for rcb in rcbs:
            if rcb.get("ref") == body.rcb_ref or rcb.get("name") == body.rcb_ref.split(".")[-1]:
                _fix_rpt_id_suffix(rcb)
                return BaseResponse(message="获取 RCB 详情成功", data=rcb)
        raise NotFoundError("RCB 未找到")
    else:
        detail = reports.get_rcb_detail(rcb_ref=body.rcb_ref)
        if not detail:
            raise NotFoundError("RCB 未找到")
        _fix_rpt_id_suffix(detail)
        return BaseResponse(message="获取 RCB 详情成功", data=detail)


@router.post("/iec61850/reports/active", response_model=BaseResponse)
async def list_active_reports(body: RcbListRequest, request: Request):
    """列出当前活跃的报告订阅"""
    reports = _get_reports_plugin(body.channel_id, request)

    if _is_server_mode(reports):
        return BaseResponse(message="服务端模式无活跃报告信息", data={"active_reports": []})

    active = reports.list_active_reports()
    return BaseResponse(message="获取活跃报告列表成功", data={"active_reports": active})
