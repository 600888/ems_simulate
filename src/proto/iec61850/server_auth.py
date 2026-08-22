"""Native ACSE password authenticator adapter for pyiec61850 servers."""

import ctypes
import hmac
from pathlib import Path
import sys
from typing import Any

_NATIVE_BOOL = ctypes.c_int if sys.platform == "win32" else ctypes.c_bool


def _find_native_library_path(libload: Any) -> str | None:
    """Locate libiec61850, including auditwheel's hashed Linux filename."""
    loaded_path = getattr(libload, "LOADED_PATH", None)
    if loaded_path:
        return str(loaded_path)

    module_file = getattr(libload, "__file__", None)
    if not module_file:
        return None
    package_dir = Path(module_file).resolve().parent
    search_dirs = (
        package_dir,
        package_dir.parent / "pyiec61850_ng.libs",
        package_dir.parent / "pyiec61850.libs",
    )
    if sys.platform == "win32":
        patterns = ("*iec61850*.dll",)
    elif sys.platform == "darwin":
        patterns = ("libiec61850*.dylib",)
    else:
        # auditwheel renames bundled libraries to forms such as
        # libiec61850-51dd1582.so.1.6.1, which pyiec61850 1.6.1.9's own
        # loader does not currently match.
        patterns = ("libiec61850*.so", "libiec61850*.so.*")

    for directory in search_dirs:
        if not directory.is_dir():
            continue
        for pattern in patterns:
            candidates = sorted(directory.glob(pattern))
            if candidates:
                return str(candidates[0])
    return None


class Iec61850ServerPasswordAuthenticator:
    """Own the native callback and validate ACSE password credentials."""

    _CALLBACK = ctypes.CFUNCTYPE(
        _NATIVE_BOOL,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_void_p,
    )

    def __init__(self, password: str):
        if not password:
            raise ValueError("IEC 61850 服务端认证密码不能为空")

        from pyiec61850 import pyiec61850 as iec61850

        try:
            from pyiec61850 import _libload as library_locator
        except ImportError:
            # Some Windows wheels place iec61850.dll beside pyiec61850.py
            # without shipping the private _libload helper module.
            library_locator = iec61850

        library_path = _find_native_library_path(library_locator)
        if not library_path:
            load_error = getattr(library_locator, "LIB_LOAD_ERROR", None)
            detail = f": {load_error}" if load_error else ""
            raise RuntimeError(f"无法定位 libiec61850 原生动态库{detail}")

        self._library = ctypes.CDLL(library_path)
        self._expected_password = password.encode("utf-8")
        self._password_mechanism = int(iec61850.ACSE_AUTH_PASSWORD)

        self._get_mechanism = self._library.AcseAuthenticationParameter_getAuthMechanism
        self._get_mechanism.argtypes = [ctypes.c_void_p]
        self._get_mechanism.restype = ctypes.c_int
        self._get_password = self._library.AcseAuthenticationParameter_getPassword
        self._get_password.argtypes = [ctypes.c_void_p]
        self._get_password.restype = ctypes.c_void_p
        self._get_password_length = self._library.AcseAuthenticationParameter_getPasswordLength
        self._get_password_length.argtypes = [ctypes.c_void_p]
        self._get_password_length.restype = ctypes.c_int

        self._set_authenticator = self._library.IedServer_setAuthenticator
        self._set_authenticator.argtypes = [ctypes.c_void_p, self._CALLBACK, ctypes.c_void_p]
        self._set_authenticator.restype = None
        self._callback = self._CALLBACK(self._authenticate)

    def install(self, native_server: Any) -> None:
        """Register this authenticator on one native IedServer instance."""
        self._set_authenticator(ctypes.c_void_p(int(native_server)), self._callback, None)

    def _authenticate(self, parameter, auth_parameter, security_token, app_reference) -> bool:
        del parameter, security_token, app_reference
        if not auth_parameter or self._get_mechanism(auth_parameter) != self._password_mechanism:
            return False

        password_length = self._get_password_length(auth_parameter)
        password_pointer = self._get_password(auth_parameter)
        if password_length < 0 or not password_pointer:
            return False

        supplied_password = ctypes.string_at(password_pointer, password_length)
        return hmac.compare_digest(supplied_password, self._expected_password)
