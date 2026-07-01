"""Report data tree builder for IEC 61850 Reports.

The report callback cache stores one report as flat dictionaries:
``data_values`` maps a data reference to a Python value, and
``reason_codes`` maps the same reference to the inclusion reason.

This module converts that flat shape into an IEDScout-like tree that can be
rendered directly by the frontend.  It deliberately has no pyiec61850 or
FastAPI dependency so it is easy to test.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from datetime import datetime
import json
import re
from typing import Any

KNOWN_FC = {
    "ST",
    "MX",
    "SP",
    "SV",
    "CF",
    "DC",
    "SG",
    "SE",
    "SR",
    "OR",
    "BL",
    "EX",
    "CO",
    "RP",
    "BR",
    "LG",
    "GO",
    "GS",
    "MS",
    "US",
}

VALIDITY_TEXT = {
    0: "good",
    1: "invalid",
    2: "questionable",
    3: "reserved",
}

DETAIL_QUALITY_FLAGS = (
    ("Overflow", "overflow"),
    ("OutOfRange", "out_of_range"),
    ("BadReference", "bad_reference"),
    ("Oscillatory", "oscillatory"),
    ("Failure", "failure"),
    ("OldData", "old_data"),
    ("Inconsistent", "inconsistent"),
    ("Inaccurate", "inaccurate"),
)


@dataclass(slots=True)
class ReportTreeNode:
    """Frontend-ready tree node."""

    id: str
    label: str
    node_type: str
    fc: str | None = None
    reason: str | None = None
    value: Any = None
    raw_ref: str | None = None
    children: list[ReportTreeNode] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "node_type": self.node_type,
            "fc": self.fc,
            "reason": self.reason,
            "value": self.value,
            "raw_ref": self.raw_ref,
            "children": [child.to_dict() for child in self.children],
        }


@dataclass(slots=True, frozen=True)
class ParsedReportRef:
    """Parsed report data reference."""

    ld: str
    ln: str
    do_name: str
    da_parts: tuple[str, ...]
    fc: str = ""

    @property
    def do_ref(self) -> str:
        return f"{self.ld}/{self.ln}.{self.do_name}"


class ReportTreeBuilder:
    """Build a report value tree from one cached report entry."""

    def build(self, entry: dict[str, Any]) -> list[dict[str, Any]]:
        values = entry.get("data_values") or {}
        reasons = entry.get("reason_codes") or {}
        if not isinstance(values, dict):
            return []

        roots: dict[str, ReportTreeNode] = {}
        unmapped = ReportTreeNode(
            id="unmapped",
            label="Unmapped Data",
            node_type="group",
            children=[],
        )

        for raw_ref, value in values.items():
            ref = str(raw_ref)
            reason = self._reason_for_ref(reasons, ref)
            parsed = parse_report_ref(ref)
            if parsed is None:
                unmapped.children.append(
                    ReportTreeNode(
                        id=f"unmapped/{len(unmapped.children)}",
                        label=ref,
                        node_type="value",
                        reason=reason,
                        value=stringify_value(value),
                        raw_ref=ref,
                    )
                )
                continue

            ld_node = self._get_child(roots, parsed.ld, parsed.ld, "ld")
            ln_node = self._get_child_by_id(ld_node, f"{parsed.ld}/{parsed.ln}", parsed.ln, "ln")
            do_node = self._get_child_by_id(ln_node, parsed.do_ref, parsed.do_name, "do", raw_ref=parsed.do_ref)
            self._append_da_path(do_node, parsed, value, reason, ref)

        ordered_roots = [roots[key] for key in sorted(roots)]
        if unmapped.children:
            ordered_roots.append(unmapped)
        return [node.to_dict() for node in ordered_roots]

    def _append_da_path(
        self,
        do_node: ReportTreeNode,
        parsed: ParsedReportRef,
        value: Any,
        reason: str,
        raw_ref: str,
    ) -> None:
        structured_value = parse_structured_value(value)
        if self._is_standard_do_structure(structured_value):
            self._append_standard_do_structure(
                do_node,
                parsed,
                structured_value,
                reason,
                raw_ref,
            )
            return

        if not parsed.da_parts:
            do_node.value = stringify_value(value)
            do_node.reason = reason
            do_node.raw_ref = raw_ref
            return

        current = do_node
        for index, part in enumerate(parsed.da_parts):
            is_leaf = index == len(parsed.da_parts) - 1
            node_id = f"{parsed.do_ref}.{'.'.join(parsed.da_parts[: index + 1])}"
            node = self._get_child_by_id(
                current,
                node_id,
                part,
                "da" if index == 0 else "bda",
                fc=parsed.fc or None,
                raw_ref=raw_ref if is_leaf else None,
            )
            if is_leaf:
                node.reason = reason
                node.value = stringify_value(value)
                if part == "q":
                    self._decorate_quality_node(node, value)
                elif part == "t":
                    self._decorate_timestamp_node(node, value)
            current = node

    @staticmethod
    def _is_standard_do_structure(value: Any) -> bool:
        """Return whether value looks like a common CDC ``value/q/t`` structure.

        Some devices return an entire MMS structure even when the DataSet member
        reference points at a leaf DA.  The most common layouts are
        ``[[mag], q, t]`` for measured values and ``[stVal, q, t]`` for status
        values.  Requiring a nested analogue value or a boolean status keeps
        arbitrary numeric arrays from being mislabeled as IEC 61850 fields.
        """
        if not isinstance(value, (list, tuple)) or len(value) < 3:
            return False
        primary = value[0]
        is_status_value = isinstance(primary, bool) or (
            isinstance(primary, int) and not isinstance(primary, bool) and primary in (0, 1)
        )
        if not isinstance(primary, (list, tuple)) and not is_status_value:
            return False
        return decode_quality(value[1]) is not None and decode_timestamp(value[2]) is not None

    def _append_standard_do_structure(
        self,
        do_node: ReportTreeNode,
        parsed: ParsedReportRef,
        value: list[Any] | tuple[Any, ...],
        reason: str,
        raw_ref: str,
    ) -> None:
        """Expand common CDC values into named DA/BDA nodes."""
        fc = parsed.fc or None
        primary = value[0]

        if isinstance(primary, (list, tuple)):
            mag_node = self._get_child_by_id(
                do_node,
                f"{parsed.do_ref}.mag",
                "mag",
                "da",
                fc=fc,
            )
            for index, item in enumerate(primary):
                if len(primary) == 1:
                    field_name = (
                        parsed.da_parts[-1]
                        if parsed.da_parts[:1] == ("mag",) and parsed.da_parts[-1] in ("f", "i")
                        else "f"
                        if isinstance(item, float)
                        else "i"
                    )
                else:
                    field_name = f"component[{index}]"
                child = self._get_child_by_id(
                    mag_node,
                    f"{parsed.do_ref}.mag.{field_name}",
                    field_name,
                    "bda",
                    raw_ref=raw_ref,
                )
                child.reason = reason
                child.value = stringify_value(item)
        else:
            st_val = self._get_child_by_id(
                do_node,
                f"{parsed.do_ref}.stVal",
                "stVal",
                "da",
                fc=fc,
                raw_ref=raw_ref,
            )
            st_val.reason = reason
            st_val.value = stringify_value(primary)

        q_node = self._get_child_by_id(
            do_node,
            f"{parsed.do_ref}.q",
            "q",
            "da",
            fc=fc,
            raw_ref=raw_ref,
        )
        q_node.reason = reason
        self._decorate_quality_node(q_node, value[1])

        t_node = self._get_child_by_id(
            do_node,
            f"{parsed.do_ref}.t",
            "t",
            "da",
            fc=fc,
            raw_ref=raw_ref,
        )
        t_node.reason = reason
        self._decorate_timestamp_node(t_node, value[2])

        for index, item in enumerate(value[3:], start=3):
            label = f"component[{index}]"
            extra_node = self._get_child_by_id(
                do_node,
                f"{parsed.do_ref}.{label}",
                label,
                "da",
                fc=fc,
                raw_ref=raw_ref,
            )
            extra_node.reason = reason
            extra_node.value = stringify_value(item)

    def _decorate_quality_node(self, node: ReportTreeNode, value: Any) -> None:
        decoded = decode_quality(value)
        if decoded is None:
            node.value = stringify_value(value)
            return

        node.value = decoded["validity_text"]
        node.children = [
            ReportTreeNode(
                id=f"{node.id}.Validity",
                label="Validity",
                node_type="bda",
                reason=node.reason,
                value=decoded["validity_text"],
                raw_ref=node.raw_ref,
            ),
            ReportTreeNode(
                id=f"{node.id}.QualityDetails",
                label="Quality Details",
                node_type="group",
                reason=node.reason,
                children=[
                    ReportTreeNode(
                        id=f"{node.id}.QualityDetails.{field_name}",
                        label=label,
                        node_type="bda",
                        reason=node.reason,
                        value=decoded[field_name],
                        raw_ref=node.raw_ref,
                    )
                    for label, field_name in DETAIL_QUALITY_FLAGS
                ],
            ),
            ReportTreeNode(
                id=f"{node.id}.Source",
                label="Source",
                node_type="bda",
                reason=node.reason,
                value=decoded["source_text"],
                raw_ref=node.raw_ref,
            ),
            ReportTreeNode(
                id=f"{node.id}.Test",
                label="Test",
                node_type="bda",
                reason=node.reason,
                value=decoded["test"],
                raw_ref=node.raw_ref,
            ),
            ReportTreeNode(
                id=f"{node.id}.OperatorBlocked",
                label="OperatorBlocked",
                node_type="bda",
                reason=node.reason,
                value=decoded["operator_blocked"],
                raw_ref=node.raw_ref,
            ),
        ]

    def _decorate_timestamp_node(self, node: ReportTreeNode, value: Any) -> None:
        decoded = decode_timestamp(value)
        if decoded is None:
            node.value = stringify_value(value)
            return

        node.value = decoded["datetime"]
        node.children = [
            ReportTreeNode(
                id=f"{node.id}.Datetime",
                label="Datetime",
                node_type="bda",
                reason=node.reason,
                value=decoded["datetime"],
                raw_ref=node.raw_ref,
            ),
            ReportTreeNode(
                id=f"{node.id}.Seconds",
                label="Seconds",
                node_type="bda",
                reason=node.reason,
                value=decoded["seconds"],
                raw_ref=node.raw_ref,
            ),
            ReportTreeNode(
                id=f"{node.id}.UnixMs",
                label="UnixMs",
                node_type="bda",
                reason=node.reason,
                value=decoded["unix_ms"],
                raw_ref=node.raw_ref,
            ),
            ReportTreeNode(
                id=f"{node.id}.Fraction",
                label="Fraction",
                node_type="bda",
                reason=node.reason,
                value=decoded["fraction"],
                raw_ref=node.raw_ref,
            ),
        ]

    @staticmethod
    def _get_child(
        roots: dict[str, ReportTreeNode],
        node_id: str,
        label: str,
        node_type: str,
    ) -> ReportTreeNode:
        if node_id not in roots:
            roots[node_id] = ReportTreeNode(id=node_id, label=label, node_type=node_type)
        return roots[node_id]

    @staticmethod
    def _get_child_by_id(
        parent: ReportTreeNode,
        node_id: str,
        label: str,
        node_type: str,
        *,
        fc: str | None = None,
        raw_ref: str | None = None,
    ) -> ReportTreeNode:
        for child in parent.children:
            if child.id == node_id:
                if fc and not child.fc:
                    child.fc = fc
                if raw_ref and not child.raw_ref:
                    child.raw_ref = raw_ref
                return child

        child = ReportTreeNode(
            id=node_id,
            label=label,
            node_type=node_type,
            fc=fc,
            raw_ref=raw_ref,
        )
        parent.children.append(child)
        return child

    @staticmethod
    def _reason_for_ref(reasons: Any, ref: str) -> str:
        if not isinstance(reasons, dict):
            return ""
        reason = reasons.get(ref)
        if reason is None:
            reason = reasons.get(ref.replace("$", "."))
        return "" if reason is None else str(reason)


class ReportEntryNotFoundError(ValueError):
    """Requested report entry is not present in the bounded cache."""


def select_report_entry(
    data: list[dict[str, Any]],
    entry_key: str | None,
    latest: bool,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Select one cached report entry and return (entry, summary)."""
    if not data:
        return None, None

    summaries = [make_entry_summary(entry, index) for index, entry in enumerate(data)]
    if entry_key:
        for entry, summary in zip(data, summaries, strict=True):
            if summary.get("entry_key") == entry_key:
                return entry, summary
        return None, None

    index = len(data) - 1 if latest else 0
    return data[index], summaries[index]


