"""TLS context construction for Modbus TCP client and server."""

from pathlib import Path
import ssl


class ModbusTlsConfigurationError(ValueError):
    """Raised when Modbus TLS settings or certificate files are invalid."""


def _required_file(path_value: str | None, label: str) -> str:
    if not path_value:
        raise ModbusTlsConfigurationError(f"Modbus TLS 缺少{label}")
    path = Path(path_value).expanduser().resolve(strict=False)
    if not path.is_file():
        raise ModbusTlsConfigurationError(f"Modbus TLS {label}文件不存在")
    return str(path)


def _validate_mode(tls_mode: str) -> str:
    if tls_mode not in {"one_way", "mutual"}:
        raise ModbusTlsConfigurationError("Modbus TLS 模式必须是 one_way 或 mutual")
    return tls_mode


def create_client_ssl_context(
    *,
    tls_mode: str,
    certificate_path: str | None,
    private_key_path: str | None,
    ca_certificate_path: str | None,
) -> ssl.SSLContext:
    """Create a CA-validating TLS client context for one-way TLS or mTLS."""
    mode = _validate_mode(tls_mode)
    ca_certificate = _required_file(ca_certificate_path, "CA 证书")

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.maximum_version = ssl.TLSVersion.TLSv1_3
    context.check_hostname = False
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_verify_locations(cafile=ca_certificate)
    if mode == "mutual":
        certificate = _required_file(certificate_path, "证书")
        private_key = _required_file(private_key_path, "私钥")
        context.load_cert_chain(certfile=certificate, keyfile=private_key)
    return context


def create_server_ssl_context(
    *,
    tls_mode: str,
    certificate_path: str | None,
    private_key_path: str | None,
    ca_certificate_path: str | None,
) -> ssl.SSLContext:
    """Create a TLS server context for one-way TLS or mTLS."""
    mode = _validate_mode(tls_mode)
    certificate = _required_file(certificate_path, "证书")
    private_key = _required_file(private_key_path, "私钥")

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.maximum_version = ssl.TLSVersion.TLSv1_3
    context.load_cert_chain(certfile=certificate, keyfile=private_key)
    if mode == "one_way":
        context.verify_mode = ssl.CERT_NONE
    else:
        ca_certificate = _required_file(ca_certificate_path, "CA 证书")
        context.verify_mode = ssl.CERT_REQUIRED
        context.load_verify_locations(cafile=ca_certificate)
    return context
