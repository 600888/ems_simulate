"""Compile traceable IEC 61850 publish artifacts from one immutable model snapshot."""

from __future__ import annotations

from collections import defaultdict
import csv
from dataclasses import dataclass
from hashlib import sha256
import io
import json
from typing import Any
import zipfile

FILE_VARIANTS: dict[str, dict[str, Any]] = {
    "ICD": {
        "status": "SUPPORTED",
        "publishable": True,
        "description": "IED capability description; exactly one IED is required.",
    },
    "CID": {
        "status": "SUPPORTED",
        "publishable": True,
        "description": "Configured IED delivery; exactly one IED and matching communication binding are required.",
    },
    "SCD": {
        "status": "PREVIEW_ONLY",
        "publishable": False,
        "description": (
            "System configuration preview is readable/writable, but system-level engineering publish is deferred."
        ),
    },
    "IID": {
        "status": "NOT_SUPPORTED",
        "publishable": False,
        "description": "Incremental IED exchange semantics are reserved for a later standard package.",
    },
    "SED": {
        "status": "NOT_SUPPORTED",
        "publishable": False,
        "description": "System exchange boundary semantics are reserved for a later standard package.",
    },
}


def list_file_variants() -> list[dict[str, Any]]:
    return [{"file_type": key, **value} for key, value in FILE_VARIANTS.items()]


def validate_file_variant(nodes: list[Any], file_type: str, *, for_publish: bool) -> list[dict[str, str]]:
    target = file_type.upper()
    policy = FILE_VARIANTS.get(target)
    if policy is None:
        return [{"code": "FILE_VARIANT_UNKNOWN", "message": f"Unknown SCL file variant: {target}"}]
    if policy["status"] == "NOT_SUPPORTED":
        return [{"code": "FILE_VARIANT_NOT_SUPPORTED", "message": policy["description"]}]
    if for_publish and not policy["publishable"]:
        return [{"code": "FILE_VARIANT_PREVIEW_ONLY", "message": policy["description"]}]

    ieds = [node for node in nodes if node.kind == "IED"]
    issues: list[dict[str, str]] = []
    if target in {"ICD", "CID"} and len(ieds) != 1:
        issues.append(
            {
                "code": "FILE_VARIANT_SINGLE_IED_REQUIRED",
                "message": f"{target} requires exactly one IED; found {len(ieds)}.",
            }
        )
    if target == "CID" and len(ieds) == 1:
        ied_name = ieds[0].name
        connected = [node for node in nodes if node.kind == "CONNECTED_AP" and _attrs(node).get("iedName") == ied_name]
        if not connected:
            issues.append(
                {
                    "code": "CID_COMMUNICATION_BINDING_REQUIRED",
                    "message": f"CID requires a ConnectedAP binding for IED {ied_name}.",
                }
            )
    return issues


@dataclass(frozen=True, slots=True)
class CompiledArtifact:
    kind: str
    filename: str
    media_type: str
    content: bytes

    @property
    def digest(self) -> str:
        return sha256(self.content).hexdigest()

    def metadata(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "filename": self.filename,
            "media_type": self.media_type,
            "size": len(self.content),
            "sha256": self.digest,
        }


@dataclass(frozen=True, slots=True)
class ArtifactBundle:
    artifacts: tuple[CompiledArtifact, ...]
    manifest: dict[str, Any]
    content: bytes
    filename: str


