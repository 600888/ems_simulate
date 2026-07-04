"""Helpers for blocking pyiec61850 calls that may re-enter Python callbacks."""

from typing import Any


def call_gil_safe(native: Any, function_name: str, *args: Any) -> Any:
    """Use the binding's GIL-releasing wrapper when one is available."""

    wrapper = getattr(native, f"pyWrap_{function_name}", None)
    if callable(wrapper):
        return wrapper(*args)
    return getattr(native, function_name)(*args)
