"""Native IEC 61850 server connection indication callback adapter."""

from collections.abc import Callable
import ctypes
from typing import Any

from .log import log
from .server_auth import _find_native_library_path


class Iec61850ServerConnectionMonitor:
    """Own a ctypes callback when the generated SWIG callback is not callable."""

    _CALLBACK = ctypes.CFUNCTYPE(
        None,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_bool,
        ctypes.c_void_p,
    )

    def __init__(self, callback: Callable[[str, bool, str | None, str | None], None]):
        try:
            from pyiec61850 import _libload as library_locator
        except ImportError:
            from pyiec61850 import pyiec61850 as library_locator

        library_path = _find_native_library_path(library_locator)
        if not library_path:
            raise RuntimeError("无法定位 libiec61850 原生动态库，不能注册 MMS 连接监控回调")

        self._library = ctypes.CDLL(library_path)
        self._application_callback = callback
        self._get_peer_address = self._library.ClientConnection_getPeerAddress
        self._get_peer_address.argtypes = [ctypes.c_void_p]
        self._get_peer_address.restype = ctypes.c_char_p
        self._get_local_address = self._library.ClientConnection_getLocalAddress
        self._get_local_address.argtypes = [ctypes.c_void_p]
        self._get_local_address.restype = ctypes.c_char_p
        self._set_handler = self._library.IedServer_setConnectionIndicationHandler
        self._set_handler.argtypes = [ctypes.c_void_p, self._CALLBACK, ctypes.c_void_p]
        self._set_handler.restype = None
        self._callback = self._CALLBACK(self._on_connection)

    @staticmethod
    def _decode(value: bytes | None) -> str | None:
        return value.decode("utf-8", errors="replace") if value else None

    def install(self, native_server: Any) -> None:
        self._set_handler(ctypes.c_void_p(int(native_server)), self._callback, None)

    def _on_connection(self, server, connection, connected, parameter) -> None:
        del server, parameter
        try:
            peer = self._decode(self._get_peer_address(connection))
            local = self._decode(self._get_local_address(connection))
            self._application_callback(f"mms:{int(connection or 0)}", bool(connected), peer, local)
        except Exception as exc:
            # Exceptions must never unwind through the native C callback.
            log.error(f"MMS 连接指示回调处理失败: {exc}")
