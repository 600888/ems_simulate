"""Core device package with lazy public exports.

Keeping package import side effects small prevents protocol base classes from
recursively importing themselves when they use a focused core submodule.
"""

from importlib import import_module

__all__ = [
    "Device",
    "PointManager",
    "DataExporter",
    "DataReader",
    "PointOperator",
    "SlaveManager",
    "MessageFormatter",
]

_EXPORTS = {
    "Device": ("src.device.core.device", "Device"),
    "PointManager": ("src.device.core.point.point_manager", "PointManager"),
    "DataExporter": ("src.device.core.data.data_exporter", "DataExporter"),
    "DataReader": ("src.device.core.data.data_reader", "DataReader"),
    "PointOperator": ("src.device.core.point.point_operator", "PointOperator"),
    "SlaveManager": ("src.device.core.slave_manager", "SlaveManager"),
    "MessageFormatter": ("src.device.core.message.message_formatter", "MessageFormatter"),
}


def __getattr__(name: str):
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value
