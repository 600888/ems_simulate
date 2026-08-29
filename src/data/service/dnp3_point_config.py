"""Load persisted point-level DNP3 JSON onto runtime point objects."""

from __future__ import annotations

import json
from typing import Any, TypeVar

from src.proto.dnp3.point_config import Dnp3PointConfig

T = TypeVar("T")


def apply_dnp3_point_config(point: T, item: dict[str, Any], frame_type: int) -> T:
    """将持久化的 DNP3 测点 JSON 配置加载到运行时测点对象上。"""
    raw = item.get("dnp3_config")
    if isinstance(raw, str) and raw:
        raw = json.loads(raw)
    if not isinstance(raw, dict):
        raw = {}
    point.dnp3_config = Dnp3PointConfig.from_mapping(frame_type, raw).to_dict()  # type: ignore[attr-defined]
    return point
