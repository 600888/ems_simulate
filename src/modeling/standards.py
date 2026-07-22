"""声明式 IEC 61850 标准包注册表。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

STANDARD_ROOT = Path(__file__).with_name("standard_packages")


def load_standard_catalog() -> dict[str, dict[str, Any]]:
    catalog: dict[str, dict[str, Any]] = {}
    for manifest_path in sorted(STANDARD_ROOT.glob("*/manifest.json")):
        item = json.loads(manifest_path.read_text(encoding="utf-8"))
        standard_id = str(item.get("id") or "")
        if not standard_id or standard_id in catalog:
            raise ValueError(f"无效或重复的标准包 ID：{standard_id or manifest_path}")
        catalog[standard_id] = item
    return catalog


def list_standards() -> list[dict[str, Any]]:
    return list(load_standard_catalog().values())


def default_standard() -> dict[str, Any]:
    catalog = load_standard_catalog()
    return next((item for item in catalog.values() if item.get("default")), next(iter(catalog.values())))
