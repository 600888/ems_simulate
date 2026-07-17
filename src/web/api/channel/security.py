"""TLS certificate and private-key upload for device channels."""

import os
from pathlib import Path
import tempfile

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from fastapi import APIRouter, File, Form, Request, UploadFile

from src.config.storage import get_storage_path
from src.data.service.channel_configuration_service import ChannelConfigurationService
from src.data.service.channel_service import ChannelService
from src.web.api.channel.helpers import reload_device_instance
from src.web.api.exceptions import NotFoundError, OperationError, ValidationError
from src.web.api.schemas import BaseResponse

router = APIRouter(tags=["channel"])

_MAX_FILE_SIZE = 5 * 1024 * 1024
_CERTIFICATE_SUFFIXES = {".crt", ".cer", ".pem"}
_PRIVATE_KEY_SUFFIXES = {".key", ".pem"}


async def _read_upload(file: UploadFile, suffixes: set[str], label: str) -> bytes:
    filename = Path(file.filename or "").name
    if Path(filename).suffix.lower() not in suffixes:
        raise ValidationError(f"{label}文件格式不支持")
    content = await file.read(_MAX_FILE_SIZE + 1)
    if not content:
        raise ValidationError(f"{label}文件不能为空")
    if len(content) > _MAX_FILE_SIZE:
        raise ValidationError(f"{label}文件不能超过 5MB")
    return content


def _load_certificate(content: bytes) -> x509.Certificate:
    try:
        return x509.load_pem_x509_certificate(content)
    except ValueError:
        try:
            return x509.load_der_x509_certificate(content)
        except ValueError as exc:
            raise ValidationError("无法解析证书文件") from exc


def _load_private_key(content: bytes):
    try:
        return serialization.load_pem_private_key(content, password=None)
    except (TypeError, ValueError):
        try:
            return serialization.load_der_private_key(content, password=None)
        except (TypeError, ValueError) as exc:
            raise ValidationError("无法解析私钥文件，请上传未加密的 PEM 或 DER 私钥") from exc


def _validate_pair(certificate: x509.Certificate, private_key) -> None:
    certificate_public_key = certificate.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    private_public_key = private_key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    if certificate_public_key != private_public_key:
        raise ValidationError("证书与私钥不匹配")


def _write_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=".tls-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as file_obj:
            file_obj.write(content)
            file_obj.flush()
            os.fsync(file_obj.fileno())
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


@router.post("/security-upload", response_model=BaseResponse)
async def upload_security_config(
    request: Request,
    channel_id: int = Form(...),
    tls_enabled: bool = Form(...),
    certificate: UploadFile | None = File(None),
    private_key: UploadFile | None = File(None),
):
    channel = ChannelService.get_channel_by_id(channel_id)
    if not channel:
        raise NotFoundError("通道不存在")
    if tls_enabled and channel.get("conn_type") not in (1, 2):
        raise ValidationError("串口模式不支持 TLS")
    if tls_enabled and channel.get("protocol_type") != 1:
        raise ValidationError("当前协议暂不支持 TLS")

    current = ChannelConfigurationService.get_runtime_security(channel_id)
    certificate_path = current.get("certificate_path")
    private_key_path = current.get("private_key_path")
    certificate_filename = ChannelConfigurationService.get_security_config(channel_id).get("certificate_filename")
    private_key_filename = ChannelConfigurationService.get_security_config(channel_id).get("private_key_filename")

    certificate_content = None
    private_key_content = None
    if certificate is not None:
        certificate_content = await _read_upload(certificate, _CERTIFICATE_SUFFIXES, "证书")
        certificate_filename = Path(certificate.filename or "certificate").name
    elif certificate_path and Path(certificate_path).is_file():
        certificate_content = Path(certificate_path).read_bytes()

    if private_key is not None:
        private_key_content = await _read_upload(private_key, _PRIVATE_KEY_SUFFIXES, "私钥")
        private_key_filename = Path(private_key.filename or "private.key").name
    elif private_key_path and Path(private_key_path).is_file():
        private_key_content = Path(private_key_path).read_bytes()

    if tls_enabled and (certificate_content is None or private_key_content is None):
        raise ValidationError("启用 TLS 后必须上传证书和私钥")

    if certificate_content is not None and private_key_content is not None:
        parsed_certificate = _load_certificate(certificate_content)
        parsed_private_key = _load_private_key(private_key_content)
        _validate_pair(parsed_certificate, parsed_private_key)

        channel_dir = Path(get_storage_path("data_directory")) / "security" / str(channel_id)
        resolved_channel_dir = channel_dir.resolve(strict=False)
        security_root = (Path(get_storage_path("data_directory")) / "security").resolve(strict=False)
        if security_root not in resolved_channel_dir.parents:
            raise OperationError("TLS 文件存储目录无效")
        certificate_target = resolved_channel_dir / "certificate.pem"
        private_key_target = resolved_channel_dir / "private_key.pem"
        _write_atomic(certificate_target, parsed_certificate.public_bytes(serialization.Encoding.PEM))
        _write_atomic(
            private_key_target,
            parsed_private_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ),
        )
        certificate_path = str(certificate_target)
        private_key_path = str(private_key_target)

    ChannelConfigurationService.save_security_config(
        channel_id,
        tls_enabled=tls_enabled,
        certificate_path=certificate_path,
        certificate_filename=certificate_filename,
        private_key_path=private_key_path,
        private_key_filename=private_key_filename,
    )

    try:
        controller = request.app.state.device_controller
        old_device = controller.get_device_by_id(channel_id)
        was_running = bool(old_device and old_device.is_protocol_running())
        await reload_device_instance(controller, channel_id, is_start=was_running)
    except Exception as exc:
        raise OperationError(f"TLS 配置已保存，但设备重载失败: {exc}") from exc

    return BaseResponse(
        message="TLS 配置保存成功",
        data=ChannelConfigurationService.get_security_config(channel_id),
    )
