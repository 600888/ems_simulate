"""Runtime compatibility helpers for the third-party dlt645 package."""

from pathlib import Path
import sys
from types import ModuleType
from typing import Any

from src.config.global_config import LOG_DIR


def _configure_writable_log_path() -> Path:
    """Redirect dlt645's package-relative logs to the application data root.

    dlt645 1.3.6 derives its log directory from the installed package path.
    That directory is read-only inside an MSIX WindowsApps installation.
    Supplying its small ``common.env`` module before importing the package
    preserves the library API while keeping all runtime writes under LOG_DIR.
    """
    log_path = Path(LOG_DIR) / "dlt645"
    log_path.mkdir(parents=True, exist_ok=True)

    module_name = "dlt645.common.env"
    env_module = sys.modules.get(module_name)
    if env_module is None:
        env_module = ModuleType(module_name)
        sys.modules[module_name] = env_module
    env_module.log_path = str(log_path)
    return log_path


_configure_writable_log_path()

from dlt645.aio import (  # noqa: E402
    AsyncMeterClientService as _AsyncMeterClientService,
)
from dlt645.aio import (  # noqa: E402
    AsyncMeterServerService,
)
from dlt645.common.transform import bcd_to_time  # noqa: E402
from dlt645.model.types.dlt645_type import CtrlCode, Demand  # noqa: E402


def _decode_demand_time(raw: bytes | bytearray):
    """Decode DL/T 645 demand occurrence time (mmhhDDMMYY on wire)."""
    if len(raw) != 5:
        raise ValueError("invalid demand occurrence time length")
    return bcd_to_time(bytes(reversed(raw)))


class AsyncMeterClientService(_AsyncMeterClientService):
    """App compatibility wrapper around dlt645's async client.

    dlt645 3.0.0 passes the little-endian occurrence-time bytes directly to
    ``bcd_to_time`` (which expects YYMMDDhhmm), swapping year/minute and
    month/hour. Correct the decoded Demand while the original frame bytes are
    still available.
    """

    def handle_response(self, frame: Any):
        raw_time = None
        original_data = getattr(frame, "data", None)
        # The upstream parser decodes demand occurrence bytes before returning
        # the DataItem. Feed it the byte order it expects so invalid intermediate
        # dates (for example minute=17 interpreted as year and hour=21 as month)
        # do not make it swallow the whole response and return None.
        is_read_response = getattr(frame, "ctrl_code", None) == (CtrlCode.ReadData | 0x80)
        if is_read_response and original_data is not None and len(original_data) >= 12 and original_data[3] == 0x01:
            raw_time = bytes(original_data[7:12])
            patched_data = bytearray(original_data)
            patched_data[7:12] = reversed(raw_time)
            frame.data = patched_data
        try:
            item = super().handle_response(frame)
        finally:
            if raw_time is not None:
                frame.data = original_data

        value = getattr(item, "value", None)
        if isinstance(value, Demand) and raw_time is not None:
            try:
                item.value = Demand(value=value.value, time=_decode_demand_time(raw_time))
            except (TypeError, ValueError):
                # Preserve the library result for malformed/non-standard frames.
                pass
        return item


__all__ = ["AsyncMeterClientService", "AsyncMeterServerService"]