def parse_report_ref(raw_ref: str) -> ParsedReportRef | None:
    """Parse common IEC 61850 report value reference forms."""
    if not raw_ref or raw_ref.startswith("data[") or "/" not in raw_ref:
        return None

    if "$" in raw_ref:
        parsed = _parse_dollar_ref(raw_ref)
        if parsed:
            return parsed

    return _parse_dot_ref(raw_ref)


def _parse_dollar_ref(raw_ref: str) -> ParsedReportRef | None:
    ld, rest = raw_ref.split("/", 1)
    tokens = [token for token in rest.split("$") if token]
    if len(tokens) < 3:
        return None

    ln = tokens[0]
    fc = ""
    path_tokens = tokens[1:]
    if path_tokens and path_tokens[0].upper() in KNOWN_FC:
        fc = path_tokens[0].upper()
        path_tokens = path_tokens[1:]

    if not ln or len(path_tokens) < 1:
        return None

    return ParsedReportRef(
        ld=ld,
        ln=ln,
        do_name=path_tokens[0],
        da_parts=tuple(path_tokens[1:]),
        fc=fc,
    )


def _parse_dot_ref(raw_ref: str) -> ParsedReportRef | None:
    ld, rest = raw_ref.split("/", 1)
    parts = [part for part in rest.split(".") if part]
    if len(parts) < 2:
        return None

    ln = parts[0]
    fc = ""
    path_parts = parts[1:]
    if path_parts and path_parts[0].upper() in KNOWN_FC:
        fc = path_parts[0].upper()
        path_parts = path_parts[1:]

    if not ln or len(path_parts) < 1:
        return None

    return ParsedReportRef(
        ld=ld,
        ln=ln,
        do_name=path_parts[0],
        da_parts=tuple(path_parts[1:]),
        fc=fc,
    )