class PointMappingExporter:
    """Produce the stable point-mapping CSV contract without mutating the model."""

    fieldnames = ("ied", "ldInst", "lnClass", "lnInst", "doName", "daName", "fc", "prefix", "desc")

    def rows(self, nodes: list[Any]) -> list[dict[str, str]]:
        children = _children(nodes)
        lnode_types = _index_types(nodes, "LNODE_TYPE")
        do_types = _index_types(nodes, "DO_TYPE")
        da_types = _index_types(nodes, "DA_TYPE")
        by_id = {node.id: node for node in nodes}
        result: list[dict[str, str]] = []

        for ln in sorted((node for node in nodes if node.kind in {"LN0", "LN"}), key=_node_key):
            ln_attrs = _attrs(ln)
            lnode_type = lnode_types.get(str(ln_attrs.get("lnType") or ""))
            if lnode_type is None:
                continue
            ied = _ancestor(ln, by_id, "IED")
            logical_device = _ancestor(ln, by_id, "LDEVICE")
            if ied is None or logical_device is None:
                continue
            for do_def in _kind_children(children, lnode_type.id, {"DO_DEF"}):
                do_attrs = _attrs(do_def)
                do_type = do_types.get(str(do_attrs.get("type") or ""))
                if do_type is None:
                    continue
                self._append_do_points(
                    result,
                    children,
                    do_types,
                    da_types,
                    do_type,
                    base={
                        "ied": ied.name,
                        "ldInst": str(_attrs(logical_device).get("inst") or logical_device.name),
                        "lnClass": str(ln_attrs.get("lnClass") or ("LLN0" if ln.kind == "LN0" else "")),
                        "lnInst": str(ln_attrs.get("inst") or ""),
                        "doName": do_def.name,
                        "prefix": str(ln_attrs.get("prefix") or ""),
                    },
                    inherited_desc=str(do_attrs.get("desc") or ""),
                )
        return sorted(result, key=lambda row: tuple(row[field] for field in self.fieldnames))

    def _append_do_points(
        self,
        result: list[dict[str, str]],
        children: dict[str | None, list[Any]],
        do_types: dict[str, Any],
        da_types: dict[str, Any],
        do_type: Any,
        *,
        base: dict[str, str],
        inherited_desc: str,
    ) -> None:
        for child in _kind_children(children, do_type.id, {"DA_DEF", "SDO_DEF"}):
            attrs = _attrs(child)
            if child.kind == "SDO_DEF":
                nested = do_types.get(str(attrs.get("type") or ""))
                if nested:
                    nested_base = dict(base)
                    nested_base["doName"] = f"{base['doName']}.{child.name}"
                    self._append_do_points(
                        result,
                        children,
                        do_types,
                        da_types,
                        nested,
                        base=nested_base,
                        inherited_desc=str(attrs.get("desc") or inherited_desc),
                    )
                continue
            self._append_da_points(
                result,
                children,
                da_types,
                child,
                base=base,
                path=child.name,
                inherited_fc=str(attrs.get("fc") or ""),
                inherited_desc=str(attrs.get("desc") or inherited_desc),
            )

    def _append_da_points(
        self,
        result: list[dict[str, str]],
        children: dict[str | None, list[Any]],
        da_types: dict[str, Any],
        da: Any,
        *,
        base: dict[str, str],
        path: str,
        inherited_fc: str,
        inherited_desc: str,
    ) -> None:
        attrs = _attrs(da)
        fc = str(attrs.get("fc") or inherited_fc)
        desc = str(attrs.get("desc") or inherited_desc)
        if attrs.get("bType") == "Struct":
            da_type = da_types.get(str(attrs.get("type") or ""))
            if da_type:
                for bda in _kind_children(children, da_type.id, {"BDA_DEF"}):
                    self._append_da_points(
                        result,
                        children,
                        da_types,
                        bda,
                        base=base,
                        path=f"{path}.{bda.name}",
                        inherited_fc=fc,
                        inherited_desc=desc,
                    )
                return
        result.append({**base, "daName": path, "fc": fc, "desc": desc})

    def export(self, nodes: list[Any]) -> bytes:
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=self.fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(self.rows(nodes))
        return stream.getvalue().encode("utf-8-sig")


class RuntimeConfigCompiler:
    """Compile a deterministic, read-only runtime projection from point rows."""

    contract_version = "ems-runtime-cfg/1"

    def compile(self, rows: list[dict[str, str]]) -> bytes:
        lines = [f"# contract={self.contract_version}"]
        grouped: dict[str, dict[str, dict[str, dict[str, list[dict[str, str]]]]]] = defaultdict(
            lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        )
        for row in rows:
            ln_name = f"{row['prefix']}{row['lnClass']}{row['lnInst']}"
            grouped[row["ied"]][row["ldInst"]][ln_name][row["doName"]].append(row)
        for ied, logical_devices in sorted(grouped.items()):
            lines.append(f"MODEL({_cfg_value(ied)}){{")
            for ld_inst, logical_nodes in sorted(logical_devices.items()):
                lines.append(f"LD({_cfg_value(ld_inst)}){{")
                for ln_name, data_objects in sorted(logical_nodes.items()):
                    lines.append(f"LN({_cfg_value(ln_name)}){{")
                    for do_name, points in sorted(data_objects.items()):
                        lines.append(f"DO({_cfg_value(do_name)}){{")
                        for point in sorted(points, key=lambda item: item["daName"]):
                            value = f"DA({_cfg_value(point['daName'])} {_cfg_value(point['fc'])})"
                            if point["desc"]:
                                value += f'="{_cfg_string(point["desc"])}"'
                            lines.append(f"{value};")
                        lines.append("}")
                    lines.append("}")
                lines.append("}")
            lines.append("}")
        return ("\n".join(lines) + "\n").encode("utf-8")


