"""校验规则 — Protocol + Registry 模式"""
from __future__ import annotations

from typing import Protocol, runtime_checkable, TYPE_CHECKING

from .result import ValidationResult

if TYPE_CHECKING:
    from ..model.scl_document import SclDocument


@runtime_checkable
class ValidationRule(Protocol):
    """校验规则协议"""
    @property
    def rule_id(self) -> str: ...
    @property
    def description(self) -> str: ...

    def validate(self, doc: SclDocument) -> ValidationResult: ...


# 规则注册表
_rules: dict[str, type] = {}


def register_rule(rule_cls: type) -> type:
    """注册校验规则 (装饰器)"""
    _rules[rule_cls.rule_id] = rule_cls  # type: ignore
    return rule_cls


def get_rule(rule_id: str) -> type | None:
    """获取校验规则类"""
    return _rules.get(rule_id)


def get_all_rules() -> dict[str, type]:
    """获取所有已注册规则"""
    return dict(_rules)


def validate_all(doc: SclDocument) -> ValidationResult:
    """执行所有已注册的校验规则"""
    result = ValidationResult.empty()
    for rule_cls in _rules.values():
        rule = rule_cls()
        result = result.merge(rule.validate(doc))
    return result
