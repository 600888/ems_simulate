"""IEC 61850 DataSet 读取使用的强类型值对象。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True, frozen=True)
class DatasetMember:
    """一个有序 FCDA 成员，以及经过模型校验的安全叶子投影。"""

    index: int
    ref: str
    fc: str = ""
    iec_type: str = "unknown"
    mms_type: str = "MMS_UNKNOWN"
    leaf_refs: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class DatasetDescriptor:
    """远端持久 DataSet 的不可变描述。"""

    ref: str
    name: str = ""
    members: tuple[DatasetMember, ...] = ()


@dataclass(slots=True, frozen=True)
class DatasetMemberError:
    """与特定 DataSet 成员关联的读取失败。"""

    index: int
    ref: str
    reason: str


@dataclass(slots=True, frozen=True)
class DatasetReadResult:
    """DataSet 详细读取结果；部分成员失败时仍保留成功值。"""

    dataset_ref: str
    values: tuple[tuple[str, Any], ...] = ()
    member_values: tuple[tuple[str, Any], ...] = ()
    runtime_types: tuple[tuple[str, str], ...] = ()
    errors: tuple[DatasetMemberError, ...] = ()
    request_count: int = 0

    @property
    def value_map(self) -> dict[str, Any]:
        """返回展开到叶子引用的值映射，供测点批读使用。"""
        return dict(self.values)

    @property
    def member_value_map(self) -> dict[str, Any]:
        """返回原始 FCDA 成员值映射，保持公开接口向后兼容。"""
        return dict(self.member_values)

    @property
    def runtime_type_map(self) -> dict[str, str]:
        """返回叶子引用对应的运行时 MMS 类型。"""
        return dict(self.runtime_types)


@dataclass(slots=True, frozen=True)
class DatasetReadPlan:
    """一次测点批读对应的确定性 DataSet 选择计划。"""

    requested: tuple[str, ...]
    datasets: tuple[DatasetDescriptor, ...]
    uncovered: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class DatasetBatchStats:
    """以单条汇总日志输出的批次诊断指标。"""

    requested: int
    datasets: int
    covered: int
    fallback: int
    failed: int
    mms_requests: int
    elapsed_ms: float
