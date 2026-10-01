"""Initial OPC UA status and native Browse/Read/Write endpoints."""

import asyncio
from datetime import datetime
from typing import Any

from asyncua import ua
from fastapi import APIRouter, File, Form, Request, Response, UploadFile, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError

from src.data.service.channel_service import ChannelService
from src.data.service.opcua_config_service import OpcUaConfigService
from src.data.service.opcua_feature_service import OpcUaFeatureService
from src.data.service.opcua_model_service import OpcUaModelService
from src.data.service.opcua_node_service import OpcUaNodeService
from src.data.service.opcua_point_import import OpcUaPointImportService, PointImportError
from src.data.service.opcua_security_service import OpcUaSecurityService
from src.device.protocol.opcua_handler import OpcUaClientHandler, OpcUaServerHandler
from src.proto.opcua.core.feature_config import (
    EventsConfig,
    HistoryConfig,
    SecurityConfig,
    SimulationConfig,
    SubscriptionsConfig,
)
from src.proto.opcua.core.transport import discover_endpoints
from src.proto.opcua.point_excel import MAX_EXCEL_BYTES
from src.web.api.exceptions import NotFoundError, OperationError, ValidationError
from src.web.api.schemas import BaseResponse
from src.web.log import log

router = APIRouter(prefix="/api/opcua", tags=["opcua"])


class ChannelRequest(BaseModel):
    channel_id: int = Field(gt=0)


class NodeRequest(ChannelRequest):
    node_id: str = Field(min_length=1, max_length=512)


class BrowseRequest(NodeRequest):
    node_id: str = "i=85"
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0, le=100000)


class WriteRequest(NodeRequest):
    value: Any


class UpsertVariableRequest(NodeRequest):
    browse_name: str = Field(min_length=1, max_length=255)
    data_type: str
    initial_value: Any
    writable: bool = False


class ClientEndpointRequest(ChannelRequest):
    endpoint_url: str = Field(min_length=1, max_length=1024)


class ServerModelRequest(ChannelRequest):
    endpoint_path: str = Field(min_length=1, max_length=255)
    namespace_uri: str = Field(min_length=1, max_length=255)


class PointListRequest(ChannelRequest):
    point_type: int | None = Field(default=None, ge=0, le=3)
    search: str = Field(default="", max_length=128)
    offset: int = Field(default=0, ge=0, le=100000)
    limit: int = Field(default=100, ge=1, le=500)


class PointDeleteRequest(ChannelRequest):
    point_code: str = Field(min_length=1, max_length=128)


class FeatureRequest(ChannelRequest):
    name: str
    config: dict = Field(default_factory=dict)


class StreamRequest(ChannelRequest):
    after: int = Field(default=0, ge=0)
    limit: int = Field(default=500, ge=1, le=500)


class CertificateGenerateRequest(ChannelRequest):
    application_uri: str = Field(min_length=1, max_length=255)
    host: str = Field(min_length=1, max_length=255)


class CertificateTrustRequest(ChannelRequest):
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    trusted: bool


class CredentialRequest(ChannelRequest):
    password: str = Field(min_length=8, max_length=1024, repr=False)


class UserRequest(ChannelRequest):
    username: str = Field(min_length=1, max_length=64)
    role: str = "viewer"
    password: str | None = Field(default=None, max_length=1024, repr=False)


class HistoryReadRequest(NodeRequest):
    start: datetime
    end: datetime
    limit: int = Field(default=100, ge=1, le=500)
    continuation: str | None = Field(default=None, max_length=8192)
    release: bool = False


class EmitEventRequest(ChannelRequest):
    message: str = Field(min_length=1, max_length=1024)
    severity: int = Field(default=500, ge=0, le=1000)


class SimulationPauseRequest(ChannelRequest):
    paused: bool


@router.post("/simulation/pause", response_model=BaseResponse)
async def pause_simulation(body: SimulationPauseRequest, request: Request):
    handler = _handler(request, body.channel_id)
    if not isinstance(handler, OpcUaServerHandler) or not handler.is_running:
        raise ValidationError("请先启动 OPC UA 服务端")
    try:
        handler.server.pause_simulation(body.paused)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    return BaseResponse(data={"paused": body.paused})


