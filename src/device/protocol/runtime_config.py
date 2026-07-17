"""Validation and defaults for device-level protocol runtime parameters."""

from typing import Any

MODBUS_CLIENT_DEFAULTS = {
    "connect_timeout_ms": 3000,
    "command_timeout_ms": 2000,
    "command_retry_count": 1,
    "reconnect_initial_interval_ms": 2000,
    "reconnect_max_interval_ms": 30000,
    "reconnect_max_attempts": 0,
}

MODBUS_SERVER_DEFAULTS = {
    "client_idle_timeout_ms": 0,
    "max_connections": 0,
}

IEC104_CLIENT_DEFAULTS = {
    "connect_timeout_ms": 3000,
}

IEC104_SERVER_DEFAULTS = {
    "connection_timeout_ms": 10000,
    "message_timeout_ms": 15000,
    "keep_alive_interval_ms": 20000,
    "max_connections": 0,
}

DLT645_CLIENT_DEFAULTS = {
    "command_timeout_ms": 3000,
}

IEC61850_CLIENT_DEFAULTS = {
    "connect_timeout_ms": 3000,
    "command_timeout_ms": 3000,
    "model_discovery_timeout_ms": 600000,
}

IEC61850_SERVER_DEFAULTS = {
    "max_connections": 5,
}

# Keys use the persisted protocol_type and conn_type values.
_DEFAULTS: dict[tuple[int, int], dict[str, int | bool]] = {
    (0, 0): MODBUS_CLIENT_DEFAULTS,
    (1, 1): MODBUS_CLIENT_DEFAULTS,
    (1, 2): MODBUS_SERVER_DEFAULTS,
    (2, 1): IEC104_CLIENT_DEFAULTS,
    (2, 2): IEC104_SERVER_DEFAULTS,
    (3, 0): DLT645_CLIENT_DEFAULTS,
    (3, 1): DLT645_CLIENT_DEFAULTS,
    (3, 2): {"session_idle_timeout_ms": 30000},
    (3, 3): {"session_idle_timeout_ms": 30000},
    (4, 1): IEC61850_CLIENT_DEFAULTS,
    (4, 2): IEC61850_SERVER_DEFAULTS,
}

_RANGES: dict[str, tuple[int, int]] = {
    "connect_timeout_ms": (100, 60000),
    "command_timeout_ms": (100, 120000),
    "command_retry_count": (0, 10),
    "reconnect_initial_interval_ms": (100, 60000),
    "reconnect_max_interval_ms": (1000, 300000),
    "reconnect_max_attempts": (0, 100),
    "health_check_interval_ms": (1000, 600000),
    "model_discovery_timeout_ms": (10000, 3600000),
    "session_idle_timeout_ms": (1000, 600000),
    "client_idle_timeout_ms": (0, 86400000),
    "connection_timeout_ms": (1000, 300000),
    "message_timeout_ms": (1000, 300000),
    "keep_alive_interval_ms": (1000, 3600000),
    "max_connections": (0, 1000),
}


def get_protocol_param_defaults(protocol_type: int, conn_type: int) -> dict[str, int | bool]:
    return dict(_DEFAULTS.get((protocol_type, conn_type), {}))


def normalize_protocol_params(protocol_type: int, conn_type: int, values: dict[str, Any] | None) -> dict[str, Any]:
    defaults = get_protocol_param_defaults(protocol_type, conn_type)
    incoming = values or {}
    unknown = set(incoming) - set(defaults)
    if unknown:
        raise ValueError(f"当前协议和连接模式不支持参数: {', '.join(sorted(unknown))}")

    result: dict[str, Any] = {**defaults, **incoming}
    for name, value in result.items():
        if isinstance(defaults[name], bool):
            if not isinstance(value, bool):
                raise ValueError(f"参数 {name} 必须是布尔值")
            continue
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"参数 {name} 必须是整数")
        minimum, maximum = _RANGES[name]
        if not minimum <= value <= maximum:
            raise ValueError(f"参数 {name} 必须在 {minimum} 到 {maximum} 之间")

    initial = result.get("reconnect_initial_interval_ms")
    maximum = result.get("reconnect_max_interval_ms")
    if initial is not None and maximum is not None and maximum < initial:
        raise ValueError("重连最大间隔不能小于重连初始间隔")
    discovery = result.get("model_discovery_timeout_ms")
    command = result.get("command_timeout_ms")
    if discovery is not None and command is not None and discovery < command:
        raise ValueError("模型发现总超时不能小于单条命令超时")
    return result