def build_artifact_bundle(project: Any, nodes: list[Any], scl_xml: str, scl_filename: str) -> ArtifactBundle:
    point_exporter = PointMappingExporter()
    point_rows = point_exporter.rows(nodes)
    artifacts = (
        CompiledArtifact("SCL", scl_filename, "application/xml", scl_xml.encode("utf-8")),
        CompiledArtifact("CFG", f"{project.code}.cfg", "text/plain", RuntimeConfigCompiler().compile(point_rows)),
        CompiledArtifact("CSV", f"{project.code}.csv", "text/csv", point_exporter.export(nodes)),
    )
    snapshot_digest = _snapshot_digest(project, nodes)
    manifest = {
        "format": "ems-iec61850-artifact-manifest/1",
        "project": {
            "id": project.id,
            "code": project.code,
            "revision": project.revision,
            "file_type": scl_filename.rsplit(".", 1)[-1].upper(),
            "standard_version": project.standard_version,
        },
        "source_snapshot_sha256": snapshot_digest,
        "contracts": {"cfg": RuntimeConfigCompiler.contract_version, "csv": "ems-point-mapping/1"},
        "artifacts": [artifact.metadata() for artifact in artifacts],
    }
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for artifact in sorted(artifacts, key=lambda item: item.filename):
            _write_zip_entry(archive, artifact.filename, artifact.content)
        _write_zip_entry(archive, "manifest.json", manifest_bytes)
    return ArtifactBundle(artifacts, manifest, buffer.getvalue(), f"{project.code}-r{project.revision}-artifacts.zip")


def _write_zip_entry(archive: zipfile.ZipFile, filename: str, content: bytes) -> None:
    info = zipfile.ZipInfo(filename, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    archive.writestr(info, content)


def _snapshot_digest(project: Any, nodes: list[Any]) -> str:
    payload = {
        "project": {
            "id": project.id,
            "code": project.code,
            "revision": project.revision,
            "file_type": project.file_type,
            "standard_version": project.standard_version,
        },
        "nodes": [
            {
                "id": node.id,
                "parent_id": node.parent_id,
                "kind": node.kind,
                "name": node.name,
                "sort_order": node.sort_order,
                "attributes": _attrs(node),
                "revision": node.revision,
            }
            for node in sorted(nodes, key=lambda item: item.id)
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


def _attrs(node: Any) -> dict[str, Any]:
    value = getattr(node, "attributes_json", "")
    try:
        result = json.loads(value) if value else {}
    except (TypeError, json.JSONDecodeError):
        return {}
    return result if isinstance(result, dict) else {}


def _children(nodes: list[Any]) -> dict[str | None, list[Any]]:
    result: dict[str | None, list[Any]] = defaultdict(list)
    for node in nodes:
        result[node.parent_id].append(node)
    for values in result.values():
        values.sort(key=_node_key)
    return result


def _node_key(node: Any) -> tuple[int, str, str]:
    return (node.sort_order, node.name, node.id)


def _kind_children(children: dict[str | None, list[Any]], parent_id: str, kinds: set[str]) -> list[Any]:
    return [node for node in children.get(parent_id, []) if node.kind in kinds]


def _index_types(nodes: list[Any], kind: str) -> dict[str, Any]:
    return {str(_attrs(node).get("id") or node.name): node for node in nodes if node.kind == kind}


def _ancestor(node: Any, by_id: dict[str, Any], kind: str) -> Any | None:
    current = node
    while current.parent_id:
        current = by_id.get(current.parent_id)
        if current is None:
            return None
        if current.kind == kind:
            return current
    return None


def _cfg_value(value: str) -> str:
    return str(value).replace("(", "_").replace(")", "_").replace("{", "_").replace("}", "_").replace(" ", "_")


def _cfg_string(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\r", " ").replace("\n", " ")
