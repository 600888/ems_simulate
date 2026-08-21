"""IEC 60870-5-104 transport security configuration."""

import os
from pathlib import Path
import select
import shutil
import socket
import ssl
import tempfile
import threading
from typing import Any

import c104


class IEC104TlsConfigurationError(ValueError):
    """Raised when IEC104 TLS material cannot be loaded safely."""


_staged_tls_material: dict[
    tuple[tuple[str, int, int], ...],
    tuple[tempfile.TemporaryDirectory, tuple[str, ...]],
] = {}
_staged_tls_lock = threading.Lock()


def _required_file(security: dict[str, Any], key: str, label: str) -> str:
    value = security.get(key)
    if not value:
        raise IEC104TlsConfigurationError(f"IEC104 TLS 缺少{label}")
    path = Path(str(value)).expanduser().resolve(strict=False)
    if not path.is_file():
        raise IEC104TlsConfigurationError(f"IEC104 TLS {label}文件不存在")
    return str(path)


def _ascii_tls_paths(*paths: str) -> tuple[str, ...]:
    """Stage native c104 TLS files when Windows paths contain non-ASCII text.

    c104 2.2.2 cannot open such paths on Windows.  The temporary directory is
    retained for the process lifetime because the native object may defer file
    access until a connection is started.
    """
    if os.name != "nt" or all(path.isascii() for path in paths):
        return paths

    cache_key = tuple((path, Path(path).stat().st_size, Path(path).stat().st_mtime_ns) for path in paths)
    with _staged_tls_lock:
        cached = _staged_tls_material.get(cache_key)
        if cached is not None:
            return cached[1]

        candidates = [Path.cwd(), Path(os.environ.get("SystemRoot", "C:\\Windows")) / "Temp"]
        temporary_directory = None
        for root in candidates:
            if not str(root).isascii() or not root.is_dir():
                continue
            try:
                temporary_directory = tempfile.TemporaryDirectory(prefix="ems-iec104-tls-", dir=root)
                break
            except OSError:
                continue
        if temporary_directory is None:
            raise IEC104TlsConfigurationError(
                "c104 2.2.2 在 Windows 上无法读取包含非 ASCII 字符的 TLS 路径，且未找到可写的纯英文暂存目录"
            )

        staged_paths = []
        stage_root = Path(temporary_directory.name)
        try:
            for index, source in enumerate(paths):
                suffix = Path(source).suffix or ".pem"
                target = stage_root / f"material-{index}{suffix}"
                shutil.copyfile(source, target)
                target.chmod(0o600)
                staged_paths.append(str(target))
        except OSError as exc:
            temporary_directory.cleanup()
            raise IEC104TlsConfigurationError(f"IEC104 TLS 文件暂存失败: {exc}") from exc

        result = tuple(staged_paths)
        _staged_tls_material[cache_key] = (temporary_directory, result)
        return result


class IEC104OneWayTlsConfig:
    """Role-specific material for CA-validated one-way TLS."""

    def __init__(
        self,
        *,
        certificate_path: str | None = None,
        private_key_path: str | None = None,
        ca_certificate_path: str | None = None,
    ) -> None:
        self.certificate_path = certificate_path
        self.private_key_path = private_key_path
        self.ca_certificate_path = ca_certificate_path

    def create_client_context(self) -> ssl.SSLContext:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.maximum_version = ssl.TLSVersion.TLSv1_3
        context.check_hostname = False
        context.verify_mode = ssl.CERT_REQUIRED
        if not self.ca_certificate_path:
            raise IEC104TlsConfigurationError("IEC104 客户端单向 TLS 缺少 CA 证书")
        context.load_verify_locations(cafile=self.ca_certificate_path)
        return context

    def create_server_context(self) -> ssl.SSLContext:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.maximum_version = ssl.TLSVersion.TLSv1_3
        context.verify_mode = ssl.CERT_NONE
        if not self.certificate_path or not self.private_key_path:
            raise IEC104TlsConfigurationError("IEC104 服务端单向 TLS 缺少证书或私钥")
        context.load_cert_chain(certfile=self.certificate_path, keyfile=self.private_key_path)
        return context


def load_one_way_tls_config(
    security: dict[str, Any] | None,
    *,
    client: bool,
) -> IEC104OneWayTlsConfig | None:
    config = security or {}
    if not config.get("tls_enabled") or str(config.get("tls_mode") or "one_way") != "one_way":
        return None
    tls_config = (
        IEC104OneWayTlsConfig(
            ca_certificate_path=_required_file(config, "ca_certificate_path", "CA 证书"),
        )
        if client
        else IEC104OneWayTlsConfig(
            certificate_path=_required_file(config, "certificate_path", "证书"),
            private_key_path=_required_file(config, "private_key_path", "私钥"),
        )
    )
    try:
        if client:
            tls_config.create_client_context()
        else:
            tls_config.create_server_context()
    except (OSError, ssl.SSLError) as exc:
        raise IEC104TlsConfigurationError(f"IEC104 单向 TLS 配置加载失败: {exc}") from exc
    return tls_config


def build_transport_security(
    security: dict[str, Any] | None,
) -> c104.TransportSecurity | None:
    """Build native c104 TLS settings from channel security settings."""
    config = security or {}
    if not config.get("tls_enabled"):
        return None

    tls_mode = str(config.get("tls_mode") or "one_way")
    if tls_mode not in {"one_way", "mutual"}:
        raise IEC104TlsConfigurationError("IEC104 TLS 模式必须是 one_way 或 mutual")
    if tls_mode == "one_way":
        return None
    certificate_path = _required_file(config, "certificate_path", "证书")
    private_key_path = _required_file(config, "private_key_path", "私钥")
    ca_certificate_path = _required_file(config, "ca_certificate_path", "CA 证书")
    certificate_path, private_key_path, ca_certificate_path = _ascii_tls_paths(
        certificate_path,
        private_key_path,
        ca_certificate_path,
    )

    try:
        transport_security = c104.TransportSecurity(validate=True, only_known=False)
        transport_security.set_certificate(certificate_path, private_key_path)
        transport_security.set_version(c104.TlsVersion.TLS_1_2, c104.TlsVersion.TLS_1_3)
        transport_security.set_ca_certificate(ca_certificate_path)

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
        self._thread = threading.Thread(target=self._accept_loop, name="iec104-one-way-tls-client", daemon=True)
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
        self._thread = threading.Thread(target=self._accept_loop, name="iec104-one-way-tls-server", daemon=True)
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
