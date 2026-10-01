"""EMS protocol lifecycle adapters for the native asynchronous UA cores."""

from __future__ import annotations

from typing import Any

from src.device.protocol.base_handler import ProtocolHandler
from src.enums.points.base_point import BasePoint
from src.proto.opcua.client import OpcUaClient
from src.proto.opcua.core.transport import make_endpoint_url
from src.proto.opcua.server import OpcUaServer


class _OpcUaHandler(ProtocolHandler):
    def __init__(self, log=None):
        super().__init__()
        self.log = log
        self.last_error: str | None = None

    def read_value(self, point: BasePoint) -> Any:
        raise NotImplementedError("OPC UA 使用 NodeId 的异步读取接口")

    def write_value(self, point: BasePoint, value: Any) -> bool:
        raise NotImplementedError("OPC UA 使用 NodeId 的异步写入接口")

    def add_points(self, points: list[BasePoint]) -> None:
        if points:
            raise ValueError("OPC UA 节点不能写入旧四遥测点表")

    def clear_captured_messages(self) -> None:
        pass

    def _failed(self, exc: Exception) -> bool:
        self.last_error = str(exc)
        self._is_running = False
        if self.log:
            self.log.error(f"OPC UA 启动失败: {exc}")
        return False


class OpcUaClientHandler(_OpcUaHandler):
    def __init__(self, log=None):
        super().__init__(log)
        self.client: OpcUaClient | None = None

    @property
    def is_running(self) -> bool:
        return self._is_running and self.client is not None and self.client.running

    def initialize(self, config: dict[str, Any]) -> None:
        self._config = config
        runtime = config.get("runtime") or {}
        opcua = config.get("opcua") or {}
        endpoint = opcua.get("endpoint_url") or make_endpoint_url(config["ip"], config["port"])
        self.client = OpcUaClient(
            endpoint, runtime.get("connect_timeout_ms", 3000), channel_id=int(config.get("channel_id") or 0)
        )

    async def start(self) -> bool:
        if self.is_running:
            return True
        if self.client is None:
            return self._failed(RuntimeError("OPC UA 客户端未初始化"))
        try:
            await self.client.start()
            self._is_running = True
            self.last_error = None
            return True
        except Exception as exc:
            return self._failed(exc)

    async def stop(self) -> bool:
        self._is_running = False
        if self.client is not None:
            await self.client.stop()
        return True

    async def browse(self, node_id: str = "i=85", limit: int = 100) -> list[dict[str, Any]]:
        if self.client is None:
            raise RuntimeError("OPC UA 客户端未初始化")
        return await self.client.browse(node_id, limit)

    async def browse_page(self, node_id: str = "i=85", limit: int = 100, offset: int = 0) -> dict[str, Any]:
        if self.client is None:
            raise RuntimeError("OPC UA 客户端未初始化")
        return await self.client.browse_page(node_id, limit, offset)

    async def read(self, node_id: str) -> dict[str, Any]:
        if self.client is None:
            raise RuntimeError("OPC UA 客户端未初始化")
        return await self.client.read(node_id)

    async def write(self, node_id: str, value: bool | int | float) -> dict[str, Any]:
        if self.client is None:
            raise RuntimeError("OPC UA 客户端未初始化")
        return await self.client.write(node_id, value)


class OpcUaServerHandler(_OpcUaHandler):
    def __init__(self, log=None):
        super().__init__(log)
        self.server: OpcUaServer | None = None

    @property
    def is_running(self) -> bool:
        return self._is_running and self.server is not None and self.server.running

    def initialize(self, config: dict[str, Any]) -> None:
        self._config = config
        from src.data.service.opcua_node_service import OpcUaNodeService

        opcua = config.get("opcua") or {}
        channel_id = int(config.get("channel_id") or 0)
        namespace_uri = opcua.get("namespace_uri") or f"urn:ems-simulate:channel:{channel_id}"
        definitions = OpcUaNodeService.list_nodes(channel_id) if channel_id else []
        self.server = OpcUaServer(
            config["ip"],
            int(config["port"]),
            namespace_uri,
            endpoint_path=opcua.get("endpoint_path", "/ems/"),
            definitions=definitions,
            channel_id=channel_id,
        )

    async def start(self) -> bool:
        if self.is_running:
            return True
        if self.server is None:
            return self._failed(RuntimeError("OPC UA 服务端未初始化"))
        try:
            await self.server.start()
            self._is_running = True
            self.last_error = None
            return True
        except Exception as exc:
            return self._failed(exc)

    async def stop(self) -> bool:
        self._is_running = False
        if self.server is not None:
            await self.server.stop()
        return True
