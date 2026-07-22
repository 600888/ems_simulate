"""Declarative CDC templates and common data-attribute inference."""

from __future__ import annotations

from copy import deepcopy
import json
import re
from typing import Any

from src.modeling.profiles import PROFILE_ROOT

MEASUREMENT_CDCS = {"CMV", "DEL", "HMV", "MV", "SAV", "SEQ", "WYE"}
PRIMARY_ATTRIBUTE_NAMES = ("stVal", "mag", "instMag", "actVal", "mxVal", "setVal")


def load_cdc_template_catalog() -> dict[str, dict[str, Any]]:
    catalog: dict[str, dict[str, Any]] = {}
    for template_path in sorted(PROFILE_ROOT.glob("*/cdc_templates.json")):
        payload = json.loads(template_path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError(f"CDC template file must contain a list: {template_path}")
        for item in payload:
            template_id = str(item.get("id") or "")
            if not template_id or template_id in catalog:
                raise ValueError(f"Invalid or duplicate CDC template ID: {template_id or template_path}")
            catalog[template_id] = item
    return catalog


def list_cdc_templates() -> list[dict[str, Any]]:
    return [deepcopy(item) for item in load_cdc_template_catalog().values()]


def materialize_cdc_template(
    template_id: str,
    *,
    do_type_name: str,
    cdc: str,
    existing_attributes: list[dict[str, Any]],
) -> dict[str, Any]:
    catalog = load_cdc_template_catalog()
    if template_id not in catalog:
        raise KeyError(template_id)
    template = deepcopy(catalog[template_id])
    template_cdc = str(template.get("cdc") or "").upper()
    current_cdc = cdc.upper()
    if template_cdc and current_cdc and template_cdc != current_cdc:
        raise ValueError(f"Template {template_id} is for CDC {template_cdc}, not {current_cdc}")

    primary_fc = _infer_primary_fc(existing_attributes, current_cdc or template_cdc)
    analogue_type = f"{_safe_identifier(do_type_name)}_AnalogueValue"
    replacements = {"$PRIMARY_FC": primary_fc, "$ANALOGUE_VALUE_TYPE": analogue_type}

    def replace(value: Any) -> Any:
        return replacements.get(value, value) if isinstance(value, str) else value

    for attribute in template.get("attributes", []):
        for key, value in list(attribute.items()):
            attribute[key] = replace(value)
    for dependency in template.get("dependencies", []):
        dependency["id"] = replace(dependency.get("id"))
        for child in dependency.get("children", []):
            for key, value in list(child.items()):
                child[key] = replace(value)
    template["resolved_cdc"] = template_cdc or current_cdc
    template["primary_fc"] = primary_fc
    return template


def _infer_primary_fc(attributes: list[dict[str, Any]], cdc: str) -> str:
    by_name = {str(item.get("name") or ""): item for item in attributes}
    for name in PRIMARY_ATTRIBUTE_NAMES:
        fc = str(by_name.get(name, {}).get("fc") or "").upper()
        if fc and fc != "DC":
            return fc
    for item in attributes:
        fc = str(item.get("fc") or "").upper()
        if fc in {"ST", "MX"}:
            return fc
    return "MX" if cdc.upper() in MEASUREMENT_CDCS else "ST"


def _safe_identifier(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_\-]", "_", value)
    return normalized or "DOType"
