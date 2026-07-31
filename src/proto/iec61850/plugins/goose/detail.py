"""Enrich captured GOOSE values with DataSet and configured point metadata."""

from __future__ import annotations

import copy
import re
import threading
import time
from typing import Any

_CACHE_TTL_SECONDS = 2.0
_CACHE_LOCK = threading.Lock()
_METADATA_CACHE: dict[
    int,
    tuple[float, list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]],
] = {}
_POINT_LOOKUP_CACHE: dict[int, tuple[int, dict[str, dict[str, Any]]]] = {}
_FC_SEGMENT = re.compile(r"\$(ST|MX|CO|SP|SG|SE|CF|DC|EX|SV|BL|OR)\$", re.IGNORECASE)


def _normalize_ref(value: Any) -> str:
    """统一 IEC 61850 对象引用的分隔符和功能约束表示，便于稳定匹配。"""
    text = str(value or "").strip().replace("\\", "/")
    text = _FC_SEGMENT.sub(".", text)
    text = text.replace("$", ".").replace("..", ".")
    return text.casefold()


def _load_channel_metadata(
    channel_id: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """加载channel元数据。"""
    now = time.monotonic()
    with _CACHE_LOCK:
        cached = _METADATA_CACHE.get(channel_id)
        if cached and now - cached[0] < _CACHE_TTL_SECONDS:
            return cached[1], cached[2], cached[3]

    from src.data.dao.goose_publisher_dao import GoosePublisherDao
    from src.data.dao.goose_receiver_dao import GooseReceiverDao
    from src.data.dao.point_dao import PointDao

    receivers = GooseReceiverDao.list_by_channel(channel_id)
    publishers = GoosePublisherDao.get_by_channel(channel_id)
    points = PointDao.get_points_by_channel(channel_id)
    with _CACHE_LOCK:
        _METADATA_CACHE[channel_id] = (now, receivers, publishers, points)
    return receivers, publishers, points


def _find_dataset_entries(
    receivers: list[dict[str, Any]],
    publishers: list[dict[str, Any]],
    go_cb_ref: str,
    data_set_ref: str,
    app_id: int | None,
) -> list[dict[str, Any]]:
    """查找数据集条目并返回匹配结果。"""
    normalized_cb = _normalize_ref(go_cb_ref)
    normalized_dataset = _normalize_ref(data_set_ref)
    dataset_fallback: list[dict[str, Any]] = []
    app_id_fallback: list[dict[str, Any]] = []
    for receiver in receivers:
        for subscription in receiver.get("subscriptions", []):
            entries = subscription.get("dataset_entries", []) or []
            if not entries:
                continue
            if _normalize_ref(subscription.get("go_cb_ref")) == normalized_cb:
                return entries
            if normalized_dataset and _normalize_ref(subscription.get("data_set_ref")) == normalized_dataset:
                dataset_fallback = entries
            if app_id is not None and subscription.get("app_id") == app_id:
                app_id_fallback = entries
    for publisher in publishers:
        entries = publisher.get("entries", []) or publisher.get("dataset_entries", []) or []
        if not entries:
            continue
        if _normalize_ref(publisher.get("go_cb_ref")) == normalized_cb:
            return entries
        if normalized_dataset and _normalize_ref(publisher.get("data_set_ref")) == normalized_dataset:
            dataset_fallback = entries
        if app_id is not None and publisher.get("app_id") == app_id:
            app_id_fallback = entries
    return dataset_fallback or app_id_fallback


def _get_point_lookup(channel_id: int, points: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    with _CACHE_LOCK:
        cached = _POINT_LOOKUP_CACHE.get(channel_id)
        if cached and cached[0] == id(points):
            return cached[1]

    lookup: dict[str, dict[str, Any]] = {}
    for point in points:
        for value in (
            point.get("reg_addr") or point.get("address"),
            point.get("code"),
            point.get("name"),
        ):
            normalized = _normalize_ref(value)
            if normalized:
                lookup.setdefault(normalized, point)
    with _CACHE_LOCK:
        _POINT_LOOKUP_CACHE[channel_id] = (id(points), lookup)
    return lookup


def _find_point(
    points: list[dict[str, Any]],
    entry: dict[str, Any],
    lookup: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """查找测点并返回匹配结果。"""
    reference = _normalize_ref(entry.get("name") or entry.get("ref") or entry.get("fcda_ref"))
    if not reference:
        return None
    if lookup and reference in lookup:
        return lookup[reference]
    best: dict[str, Any] | None = None
    for point in points:
        point_ref = _normalize_ref(point.get("reg_addr") or point.get("address"))
        point_code = _normalize_ref(point.get("code"))
        point_name = _normalize_ref(point.get("name"))
        if reference in (point_code, point_name):
            return point
        if not point_ref:
            continue
        if point_ref == reference:
            return point
        if point_ref.endswith(reference) or reference.endswith(point_ref):
            best = point
    return best


def enrich_goose_packet(packet: dict[str, Any], channel_id: int) -> dict[str, Any]:
    """补充GOOSE报文。"""
    enriched = dict(packet)
    enriched["data_values"] = [copy.deepcopy(item) for item in packet.get("data_values", [])]
    try:
        receivers, publishers, points = _load_channel_metadata(channel_id)
    except Exception:
        receivers, publishers, points = [], [], []
    entries = _find_dataset_entries(
        receivers,
        publishers,
        str(packet.get("go_cb_ref", "")),
        str(packet.get("data_set_ref", "")),
        int(packet["app_id"]) if packet.get("app_id") is not None else None,
    )
    point_lookup = _get_point_lookup(channel_id, points)
    for index, value in enumerate(enriched["data_values"]):
        value["index"] = index
        if index >= len(entries):
            value.setdefault("name", f"Entry[{index}]")
            continue
        entry = entries[index]
        value["name"] = entry.get("name") or f"Entry[{index}]"
        value["fc"] = entry.get("fc", "")
        value["description"] = entry.get("description", "")
        value["dataset_type"] = entry.get("type") or entry.get("iec_type") or ""
        point = _find_point(points, entry, point_lookup)
        if point:
            value["point"] = {
                "code": point.get("code", ""),
                "name": point.get("name", ""),
                "address": point.get("reg_addr") or point.get("address") or "",
                "frame_type": point.get("frame_type"),
                "fc": point.get("fc", ""),
                "mms_type": point.get("mms_type", ""),
            }
    enriched["metadata_matched"] = bool(entries)
    return enriched


def clear_goose_detail_cache(channel_id: int | None = None) -> None:
    """清空GOOSEdetail缓存。"""
    with _CACHE_LOCK:
        if channel_id is None:
            _METADATA_CACHE.clear()
            _POINT_LOOKUP_CACHE.clear()
        else:
            _METADATA_CACHE.pop(channel_id, None)
            _POINT_LOOKUP_CACHE.pop(channel_id, None)
