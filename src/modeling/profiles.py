"""版本化 IEC 61850 建模配置档目录。"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

PROFILE_ROOT = Path(__file__).with_name("profile_packages")


def load_profile_catalog() -> dict[str, dict[str, Any]]:
    """从声明式 manifest 加载配置档；增加配置档不需要修改核心代码。"""
    catalog: dict[str, dict[str, Any]] = {}
    for manifest_path in sorted(PROFILE_ROOT.glob("*/manifest.json")):
        item = json.loads(manifest_path.read_text(encoding="utf-8"))
        profile_id = str(item.get("id") or "")
        if not profile_id or profile_id in catalog:
            raise ValueError(f"无效或重复的配置档 ID：{profile_id or manifest_path}")
        catalog[profile_id] = item
    return catalog


def list_profiles() -> list[dict[str, Any]]:
    """返回稳定排序的不可变配置档元数据副本。"""
    catalog = load_profile_catalog()
    return [deepcopy(catalog[key]) for key in catalog]


def resolve_profiles(requested: list[str] | None) -> list[str]:
    """解析依赖并保持确定性顺序。"""
    catalog = load_profile_catalog()
    selected = requested or [key for key, item in catalog.items() if item.get("default")]
    unknown = sorted(set(selected) - catalog.keys())
    if unknown:
        raise KeyError(", ".join(unknown))

    resolved: list[str] = []

    def add(profile_id: str) -> None:
        for dependency in catalog[profile_id]["dependencies"]:
            add(dependency)
        if profile_id not in resolved:
            resolved.append(profile_id)

    for profile_id in selected:
        add(profile_id)
    return resolved


def profile_lock(profile_ids: list[str]) -> list[dict[str, str]]:
    catalog = load_profile_catalog()
    return [{"id": profile_id, "version": str(catalog[profile_id]["version"])} for profile_id in profile_ids]


def service_capabilities(profile_ids: list[str]) -> list[tuple[str, dict[str, Any]]]:
    catalog = load_profile_catalog()
    result: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    for profile_id in profile_ids:
        for item in catalog[profile_id].get("service_capabilities", []):
            tag = str(item["tag"])
            if tag not in seen:
                result.append((tag, dict(item.get("attributes") or {})))
                seen.add(tag)
    return result


def logical_node_templates(profile_ids: list[str]) -> list[dict[str, Any]]:
    catalog = load_profile_catalog()
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for profile_id in profile_ids:
        for item in catalog[profile_id].get("ln_templates", []):
            template = dict(item)
            key = (
                str(template.get("prefix") or ""),
                str(template["lnClass"]),
                str(template.get("inst") or "1"),
            )
            if key not in seen:
                result.append(template)
                seen.add(key)
    return result
