"""Connection-aware adapter for pydnp3-pure's single-client TcpServer."""

import asyncio

from pydnp3_pure.io.tcp_server import TcpServer


class TrackedTcpServer(TcpServer):
    def __init__(self, *args, on_connect=None, on_activity=None, on_disconnect=None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._on_connect = on_connect
        self._on_activity = on_activity
        self._on_disconnect = on_disconnect
        self._active_connection_key: str | None = None
        self._replaced_writers: set[int] = set()

    @property
    def active_connection_key(self) -> str | None:
        return self._active_connection_key

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        local = writer.get_extra_info("sockname")
        previous = self._writer
        if previous and not previous.is_closing():
            self._replaced_writers.add(id(previous))
            previous.close()

        self._reader = reader
        self._writer = writer
        self._connection_id += 1
        key = f"dnp3:{self._connection_id}"
        self._active_connection_key = key
        self._connected_event.set()
        if self._on_connect:
            self._on_connect(key, peer, local)

        reason = "remote_closed"
        detail = None
        try:
            while self._running:
                data = await reader.read(4096)
                if not data:
                    break
                if self._on_activity:
                    self._on_activity(key, "rx", len(data))
                if self._receive_callback:
                    self._receive_callback(data)
            if not self._running:
                reason = "server_stopped"
        except asyncio.CancelledError:
            reason = "server_stopped" if not self._running else "network_reset"
            raise
        except (ConnectionError, OSError) as exc:
            reason = "network_reset"
            detail = str(exc)
        except Exception as exc:
            reason = "protocol_error"
            detail = str(exc)
        finally:
            if id(writer) in self._replaced_writers:
                self._replaced_writers.discard(id(writer))
                reason = "connection_replaced"
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass
            if self._writer is writer:
                self._writer = None
                self._reader = None
                self._active_connection_key = None
                self._connected_event.clear()
            if self._on_disconnect:
                self._on_disconnect(key, reason, detail)

    def send(self, data: bytes) -> None:
        key = self._active_connection_key
        super().send(data)
        if key and self._on_activity:
            self._on_activity(key, "tx", len(data))
