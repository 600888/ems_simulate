"""TLS transport adapter for IEC 61850 MMS.

The bundled libIEC61850 is compiled without native TLS support.  These bridges
keep the native MMS stack on loopback and expose/consume only TLS externally.
"""

from pathlib import Path
import select
import socket
import ssl
import threading
from typing import Any


class IEC61850TlsConfigurationError(ValueError):
    """Raised when IEC 61850 TLS settings or files are invalid."""


def _required_file(config: dict[str, Any], key: str, label: str) -> str:
    value = config.get(key)
    if not value:
        raise IEC61850TlsConfigurationError(f"IEC61850 TLS 缺少{label}")
    path = Path(str(value)).expanduser().resolve(strict=False)
    if not path.is_file():
        raise IEC61850TlsConfigurationError(f"IEC61850 TLS {label}文件不存在")
    return str(path)


def _mode(config: dict[str, Any]) -> str:
    mode = str(config.get("tls_mode") or "mutual")
    if mode not in {"basic", "mutual"}:
        raise IEC61850TlsConfigurationError("IEC61850 TLS 模式必须是 basic 或 mutual")
    return mode


def create_client_context(config: dict[str, Any] | None) -> ssl.SSLContext | None:
    settings = config or {}
    if not settings.get("tls_enabled"):
        return None
    mode = _mode(settings)
    certificate = _required_file(settings, "certificate_path", "证书")
    private_key = _required_file(settings, "private_key_path", "私钥")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.maximum_version = ssl.TLSVersion.TLSv1_3
    if mode == "basic":
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    else:
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        context.load_verify_locations(cafile=_required_file(settings, "ca_certificate_path", "CA 证书"))
    try:
        context.load_cert_chain(certfile=certificate, keyfile=private_key)
    except (OSError, ssl.SSLError) as exc:
        raise IEC61850TlsConfigurationError(f"IEC61850 TLS 客户端配置加载失败: {exc}") from exc
    return context


def create_server_context(config: dict[str, Any] | None) -> ssl.SSLContext | None:
    settings = config or {}
    if not settings.get("tls_enabled"):
        return None
    mode = _mode(settings)
    certificate = _required_file(settings, "certificate_path", "证书")
    private_key = _required_file(settings, "private_key_path", "私钥")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.maximum_version = ssl.TLSVersion.TLSv1_3
    try:
        context.load_cert_chain(certfile=certificate, keyfile=private_key)
        if mode == "basic":
            context.verify_mode = ssl.CERT_NONE
        else:
            context.verify_mode = ssl.CERT_REQUIRED
            context.load_verify_locations(cafile=_required_file(settings, "ca_certificate_path", "CA 证书"))
    except (OSError, ssl.SSLError) as exc:
        raise IEC61850TlsConfigurationError(f"IEC61850 TLS 服务端配置加载失败: {exc}") from exc
    return context


def allocate_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class _TlsBridge:
    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self._listener: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._active_sockets: set[socket.socket] = set()
        self._lock = threading.Lock()
        self.last_error: str | None = None

    def stop(self) -> None:
        self._stop_event.set()
        if self._listener:
            try:
                self._listener.close()
            except OSError:
                pass
        with self._lock:
            active = tuple(self._active_sockets)
        for active_socket in active:
            try:
                active_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                active_socket.close()
            except OSError:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._listener = None
        self._thread = None

    def _track(self, *sockets: socket.socket) -> None:
        with self._lock:
            self._active_sockets.update(sockets)

    def _untrack(self, *sockets: socket.socket) -> None:
        with self._lock:
            for active_socket in sockets:
                self._active_sockets.discard(active_socket)

    def _relay(self, left: socket.socket, right: socket.socket) -> None:
        self._track(left, right)
        try:
            while not self._stop_event.is_set():
                readable, _, _ = select.select((left, right), (), (), 0.5)
                for source in readable:
                    target = right if source is left else left
                    data = source.recv(65536)
                    if not data:
                        return
                    target.sendall(data)
        except (OSError, ssl.SSLError):
            return
        finally:
            self._untrack(left, right)
            for active_socket in (left, right):
                try:
                    active_socket.close()
                except OSError:
                    pass


class TlsClientBridge(_TlsBridge):
    def __init__(self, remote_host: str, remote_port: int, context: ssl.SSLContext) -> None:
        super().__init__()
        self.remote_host = remote_host
        self.remote_port = remote_port
        self.context = context
        self.local_port = allocate_loopback_port()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self.last_error = None
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", self.local_port))
        listener.listen()
        listener.settimeout(0.5)
        self._listener = listener
        self._thread = threading.Thread(target=self._accept_loop, name="iec61850-tls-client", daemon=True)
        self._thread.start()

    def _accept_loop(self) -> None:
        assert self._listener is not None
        while not self._stop_event.is_set():
            try:
                local_socket, _ = self._listener.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            self._track(local_socket)
            threading.Thread(target=self._connect_remote, args=(local_socket,), daemon=True).start()

    def _connect_remote(self, local_socket: socket.socket) -> None:
        remote_socket = None
        try:
            remote_socket = socket.create_connection((self.remote_host, self.remote_port), timeout=5)
            self._track(remote_socket)
            server_hostname = self.remote_host if self.context.check_hostname else None
            tls_socket = self.context.wrap_socket(remote_socket, server_hostname=server_hostname)
            self._untrack(local_socket, remote_socket)
            self.last_error = None
        except (OSError, ssl.SSLError) as exc:
            self.last_error = str(exc)
            self._untrack(local_socket)
            local_socket.close()
            if remote_socket is not None:
                self._untrack(remote_socket)
                remote_socket.close()
            return
        self._relay(local_socket, tls_socket)


class TlsServerBridge(_TlsBridge):
    def __init__(self, listen_host: str, listen_port: int, backend_port: int, context: ssl.SSLContext) -> None:
        super().__init__()
        self.listen_host = listen_host
        self.listen_port = listen_port
        self.backend_port = backend_port
        self.context = context

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self.last_error = None
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((self.listen_host, self.listen_port))
        listener.listen()
        listener.settimeout(0.5)
        self._listener = listener
        self._thread = threading.Thread(target=self._accept_loop, name="iec61850-tls-server", daemon=True)
        self._thread.start()

    def _accept_loop(self) -> None:
        assert self._listener is not None
        while not self._stop_event.is_set():
            try:
                remote_socket, _ = self._listener.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            remote_socket.settimeout(5)
            self._track(remote_socket)
            threading.Thread(target=self._connect_backend, args=(remote_socket,), daemon=True).start()

    def _connect_backend(self, remote_socket: socket.socket) -> None:
        backend_socket = None
        try:
            tls_socket = self.context.wrap_socket(remote_socket, server_side=True)
            backend_socket = socket.create_connection(("127.0.0.1", self.backend_port), timeout=5)
            self._untrack(remote_socket)
            self.last_error = None
        except (OSError, ssl.SSLError) as exc:
            self.last_error = str(exc)
            self._untrack(remote_socket)
            remote_socket.close()
            if backend_socket is not None:
                backend_socket.close()
            return
        self._relay(tls_socket, backend_socket)
