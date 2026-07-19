"""Validation and defaults for device-level protocol runtime parameters."""

import re
from typing import Any

MODBUS_CLIENT_DEFAULTS = {
    "connect_timeout_ms": 3000,
    "command_timeout_ms": 2000,
    "command_retry_count": 1,
    "reconnect_initial_interval_ms": 2000,
    "reconnect_max_interval_ms": 30000,
    "reconnect_max_attempts": -1,
}

MODBUS_SERVER_DEFAULTS = {
    "client_idle_timeout_ms": 0,
    "max_connections": 0,
}

IEC104_CLIENT_DEFAULTS = {
    "send_window_size": 12,
    "receive_window_size": 8,
    "t0_timeout_s": 10,
    "t1_timeout_s": 15,
    "t2_timeout_s": 10,
    "t3_interval_s": 20,
    "originator_address": 0,
    "clock_sync_interval_s": 0,
    "general_interrogation_interval_s": 0,
    "counter_interrogation_interval_s": 0,
    "general_interrogation_on_connect": True,
    "counter_interrogation_on_connect": True,
    "reconnect_initial_interval_ms": 2000,
    "reconnect_max_interval_ms": 30000,
    "reconnect_max_attempts": -1,
}

IEC104_SERVER_DEFAULTS = {
    "send_window_size": 12,
    "receive_window_size": 8,
    "t0_timeout_s": 3,
    "t1_timeout_s": 3,
    "t2_timeout_s": 1,
    "t3_interval_s": 20,
    "max_connections": 0,
}

DLT645_CLIENT_DEFAULTS = {
    "command_timeout_ms": 3000,
}

IEC61850_CLIENT_DEFAULTS = {
    "connect_timeout_ms": 3000,
    "command_timeout_ms": 3000,
    "model_discovery_timeout_s": 60,
    "mms_capture_enabled": False,
    "authentication_enabled": False,
    "authentication_password": "",
    "remote_ap_title": "1,1,1,999,1",
    "remote_ae_qualifier": 12,
    "remote_p_selector": "00 00 00 01",
    "remote_s_selector": "00 01",
    "remote_t_selector": "00 01",
    "local_ap_title": "1,1,1,999,1",
    "local_ae_qualifier": 12,
    "local_p_selector": "00 00 00 01",
    "local_s_selector": "00 01",
    "local_t_selector": "00 01",
}

IEC61850_SERVER_DEFAULTS = {
    "max_connections": 5,
    "mms_capture_enabled": False,
    "authentication_enabled": False,
    "authentication_password": "",
    "file_service_directory": "",
}

# Keys use the persisted protocol_type and conn_type values.
_DEFAULTS: dict[tuple[int, int], dict[str, int | bool | str]] = {
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
    "reconnect_max_attempts": (-1, 100),
    "health_check_interval_ms": (1000, 600000),
    "model_discovery_timeout_s": (10, 3600),
    "session_idle_timeout_ms": (1000, 600000),
    "client_idle_timeout_ms": (0, 86400000),
    "connection_timeout_ms": (1000, 300000),
    "message_timeout_ms": (1000, 300000),
    "keep_alive_interval_ms": (1000, 3600000),
    "send_window_size": (1, 32767),
    "receive_window_size": (1, 32767),
    "t0_timeout_s": (1, 3600),
    "t1_timeout_s": (1, 3600),
    "t2_timeout_s": (1, 3600),
    "t3_interval_s": (1, 86400),
    "originator_address": (0, 255),
    "clock_sync_interval_s": (0, 86400),
    "general_interrogation_interval_s": (0, 86400),
    "counter_interrogation_interval_s": (0, 86400),
    "max_connections": (0, 1000),
    "remote_ae_qualifier": (0, 2147483647),
    "local_ae_qualifier": (0, 2147483647),
}

_AP_TITLE_FIELDS = {"remote_ap_title", "local_ap_title"}
_SELECTOR_MAX_BYTES = {
    "remote_p_selector": 16,
    "remote_s_selector": 16,
    "remote_t_selector": 4,
    "local_p_selector": 16,
    "local_s_selector": 16,
    "local_t_selector": 4,
}

_IEC104_LEGACY_TIME_PARAMS = {
    "connect_timeout_ms": "t0_timeout_s",
    "connection_timeout_ms": "t0_timeout_s",
    "message_timeout_ms": "t1_timeout_s",
    "keep_alive_interval_ms": "t3_interval_s",
}


def get_protocol_param_defaults(protocol_type: int, conn_type: int) -> dict[str, int | bool | str]:
    return dict(_DEFAULTS.get((protocol_type, conn_type), {}))


def normalize_protocol_params(protocol_type: int, conn_type: int, values: dict[str, Any] | None) -> dict[str, Any]:
    defaults = get_protocol_param_defaults(protocol_type, conn_type)
    incoming = dict(values or {})
    if protocol_type == 2:
        for legacy_name, current_name in _IEC104_LEGACY_TIME_PARAMS.items():
            if legacy_name not in incoming:
                continue
            legacy_value = incoming.pop(legacy_name)
            if current_name not in incoming and isinstance(legacy_value, int) and not isinstance(legacy_value, bool):
                incoming[current_name] = max(1, legacy_value // 1000)
    unknown = set(incoming) - set(defaults)
    if unknown:
        raise ValueError(f"当前协议和连接模式不支持参数: {', '.join(sorted(unknown))}")

    result: dict[str, Any] = {**defaults, **incoming}
    for name, value in result.items():
        if isinstance(defaults[name], bool):
            if not isinstance(value, bool):
                raise ValueError(f"参数 {name} 必须是布尔值")
            continue
        if isinstance(defaults[name], str):
            if not isinstance(value, str):
                raise ValueError(f"参数 {name} 必须是字符串")
            value = value.strip()
            if name in _AP_TITLE_FIELDS:
                parts = [part.strip() for part in re.split(r"[,.]", value)]
                if not parts or any(not part.isdigit() for part in parts):
                    raise ValueError(f"参数 {name} 必须是逗号或点分隔的数字，例如 1,1,1,999,1")
                value = ",".join(str(int(part)) for part in parts)
            elif name in _SELECTOR_MAX_BYTES:
                compact = re.sub(r"[\s:-]", "", value)
                if not compact or len(compact) % 2 or not re.fullmatch(r"[0-9a-fA-F]+", compact):
                    raise ValueError(f"参数 {name} 必须是十六进制字节，例如 00 01")
                byte_count = len(compact) // 2
                if byte_count > _SELECTOR_MAX_BYTES[name]:
                    raise ValueError(f"参数 {name} 最多允许 {_SELECTOR_MAX_BYTES[name]} 个字节")
                value = " ".join(compact[index : index + 2].upper() for index in range(0, len(compact), 2))
            result[name] = value
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
    discovery = result.get("model_discovery_timeout_s")
    command = result.get("command_timeout_ms")
    if discovery is not None and command is not None and discovery * 1000 < command:
        raise ValueError("模型发现总超时不能小于单条命令超时")
    t1 = result.get("t1_timeout_s")
    t2 = result.get("t2_timeout_s")
    if t1 is not None and t2 is not None and t2 > t1:
        raise ValueError("IEC104 t2 确认间隔不能大于 t1 报文确认超时")
    send_window = result.get("send_window_size")
    receive_window = result.get("receive_window_size")
    if send_window is not None and receive_window is not None and receive_window > send_window:
        raise ValueError("IEC104 接收窗口 w 不能大于发送窗口 k")
    if result.get("authentication_enabled") and not result.get("authentication_password"):
        raise ValueError("启用 IEC61850 用户认证时必须填写认证密码")
    return result
