"""TLS context construction for DNP3 TCP client and server."""

import asyncio
from pathlib import Path
import ssl
from typing import Any


class Dnp3TlsConfigurationError(ValueError):
    """Raised when DNP3 TLS settings or certificate files are invalid."""


def _required_file(config: dict[str, Any], key: str, label: str) -> str:
    value = config.get(key)
    if not value:
        raise Dnp3TlsConfigurationError(f"DNP3 TLS 缺少{label}")
    path = Path(str(value)).expanduser().resolve(strict=False)
    if not path.is_file():
        raise Dnp3TlsConfigurationError(f"DNP3 TLS {label}文件不存在")
    return str(path)


def _mode(config: dict[str, Any]) -> str:
    mode = str(config.get("tls_mode") or "one_way")
    if mode not in {"one_way", "mutual"}:
        raise Dnp3TlsConfigurationError("DNP3 TLS 模式必须是 one_way 或 mutual")
    return mode


def create_client_ssl_context(config: dict[str, Any] | None) -> ssl.SSLContext | None:
    """Create the DNP3 Master TLS context using the shared channel semantics."""
    settings = config or {}
    if not settings.get("tls_enabled"):
        return None

    mode = _mode(settings)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.maximum_version = ssl.TLSVersion.TLSv1_3
    # Industrial endpoints are commonly addressed by IP. Match the other
    # protocols: validate the certificate chain, but not a DNS/IP identity.
    context.check_hostname = False
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_verify_locations(cafile=_required_file(settings, "ca_certificate_path", "CA 证书"))
    if mode == "mutual":
        context.load_cert_chain(
            certfile=_required_file(settings, "certificate_path", "证书"),
            keyfile=_required_file(settings, "private_key_path", "私钥"),
        )
    return context


def create_server_ssl_context(config: dict[str, Any] | None) -> ssl.SSLContext | None:
    """Create the DNP3 Outstation TLS context using the shared channel semantics."""
    settings = config or {}
    if not settings.get("tls_enabled"):
        return None

    mode = _mode(settings)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.maximum_version = ssl.TLSVersion.TLSv1_3
    context.load_cert_chain(
        certfile=_required_file(settings, "certificate_path", "证书"),
        keyfile=_required_file(settings, "private_key_path", "私钥"),
    )
    if mode == "one_way":
        context.verify_mode = ssl.CERT_NONE
    else:
        context.verify_mode = ssl.CERT_REQUIRED
        context.load_verify_locations(cafile=_required_file(settings, "ca_certificate_path", "CA 证书"))
    return context


def connection_security(writer: asyncio.StreamWriter | None) -> dict[str, Any]:
    """Return negotiated TLS metadata in the connection monitor's common shape."""
    ssl_object = writer.get_extra_info("ssl_object") if writer else None
    security: dict[str, Any] = {"tls": bool(ssl_object)}
    if ssl_object:
        security["version"] = ssl_object.version()
        cipher = ssl_object.cipher()
        if cipher:
            security["cipher"] = cipher[0]
    return security
