"""DPAPI on Windows, a mode-0600 Fernet key on POSIX; no plaintext persistence."""

import base64
import ctypes
from ctypes import wintypes
import os
from pathlib import Path

from cryptography.fernet import Fernet


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _dpapi(value: bytes, decrypt: bool) -> bytes:
    buffer = ctypes.create_string_buffer(value)
    source = _Blob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = _Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [
        ctypes.POINTER(_Blob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_Blob),
    ]
    function.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise OSError("OPC UA 凭据保护失败")
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        kernel.LocalFree(output.pbData)


def protect(value: str, key_directory: str | Path, *, decrypt: bool = False) -> str:
    binary = base64.b64decode(value) if decrypt else value.encode()
    if os.name == "nt":
        result = _dpapi(binary, decrypt)
    else:
        directory = Path(key_directory)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = directory / "credentials.key"
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, "wb") as stream:
                stream.write(Fernet.generate_key())
        if path.stat().st_mode & 0o077:
            raise ValueError("OPC UA 凭据密钥须仅允许当前用户访问")
        cipher = Fernet(path.read_bytes())
        result = cipher.decrypt(binary) if decrypt else cipher.encrypt(binary)
    return result.decode() if decrypt else base64.b64encode(result).decode()
