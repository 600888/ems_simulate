"""Native TLS configuration for IEC 61850 MMS."""

from __future__ import annotations

import contextlib
import os
from pathlib import Path
import shutil
import tempfile
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
    mode = str(config.get("tls_mode") or "one_way")
    if mode not in {"one_way", "mutual"}:
        raise IEC61850TlsConfigurationError("IEC61850 TLS 模式必须是 one_way 或 mutual")
    return mode


@contextlib.contextmanager
def _native_file_paths(
    certificate: str | None,
    private_key: str | None,
    ca_certificate: str | None,
):
    """Give the C library ASCII paths, including on Windows user profiles with non-ASCII names."""
    paths = (certificate, private_key, ca_certificate)
    if all(path is None or path.isascii() for path in paths):
        yield paths
        return

    staging_parent = Path.cwd() / "tmp"
    staging_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="iec61850-tls-", dir=staging_parent) as staging_directory:
        staged_paths: list[str | None] = []
        for index, source in enumerate(paths):
            if source is None:
                staged_paths.append(None)
                continue
            destination = Path(staging_directory) / f"tls-{index}{Path(source).suffix}"
            shutil.copyfile(source, destination)
            if os.name != "nt":
                destination.chmod(0o600)
            staged_paths.append(str(destination))
        yield tuple(staged_paths)


class NativeTlsConfiguration:
    """Own a libIEC61850 ``TLSConfiguration`` for a client or server."""

    def __init__(self, native: Any) -> None:
        self.native = native

    def close(self) -> None:
        if self.native is None:
            return
        from pyiec61850 import pyiec61850 as iec61850

        iec61850.TLSConfiguration_destroy(self.native)
        self.native = None

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


def create_native_tls_configuration(
    config: dict[str, Any] | None,
    *,
    client: bool,
) -> NativeTlsConfiguration | None:
    """Build the TLS configuration exported by pyiec61850-ng 1.6.1.9."""
    settings = config or {}
    if not settings.get("tls_enabled"):
        return None

    from pyiec61850 import pyiec61850 as iec61850

    mode = _mode(settings)
    requires_identity = mode == "mutual" or not client
    requires_ca = mode == "mutual" or client
    certificate = _required_file(settings, "certificate_path", "证书") if requires_identity else None
    private_key = _required_file(settings, "private_key_path", "私钥") if requires_identity else None
    ca_certificate = _required_file(settings, "ca_certificate_path", "CA 证书") if requires_ca else None

    native = iec61850.TLSConfiguration_create()
    if native is None:
        raise IEC61850TlsConfigurationError("IEC61850 TLS 原生配置创建失败")

    configuration = NativeTlsConfiguration(native)
    try:
        if client:
            iec61850.TLSConfiguration_setClientMode(native)
        iec61850.TLSConfiguration_setMinTlsVersion(native, iec61850.TLS_VERSION_TLS_1_2)
        iec61850.TLSConfiguration_setMaxTlsVersion(native, iec61850.TLS_VERSION_TLS_1_3)
        # 单向客户端和双向模式校验对端 CA 链；单向服务端不要求客户端证书。
        validate_peer = requires_ca
        if not validate_peer:
            set_insecure = getattr(iec61850, "TLSConfiguration_setInsecure", None)
            if set_insecure is None:
                raise IEC61850TlsConfigurationError("IEC61850 单向服务端 TLS 需要 pyiec61850-ng 1.6.1.9 或更高版本")
            set_insecure(native, True)
        iec61850.TLSConfiguration_setChainValidation(native, validate_peer)
        iec61850.TLSConfiguration_setAllowOnlyKnownCertificates(native, False)
        iec61850.TLSConfiguration_setTimeValidation(native, validate_peer)

        with _native_file_paths(certificate, private_key, ca_certificate) as native_paths:
            native_certificate, native_private_key, native_ca_certificate = native_paths
            if native_certificate and not iec61850.TLSConfiguration_setOwnCertificateFromFile(
                native, native_certificate
            ):
                raise IEC61850TlsConfigurationError("IEC61850 TLS 证书加载失败")
            if native_private_key and not iec61850.TLSConfiguration_setOwnKeyFromFile(native, native_private_key, None):
                raise IEC61850TlsConfigurationError("IEC61850 TLS 私钥加载失败")
            if native_ca_certificate and not iec61850.TLSConfiguration_addCACertificateFromFile(
                native, native_ca_certificate
            ):
                raise IEC61850TlsConfigurationError("IEC61850 TLS CA 证书加载失败")
    except Exception:
        configuration.close()
        raise
    return configuration


def create_client_tls_configuration(config: dict[str, Any] | None) -> NativeTlsConfiguration | None:
    return create_native_tls_configuration(config, client=True)


def create_server_tls_configuration(config: dict[str, Any] | None) -> NativeTlsConfiguration | None:
    return create_native_tls_configuration(config, client=False)