def decode_quality(value: Any) -> dict[str, Any] | None:
    """Decode IEC 61850 Quality packed bits or quality-like dictionaries."""
    packed = _quality_packed_value(value)
    if packed is None:
        return None

    validity = packed & 0x03
    detail_quality = (packed >> 2) & 0xFF
    source = (packed >> 10) & 0x01
    decoded: dict[str, Any] = {
        "validity": validity,
        "validity_text": VALIDITY_TEXT.get(validity, str(validity)),
        "detail_quality": detail_quality,
        "source": source,
        "source_text": "substituted" if source else "process",
        "test": bool((packed >> 11) & 0x01),
        "operator_blocked": bool((packed >> 12) & 0x01),
    }

    for index, (_, field_name) in enumerate(DETAIL_QUALITY_FLAGS):
        decoded[field_name] = bool(detail_quality & (1 << index))
    return decoded


def _quality_packed_value(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if re.fullmatch(r"0x[0-9a-fA-F]+", text):
            return int(text, 16)
        if re.fullmatch(r"\d+", text):
            return int(text)
        return None
    if isinstance(value, dict):
        validity = value.get("validity")
        detail = value.get("detailQuality", value.get("detail_quality", 0))
        source = value.get("source", 0)
        test = value.get("test", False)
        operator_blocked = value.get("operatorBlocked", value.get("operator_blocked", False))
        if validity is None:
            return None
        try:
            packed = int(validity) & 0x03
            packed |= (int(detail or 0) & 0xFF) << 2
            packed |= (int(source or 0) & 0x01) << 10
            packed |= (1 if bool(test) else 0) << 11
            packed |= (1 if bool(operator_blocked) else 0) << 12
            return packed
        except (TypeError, ValueError):
            return None
    return None


def decode_timestamp(value: Any) -> dict[str, Any] | None:
    """Decode timestamps represented as Unix milliseconds."""
    ms = _timestamp_ms(value)
    if ms is None:
        return None

    seconds = ms // 1000
    fraction = int((ms % 1000) * (1 << 24) / 1000)
    try:
        dt_text = datetime.fromtimestamp(ms / 1000.0).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    except (OverflowError, OSError, ValueError):
        return None

    return {
        "datetime": dt_text,
        "seconds": seconds,
        "unix_ms": ms,
        "fraction": fraction,
    }


def _timestamp_ms(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not re.fullmatch(r"\d+(\.\d+)?", text):
            return None
        number = float(text)
        return int(number)
    return None


def stringify_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    # Legacy cache entries can still contain a SWIG MmsValue. Use the runtime
    # MMS type dispatcher rather than trying float/int/bool accessors in order.
    raw_str = str(value)
    if "<Swig Object" in raw_str:
        try:
            from ...core.mms_value import mms_value_to_python

            converted = mms_value_to_python(value)
            if converted is not None:
                return converted
        except Exception:
            pass
        return "[unresolved]"
    return raw_str


def parse_structured_value(value: Any) -> Any:
    """Convert a serialized MMS aggregate into safe Python containers.

    ``MmsValue_toString`` commonly returns structures such as
    ``[[43.0], 0.0, 0.0]``.  ``literal_eval`` accepts only Python literals, so
    the display layer can recover the hierarchy without evaluating code.
    """
    if isinstance(value, (list, tuple, dict)):
        return value
    if not isinstance(value, str):
        return value

    text = value.strip()
    if len(text) < 2 or text[0] not in "[{(" or text[-1] not in "]})":
        return value
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        try:
            parsed = ast.literal_eval(text)
        except (SyntaxError, ValueError):
            return value
    return parsed if isinstance(parsed, (list, tuple, dict)) else value


def make_entry_summary(entry: dict[str, Any], index: int) -> dict[str, Any]:
    """Create a stable frontend key for a cached report entry."""
    received_at = str(entry.get("received_at") or "")
    seq_num = entry.get("seq_num")
    rpt_id = str(entry.get("rpt_id") or "")
    uid = entry.get("uid", 0)
    entry_key = f"uid:{uid}"

    return {
        "entry_key": entry_key,
        "index": index,
        "seq_num": seq_num,
        "time_stamp": entry.get("time_stamp") or "",
        "received_at": received_at,
        "data_set": entry.get("data_set") or "",
        "rpt_id": rpt_id,
        "conf_rev": entry.get("conf_rev"),
        "entry_id": entry.get("entry_id"),
        "value_count": len(entry.get("data_values") or {}),
        "uid": uid,
    }
