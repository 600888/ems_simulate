"""Shared cached DataModel metadata for DataSet and GOOSE views."""

from typing import Any

from src.device.protocol.iec61850_handler import get_iec61850_value_model
from src.proto.iec61850.plugins.datasets.catalog import normalize_dataset_ref, normalize_point_ref
from src.proto.iec61850.plugins.datasets.metadata import build_description_index, enrich_member_metadata


def enrich_iec61850_metadata(device: Any, data: Any) -> Any:
    """Resolve dU and FC from this device only; never read through MMS."""
    if device is None:
        return data
    handler = getattr(device, "protocol_handler", None)
    model = get_iec61850_value_model(handler)
    points = []
    if model is not None:
        points.extend({**info, "address": address} for address, info in model.point_refs.items())
        for _, _, do in model.iter_dos():
            for da in do.das:
                for attribute in (da, *da.iter_leaves()):
                    points.append({"address": f"{do.ref}.{attribute.path}", "fc": attribute.fc or da.fc})
    point_manager = getattr(device, "point_manager", None)
    live_points = []
    if point_manager is not None:
        live_points = [
            {
                "address": str(point.address),
                "name": str(point.name),
                "code": str(point.code),
                "fc": getattr(point, "fc", ""),
            }
            for point in point_manager.get_all_points()
        ]
        points.extend(live_points)
    descriptions = build_description_index(points)
    descriptions.update(build_description_index(live_points))
    server = getattr(handler, "_server", None)
    stored = getattr(server, "_du_descriptions", None)
    if isinstance(stored, dict):
        descriptions.update({normalize_point_ref(ref): value for ref, value in stored.items() if value})
    client = getattr(handler, "_client", None)
    registry = getattr(client, "_registry", None)
    refs = getattr(registry, "point_refs", None)
    if isinstance(refs, dict):
        # Add only the aliases explicitly recorded by this device's registry.
        registry_points = [
            {"address": ref, "name": registry.get_name(address), "code": address, "fc": registry.get_fc(address)}
            for address, ref in refs.items()
        ]
        points.extend(registry_points)
        for ref, description in build_description_index(registry_points).items():
            descriptions.setdefault(ref, description)

    candidates: dict[str, set[str]] = {}

    def add_fc(reference: str, fc: str) -> None:
        if reference and fc:
            candidates.setdefault(normalize_point_ref(reference), set()).add(fc)

    for point in points:
        add_fc(point["address"], point.get("fc") or "")
    get_datasets = getattr(handler, "get_discovered_datasets", None)
    datasets = get_datasets() if callable(get_datasets) else []
    dataset_members = {}
    for dataset in datasets if isinstance(datasets, (list, tuple)) else []:
        members = []
        for member in dataset.get("members", []):
            reference = member.get("ref") or member.get("fcda_ref") or member.get("name", "")
            fc = member.get("fc") or ""
            members.append((normalize_point_ref(reference), fc))
            add_fc(reference, fc)
        dataset_members[normalize_dataset_ref(dataset.get("ref", ""))] = members
    # A DO can occur in multiple FCs. Only use a global fallback when unique;
    # otherwise the member's DataSet and ordinal determine its actual FC.
    fcs = {ref: next(iter(values)) for ref, values in candidates.items() if len(values) == 1}
    return enrich_member_metadata(data, descriptions, fcs, dataset_members)
