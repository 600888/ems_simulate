"""Helpers for blocking pyiec61850 calls that may re-enter Python callbacks."""

from typing import Any


def call_gil_safe(native: Any, function_name: str, *args: Any) -> Any:
    """调用 pyiec61850 原生函数；绑定支持时临时释放 GIL，避免长时间阻塞其他 Python 线程。"""

    wrapper = getattr(native, f"pyWrap_{function_name}", None)
    if callable(wrapper):
        return wrapper(*args)
    return getattr(native, function_name)(*args)
