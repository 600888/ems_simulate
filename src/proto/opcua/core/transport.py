"""The only layer that owns asyncua Client and Server instances."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from contextvars import ContextVar
from datetime import UTC, datetime
import ipaddress
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from urllib.parse import urlparse

from asyncua import Client, Server, ua
from asyncua.client.ua_client import UaClientState
from asyncua.common.subscription import Subscription

from src.proto.opcua.core.connection_observer import ConnectionObserver, ObservedServer
from src.proto.opcua.core.diagnostics import CallLog, observed
from src.proto.opcua.core.model import validate_variable
from src.proto.opcua.core.security import UaUsers, certificate_info, configure_client, configure_server
from src.proto.opcua.core.server_observer import ObservedInternalServer
from src.proto.opcua.core.types import _json_value, value_snapshot
from src.proto.opcua.core.values import sdk_value

MAX_BROWSE_REFERENCES = 10000
MAX_BROWSE_REQUESTS = 100


async def _node_capabilities(node) -> dict:
    node_class = await node.read_node_class()
    result = {
        "node_id": node.nodeid.to_string(),
        "browse_name": (await node.read_browse_name()).Name,
        "node_class": node_class.name,
        "history_read": False,
        "historizing": False,
        "event_notifier": False,
    }
    if node_class == ua.NodeClass.Variable:
        result["data_type"] = (await node.read_data_type_as_variant_type()).name
        result["history_read"] = (
            ua.AccessLevel.HistoryRead in await node.get_access_level()
            and ua.AccessLevel.HistoryRead in await node.get_user_access_level()
        )
        result["historizing"] = (await node.read_attribute(ua.AttributeIds.Historizing)).Value.Value
    elif node_class in {ua.NodeClass.Object, ua.NodeClass.View}:
        result["event_notifier"] = ua.EventNotifier.SubscribeToEvents in await node.read_event_notifier()
    return result


async def _browse_page(node, limit: int, offset: int) -> dict[str, Any]:
    if not 1 <= limit <= 500 or not 0 <= offset <= 100000:
        raise ValueError("浏览分页参数超出范围")
    session = node.session
    description = ua.BrowseDescription(
        NodeId=node.nodeid,
        BrowseDirection=ua.BrowseDirection.Forward,
        ReferenceTypeId=ua.NodeId(ua.ObjectIds.HierarchicalReferences),
        IncludeSubtypes=True,
        ResultMask=ua.BrowseResultMask.All,
    )
    parameters = ua.BrowseParameters(NodesToBrowse=[description], RequestedMaxReferencesPerNode=500)
    parameters.View.Timestamp = ua.get_win_epoch()
    references = []
    continuation = None
    try:
        async with asyncio.timeout(10):
            results = await session.browse(parameters)
            for request_index in range(MAX_BROWSE_REQUESTS):
                if len(results) != 1:
                    raise ValueError("远端 Browse 响应条数不匹配")
                page = results[0]
                continuation = page.ContinuationPoint
                page.StatusCode.check()
                if len(references) + len(page.References) > MAX_BROWSE_REFERENCES:
                    raise ValueError(f"单层浏览超过 {MAX_BROWSE_REFERENCES} 个引用，请缩小起始节点")
                references.extend(page.References)
                if not continuation:
                    break
                if request_index == MAX_BROWSE_REQUESTS - 1:
                    raise ValueError("远端 Browse continuation 次数超出上限")
                results = await session.browse_next(
                    ua.BrowseNextParameters(
                        ContinuationPoints=[continuation],
                        ReleaseContinuationPoints=False,
                    )
                )
    finally:
        if continuation:
            with suppress(Exception):
                async with asyncio.timeout(1):
                    await session.browse_next(
                        ua.BrowseNextParameters(
                            ContinuationPoints=[continuation],
                            ReleaseContinuationPoints=True,
                        )
                    )
    result = []
    for reference in references[offset : offset + limit]:
        result.append(
            {
                "node_id": reference.NodeId.to_string(),
                "browse_name": reference.BrowseName.Name,
                "display_name": reference.DisplayName.Text,
                "node_class": reference.NodeClass.name,
            }
        )
    return {
        "nodes": result,
        "total": len(references),
        "offset": offset,
        "limit": limit,
        "has_more": offset + len(result) < len(references),
    }


async def discover_endpoints(endpoint_url: str) -> list[dict]:
    import base64

    client = Client(validate_endpoint(endpoint_url), timeout=5)
    endpoints = await client.connect_and_get_server_endpoints()
    return [
        {
            "endpoint_url": item.EndpointUrl,
            "security_mode": item.SecurityMode.name,
            "security_policy": item.SecurityPolicyUri,
            "application_uri": item.Server.ApplicationUri,
            "identity_tokens": [token.TokenType.name for token in item.UserIdentityTokens],
            "certificate": base64.b64encode(item.ServerCertificate).decode() if item.ServerCertificate else None,
            "certificate_info": certificate_info(item.ServerCertificate) if item.ServerCertificate else None,
        }
        for item in endpoints
    ]


class _RevisionSession:
    """Public SDK services adapter capturing the actual server revisions."""

    def __init__(self, session):
        self.session = session
        self.results = []

    def __getattr__(self, name):
        return getattr(self.session, name)

    async def create_monitored_items(self, parameters):
        self.results = await self.session.create_monitored_items(parameters)
        return self.results


class _ValueHandler:
    def __init__(self, callback, subscription_id):
        self.callback = callback
        self.subscription_id = subscription_id

    async def datachange_notification(self, node, value, data):
        await self.callback(
            {"subscription": self.subscription_id, **value_snapshot(node.nodeid.to_string(), data.monitored_item.Value)}
        )

    async def status_change_notification(self, status):
        await self.callback(
            {"subscription": self.subscription_id, "node_id": None, "status_code": status.Status.name, "value": None}
        )


def event_snapshot(event) -> dict:
    fields = {}
    for key in (
        "EventId",
        "EventType",
        "SourceNode",
        "SourceName",
        "Time",
        "ReceiveTime",
        "Severity",
        "Message",
        "ConditionId",
        "AckedState",
        "Retain",
    ):
        value = getattr(event, key, None)
        if isinstance(value, ua.Variant):
            value = value.Value
        if value is None:
            continue
        if isinstance(value, ua.NodeId):
            value = value.to_string()
        elif isinstance(value, ua.LocalizedText):
            value = value.Text
        fields[key] = _json_value(value)
    return fields


class _EventHandler:
    def __init__(self, callback):
        self.callback = callback

    async def event_notification(self, event):
        await self.callback(event_snapshot(event))


def validate_endpoint(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "opc.tcp" or not parsed.hostname or not parsed.port:
        raise ValueError("OPC UA Endpoint 必须是带端口的 opc.tcp:// URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("OPC UA Endpoint 不允许凭据、查询参数或片段")
    return url


def loopback_endpoint(url: str) -> str:
    """M1 permits NoSecurity only on an isolated loopback endpoint."""
    parsed = urlparse(url)
    if parsed.scheme != "opc.tcp" or not parsed.hostname or not parsed.port:
        raise ValueError("OPC UA Endpoint 必须是带端口的 opc.tcp:// URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("OPC UA Endpoint 不允许凭据、查询参数或片段")
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError as exc:
        raise ValueError("M1 无安全模式只允许 loopback IP 地址") from exc
    if not address.is_loopback:
        raise ValueError("M1 无安全模式只允许 loopback IP 地址")
    return url


def make_endpoint_url(host: str, port: int, path: str = "/ems/") -> str:
    if not host or not port or not 1 <= port <= 65535:
        raise ValueError("OPC UA 地址和端口必须有效")
    authority = f"[{host}]" if ":" in host and not host.startswith("[") else host
    return f"opc.tcp://{authority}:{port}{path}"


class UaClientCore:
    def __init__(
        self,
        endpoint_url: str,
        timeout_ms: int = 3000,
        *,
        security: dict | None = None,
        credentials: dict | None = None,
        rejected=None,
        runtime: dict | None = None,
    ):
        self.security = security or {}
        self.credentials = credentials or {}
        self.rejected = rejected
        self.endpoint_url = (
            loopback_endpoint(endpoint_url)
            if self.security.get("mode", "None") == "None"
            else validate_endpoint(endpoint_url)
        )
        self.timeout_ms = timeout_ms
        self.runtime = runtime or {}
        self._client: Client | None = None
        self.connection_error: str | None = None
        self._namespace_indexes: dict[str, int] = {}
        self._subscriptions: list[Subscription] = []
        self._event_subscription = None
        self.generation = 0
        self.diagnostics = CallLog()

    @property
    def running(self) -> bool:
        return self._client is not None and self._client.uaclient.state is UaClientState.CONNECTED

    async def start(self) -> None:
        if self.running:
            return
        if self._client is not None:
            await self.stop()
        client = Client(
            self.endpoint_url,
            timeout=self.runtime.get("command_timeout_ms", self.timeout_ms) / 1000,
            auto_reconnect=False,
        )
        client.session_timeout = self.runtime.get("session_timeout_ms", 3600000)
        client.secure_channel_timeout = self.runtime.get("secure_channel_lifetime_ms", 3600000)
        client.connection_lost_callback = self._connection_lost
        try:
            async with asyncio.timeout(self.timeout_ms / 1000):
                await configure_client(client, self.security, self.credentials, self.rejected)
                await client.connect()
        except BaseException:
            await client.disconnect()
            raise
        self._client = client
        self.connection_error = None
        self.generation += 1
        self.diagnostics.started_at = datetime.now(UTC).isoformat()

    async def _connection_lost(self, exc: Exception) -> None:
        self.connection_error = str(exc) or "OPC UA 连接已断开"

    async def reconnect(self) -> None:
        await self.stop()
        await self.start()

    async def clear_subscriptions(self) -> None:
        subscriptions, self._subscriptions = self._subscriptions, []
        for subscription in subscriptions:
            with suppress(Exception):
                await asyncio.wait_for(subscription.delete(), 1)

    @observed("CreateSubscription")
    async def create_subscription(self, config: dict, callback) -> dict:
        if not self.running:
            raise RuntimeError("OPC UA 客户端尚未连接")
        parameters = ua.CreateSubscriptionParameters(
            RequestedPublishingInterval=config["publishing_interval_ms"],
            RequestedLifetimeCount=config["lifetime_count"],
            RequestedMaxKeepAliveCount=config["keepalive_count"],
            MaxNotificationsPerPublish=1000,
            PublishingEnabled=True,
        )
        session = _RevisionSession(self._client.uaclient.session)
        subscription = Subscription(session, parameters, _ValueHandler(callback, config["id"]), queue_maxsize=1000)
        result = await subscription.init()
        self._subscriptions.append(subscription)
        states = []
        for index, item in enumerate(config["items"], 1):
            try:
                node_id = item["node_id"]
                if item.get("namespace_uri"):
                    node_id = await self.resolve_node_id(item["namespace_uri"], node_id)
                request = ua.MonitoredItemCreateRequest(
                    ItemToMonitor=ua.ReadValueId(NodeId=self._node(node_id).nodeid, AttributeId=ua.AttributeIds.Value),
                    MonitoringMode=ua.MonitoringMode[item["mode"]],
                    RequestedParameters=ua.MonitoringParameters(
                        ClientHandle=index,
                        SamplingInterval=item["sampling_interval_ms"],
                        QueueSize=item["queue_size"],
                        DiscardOldest=True,
                        Filter=ua.DataChangeFilter(
                            Trigger=ua.DataChangeTrigger.StatusValueTimestamp,
                            DeadbandType=ua.DeadbandType.Absolute,
                            DeadbandValue=item["deadband"],
                        ),
                    ),
                )
                await subscription.create_monitored_items([request])
                revised = session.results[0]
                states.append(
                    {
                        "node_id": node_id,
                        "requested": item,
                        "status_code": revised.StatusCode.name,
                        "monitored_item_id": revised.MonitoredItemId,
                        "sampling_interval_ms": revised.RevisedSamplingInterval,
                        "queue_size": revised.RevisedQueueSize,
                    }
                )
            except Exception as exc:
                states.append({"node_id": item["node_id"], "status_code": str(exc), "requested": item})
        return {
            "id": config["id"],
            "running": True,
            "subscription_id": result.SubscriptionId,
            "publishing_interval_ms": result.RevisedPublishingInterval,
            "lifetime_count": result.RevisedLifetimeCount,
            "keepalive_count": result.RevisedMaxKeepAliveCount,
            "items": states,
        }

    async def stop(self) -> None:
        await self.clear_event_subscription()
        await self.clear_subscriptions()
        client, self._client = self._client, None
        self._namespace_indexes.clear()
        if client is not None:
            await client.disconnect()

    def _node(self, node_id: str):
        if not self.running:
            raise RuntimeError("OPC UA 客户端尚未连接")
        try:
            parsed = ua.NodeId.from_string(node_id)
        except ua.UaStringParsingError as exc:
            raise ValueError(f"无效的 OPC UA NodeId: {node_id}") from exc
        return self._client.get_node(parsed)

    async def browse(self, node_id: str = "i=85", limit: int = 100) -> list[dict[str, Any]]:
        return (await self.browse_page(node_id, limit))["nodes"]

    @observed("Browse")
    async def browse_page(self, node_id: str = "i=85", limit: int = 100, offset: int = 0) -> dict[str, Any]:
        return await _browse_page(self._node(node_id), limit, offset)

    async def resolve_node_id(self, namespace_uri: str, node_id: str) -> str:
        if not self.running or self._client is None:
            raise RuntimeError("OPC UA 客户端尚未连接")
        parsed = self._node(node_id).nodeid
        if namespace_uri not in self._namespace_indexes:
            try:
                self._namespace_indexes[namespace_uri] = await self._client.get_namespace_index(namespace_uri)
            except ValueError as exc:
                raise ValueError(f"远端服务器未声明命名空间 URI: {namespace_uri}") from exc
        return ua.NodeId(parsed.Identifier, self._namespace_indexes[namespace_uri], parsed.NodeIdType).to_string()

    @observed("Read")
    async def read(self, node_id: str) -> dict[str, Any]:
        value = await self._node(node_id).read_data_value(raise_on_bad_status=False)
        return value_snapshot(node_id, value)

    async def clear_event_subscription(self) -> None:
        subscription, self._event_subscription = self._event_subscription, None
        if subscription:
            with suppress(Exception):
                await asyncio.wait_for(subscription.delete(), 1)

    async def subscribe_events(self, config: dict, callback) -> None:
        await self.clear_event_subscription()
        subscription = await self._client.create_subscription(100, _EventHandler(callback), queue_maxsize=1000)
        self._event_subscription = subscription
        for source in config.get("source_nodes") or [config["source_node"]]:
            handle = await subscription.subscribe_events(self._node(source), self._node(config["event_type"]))
            if isinstance(handle, ua.StatusCode):
                handle.check()

    async def node_capabilities(self, node_id: str) -> dict:
        return await _node_capabilities(self._node(node_id))

    @observed("HistoryRead")
    async def read_history(
        self,
        node_id: str,
        start: datetime,
        end: datetime,
        limit: int,
        continuation: str | None = None,
        release: bool = False,
        *,
        mode: str = "raw",
        aggregate: str = "Average",
        processing_interval_ms: float = 1000,
        timestamps: str = "Both",
        return_bounds: bool = False,
    ) -> dict:
        import base64
        from datetime import timedelta
        import hashlib
        import json

        if not 1 <= limit <= 500 or start.tzinfo is None or end.tzinfo is None or start >= end:
            raise ValueError("历史查询必须指定有效的带时区时间范围和 1–500 条记录")
        token = base64.b64decode(continuation, validate=True) if continuation else None
        if token and len(token) > 4096:
            raise ValueError("历史 continuation 过大")
        node = self._node(node_id)
        details = ua.ReadRawModifiedDetails(
            IsReadModified=False,
            StartTime=start.astimezone(UTC),
            EndTime=end.astimezone(UTC),
            NumValuesPerNode=limit,
            ReturnBounds=return_bounds,
        )
        window_start, window_end, signature = start.astimezone(UTC), end.astimezone(UTC), None
        if mode == "processed":
            if (
                aggregate not in {"Average", "Minimum", "Maximum", "Count", "Total"}
                or not 50 <= processing_interval_ms <= 3600000
            ):
                raise ValueError("聚合函数或处理间隔无效")
            # ReadProcessed has no NumValuesPerNode. Bound each request by the
            # number of processing intervals, preserving native continuation points.
            signature = hashlib.sha256(
                json.dumps(
                    [node_id, start.isoformat(), end.isoformat(), aggregate, processing_interval_ms, limit, timestamps]
                ).encode()
            ).hexdigest()
            if token:
                try:
                    cursor = json.loads(token)
                    if cursor["query"] != signature:
                        raise ValueError("聚合 continuation 与查询不匹配")
                    window_start = datetime.fromisoformat(cursor["start"])
                    if window_start.tzinfo is None or not start <= window_start < end:
                        raise ValueError("聚合 continuation 时间无效")
                    token = base64.b64decode(cursor["native"], validate=True) if cursor["native"] else None
                except (KeyError, TypeError, json.JSONDecodeError) as exc:
                    raise ValueError("聚合 continuation 无效") from exc
            if release and token is None:
                return {"values": [], "continuation": None, "status_code": "Good"}
            window_end = min(window_start + timedelta(milliseconds=processing_interval_ms * limit), end)
            details = ua.ReadProcessedDetails(
                StartTime=window_start,
                EndTime=window_end,
                ProcessingInterval=processing_interval_ms,
                AggregateType=[ua.NodeId(getattr(ua.ObjectIds, f"AggregateFunction_{aggregate}"))],
            )
        elif mode != "raw":
            raise ValueError("历史读取模式无效")
        if timestamps not in {"Source", "Server", "Both", "Neither"}:
            raise ValueError("时间戳选项无效")
        params = ua.HistoryReadParameters(
            HistoryReadDetails=details,
            TimestampsToReturn=ua.TimestampsToReturn[timestamps],
            ReleaseContinuationPoints=release,
            NodesToRead=[ua.HistoryReadValueId(NodeId=node.nodeid, ContinuationPoint=token)],
        )
        result = (await node.session.history_read(params))[0]
        result.StatusCode.check()
        values = [] if release else [value_snapshot(node_id, item) for item in result.HistoryData.DataValues]
        for value in values:
            if timestamps not in {"Source", "Both"}:
                value["source_timestamp"] = None
            if timestamps not in {"Server", "Both"}:
                value["server_timestamp"] = None
        next_token = result.ContinuationPoint if not release else None
        if mode == "processed" and not release and (next_token or window_end < end):
            next_token = json.dumps(
                {
                    "query": signature,
                    "start": (window_start if next_token else window_end).isoformat(),
                    "native": base64.b64encode(next_token).decode() if next_token else None,
                }
            ).encode()
        return {
            "values": values,
            "continuation": base64.b64encode(next_token).decode() if next_token else None,
            "status_code": result.StatusCode.name,
        }

    @observed("Write")
    async def write(self, node_id: str, value: Any) -> dict[str, Any]:
        node = self._node(node_id)
        variant_type = await node.read_data_type_as_variant_type()
        rank = await node.read_value_rank()
        value = sdk_value(variant_type.name, value, 1 if isinstance(value, list) and rank != -1 else -1)
        await node.write_value(value, variant_type)
        return await self.read(node_id)


class UaServerCore:
    def __init__(
        self,
        bind_host: str,
        port: int,
        namespace_uri: str,
        *,
        endpoint_path: str = "/ems/",
        definitions: list[dict[str, Any]] | None = None,
        security: dict | None = None,
        credentials: dict | None = None,
        rejected=None,
        connection_observer: ConnectionObserver | None = None,
        runtime: dict | None = None,
    ):
        self.connection_observer = connection_observer
        self.runtime = runtime or {}
        self.security = security or {}
        self.credentials = credentials or {}
        self.rejected = rejected
        self.bind_host = bind_host
        self.port = port
        self.namespace_uri = namespace_uri
        self.endpoint_path = endpoint_path
        self.definitions = list(definitions or [])
        self._server: Server | None = None
        self._namespace_index: int | None = None
        self.node_count = 0
        self._guards: dict[str, bool] = {}
        self._internal_write = ContextVar("opcua_internal_write", default=False)
        self.diagnostics = CallLog()
        self._event_generator = None
        self._history_storage = None
        self._history_nodes: list[str] = []
        self._live_definitions: dict[str, dict] = {}

    @property
    def running(self) -> bool:
        return self._server is not None

    @property
    def endpoint_url(self) -> str:
        return make_endpoint_url(self.security.get("advertised_host") or self.bind_host, self.port, self.endpoint_path)

    async def start(self) -> None:
        if self._server is not None:
            return
        if self.security.get("mode", "None") == "None":
            loopback_endpoint(make_endpoint_url(self.bind_host, self.port, self.endpoint_path))
            loopback_endpoint(self.endpoint_url)
        internal_server = ObservedInternalServer(self.diagnostics, UaUsers(self.security, self.credentials))
        server = (
            ObservedServer(iserver=internal_server, observer=self.connection_observer)
            if self.connection_observer is not None
            else Server(iserver=internal_server)
        )
        try:
            await server.init()
            server.set_server_name(self.runtime.get("server_name", "EMS Simulate OPC UA"))
            server.set_endpoint(self.endpoint_url)
            server.socket_address = (self.bind_host, self.port)
            await configure_server(server, self.security, self.credentials, self.rejected)
            namespace_index = await server.register_namespace(self.namespace_uri)
            await self._install(server, namespace_index, self.definitions)
            await server.start()
        except BaseException:
            await server.stop()
            raise
        self._server = server
        self._namespace_index = namespace_index
        self._live_definitions = {item["node_id"]: dict(item) for item in self.definitions}
        self.node_count = len(self.definitions)
        self.diagnostics.started_at = datetime.now(UTC).isoformat()

    async def _install(self, server: Server, namespace_index: int, definitions: list[dict[str, Any]]) -> None:
        for raw in definitions:
            definition = validate_variable(raw)
            if raw.get("namespace_uri", self.namespace_uri) != self.namespace_uri:
                raise ValueError("节点定义与服务端命名空间 URI 不一致")
            node_id = ua.NodeId.from_string(definition["node_id"])
            node_id.NamespaceIndex = namespace_index
            variable = await server.nodes.objects.add_variable(
                node_id,
                ua.QualifiedName(definition["browse_name"], namespace_index),
                sdk_value(definition["data_type"], definition["initial_value"]),
                varianttype=ua.VariantType[definition["data_type"]],
            )
            if definition["writable"]:
                await variable.set_writable()

    def _node(self, node_id: str):
        if self._server is None:
            raise ValueError("OPC UA 服务端尚未启动")
        try:
            return self._server.get_node(ua.NodeId.from_string(node_id))
        except ua.UaStringParsingError as exc:
            raise ValueError(f"无效的 OPC UA NodeId: {node_id}") from exc

    @observed("Browse")
    async def browse_page(self, node_id: str = "i=85", limit: int = 100, offset: int = 0) -> dict:
        return await _browse_page(self._node(node_id), limit, offset)

    @observed("Read")
    async def node_capabilities(self, node_id: str) -> dict:
        return await _node_capabilities(self._node(node_id))

    async def inspect_node(self, node_id: str) -> dict:
        node = self._node(node_id)
        node_class = await node.read_node_class()
        browse_name = await node.read_browse_name()
        description = await node.read_description()
        namespaces = await self._server.get_namespace_array()
        result = {
            "node_id": node_id,
            "browse_name": browse_name.Name,
            "display_name": (await node.read_display_name()).Text,
            "node_class": node_class.name,
            "description": description.Text,
            "namespace_uri": namespaces[node.nodeid.NamespaceIndex],
            "data_type": None,
            "value_rank": None,
            "array_dimensions": None,
            "writable": False,
            "type_definition": None,
        }
        type_definition = await node.read_type_definition()
        if type_definition is not None:
            result["type_definition"] = (await self._server.get_node(type_definition).read_browse_name()).Name
        if node_class == ua.NodeClass.Variable:
            data_type = self._server.get_node(await node.read_data_type())
            result.update(
                data_type=(await data_type.read_browse_name()).Name,
                value_rank=await node.read_value_rank(),
                array_dimensions=await node.read_array_dimensions(),
                writable=ua.AccessLevel.CurrentWrite in await node.get_access_level(),
            )
        references = await node.get_references()
        result["references"] = [
            {
                "node_id": ref.NodeId.to_string(),
                "browse_name": ref.BrowseName.Name,
                "node_class": ref.NodeClass.name,
                "reference_type": ref.ReferenceTypeId.to_string(),
                "forward": ref.IsForward,
            }
            for ref in references[:500]
        ]
        result["references_truncated"] = len(references) > 500
        return result

    @observed("Write")
    async def write(self, node_id: str, value: Any) -> dict:
        node = self._node(node_id)
        if ua.AccessLevel.CurrentWrite not in await node.get_access_level():
            raise ValueError("该变量不允许写入")
        variant_type = await node.read_data_type_as_variant_type()
        rank = await node.read_value_rank()
        value = sdk_value(variant_type.name, value, 1 if isinstance(value, list) and rank != -1 else -1)
        await node.write_value(value, variant_type)
        return await self.read(node_id)

    async def install_variables(self, definitions: list[dict[str, Any]]) -> None:
        if self._server is None or self._namespace_index is None:
            raise RuntimeError("OPC UA 服务端尚未启动")
        await self._install(self._server, self._namespace_index, definitions)
        self.node_count += len(definitions)
        self._live_definitions.update({item["node_id"]: dict(item) for item in definitions})

    def validate_variable_changes(self, definitions: list[dict]) -> None:
        for definition in definitions:
            validate_variable(definition)
            if definition.get("namespace_uri", self.namespace_uri) != self.namespace_uri:
                raise ValueError("在线更新不能改变命名空间 URI")
            old = self._live_definitions.get(definition["node_id"])
            if old and old["data_type"] != definition["data_type"]:
                raise ValueError(f"节点 {definition['node_id']} 的数据类型变化需要先停止该 OPC UA 通道")

    async def sync_variables(self, definitions: list[dict]) -> None:
        """Apply node differences; initial values are defaults, not live writes."""
        self.validate_variable_changes(definitions)
        desired = {item["node_id"]: dict(item) for item in definitions}
        old = dict(self._live_definitions)
        removed_values = {key: await self._node(key).read_data_value() for key in old.keys() - desired.keys()}
        try:
            for key in old.keys() - desired.keys():
                await self._server.delete_nodes([self._node(key)])
            for key, definition in desired.items():
                if key not in old:
                    await self._install(self._server, self._namespace_index, [definition])
                elif any(old[key][field] != definition[field] for field in ("browse_name", "writable")):
                    await self._update_variable(definition)
        except BaseException:
            for key in desired.keys() - old.keys():
                with suppress(Exception):
                    await self._server.delete_nodes([self._node(key)])
            for key, definition in old.items():
                if key in removed_values:
                    with suppress(Exception):
                        await self._install(self._server, self._namespace_index, [definition])
                    await self._node(key).write_value(removed_values[key])
                else:
                    await self._update_variable(definition)
            raise
        self._live_definitions = desired
        self.node_count = len(desired)

    async def _update_variable(self, definition: dict) -> None:
        node = self._node(definition["node_id"])
        await node.write_attribute(
            ua.AttributeIds.BrowseName,
            ua.DataValue(ua.Variant(ua.QualifiedName(definition["browse_name"], self._namespace_index))),
        )
        await node.write_attribute(
            ua.AttributeIds.DisplayName, ua.DataValue(ua.Variant(ua.LocalizedText(definition["browse_name"])))
        )
        await node.set_writable(definition["writable"])

    async def guard_simulation(self, node_id: str, policy: str, pause) -> None:
        node = self._server.get_node(node_id)
        writable = ua.AccessLevel.CurrentWrite in await node.get_access_level()
        self._guards[node_id] = writable
        if policy == "reject":
            await node.set_writable(False)

        def setter(node_data, attribute, value):
            if policy == "pause" and not self._internal_write.get():
                pause(node_id)
            node_data.attributes[attribute].value = value

        self._server.set_attribute_value_setter(node.nodeid, setter)

    async def clear_simulation_guards(self) -> None:
        if self._server:
            for node_id, writable in self._guards.items():
                node = self._server.get_node(node_id)
                self._server.set_attribute_value_setter(node.nodeid, None)
                await node.set_writable(writable)
        self._guards.clear()

    async def write_simulated(self, node_id: str, value: Any) -> dict:
        node = self._server.get_node(node_id)
        data_type = await node.read_data_type_as_variant_type()
        token = self._internal_write.set(True)
        try:
            await node.write_value(
                ua.DataValue(
                    ua.Variant(sdk_value(data_type.name, value), data_type),
                    SourceTimestamp=datetime.now(UTC),
                )
            )
        finally:
            self._internal_write.reset(token)
        return await self.read(node_id)

    async def enable_history(self, config: dict, path: str) -> None:
        from datetime import timedelta

        from src.proto.opcua.core.history_storage import UaHistorySQLite

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        for node_id in config["nodes"]:
            if await self._node(node_id).read_node_class() != ua.NodeClass.Variable:
                raise ValueError(f"历史记录节点不是变量: {node_id}")
        if self._history_storage is None:
            storage = UaHistorySQLite(path, max_history_data_response_size=501)
            await storage.init()
            self._server.iserver.history_manager.set_storage(storage)
            self._history_storage = storage
        for node_id in config["nodes"]:
            await self._server.historize_node_data_change(
                self._server.get_node(node_id), timedelta(days=config["retention_days"]), config["max_values"]
            )
            self._history_nodes.append(node_id)

    async def disable_history(self) -> None:
        if self._server:
            for node_id in self._history_nodes:
                await self._server.dehistorize_node_data_change(self._node(node_id))
        self._history_nodes = []

    async def enable_events(self, config: dict) -> None:
        generators = {}
        for source in config.get("source_nodes") or [config["source_node"]]:
            node = self._server.get_node(source)
            if await node.read_node_class() != ua.NodeClass.Object:
                raise ValueError("事件源必须是 Object 节点")
            generators[source] = await self._server.get_event_generator(
                self._server.get_node(config["event_type"]), node.nodeid
            )
        self._event_generator = generators

    async def emit_event(self, message: str, severity: int, source_node: str | None = None) -> dict:
        if self._event_generator is None:
            raise ValueError("服务端事件功能未启用")
        generator = (
            self._event_generator.get(source_node) if source_node else next(iter(self._event_generator.values()), None)
        )
        if generator is None:
            raise ValueError("该事件源尚未启用")
        generator.event.Severity = severity
        await generator.trigger(message=message)
        return event_snapshot(generator.event)

    async def disable_events(self) -> None:
        self._event_generator = None

    async def reset_variables(self, definitions: list[dict[str, Any]]) -> int:
        if self._server is None:
            raise ValueError("OPC UA 服务端尚未启动")
        normalized = [validate_variable(item) for item in definitions]
        for definition in normalized:
            node = self._server.get_node(definition["node_id"])
            await node.write_value(
                sdk_value(definition["data_type"], definition["initial_value"]), ua.VariantType[definition["data_type"]]
            )
        return len(normalized)

    async def export_nodeset(self) -> bytes:
        if self._server is None or self._namespace_index is None:
            raise ValueError("请先启动服务端再导出 NodeSet XML")
        with TemporaryDirectory(prefix="ems_opcua_export_") as directory:
            path = Path(directory) / "model.xml"
            await self._server.export_xml_by_ns(str(path), [self._namespace_index], export_values=True)
            return path.read_bytes()

    @observed("Read")
    async def read(self, node_id: str) -> dict[str, Any]:
        if self._server is None:
            raise RuntimeError("OPC UA 服务端尚未启动")
        try:
            node = self._server.get_node(ua.NodeId.from_string(node_id))
        except ua.UaStringParsingError as exc:
            raise ValueError(f"无效的 OPC UA NodeId: {node_id}") from exc
        value = await node.read_data_value(raise_on_bad_status=False)
        return value_snapshot(node_id, value)

    async def stop(self) -> None:
        server, self._server = self._server, None
        self._namespace_index = None
        self.node_count = 0
        self._event_generator = None
        self._history_nodes = []
        self._history_storage = None
        self._live_definitions = {}
        if server is not None:
            await server.stop()
