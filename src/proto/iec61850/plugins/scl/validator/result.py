"""校验结果 — Result 模式

替代异常处理校验结果，支持合并多个校验结果。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Severity(Enum):
    """校验问题严重级别"""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(slots=True)
class ValidationIssue:
    """单个校验问题"""
    severity: Severity = Severity.ERROR
    rule_id: str = ""
    message: str = ""
    location: str = ""  # 如 "IED.KG_BAMS.LD0.LLN0"

    def __str__(self) -> str:
        prefix = self.severity.value.upper()
        loc = f" [{self.location}]" if self.location else ""
        return f"{prefix} ({self.rule_id}): {self.message}{loc}"


@dataclass
class ValidationResult:
    """校验结果 — 可合并"""

    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """是否无 ERROR 级别问题"""
        return not any(i.severity == Severity.ERROR for i in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(i.severity == Severity.WARNING for i in self.issues)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.WARNING)

    def add_error(self, rule_id: str, message: str, location: str = "") -> None:
        self.issues.append(ValidationIssue(
            severity=Severity.ERROR, rule_id=rule_id, message=message, location=location
        ))

    def add_warning(self, rule_id: str, message: str, location: str = "") -> None:
        self.issues.append(ValidationIssue(
            severity=Severity.WARNING, rule_id=rule_id, message=message, location=location
        ))

    def add_info(self, rule_id: str, message: str, location: str = "") -> None:
        self.issues.append(ValidationIssue(
            severity=Severity.INFO, rule_id=rule_id, message=message, location=location
        ))

    def merge(self, other: ValidationResult) -> ValidationResult:
        """合并另一个校验结果"""
        return ValidationResult(issues=self.issues + other.issues)

    @classmethod
    def empty(cls) -> ValidationResult:
        """无错误时返回的有效空对象"""
        return cls()

    def __str__(self) -> str:
        lines = [f"校验结果: {self.error_count} 个错误, {self.warning_count} 个警告"]
        for issue in self.issues:
            lines.append(f"  {issue}")
        return "\n".join(lines)
