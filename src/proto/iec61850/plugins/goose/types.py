"""GOOSE 插件数据类型定义

定义 GOOSE 相关的枚举、常量、不可变值对象和可变数据类。
遵循现代 Python 设计模式：dataclass + StrEnum/IntEnum。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, StrEnum
from typing import Any

from src.common.mac_address import format_mac_address, normalize_mac_address

# ===== 枚举类型 =====


class GooseState(StrEnum):
    """GOOSE 订阅状态"""

    INIT = "init"
    CONNECTED = "connected"
    LOST = "lost"
    ERROR = "error"


class IecDataType(StrEnum):
    """IEC 61850 数据类型标识"""

    BOOLEAN = "boolean"
    INTEGER = "integer"
    FLOAT = "float"
    STRING = "string"
    BITSTRING = "bitstring"
    TIMESTAMP = "timestamp"


class MmsType(IntEnum):
    """MMS 数据类型常量 (与 pyiec61850 对应)"""

    BOOLEAN = 0
    BIT_STRING = 1
    INTEGER = 2
    UNSIGNED = 3
    FLOAT = 4
    VISIBLE_STRING = 10
    UTC_TIME = 17


# ===== 常量 =====

GOOSE_MULTICAST_MAC_PREFIX = [0x01, 0x0C, 0xCD, 0x01, 0x00]
DEFAULT_TIME_ALLOWED_TO_LIVE = 1000
DEFAULT_CONF_REV = 1
DEFAULT_ST_NUM = 1
DEFAULT_SQ_NUM = 0

GOOSE_STATE_COLOR: dict[GooseState, str] = {
    GooseState.INIT: "#909399",
    GooseState.CONNECTED: "#67C23A",
    GooseState.LOST: "#E6A23C",
    GooseState.ERROR: "#F56C6C",
}


# ===== 数据类 =====


@dataclass(frozen=True, slots=True)
class GooseDataSetEntry:
    """GOOSE 数据集条目 (不可变值对象)

    修改时创建新实例，而非原地修改 value 字段。
    """

    name: str
    value: Any = False
    iec_type: IecDataType = IecDataType.BOOLEAN


@dataclass
class GooseSubscriptionInfo:
    """GOOSE 订阅信息 (可变状态)"""

    go_cb_ref: str
    app_id: int | None = None
    dst_mac: list[int] | None = None
    description: str = ""
    enabled: bool = True
    ied_name: str = ""
    ld_inst: str = ""
    ln_name: str = "LLN0"
    dataset_entries: list[dict[str, Any]] = field(default_factory=list)
    go_id: str = ""
    data_set_ref: str = ""
    conf_rev: int = 0
    received_conf_rev: int = 0
    config_mismatch: bool = False
    st_num: int = 0
    sq_num: int = 0
    time_allowed_to_live: int = 0
    timestamp: int = 0
    state: GooseState = GooseState.INIT
    last_update: float = 0.0
    data_values: list[dict[str, Any]] = field(default_factory=list)
    message_count: int = 0
    last_change: float = 0.0

    def __post_init__(self) -> None:
        self.dst_mac = normalize_mac_address(self.dst_mac)

    def to_dict(self) -> dict[str, Any]:
        return {
            "go_cb_ref": self.go_cb_ref,
            "app_id": self.app_id,
            "go_id": self.go_id,
            "data_set_ref": self.data_set_ref,
            "conf_rev": self.conf_rev,
            "received_conf_rev": self.received_conf_rev,
            "config_mismatch": self.config_mismatch,
            "st_num": self.st_num,
            "sq_num": self.sq_num,
            "time_allowed_to_live": self.time_allowed_to_live,
            "timestamp": self.timestamp,
            "state": self.state.value,
            "last_update": self.last_update,
            "description": self.description,
            "enabled": self.enabled,
            "ied_name": self.ied_name,
            "ld_inst": self.ld_inst,
            "ln_name": self.ln_name,
            "dataset_entries": self.dataset_entries,
            "dst_mac": format_mac_address(self.dst_mac),
            "data_values": self.data_values,
            "message_count": self.message_count,
            "last_change": self.last_change,
        }


@dataclass(frozen=True, slots=True)
class PublisherConfig:
    """GOOSE Publisher 创建配置 (不可变)"""

    interface: str = "eth0"
    go_cb_ref: str = ""
    go_id: str = ""
    data_set_ref: str = ""
    app_id: int = 0x0001
    conf_rev: int = DEFAULT_CONF_REV
    time_allowed_to_live: int = DEFAULT_TIME_ALLOWED_TO_LIVE
    dst_mac: list[int] | None = None
    vlan_id: int = 0
    vlan_prio: int = 4
    simulation: bool = True


@dataclass(frozen=True, slots=True)
class ReceiverConfig:
    """GOOSE Receiver 创建配置 (不可变)"""

    interface: str = "eth0"