@router.post("/history/read", response_model=BaseResponse)
async def history_read(body: HistoryReadRequest, request: Request):
    facade = _client(request, body.channel_id).client
    try:
        result = await facade.read_history(
            body.node_id, body.start, body.end, body.limit, body.continuation, body.release
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    except Exception as exc:
        raise OperationError(f"OPC UA HistoryRead 失败: {exc}") from exc
    return BaseResponse(data=result)


@router.post("/events/emit", response_model=BaseResponse)
async def emit_event(body: EmitEventRequest, request: Request):
    facade = _facade(request, body.channel_id)
    handler = _handler(request, body.channel_id)
    if not isinstance(handler, OpcUaServerHandler):
        raise ValidationError("事件触发仅适用于 OPC UA 服务端")
    try:
        return BaseResponse(data=await facade.emit_event(body.message, body.severity))
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc


@router.post("/diagnostics", response_model=BaseResponse)
async def diagnostics(body: ChannelRequest, request: Request):
    return BaseResponse(data=_facade(request, body.channel_id).diagnostics())


@router.post("/endpoints/discover", response_model=BaseResponse)
async def endpoints(body: ClientEndpointRequest):
    _channel(body.channel_id)
    try:
        endpoints = await discover_endpoints(body.endpoint_url)
        for endpoint in endpoints:
            if endpoint.get("certificate"):
                import base64

                await asyncio.to_thread(
                    OpcUaSecurityService.register_peer, body.channel_id, base64.b64decode(endpoint["certificate"])
                )
        return BaseResponse(data={"endpoints": endpoints})
    except Exception as exc:
        raise OperationError(f"Endpoint 发现失败: {exc}") from exc


@router.post("/certificates/generate", response_model=BaseResponse)
async def certificate_generate(body: CertificateGenerateRequest, request: Request):
    _channel(body.channel_id)
    _ensure_stopped(request, body.channel_id)
    result = await asyncio.to_thread(OpcUaSecurityService.generate, body.channel_id, body.application_uri, body.host)
    log.info(f"OPC UA 应用证书已生成: channel_id={body.channel_id}, fingerprint={result['fingerprint']}")
    config = await asyncio.to_thread(OpcUaConfigService.get, body.channel_id)
    await _refresh_stopped_device(request, body.channel_id, config)
    return BaseResponse(data=result)


@router.post("/certificates/trust", response_model=BaseResponse)
async def certificate_trust(body: CertificateTrustRequest, request: Request):
    _channel(body.channel_id)
    _ensure_stopped(request, body.channel_id)
    try:
        await asyncio.to_thread(OpcUaSecurityService.trust, body.channel_id, body.fingerprint, body.trusted)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    log.info(
        f"OPC UA 证书信任已更新: channel_id={body.channel_id}, trusted={body.trusted}, fingerprint={body.fingerprint}"
    )
    config = await asyncio.to_thread(OpcUaConfigService.get, body.channel_id)
    await _refresh_stopped_device(request, body.channel_id, config)
    return BaseResponse(data={"trusted": body.trusted})


@router.post("/credentials/client", response_model=BaseResponse)
async def client_credential(body: CredentialRequest, request: Request):
    if _channel(body.channel_id)["conn_type"] != 1:
        raise ValidationError("仅适用于 OPC UA 客户端")
    _ensure_stopped(request, body.channel_id)
    await asyncio.to_thread(OpcUaSecurityService.save_secret, body.channel_id, "password", body.password)
    config = await asyncio.to_thread(OpcUaConfigService.get, body.channel_id)
    await _refresh_stopped_device(request, body.channel_id, config)
    return BaseResponse(data={"saved": True})


@router.post("/users/save", response_model=BaseResponse)
async def user_save(body: UserRequest, request: Request):
    if _channel(body.channel_id)["conn_type"] != 2:
        raise ValidationError("仅适用于 OPC UA 服务端")
    _ensure_stopped(request, body.channel_id)
    try:
        await asyncio.to_thread(OpcUaSecurityService.user, body.channel_id, body.username, body.role, body.password)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    config = await asyncio.to_thread(OpcUaConfigService.get, body.channel_id)
    await _refresh_stopped_device(request, body.channel_id, config)
    log.info(f"OPC UA 用户权限已更新: channel_id={body.channel_id}, username={body.username}, role={body.role}")
    return BaseResponse(data={"saved": True})


def _facade(request, channel_id):
    handler = _handler(request, channel_id)
    facade = handler.client if isinstance(handler, OpcUaClientHandler) else handler.server
    if facade is None:
        raise OperationError("OPC UA 运行实例不可用")
    return facade


@router.post("/features/config", response_model=BaseResponse)
async def feature_config(body: ChannelRequest):
    _channel(body.channel_id)
    return BaseResponse(data=await asyncio.to_thread(OpcUaFeatureService.load, body.channel_id))


@router.post("/features/save", response_model=BaseResponse)
async def save_feature(body: FeatureRequest, request: Request):
    channel = _channel(body.channel_id)
    models = {"simulation": (2, SimulationConfig), "subscriptions": (1, SubscriptionsConfig)}
    models["history"] = (2, HistoryConfig)
    models["events"] = (channel["conn_type"], EventsConfig)
    if body.name == "security":
        models["security"] = (channel["conn_type"], SecurityConfig)
    if body.name not in models or channel["conn_type"] != models[body.name][0]:
        raise ValidationError("功能名称或 OPC UA 角色不匹配")
    if body.name != "subscriptions":
        _ensure_stopped(request, body.channel_id)
    try:
        raw_config = body.config
        if body.name == "security":
            # Trust, certificate and user records are only changed through audited dedicated endpoints.
            saved = (await asyncio.to_thread(OpcUaFeatureService.load, body.channel_id)).get("security", {})
            raw_config = {
                **body.config,
                **{
                    key: saved.get(key, default)
                    for key, default in (("trusted", []), ("certificate", None), ("users", []))
                },
            }
        config = models[body.name][1].model_validate(raw_config).model_dump()
        if body.name == "security":
            from src.proto.opcua.core.security import validate_application_identity

            credentials = await asyncio.to_thread(OpcUaSecurityService.secrets, body.channel_id)
            validate_application_identity(config, credentials)
        if body.name == "simulation":
            nodes = await asyncio.to_thread(OpcUaNodeService.list_nodes, body.channel_id)
            if any(rule["node_id"] not in {node["node_id"] for node in nodes} for rule in config["rules"]):
                raise ValueError("模拟规则包含不存在的节点")
        await asyncio.to_thread(OpcUaFeatureService.save, body.channel_id, body.name, config)
    except PydanticValidationError as exc:
        message = "; ".join(error["msg"] for error in exc.errors(include_input=False, include_context=False))
        raise ValidationError(message) from exc
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    runtime_config = await asyncio.to_thread(OpcUaConfigService.get, body.channel_id)
    device = request.app.state.device_controller.get_device_by_id(body.channel_id)
    handler = device.protocol_handler if device is not None else None
    if body.name == "subscriptions" and isinstance(handler, OpcUaClientHandler) and handler.lifecycle_active:
        await handler.client.configure_subscriptions(config)
        return BaseResponse(data=config)
    await _refresh_stopped_device(request, body.channel_id, runtime_config)
    return BaseResponse(data=config)


@router.post("/stream/read", response_model=BaseResponse)
async def stream_read(body: StreamRequest, request: Request):
    return BaseResponse(data=_facade(request, body.channel_id).stream.page(body.after, body.limit))


@router.websocket("/stream/{channel_id}")
async def value_stream(websocket: WebSocket, channel_id: int):
    try:
        facade = _facade(websocket, channel_id)
        after = max(0, int(websocket.query_params.get("after", "0")))
    except (ValueError, OperationError, ValidationError, NotFoundError):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    try:
        while True:
            page = await facade.stream.wait(after)
            await websocket.send_json(page)
            if page["events"]:
                after = page["events"][-1]["sequence"]
    except (WebSocketDisconnect, RuntimeError):
        pass


def _channel(channel_id: int) -> dict:
    channel = ChannelService.get_channel_by_id(channel_id)
    if channel is None:
        raise NotFoundError("通道不存在")
    if channel.get("protocol_type") != 7:
        raise ValidationError("通道不是 OPC UA 协议")
    return channel


def _handler(request: Request, channel_id: int) -> OpcUaClientHandler | OpcUaServerHandler:
    _channel(channel_id)
    controller = request.app.state.device_controller
    device = controller.get_device_by_id(channel_id)
    if device is None or not isinstance(device.protocol_handler, (OpcUaClientHandler, OpcUaServerHandler)):
        raise OperationError("OPC UA 运行实例不可用")
    return device.protocol_handler


def _ensure_stopped(request: Request, channel_id: int) -> None:
    device = request.app.state.device_controller.get_device_by_id(channel_id)
    handler = device.protocol_handler if device is not None else None
    if device is not None and (
        device.is_protocol_running()
        or (isinstance(handler, (OpcUaClientHandler, OpcUaServerHandler)) and handler.lifecycle_active)
    ):
        raise ValidationError("请先停止 OPC UA 设备，再修改配置")


async def _refresh_stopped_device(request: Request, channel_id: int, config: dict) -> None:
    device = request.app.state.device_controller.get_device_by_id(channel_id)
    if device is not None:
        if isinstance(device.protocol_handler, (OpcUaClientHandler, OpcUaServerHandler)):
            await device.protocol_handler.stop()
        device.ip = config["bind_host"]
        device.port = config["bind_port"]
        device.opcua_config = config
        device.initProtocol()


def _client(request: Request, channel_id: int) -> OpcUaClientHandler:
    handler = _handler(request, channel_id)
    if not isinstance(handler, OpcUaClientHandler):
        raise ValidationError("该操作仅适用于 OPC UA 客户端通道")
    if not handler.is_running:
        reason = handler.last_error or (handler.client.connection_error if handler.client else None)
        raise OperationError(reason or "OPC UA 客户端未连接")
    return handler


@router.post("/status", response_model=BaseResponse)
async def status(body: ChannelRequest, request: Request):
    channel = _channel(body.channel_id)
    role = "client" if channel.get("conn_type") == 1 else "server"
    device = request.app.state.device_controller.get_device_by_id(body.channel_id)
    handler = device.protocol_handler if device is not None else None
    if not isinstance(handler, (OpcUaClientHandler, OpcUaServerHandler)):
        config = await asyncio.to_thread(OpcUaConfigService.get, body.channel_id)
        return BaseResponse(
            data={
                "channel_id": body.channel_id,
                "role": role,
                "running": False,
                "endpoint_url": config["endpoint_url"],
                "error": "运行实例未创建",
            }
        )
    core = handler.client if role == "client" else handler.server
    return BaseResponse(
        data={
            "channel_id": body.channel_id,
            "role": role,
            "running": handler.is_running,
            "endpoint_url": core.endpoint_url if core else None,
            "error": handler.last_error or (core.connection_error if core else None),
            "node_count": core.node_count if role == "server" and core else None,
        }
    )


@router.post("/capabilities", response_model=BaseResponse)
async def capabilities(body: ChannelRequest, request: Request):
    handler = _handler(request, body.channel_id)
    facade = handler.client if isinstance(handler, OpcUaClientHandler) else handler.server
    return BaseResponse(data={"capabilities": facade.capabilities() if facade else []})


@router.post("/config", response_model=BaseResponse)
async def get_config(body: ChannelRequest):
    _channel(body.channel_id)
    config = await asyncio.to_thread(OpcUaConfigService.get, body.channel_id)
    return BaseResponse(data=config)


@router.post("/config/client-endpoint", response_model=BaseResponse)
async def save_client_endpoint(body: ClientEndpointRequest, request: Request):
    channel = _channel(body.channel_id)
    if channel.get("conn_type") != 1:
        raise ValidationError("通道不是 OPC UA 客户端")
    _ensure_stopped(request, body.channel_id)
    try:
        config = await asyncio.to_thread(OpcUaConfigService.save_client_endpoint, body.channel_id, body.endpoint_url)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    await _refresh_stopped_device(request, body.channel_id, config)
    log.info(f"OPC UA 客户端 Endpoint 已更新: channel_id={body.channel_id}")
    return BaseResponse(data=config)


@router.post("/config/server-model", response_model=BaseResponse)
async def save_server_model(body: ServerModelRequest, request: Request):
    channel = _channel(body.channel_id)
    if channel.get("conn_type") != 2:
        raise ValidationError("通道不是 OPC UA 服务端")
    _ensure_stopped(request, body.channel_id)
    try:
        config = await asyncio.to_thread(
            OpcUaConfigService.save_server_model,
            body.channel_id,
            body.endpoint_path,
            body.namespace_uri,
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    await _refresh_stopped_device(request, body.channel_id, config)
    log.info(f"OPC UA 服务端模型配置已更新: channel_id={body.channel_id}")
    return BaseResponse(data=config)


@router.post("/nodes/browse", response_model=BaseResponse)
async def browse(body: BrowseRequest, request: Request):
    handler = _client(request, body.channel_id)
    try:
        page = await handler.browse_page(body.node_id, body.limit, body.offset)
    except ua.UaStatusCodeError as exc:
        raise OperationError(f"OPC UA Browse 失败: {exc}") from exc
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    return BaseResponse(data=page)


@router.post("/nodes/read", response_model=BaseResponse)
async def read(body: NodeRequest, request: Request):
    handler = _client(request, body.channel_id)
    try:
        return BaseResponse(data=await handler.read(body.node_id))
    except ua.UaStatusCodeError as exc:
        raise OperationError(f"OPC UA Read 失败: {exc}") from exc
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc


@router.post("/nodes/write", response_model=BaseResponse)
async def write(body: WriteRequest, request: Request):
    handler = _client(request, body.channel_id)
    try:
        result = await handler.write(body.node_id, body.value)
    except ua.UaStatusCodeError as exc:
        raise OperationError(f"OPC UA Write 失败: {exc}") from exc
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    log.info(f"OPC UA 写入成功: channel_id={body.channel_id}, node_id={body.node_id}")
    return BaseResponse(data=result)


@router.post("/nodes/variables", response_model=BaseResponse)
async def variables(body: ChannelRequest):
    channel = _channel(body.channel_id)
    if channel.get("conn_type") != 2:
        raise ValidationError("该操作仅适用于 OPC UA 服务端通道")
    nodes = await asyncio.to_thread(OpcUaNodeService.list_nodes, body.channel_id)
    return BaseResponse(data={"nodes": nodes})


@router.post("/nodes/upsert", response_model=BaseResponse)
async def upsert_variable(body: UpsertVariableRequest, request: Request):
    channel = _channel(body.channel_id)
    if channel.get("conn_type") != 2:
        raise ValidationError("该操作仅适用于 OPC UA 服务端通道")
    _ensure_stopped(request, body.channel_id)
    config = await asyncio.to_thread(OpcUaConfigService.get, body.channel_id)
    try:
        result = await asyncio.to_thread(
            OpcUaNodeService.upsert_variable,
            body.channel_id,
            config["namespace_uri"],
            body.model_dump(exclude={"channel_id"}),
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    log.info(f"OPC UA 节点定义已保存: channel_id={body.channel_id}, node_id={body.node_id}")
    await _refresh_stopped_device(request, body.channel_id, config)
    return BaseResponse(data=result)


async def _read_point_file(file: UploadFile) -> bytes:
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise ValidationError("请选择 .xlsx 点表文件")
    content = await file.read(MAX_EXCEL_BYTES + 1)
    if not content or len(content) > MAX_EXCEL_BYTES:
        raise ValidationError("Excel 文件为空或超过 5 MB")
    return content


@router.post("/points/import/preview", response_model=BaseResponse)
async def preview_points(channel_id: int = Form(...), file: UploadFile = File(...)):
    _channel(channel_id)
    content = await _read_point_file(file)
    try:
        inspection = await asyncio.to_thread(OpcUaPointImportService.preview, channel_id, content)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    return BaseResponse(data=inspection.to_dict())


@router.post("/points/import/apply", response_model=BaseResponse)
async def apply_points(
    request: Request,
    channel_id: int = Form(...),
    expected_sha256: str = Form(...),
    mode: str = Form(...),
    file: UploadFile = File(...),
):
    channel = _channel(channel_id)
    if channel.get("conn_type") == 2:
        _ensure_stopped(request, channel_id)
    content = await _read_point_file(file)
    try:
        result = await asyncio.to_thread(OpcUaPointImportService.apply, channel_id, content, expected_sha256, mode)
    except PointImportError as exc:
        raise ValidationError(
            str(exc),
            data={
                "errors": [error.to_dict() for error in exc.errors],
                "conflicts": exc.conflicts,
            },
        ) from exc
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    if channel.get("conn_type") == 2:
        config = await asyncio.to_thread(OpcUaConfigService.get, channel_id)
        await _refresh_stopped_device(request, channel_id, config)
    log.info(f"OPC UA 点表已导入: channel_id={channel_id}, created={result['created']}, updated={result['updated']}")
    return BaseResponse(data=result)


@router.post("/points/list", response_model=BaseResponse)
async def list_points(body: PointListRequest):
    _channel(body.channel_id)
    result = await asyncio.to_thread(
        OpcUaPointImportService.list_points,
        body.channel_id,
        point_type=body.point_type,
        search=body.search,
        offset=body.offset,
        limit=body.limit,
    )
    return BaseResponse(data=result)


@router.post("/points/export")
async def export_points(body: ChannelRequest):
    _channel(body.channel_id)
    content = await asyncio.to_thread(OpcUaPointImportService.export, body.channel_id)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="opcua-points-{body.channel_id}.xlsx"',
        },
    )


@router.post("/points/read", response_model=BaseResponse)
async def read_point(body: PointDeleteRequest, request: Request):
    handler = _handler(request, body.channel_id)
    if not handler.is_running:
        raise OperationError("OPC UA 设备未运行")
    point = await asyncio.to_thread(OpcUaPointImportService.get_point, body.channel_id, body.point_code)
    if point is None:
        raise NotFoundError("测点不存在")
    try:
        if isinstance(handler, OpcUaClientHandler):
            snapshot = await handler.client.read_point(point["namespace_uri"], point["node_id"])
        else:
            snapshot = await handler.server.read(point["node_id"])
    except ua.UaStatusCodeError as exc:
        raise OperationError(f"OPC UA Read 失败: {exc}") from exc
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    return BaseResponse(data={"point_code": body.point_code, **snapshot})


@router.post("/points/delete", response_model=BaseResponse)
async def delete_point(body: PointDeleteRequest, request: Request):
    channel = _channel(body.channel_id)
    if channel.get("conn_type") == 2:
        _ensure_stopped(request, body.channel_id)
    try:
        removed = await asyncio.to_thread(OpcUaPointImportService.delete_point, body.channel_id, body.point_code)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    if not removed:
        raise NotFoundError("测点不存在")
    if channel.get("conn_type") == 2:
        config = await asyncio.to_thread(OpcUaConfigService.get, body.channel_id)
        await _refresh_stopped_device(request, body.channel_id, config)
    return BaseResponse(data={"deleted": True})


@router.post("/nodes/delete", response_model=BaseResponse)
async def delete_variable(body: NodeRequest, request: Request):
    channel = _channel(body.channel_id)
    if channel.get("conn_type") != 2:
        raise ValidationError("该操作仅适用于 OPC UA 服务端通道")
    _ensure_stopped(request, body.channel_id)
    try:
        deleted = await asyncio.to_thread(OpcUaNodeService.delete_variable, body.channel_id, body.node_id)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    if not deleted:
        raise NotFoundError("节点不存在")
    config = await asyncio.to_thread(OpcUaConfigService.get, body.channel_id)
    await _refresh_stopped_device(request, body.channel_id, config)
    return BaseResponse(data={"deleted": True})


@router.post("/points/clear", response_model=BaseResponse)
async def clear_points(body: ChannelRequest, request: Request):
    channel = _channel(body.channel_id)
    if channel.get("conn_type") == 2:
        _ensure_stopped(request, body.channel_id)
    result = await asyncio.to_thread(OpcUaPointImportService.clear, body.channel_id)
    if channel.get("conn_type") == 2:
        config = await asyncio.to_thread(OpcUaConfigService.get, body.channel_id)
        await _refresh_stopped_device(request, body.channel_id, config)
    log.info(f"OPC UA 本地点表已清空: channel_id={body.channel_id}, count={result['deleted']}")
    return BaseResponse(data=result)


@router.post("/nodes/reset", response_model=BaseResponse)
async def reset_variables(body: ChannelRequest, request: Request):
    handler = _handler(request, body.channel_id)
    if not isinstance(handler, OpcUaServerHandler) or handler.server is None:
        raise ValidationError("重置变量仅适用于 OPC UA 服务端通道")
    try:
        count = await handler.server.reset_values()
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    log.info(f"OPC UA 变量已重置: channel_id={body.channel_id}, count={count}")
    return BaseResponse(data={"reset": count})


@router.post("/model/export")
async def export_model(body: ChannelRequest, request: Request):
    handler = _handler(request, body.channel_id)
    if not isinstance(handler, OpcUaServerHandler) or handler.server is None:
        raise ValidationError("NodeSet XML 导出仅适用于 OPC UA 服务端通道")
    try:
        content = await handler.server.export_nodeset()
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    return Response(
        content=content,
        media_type="application/xml",
        headers={
            "Content-Disposition": f'attachment; filename="opcua-channel-{body.channel_id}.xml"',
        },
    )


async def _read_nodeset_file(file: UploadFile) -> bytes:
    if not (file.filename or "").lower().endswith(".xml"):
        raise ValidationError("请选择 NodeSet .xml 文件")
    content = await file.read(MAX_EXCEL_BYTES + 1)
    if not content or len(content) > MAX_EXCEL_BYTES:
        raise ValidationError("NodeSet XML 为空或超过 5 MB")
    return content


@router.post("/model/import/preview", response_model=BaseResponse)
async def preview_model(channel_id: int = Form(...), file: UploadFile = File(...)):
    channel = _channel(channel_id)
    if channel.get("conn_type") != 2:
        raise ValidationError("NodeSet XML 导入仅适用于 OPC UA 服务端通道")
    content = await _read_nodeset_file(file)
    try:
        result = await OpcUaModelService.preview_upload(channel_id, content)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    return BaseResponse(data=result)


@router.post("/model/import/apply", response_model=BaseResponse)
async def apply_model(
    request: Request,
    channel_id: int = Form(...),
    expected_sha256: str = Form(...),
    mode: str = Form(...),
    file: UploadFile = File(...),
):
    channel = _channel(channel_id)
    if channel.get("conn_type") != 2:
        raise ValidationError("NodeSet XML 导入仅适用于 OPC UA 服务端通道")
    _ensure_stopped(request, channel_id)
    content = await _read_nodeset_file(file)
    try:
        result = await OpcUaModelService.apply_upload(channel_id, content, expected_sha256, mode)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    config = await asyncio.to_thread(OpcUaConfigService.get, channel_id)
    await _refresh_stopped_device(request, channel_id, config)
    log.info(
        f"OPC UA NodeSet 已导入: channel_id={channel_id}, created={result['created']}, updated={result['updated']}"
    )
    return BaseResponse(data=result)
