"""Resolve DataSet/GOOSE member metadata from the owning DataModel object."""

from collections.abc import Iterable, Mapping
from typing import Any

from .catalog import normalize_dataset_ref, normalize_point_ref


def build_description_index(points: Iterable[Mapping[str, Any]]) -> dict[str, str]:
    """Index dU values and the point names populated by model discovery/import.

    dU is normally virtual: its value is stored as the name of the DO's
    registered value points. Explicit dU rows take precedence when present.
    """
    descriptions: dict[str, str] = {}
    explicit: dict[str, str] = {}
    for point in points:
        address = normalize_point_ref(str(point.get("reg_addr") or point.get("address") or ""))
        if "/" not in address or "." not in address:
            continue
        name = str(point.get("name") or "").strip()
        if address.rsplit(".", 1)[-1] in {"dU", "du", "d"}:
            value = point.get("value")
            description = str(value if value is not None else name).strip()
            if description and description not in {address, str(point.get("code") or ""), "dU", "du", "d"}:
                explicit[address.rsplit(".", 1)[0]] = description
            continue
        ln_path = address.split("/", 1)[1].split(".")
        if len(ln_path) < 3:
            continue
        # Match the same DO/name convention used by the DataModels table.
        if not name or name in {address, str(point.get("code") or ""), ln_path[1], ".".join(ln_path)}:
            continue
        do_ref = ".".join(address.split(".")[:2])
        descriptions.setdefault(do_ref, name)
    descriptions.update(explicit)
    return descriptions


def description_for_ref(reference: str, descriptions: Mapping[str, str]) -> str:
    """Use exact DO ancestors, retaining LD/LN scope and nested SDO overrides."""
    reference = normalize_point_ref(reference)
    while "." in reference:
        if reference in descriptions:
            return descriptions[reference]
        reference = reference.rsplit(".", 1)[0]
    return ""


def enrich_member_metadata(
    data: Any,
    descriptions: Mapping[str, str],
    fcs: Mapping[str, str],
    datasets: Mapping[str, list[tuple[str, str]]],
    dataset_ref: str = "",
    ordinal: int | None = None,
) -> Any:
    """Copy snapshots and decorate rows, preserving explicit member FCs and order."""
    if isinstance(data, list):
        return [
            enrich_member_metadata(item, descriptions, fcs, datasets, dataset_ref, i) for i, item in enumerate(data)
        ]
    if not isinstance(data, dict):
        return data
    dataset_ref = normalize_dataset_ref(data.get("data_set_ref") or dataset_ref)
    result = {
        key: enrich_member_metadata(value, descriptions, fcs, datasets, dataset_ref) for key, value in data.items()
    }
    reference = data.get("ref") or data.get("fcda_ref") or data.get("name")
    if isinstance(reference, str):
        description = description_for_ref(reference, descriptions)
        if description:
            result["description"] = description
        if not data.get("fc"):
            normalized = normalize_point_ref(reference)
            members = datasets.get(dataset_ref, [])
            fc = ""
            if ordinal is not None and ordinal < len(members) and members[ordinal][0] == normalized:
                fc = members[ordinal][1]
            fc = fc or fcs.get(normalized, "")
            if fc:
                result["fc"] = fc
    return result
