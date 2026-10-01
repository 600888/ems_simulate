"""The only layer that owns asyncua Client and Server instances."""

from __future__ import annotations

import asyncio
from contextlib import suppress
import ipaddress
import math
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from urllib.parse import urlparse

from asyncua import Client, Server, ua
from asyncua.client.ua_client import UaClientState

from src.proto.opcua.core.model import validate_variable
from src.proto.opcua.core.types import value_snapshot

MAX_BROWSE_REFERENCES = 10000
MAX_BROWSE_REQUESTS = 100


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
    def __init__(self, endpoint_url: str, timeout_ms: int = 3000):
        self.endpoint_url = loopback_endpoint(endpoint_url)
        self.timeout_ms = timeout_ms
        self._client: Client | None = None
        self.connection_error: str | None = None
        self._namespace_indexes: dict[str, int] = {}

    @property
    def running(self) -> bool:
        return self._client is not None and self._client.uaclient.state is UaClientState.CONNECTED

    async def start(self) -> None:
        if self.running:
            return
        if self._client is not None:
            await self.stop()
        client = Client(self.endpoint_url, timeout=self.timeout_ms / 1000, auto_reconnect=False)
        client.connection_lost_callback = self._connection_lost
        try:
            await client.connect()
        except BaseException:
            await client.disconnect()
            raise
        self._client = client
        self.connection_error = None

    async def _connection_lost(self, exc: Exception) -> None:
        self.connection_error = str(exc) or "OPC UA 连接已断开"

    async def stop(self) -> None:
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

    async def browse_page(self, node_id: str = "i=85", limit: int = 100, offset: int = 0) -> dict[str, Any]:
        if not 1 <= limit <= 500 or not 0 <= offset <= 100000:
            raise ValueError("浏览分页参数超出范围")
        node = self._node(node_id)
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

    async def read(self, node_id: str) -> dict[str, Any]:
        value = await self._node(node_id).read_data_value(raise_on_bad_status=False)
        return value_snapshot(node_id, value)

    async def write(self, node_id: str, value: bool | int | float) -> dict[str, Any]:
        node = self._node(node_id)
        variant_type = await node.read_data_type_as_variant_type()
        integer_types = {
            ua.VariantType.SByte,
            ua.VariantType.Byte,
            ua.VariantType.Int16,
            ua.VariantType.UInt16,
            ua.VariantType.Int32,
            ua.VariantType.UInt32,
            ua.VariantType.Int64,
            ua.VariantType.UInt64,
        }
        if variant_type == ua.VariantType.Boolean:
            if not isinstance(value, bool):
                raise ValueError("节点要求 Boolean 值")
        elif variant_type in integer_types:
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"节点要求 {variant_type.name} 整数")
            ranges = {
                ua.VariantType.SByte: (-128, 127),
                ua.VariantType.Byte: (0, 255),
                ua.VariantType.Int16: (-(2**15), 2**15 - 1),
                ua.VariantType.UInt16: (0, 2**16 - 1),
                ua.VariantType.Int32: (-(2**31), 2**31 - 1),
                ua.VariantType.UInt32: (0, 2**32 - 1),
                ua.VariantType.Int64: (-(2**63), 2**63 - 1),
                ua.VariantType.UInt64: (0, 2**64 - 1),
            }
            lower, upper = ranges[variant_type]
            if not lower <= value <= upper:
                raise ValueError(f"写入值超出 {variant_type.name} 范围")
        elif variant_type in {ua.VariantType.Float, ua.VariantType.Double}:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"节点要求 {variant_type.name} 数值")
            try:
                value = float(value)
            except OverflowError as exc:
                raise ValueError("写入值超出浮点数范围") from exc
            if not math.isfinite(value):
                raise ValueError("写入值必须是有限数值")
            if variant_type == ua.VariantType.Float and abs(value) > 3.4028234663852886e38:
                raise ValueError("写入值超出 Float 范围")
        else:
            raise ValueError(f"M1 暂不支持写入 {variant_type.name} 节点")
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
    ):
        self.bind_host = bind_host
        self.port = port
        self.namespace_uri = namespace_uri
        self.endpoint_path = endpoint_path
        self.definitions = list(definitions or [])
        self._server: Server | None = None
        self._namespace_index: int | None = None
        self.node_count = 0

    @property
    def running(self) -> bool:
        return self._server is not None

    @property
    def endpoint_url(self) -> str:
        return make_endpoint_url(self.bind_host, self.port, self.endpoint_path)

    async def start(self) -> None:
        if self._server is not None:
            return
        loopback_endpoint(self.endpoint_url)
        server = Server()
        try:
            await server.init()
            server.set_endpoint(self.endpoint_url)
            server.socket_address = (self.bind_host, self.port)
            server.set_security_policy([ua.SecurityPolicyType.NoSecurity])
            namespace_index = await server.register_namespace(self.namespace_uri)
            await self._install(server, namespace_index, self.definitions)
            await server.start()
        except BaseException:
            await server.stop()
            raise
        self._server = server
        self._namespace_index = namespace_index
        self.node_count = len(self.definitions)

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
                definition["initial_value"],
                varianttype=ua.VariantType[definition["data_type"]],
            )
            if definition["writable"]:
                await variable.set_writable()

    async def install_variables(self, definitions: list[dict[str, Any]]) -> None:
        if self._server is None or self._namespace_index is None:
            raise RuntimeError("OPC UA 服务端尚未启动")
        await self._install(self._server, self._namespace_index, definitions)
        self.node_count += len(definitions)

    async def reset_variables(self, definitions: list[dict[str, Any]]) -> int:
        if self._server is None:
            raise ValueError("OPC UA 服务端尚未启动")
        normalized = [validate_variable(item) for item in definitions]
        for definition in normalized:
            node = self._server.get_node(definition["node_id"])
            await node.write_value(definition["initial_value"], ua.VariantType[definition["data_type"]])
        return len(normalized)

    async def export_nodeset(self) -> bytes:
        if self._server is None or self._namespace_index is None:
            raise ValueError("请先启动服务端再导出 NodeSet XML")
        with TemporaryDirectory(prefix="ems_opcua_export_") as directory:
            path = Path(directory) / "model.xml"
            await self._server.export_xml_by_ns(str(path), [self._namespace_index], export_values=True)
            return path.read_bytes()

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
        if server is not None:
            await server.stop()
