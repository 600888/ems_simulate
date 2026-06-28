"""Defensive filtering for legacy point rows without a protocol discriminator."""

from collections.abc import Iterable

from src.enums.modbus_def import ProtocolType
from src.web.log import log

_IEC61850_PROTOCOLS = (ProtocolType.Iec61850Server, ProtocolType.Iec61850Client)


def _looks_like_iec61850(item: dict) -> bool:
    address = str(item.get("reg_addr") or "")
    return bool(item.get("fc")) or ("/" in address and "." in address)


def reject_foreign_protocol_points(
    items: Iterable[dict],
    channel_id: int,
    protocol_type: ProtocolType,
    point_type: str,
) -> list[dict]:
    """Reject rows that are unambiguously from another protocol family.

    Older point tables do not store a source protocol. IEC 61850 rows can still
    be identified reliably by their FC metadata or MMS object-reference address.
    This is a final read-side guard; write-side API validation remains mandatory.
    """
    target_is_iec61850 = protocol_type in _IEC61850_PROTOCOLS
    accepted: list[dict] = []
    rejected = 0

    for item in items:
        source_is_iec61850 = _looks_like_iec61850(item)
        if source_is_iec61850 != target_is_iec61850:
            rejected += 1
            continue
        accepted.append(item)

    if rejected:
        log.warning(
            f"通道 {channel_id} 的 {point_type} 测点中有 {rejected} 个与 {protocol_type.value} 协议不兼容，已拒绝加载"
        )
    return accepted
