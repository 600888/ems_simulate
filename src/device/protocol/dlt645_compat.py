"""Runtime compatibility helpers for the third-party dlt645 package."""

from pathlib import Path
import sys
from types import ModuleType

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

from dlt645 import MeterClientService, MeterServerService  # noqa: E402

__all__ = ["MeterClientService", "MeterServerService"]
