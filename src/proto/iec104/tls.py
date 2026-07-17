"""IEC 60870-5-104 transport security configuration."""

import os
from pathlib import Path
import select
import socket
import ssl
import threading
from typing import Any

import c104


class IEC104TlsConfigurationError(ValueError):
    """Raised when IEC104 TLS material cannot be loaded safely."""


def _required_file(
    security: dict[str, Any],
    key: str,
    label: str,
    *,
    require_ascii: bool = False,
) -> str:
    value = security.get(key)
    if not value:
        raise IEC104TlsConfigurationError(f"IEC104 TLS 缺少{label}")
    path = Path(str(value)).expanduser().resolve(strict=False)
    if not path.is_file():
        raise IEC104TlsConfigurationError(f"IEC104 TLS {label}文件不存在")
    if require_ascii and os.name == "nt" and not str(path).isascii():
        raise IEC104TlsConfigurationError(
            f"c104 2.2.2 在 Windows 上不支持包含非 ASCII 字符的{label}路径，请将数据目录设置为纯英文路径"
        )
    return str(path)


class IEC104BasicTlsConfig:
    """Certificate and key material for encryption-only TLS."""

    def __init__(self, certificate_path: str, private_key_path: str) -> None:
        self.certificate_path = certificate_path
        self.private_key_path = private_key_path

    def create_client_context(self) -> ssl.SSLContext:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.maximum_version = ssl.TLSVersion.TLSv1_3
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        context.load_cert_chain(certfile=self.certificate_path, keyfile=self.private_key_path)
        return context

    def create_server_context(self) -> ssl.SSLContext:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.maximum_version = ssl.TLSVersion.TLSv1_3
        context.verify_mode = ssl.CERT_NONE
        context.load_cert_chain(certfile=self.certificate_path, keyfile=self.private_key_path)
        return context


def load_basic_tls_config(security: dict[str, Any] | None) -> IEC104BasicTlsConfig | None:
    config = security or {}
    if not config.get("tls_enabled") or str(config.get("tls_mode") or "mutual") != "basic":
        return None
    tls_config = IEC104BasicTlsConfig(
        certificate_path=_required_file(config, "certificate_path", "证书"),
        private_key_path=_required_file(config, "private_key_path", "私钥"),
    )
    try:
        tls_config.create_client_context()
        tls_config.create_server_context()
    except (OSError, ssl.SSLError) as exc:
        raise IEC104TlsConfigurationError(f"IEC104 基础 TLS 配置加载失败: {exc}") from exc
    return tls_config


def build_transport_security(
    security: dict[str, Any] | None,
    *,
    peer_hostname: str | None = None,
) -> c104.TransportSecurity | None:
    """Build native c104 TLS settings from channel security settings."""
    config = security or {}
    if not config.get("tls_enabled"):
        return None

    tls_mode = str(config.get("tls_mode") or "mutual")
    if tls_mode not in {"basic", "mutual"}:
        raise IEC104TlsConfigurationError("IEC104 TLS 模式必须是 basic 或 mutual")
    if tls_mode == "basic":
        return None
    certificate_path = _required_file(config, "certificate_path", "证书", require_ascii=True)
    private_key_path = _required_file(config, "private_key_path", "私钥", require_ascii=True)
    ca_certificate_path = _required_file(config, "ca_certificate_path", "CA 证书", require_ascii=True)

    try:
        transport_security = c104.TransportSecurity(validate=True, only_known=False)
        transport_security.set_certificate(certificate_path, private_key_path)
        transport_security.set_version(c104.TlsVersion.TLS_1_2, c104.TlsVersion.TLS_1_3)
        transport_security.set_ca_certificate(ca_certificate_path)

        if peer_hostname is not None:
            set_hostname_verification = getattr(transport_security, "set_hostname_verification", None)
            if set_hostname_verification is None:
                raise IEC104TlsConfigurationError("IEC104 TLS 主机名校验需要 c104 2.2.2 或更高版本")
            set_hostname_verification(peer_hostname)
        return transport_security
    except IEC104TlsConfigurationError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise IEC104TlsConfigurationError(f"IEC104 TLS 配置加载失败: {exc}") from exc


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
        self._socket_lock = threading.Lock()
        self.last_error: str | None = None

    def stop(self) -> None:
        self._stop_event.set()
        if self._listener:
            try:
                self._listener.close()
            except OSError:
                pass
        with self._socket_lock:
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
        with self._socket_lock:
            self._active_sockets.update(sockets)

    def _untrack(self, *sockets: socket.socket) -> None:
        with self._socket_lock:
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
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", self.local_port))
        listener.listen()
        listener.settimeout(0.5)
        self._listener = listener
        self._thread = threading.Thread(target=self._accept_loop, name="iec104-basic-tls-client", daemon=True)
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
            tls_socket = self.context.wrap_socket(remote_socket, server_hostname=None)
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
    def __init__(
        self,
        listen_host: str,
        listen_port: int,
        backend_port: int,
        context: ssl.SSLContext,
    ) -> None:
        super().__init__()
        self.listen_host = listen_host
        self.listen_port = listen_port
        self.backend_port = backend_port
        self.context = context

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((self.listen_host, self.listen_port))
        listener.listen()
        listener.settimeout(0.5)
        self._listener = listener
        self._thread = threading.Thread(target=self._accept_loop, name="iec104-basic-tls-server", daemon=True)
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
