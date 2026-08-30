"""IEC 60870-5-101 serial master/slave protocol handlers."""

from __future__ import annotations

import asyncio
from typing import Any

from src.device.protocol.base_handler import ClientHandler, ServerHandler
from src.device.protocol.iec60870_common import decode_point_value, resolve_asdu_type_code
from src.enums.point_data import Yc, Yk, Yt, Yx
from src.enums.points.base_point import BasePoint
from src.enums.points.change_tracker import ChangeSource, track_change
from src.enums.points.iec104_quality import IEC104QualityDescriptor
from src.proto.iec60870.asdu import ASDU, InformationObject


def _endpoint_options(config: dict[str, Any]) -> dict[str, Any]:
    runtime = config.get("runtime", {})
    common_addresses = [int(value) for value in config.get("slave_id_list", [])] or [1]
    configured_link_address = int(runtime.get("link_address", 1))
    link_addresses = [configured_link_address] if len(common_addresses) == 1 else common_addresses
    return {
        "port": config.get("serial_port", ""),
        "baudrate": int(config.get("baudrate", 9600)),
        "databits": int(config.get("databits", 8)),
        "stopbits": int(config.get("stopbits", 1)),
        "parity": str(config.get("parity", "E")),
        "link_addresses": link_addresses,
        "common_addresses": common_addresses,
        "link_address_size": int(runtime.get("link_address_size", 1)),
        "cause_size": int(runtime.get("cause_size", 2)),
        "common_address_size": int(runtime.get("common_address_size", 2)),
        "io_address_size": int(runtime.get("io_address_size", 3)),
        "response_timeout_ms": int(runtime.get("response_timeout_ms", 1000)),
        "balanced": runtime.get("link_mode", "unbalanced") == "balanced",
    }


