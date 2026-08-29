"""Connection-aware asyncio TCP client used by the DNP3 Master."""

from __future__ import annotations

import asyncio
from collections.abc import Callable


class TrackedTcpClient:
    def __init__(
        self,
        host: str,
        port: int,
        *,
        on_connect: Callable[[object, object], None] | None = None,
        on_activity: Callable[[str, int], None] | None = None,
        on_disconnect: Callable[[str, str | None], None] | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._on_connect = on_connect
        self._on_activity = on_activity
        self._on_disconnect = on_disconnect
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._receive_callback: Callable[[bytes], None] | None = None
        self._read_task: asyncio.Task[None] | None = None
        self._running = False

    @property
    def is_open(self) -> bool:
        """TCP 连接是否打开。"""
        return bool(self._writer and not self._writer.is_closing())

    def set_receive_callback(self, callback: Callable[[bytes], None]) -> None:
        """设置接收数据的回调函数。"""
        self._receive_callback = callback

    async def open(self, timeout_seconds: float) -> None:
        """在指定超时内建立 TCP 连接并启动接收循环。"""
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self._host, self._port),
            timeout=timeout_seconds,
        )
        self._running = True
        self._read_task = asyncio.create_task(self._read_loop())
        if self._on_connect:
            self._on_connect(self._writer.get_extra_info("peername"), self._writer.get_extra_info("sockname"))

    async def close(self) -> None:
        """关闭 TCP 连接并停止接收循环。"""
        self._running = False
        current = asyncio.current_task()
        if self._read_task and self._read_task is not current:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass
        self._read_task = None
        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except OSError:
                pass
        self._writer = None
        self._reader = None

    def send(self, data: bytes) -> None:
        """向对端写入数据并触发发送活动回调。"""
        if not self.is_open:
            raise ConnectionError("DNP3 TCP connection is not open")
        assert self._writer is not None
        self._writer.write(data)
        if self._on_activity:
            self._on_activity("tx", len(data))

    async def _read_loop(self) -> None:
        """持续读取对端数据并回调，处理断开与错误。"""
        reason = "remote_closed"
        detail = None
        try:
            while self._running and self._reader:
                data = await self._reader.read(4096)
                if not data:
                    break
                if self._on_activity:
                    self._on_activity("rx", len(data))
                if self._receive_callback:
                    self._receive_callback(data)
        except asyncio.CancelledError:
            reason = "local_stop"
            raise
        except (ConnectionError, OSError) as exc:
            reason = "network_error"
            detail = str(exc)
        finally:
            self._running = False
            if self._writer:
                self._writer.close()
            self._writer = None
            self._reader = None
            if self._on_disconnect:
                self._on_disconnect(reason, detail)