class IEC101ServerHandler(ServerHandler):
    """IEC 101 controlled station (serial slave)."""

    def __init__(self, log=None):
        super().__init__()
        self._server = None
        self._log = log
        self._points: dict[tuple[int, int], BasePoint] = {}
        self._common_to_link: dict[int, int] = {}

    def initialize(self, config: dict[str, Any]) -> None:
        from src.proto.iec101.server import IEC101Slave

        self._config = config
        self._server = IEC101Slave(**_endpoint_options(config))
        self._common_to_link = dict(self._server.station_links)
        self._server.set_command_callback(self._on_command)
        self._configure_connection_monitoring(config, supported=False)

    async def start(self) -> bool:
        if not self._server:
            return False
        try:
            self._is_running = await asyncio.to_thread(self._server.start)
            return self._is_running
        except Exception as exc:
            if self._log:
                self._log.error(f"启动 IEC101 从站失败: {exc}")
            self._is_running = False
            return False

    async def stop(self) -> bool:
        if self._server:
            await asyncio.to_thread(self._server.stop)
        self._is_running = False
        return True

    def add_points(self, points: list[BasePoint]) -> None:
        if not self._server:
            return
        for point in points:
            common_address = int(point.rtu_addr or 1)
            io_address = int(point.address)
            self._points[(common_address, io_address)] = point
            self._server.add_point(
                common_address,
                io_address,
                resolve_asdu_type_code(point),
                lambda point=point: (point.value, point.iec_quality_value),
            )

    def _on_command(self, asdu: ASDU, obj: InformationObject) -> bool:
        point = self._points.get((asdu.common_address, obj.io_address))
        if point is None or not isinstance(point, (Yk, Yt, Yx, Yc)):
            return False
        try:
            point.value = decode_point_value(point, obj.value)
            return True
        except (TypeError, ValueError):
            return False

    def read_value(self, point: BasePoint) -> Any:
        return point.value

    def write_value(self, point: BasePoint, value: Any) -> bool:
        if not self._server:
            return False
        point.value = decode_point_value(point, value)
        self._server.queue_spontaneous(
            common_address=int(point.rtu_addr or 1),
            io_address=int(point.address),
            type_id=resolve_asdu_type_code(point),
            value=point.value,
            quality=point.iec_quality_value,
            link_address=self._common_to_link.get(int(point.rtu_addr or 1), int(point.rtu_addr or 1)),
        )
        return True

    def get_value_by_address(self, func_code: int, slave_id: int, address: int) -> Any:
        point = self._points.get((int(slave_id), int(address)))
        return None if point is None else point.value

    def set_value_by_address(self, func_code: int, slave_id: int, address: int, value: Any) -> None:
        point = self._points.get((int(slave_id), int(address)))
        if point:
            self.write_value(point, value)

    @property
    def server(self):
        return self._server

    def get_captured_messages(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._server.get_captured_messages(limit) if self._server else []

    def clear_captured_messages(self) -> None:
        if self._server:
            self._server.clear_captured_messages()


class IEC101ClientHandler(ClientHandler):
    """IEC 101 controlling station (serial master)."""

    def __init__(self, log=None):
        super().__init__()
        self._client = None
        self._log = log
        self._points: dict[tuple[int, int], BasePoint] = {}
        self._common_to_link: dict[int, int] = {}

    def initialize(self, config: dict[str, Any]) -> None:
        from src.proto.iec101.client import IEC101Master

        self._config = config
        runtime = config.get("runtime", {})
        self._client = IEC101Master(
            **_endpoint_options(config),
            poll_interval_ms=int(runtime.get("poll_interval_ms", 200)),
            general_interrogation_on_connect=bool(runtime.get("general_interrogation_on_connect", True)),
            originator_address=int(runtime.get("originator_address", 0)),
        )
        self._common_to_link = dict(self._client.station_links)
        self._client.set_asdu_callback(self._on_asdu)

    async def start(self) -> bool:
        return await self.connect()

    async def stop(self) -> bool:
        self.disconnect()
        return True

    async def connect(self) -> bool:
        if not self._client:
            return False
        try:
            self._is_running = await asyncio.to_thread(self._client.start)
            return self._is_running
        except Exception as exc:
            if self._log:
                self._log.error(f"启动 IEC101 主站失败: {exc}")
            self._is_running = False
            return False

    def disconnect(self) -> None:
        if self._client:
            self._client.stop()
        self._is_running = False

    def add_points(self, points: list[BasePoint]) -> None:
        for point in points:
            self._points[(int(point.rtu_addr or 1), int(point.address))] = point

    def _on_asdu(self, asdu: ASDU) -> None:
        for obj in asdu.objects:
            point = self._points.get((asdu.common_address, obj.io_address))
            if point is None or obj.value is None:
                continue
            try:
                with track_change(ChangeSource.CLIENT_READ, f"IEC101响应更新 {point.code}"):
                    point.value = decode_point_value(point, obj.value)
                point.iec_quality = IEC104QualityDescriptor.from_int(obj.quality)
                # 客户端表格会屏蔽未知/失败状态的值。被动接收总召唤、
                # 周期数据或主动上送后必须显式标记为有效。
                point.is_valid = True
            except (TypeError, ValueError):
                point.is_valid = False
                continue

    def read_value(self, point: BasePoint) -> Any:
        if not self._client or not self._is_running:
            return None
        value = self._client.cached_value(int(point.rtu_addr or 1), int(point.address))
        return None if value is None else decode_point_value(point, value)

    async def active_read_value_async(self, point: BasePoint) -> Any:
        if not self._client or not self._is_running:
            return None
        common_address = int(point.rtu_addr or 1)
        value = await asyncio.to_thread(
            self._client.read,
            common_address,
            int(point.address),
            self._common_to_link.get(common_address, common_address),
        )
        return None if value is None else decode_point_value(point, value)

    def write_value(self, point: BasePoint, value: Any) -> bool:
        if not self._client or not self._is_running:
            return False
        return self._client.command(
            common_address=int(point.rtu_addr or 1),
            io_address=int(point.address),
            type_id=resolve_asdu_type_code(point),
            value=value,
            link_address=self._common_to_link.get(int(point.rtu_addr or 1), int(point.rtu_addr or 1)),
        )

    async def write_value_async(self, point: BasePoint, value: Any) -> bool:
        return await asyncio.to_thread(self.write_value, point, value)

    async def send_interrogation(self) -> bool:
        if not self._client or not self._is_running:
            return False
        results = [
            await asyncio.to_thread(self._client.interrogate, common_address, link_address=link_address)
            for common_address, link_address in self._common_to_link.items()
        ]
        return all(results)

    @property
    def client(self):
        return self._client

    def get_captured_messages(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._client.get_captured_messages(limit) if self._client else []

    def clear_captured_messages(self) -> None:
        if self._client:
            self._client.clear_captured_messages()
