"""IEC 61850 可编辑模型的应用服务。"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import datetime
import json
import re
from typing import Any
import uuid

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from src.data.controller.db import local_session
from src.data.model.iec61850_modeling import (
    Iec61850ModelNode,
    Iec61850ModelProject,
    Iec61850ModelReference,
    Iec61850ModelVersion,
)
from src.modeling.artifacts import build_artifact_bundle, list_file_variants, validate_file_variant
from src.modeling.catalog import (
    CHILD_RULES,
    KIND_LABELS,
    PROTECTED_KINDS,
    SINGLETON_CHILD_KINDS,
    get_kind_schema,
)
from src.modeling.cdc_templates import list_cdc_templates, materialize_cdc_template
from src.modeling.profiles import (
    list_profiles,
    logical_node_templates,
    profile_lock,
    resolve_profiles,
    service_capabilities,
)
from src.modeling.scl_importer import SclModelImporter
from src.modeling.standards import list_standards
import src.proto.iec61850.plugins.scl.validator.builtin_rules  # noqa: F401
from src.web.api.exceptions import ConflictError, NotFoundError, ValidationError

SessionFactory = Callable[[], Session]
NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_\-]{0,63}$")
LN_CLASS_PATTERN = re.compile(r"^[A-Z][A-Z0-9]{3}$")


def _json_loads(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def _json_dumps(value: dict[str, Any] | None) -> str:
    return json.dumps(value or {}, ensure_ascii=False, separators=(",", ":"))


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


class Iec61850ModelingService:
    """管理模型工程、节点树、影响分析和基础规则校验。"""

    def __init__(self, session_factory: SessionFactory = local_session):
        self.session_factory = session_factory

    @staticmethod
    def _require_project(session: Session, project_id: str) -> Iec61850ModelProject:
        project = session.get(Iec61850ModelProject, project_id)
        if not project:
            raise NotFoundError("模型工程不存在或已被删除")
        return project

    @staticmethod
    def _require_node(session: Session, project_id: str, node_id: str) -> Iec61850ModelNode:
        node = session.scalar(
            select(Iec61850ModelNode).where(
                Iec61850ModelNode.id == node_id,
                Iec61850ModelNode.project_id == project_id,
            )
        )
        if not node:
            raise NotFoundError("模型节点不存在或已被删除")
        return node

    @staticmethod
    def _project_dict(project: Iec61850ModelProject, node_count: int | None = None) -> dict[str, Any]:
        result = {
            "id": project.id,
            "name": project.name,
            "code": project.code,
            "description": project.description,
            "file_type": project.file_type,
            "standard_version": project.standard_version,
            "namespace": project.namespace,
            "modeling_mode": project.modeling_mode,
            "status": project.status,
            "revision": project.revision,
            "validation_errors": project.validation_errors,
            "validation_warnings": project.validation_warnings,
            "created_at": _iso(project.created_at),
            "updated_at": _iso(project.updated_at),
        }
        if node_count is not None:
            result["node_count"] = node_count
        return result

    @staticmethod
    def _node_dict(node: Iec61850ModelNode, *, child_count: int = 0) -> dict[str, Any]:
        return {
            "id": node.id,
            "project_id": node.project_id,
            "parent_id": node.parent_id,
            "kind": node.kind,
            "kind_label": KIND_LABELS.get(node.kind, node.kind),
            "name": node.name,
            "label": node.name,
            "sort_order": node.sort_order,
            "attributes": _json_loads(node.attributes_json),
            "revision": node.revision,
            "child_count": child_count,
            "protected": node.kind in PROTECTED_KINDS,
            "created_at": _iso(node.created_at),
            "updated_at": _iso(node.updated_at),
        }

    def list_projects(
        self,
        *,
        keyword: str = "",
        status: str = "",
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        with self.session_factory() as session:
            filters = []
            if keyword.strip():
                value = f"%{keyword.strip()}%"
                filters.append(or_(Iec61850ModelProject.name.like(value), Iec61850ModelProject.code.like(value)))
            if status.strip():
                filters.append(Iec61850ModelProject.status == status.upper())

            total = session.scalar(select(func.count(Iec61850ModelProject.id)).where(*filters)) or 0
            projects = session.scalars(
                select(Iec61850ModelProject)
                .where(*filters)
                .order_by(Iec61850ModelProject.updated_at.desc(), Iec61850ModelProject.name)
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
            counts = (
                dict(
                    session.execute(
                        select(Iec61850ModelNode.project_id, func.count(Iec61850ModelNode.id))
                        .where(Iec61850ModelNode.project_id.in_([p.id for p in projects]))
                        .group_by(Iec61850ModelNode.project_id)
                    ).all()
                )
                if projects
                else {}
            )
            return {
                "items": [self._project_dict(project, counts.get(project.id, 0)) for project in projects],
                "total": total,
                "page": page,
                "page_size": page_size,
            }

    def create_project(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name", "")).strip()
        code = str(payload.get("code", "")).strip()
        ied = payload.get("ied") or {}
        ied_name = str(ied.get("name", "")).strip()
        if not name:
            raise ValidationError("工程名称不能为空")
        if not NAME_PATTERN.fullmatch(code):
            raise ValidationError("工程编码需以字母开头，只能包含字母、数字、下划线和短横线")
        if not NAME_PATTERN.fullmatch(ied_name):
            raise ValidationError("IED 名称需以字母开头，只能包含字母、数字、下划线和短横线")

        logical_devices = payload.get("logical_devices") or [{"inst": "LD0", "desc": "默认逻辑设备"}]
        if not logical_devices:
            raise ValidationError("至少需要创建一个逻辑设备")
        logical_device_names = [str(item.get("inst", "")).strip() for item in logical_devices]
        if len(logical_device_names) != len(set(logical_device_names)):
            raise ConflictError("逻辑设备实例标识不能重复")

        try:
            profile_ids = resolve_profiles(payload.get("profiles"))
        except KeyError as exc:
            raise ValidationError(f"未知建模配置档：{exc}") from exc

        project_id = str(uuid.uuid4())
        with self.session_factory() as session, session.begin():
            if session.scalar(select(Iec61850ModelProject.id).where(Iec61850ModelProject.code == code)):
                raise ConflictError(f"工程编码 {code} 已存在")
            project = Iec61850ModelProject(
                id=project_id,
                name=name,
                code=code,
                description=str(payload.get("description", "")).strip(),
                file_type=str(payload.get("file_type", "ICD")).upper(),
                standard_version=str(payload.get("standard_version", "IEC 61850 Ed2.1")),
                namespace=str(payload.get("namespace", "")),
                modeling_mode="FROM_SCRATCH",
            )
            session.add(project)

            def add_node(
                kind: str,
                node_name: str,
                parent_id: str | None,
                attributes: dict[str, Any] | None = None,
                sort_order: int = 0,
            ) -> Iec61850ModelNode:
                node = Iec61850ModelNode(
                    id=str(uuid.uuid4()),
                    project_id=project_id,
                    parent_id=parent_id,
                    kind=kind,
                    name=node_name,
                    attributes_json=_json_dumps(attributes),
                    sort_order=sort_order,
                )
                session.add(node)
                return node

            root = add_node(
                "ROOT",
                name,
                None,
                {
                    "code": code,
                    "emitEdition": True,
                    "schemaLocation": "http://www.iec.ch/61850/2003/SCL SCL.xsd",
                    "profiles": profile_lock(profile_ids),
                },
            )
            add_node(
                "HEADER",
                "Header",
                root.id,
                {
                    "id": code,
                    "version": "1",
                    "revision": "1",
                    "nameStructure": "IEDName",
                    "toolID": "EMS Simulator IEC61850 Modeler",
                },
                0,
            )
            communication = add_node("COMMUNICATION", "Communication", root.id, {}, 5)
            subnet = add_node(
                "SUBNETWORK",
                "StationBus",
                communication.id,
                {"type": "8-MMS", "bitRate": 100, "multiplier": "M"},
                0,
            )
            ied_node = add_node(
                "IED",
                ied_name,
                root.id,
                {
                    "manufacturer": ied.get("manufacturer", ""),
                    "type": ied.get("type", ""),
                    "configVersion": ied.get("configVersion", "1.0"),
                    "desc": ied.get("desc", ""),
                },
                10,
            )
            services = add_node("SERVICES", "Services", ied_node.id, {}, 0)
            for index, (tag, capability_attrs) in enumerate(service_capabilities(profile_ids)):
                add_node(
                    "SERVICE_CAPABILITY",
                    tag,
                    services.id,
                    {"tag": tag, **capability_attrs},
                    index,
                )
            ap_name = str(payload.get("access_point_name", "AP1")).strip() or "AP1"
            access_point = add_node("ACCESS_POINT", ap_name, ied_node.id, {}, 10)
            server = add_node("SERVER", "Server", access_point.id, {}, 0)
            connected_ap = add_node(
                "CONNECTED_AP",
                f"{ied_name}_{ap_name}",
                subnet.id,
                {"iedName": ied_name, "apName": ap_name},
                0,
            )
            address = add_node("ADDRESS", "Address", connected_ap.id, {}, 0)
            for index, (parameter_type, value) in enumerate(
                (
                    ("IP", "192.168.1.10"),
                    ("IP-SUBNET", "255.255.255.0"),
                    ("IP-GATEWAY", "192.168.1.1"),
                    ("OSI-TSEL", "0001"),
                    ("OSI-SSEL", "0001"),
                    ("OSI-PSEL", "00000001"),
                )
            ):
                add_node("P", parameter_type, address.id, {"type": parameter_type, "value": value}, index)
            ln0_type_id = f"{code}_LLN0"
            ln_templates = logical_node_templates(profile_ids)
            for index, logical_device in enumerate(logical_devices):
                inst = str(logical_device.get("inst", "")).strip()
                if not NAME_PATTERN.fullmatch(inst):
                    raise ValidationError(f"逻辑设备实例 {inst or '(空)'} 格式不正确")
                ld = add_node(
                    "LDEVICE",
                    inst,
                    server.id,
                    {"inst": inst, "desc": logical_device.get("desc", "")},
                    index,
                )
                add_node(
                    "LN0",
                    "LLN0",
                    ld.id,
                    {"lnClass": "LLN0", "inst": "", "lnType": ln0_type_id},
                    0,
                )
                for template_index, template in enumerate(ln_templates, start=1):
                    ln_class = str(template["lnClass"])
                    ln_inst = str(template.get("inst") or "1")
                    prefix = str(template.get("prefix") or "")
                    add_node(
                        "LN",
                        f"{prefix}{ln_class}{ln_inst}",
                        ld.id,
                        {
                            "prefix": prefix,
                            "lnClass": ln_class,
                            "inst": ln_inst,
                            "lnType": f"{code}_{prefix}{ln_class}",
                            "desc": str(template.get("desc") or ""),
                        },
                        template_index,
                    )

            templates = add_node("DATA_TYPE_TEMPLATES", "DataTypeTemplates", root.id, {}, 20)
            add_node(
                "LNODE_TYPE",
                ln0_type_id,
                templates.id,
                {"id": ln0_type_id, "lnClass": "LLN0", "desc": "自动生成的 LLN0 基础类型"},
                0,
            )
            for index, template in enumerate(ln_templates, start=1):
                prefix = str(template.get("prefix") or "")
                ln_class = str(template["lnClass"])
                type_id = f"{code}_{prefix}{ln_class}"
                add_node(
                    "LNODE_TYPE",
                    type_id,
                    templates.id,
                    {"id": type_id, "lnClass": ln_class, "desc": str(template.get("desc") or "")},
                    index,
                )
            session.flush()
            node_count = (
                session.scalar(
                    select(func.count(Iec61850ModelNode.id)).where(Iec61850ModelNode.project_id == project_id)
                )
                or 0
            )

        return {"project": self._project_dict(project, node_count), "tree": self.get_tree(project_id)}

    @staticmethod
    def list_profiles() -> list[dict[str, Any]]:
        return list_profiles()

    @staticmethod
    def list_standards() -> list[dict[str, Any]]:
        return list_standards()

    @staticmethod
    def list_file_variants() -> list[dict[str, Any]]:
        return list_file_variants()

    @staticmethod
    def list_cdc_templates() -> list[dict[str, Any]]:
        return list_cdc_templates()

    @staticmethod
    def preview_import(
        content: bytes,
        *,
        filename: str,
        progress: Callable[[str, int, int, str], None] | None = None,
        cancel_check: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        try:
            imported = SclModelImporter().parse(
                content,
                filename=filename,
                progress=progress,
                cancel_check=cancel_check,
            )
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        return {"project": imported.project, "summary": imported.summary, "warnings": imported.warnings}

    def import_scl(
        self,
        content: bytes,
        *,
        filename: str,
        code: str = "",
        name: str = "",
    ) -> dict[str, Any]:
        try:
            imported = SclModelImporter().parse(content, filename=filename)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        project_data = imported.project
        target_code = (code or project_data["code"]).strip()
        target_name = (name or project_data["name"]).strip()
        if not NAME_PATTERN.fullmatch(target_code):
            raise ValidationError("导入工程编码格式不正确")
        project_id = str(uuid.uuid4())
        with self.session_factory() as session, session.begin():
            if session.scalar(select(Iec61850ModelProject.id).where(Iec61850ModelProject.code == target_code)):
                raise ConflictError(f"工程编码 {target_code} 已存在")
            project = Iec61850ModelProject(
                id=project_id,
                name=target_name,
                code=target_code,
                description=f"从 {filename} 导入",
                file_type=project_data["file_type"],
                standard_version=project_data["standard_version"],
                namespace=project_data["namespace"],
                modeling_mode="IMPORTED",
                status="DRAFT",
            )
            session.add(project)
            for item in imported.nodes:
                session.add(
                    Iec61850ModelNode(
                        id=item["id"],
                        project_id=project_id,
                        parent_id=item["parent_id"],
                        kind=item["kind"],
                        name=item["name"],
                        sort_order=item["sort_order"],
                        attributes_json=_json_dumps(item["attributes"]),
                    )
                )
            session.flush()
            self._rebuild_references_in_session(session, project_id)

        return {
            "project": self.get_project(project_id),
            "tree": self.get_tree(project_id),
            "summary": imported.summary,
            "warnings": imported.warnings,
        }

    def get_project(self, project_id: str) -> dict[str, Any]:
        with self.session_factory() as session:
            project = self._require_project(session, project_id)
            count = (
                session.scalar(
                    select(func.count(Iec61850ModelNode.id)).where(Iec61850ModelNode.project_id == project_id)
                )
                or 0
            )
            kinds = dict(
                session.execute(
                    select(Iec61850ModelNode.kind, func.count(Iec61850ModelNode.id))
                    .where(Iec61850ModelNode.project_id == project_id)
                    .group_by(Iec61850ModelNode.kind)
                ).all()
            )
            result = self._project_dict(project, count)
            result["summary"] = {"by_kind": kinds}
            return result

    def delete_project(self, project_id: str) -> None:
        with self.session_factory() as session, session.begin():
            project = self._require_project(session, project_id)
            session.execute(delete(Iec61850ModelVersion).where(Iec61850ModelVersion.project_id == project_id))
            session.execute(delete(Iec61850ModelReference).where(Iec61850ModelReference.project_id == project_id))
            session.execute(delete(Iec61850ModelNode).where(Iec61850ModelNode.project_id == project_id))
            session.delete(project)

    def get_tree(self, project_id: str) -> list[dict[str, Any]]:
        with self.session_factory() as session:
            self._require_project(session, project_id)
            nodes = session.scalars(
                select(Iec61850ModelNode)
                .where(Iec61850ModelNode.project_id == project_id)
                .order_by(Iec61850ModelNode.sort_order, Iec61850ModelNode.name)
            ).all()
            children: dict[str | None, list[Iec61850ModelNode]] = defaultdict(list)
            for node in nodes:
                children[node.parent_id].append(node)

            def build(node: Iec61850ModelNode, parent_path: str = "") -> dict[str, Any]:
                node_children = children.get(node.id, [])
                result = self._node_dict(node, child_count=len(node_children))
                result["path"] = f"{parent_path}/{node.name}" if parent_path else node.name
                result["children"] = [build(child, result["path"]) for child in node_children]
                return result

            return [build(root) for root in children.get(None, [])]

    def get_node(self, project_id: str, node_id: str) -> dict[str, Any]:
        with self.session_factory() as session:
            node = self._require_node(session, project_id, node_id)
            child_count = (
                session.scalar(select(func.count(Iec61850ModelNode.id)).where(Iec61850ModelNode.parent_id == node.id))
                or 0
            )
            result = self._node_dict(node, child_count=child_count)
            result["schema"] = get_kind_schema(node.kind)
            result["path"] = self._node_path(session, node)
            return result

    @staticmethod
    def _node_path(session: Session, node: Iec61850ModelNode) -> str:
        names = [node.name]
        parent_id = node.parent_id
        while parent_id:
            parent = session.get(Iec61850ModelNode, parent_id)
            if not parent:
                break
            names.append(parent.name)
            parent_id = parent.parent_id
        return "/".join(reversed(names))

    def create_node(self, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        parent_id = str(payload.get("parent_id", ""))
        kind = str(payload.get("kind", "")).upper()
        name = str(payload.get("name", "")).strip()
        if not name:
            raise ValidationError("节点名称不能为空")
        with self.session_factory() as session, session.begin():
            project = self._require_project(session, project_id)
            parent = self._require_node(session, project_id, parent_id)
            if kind not in CHILD_RULES.get(parent.kind, ()):
                parent_label = KIND_LABELS.get(parent.kind, parent.kind)
                child_label = KIND_LABELS.get(kind, kind)
                raise ValidationError(f"{parent_label} 下不能添加 {child_label}")
            if session.scalar(
                select(Iec61850ModelNode.id).where(
                    Iec61850ModelNode.project_id == project_id,
                    Iec61850ModelNode.parent_id == parent_id,
                    Iec61850ModelNode.kind == kind,
                    Iec61850ModelNode.name == name,
                )
            ):
                raise ConflictError("同一父节点下已存在同类型、同名节点")
            if kind in SINGLETON_CHILD_KINDS and session.scalar(
                select(Iec61850ModelNode.id).where(
                    Iec61850ModelNode.parent_id == parent_id, Iec61850ModelNode.kind == kind
                )
            ):
                raise ConflictError(f"每个父节点只能包含一个 {KIND_LABELS.get(kind, kind)}")
            max_order = session.scalar(
                select(func.max(Iec61850ModelNode.sort_order)).where(Iec61850ModelNode.parent_id == parent_id)
            )
            requested_order = payload.get("sort_order")
            node = Iec61850ModelNode(
                id=str(uuid.uuid4()),
                project_id=project_id,
                parent_id=parent_id,
                kind=kind,
                name=name,
                attributes_json=_json_dumps(payload.get("attributes")),
                sort_order=int(requested_order if requested_order is not None else (max_order or 0) + 10),
            )
            session.add(node)
            project.revision += 1
            project.status = "DRAFT"
            session.flush()
            self._rebuild_references_in_session(session, project_id)
            result = self._node_dict(node)
            result["schema"] = get_kind_schema(kind)
            result["path"] = self._node_path(session, node)
            return result

    def update_node(self, project_id: str, node_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self.session_factory() as session, session.begin():
            project = self._require_project(session, project_id)
            node = self._require_node(session, project_id, node_id)
            expected_revision = payload.get("expected_revision")
            if expected_revision is not None and int(expected_revision) != node.revision:
                raise ConflictError("该节点已被其他操作修改，请刷新后重试", {"current_revision": node.revision})
            name = str(payload.get("name", node.name)).strip()
            if not name:
                raise ValidationError("节点名称不能为空")
            if name != node.name and session.scalar(
                select(Iec61850ModelNode.id).where(
                    Iec61850ModelNode.project_id == project_id,
                    Iec61850ModelNode.parent_id == node.parent_id,
                    Iec61850ModelNode.kind == node.kind,
                    Iec61850ModelNode.name == name,
                    Iec61850ModelNode.id != node.id,
                )
            ):
                raise ConflictError("同一父节点下已存在同类型、同名节点")
            node.name = name
            if "attributes" in payload:
                node.attributes_json = _json_dumps(payload.get("attributes"))
            if "sort_order" in payload and payload["sort_order"] is not None:
                node.sort_order = int(payload["sort_order"])
            node.revision += 1
            project.revision += 1
            project.status = "DRAFT"
            if node.kind == "ROOT":
                project.name = name
            session.flush()
            self._rebuild_references_in_session(session, project_id)
            result = self._node_dict(node)
            result["schema"] = get_kind_schema(node.kind)
            result["path"] = self._node_path(session, node)
            return result

    def apply_cdc_template(self, project_id: str, do_type_id: str, template_id: str) -> dict[str, Any]:
        """Merge a declarative CDC template into one DOType as a single project revision."""

        with self.session_factory() as session, session.begin():
            project = self._require_project(session, project_id)
            do_type = self._require_node(session, project_id, do_type_id)
            if do_type.kind != "DO_TYPE":
                raise ValidationError("CDC 模板只能应用到数据对象类型 DOType")
            do_type_attrs = _json_loads(do_type.attributes_json)
            existing = list(
                session.scalars(
                    select(Iec61850ModelNode)
                    .where(
                        Iec61850ModelNode.project_id == project_id,
                        Iec61850ModelNode.parent_id == do_type.id,
                        Iec61850ModelNode.kind == "DA_DEF",
                    )
                    .order_by(Iec61850ModelNode.sort_order, Iec61850ModelNode.name)
                ).all()
            )
            existing_payload = [{"name": node.name, **_json_loads(node.attributes_json)} for node in existing]
            try:
                template = materialize_cdc_template(
                    template_id,
                    do_type_name=str(do_type_attrs.get("id") or do_type.name),
                    cdc=str(do_type_attrs.get("cdc") or ""),
                    existing_attributes=existing_payload,
                )
            except KeyError as exc:
                raise ValidationError(f"未知 CDC 模板：{template_id}") from exc
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc

            created: list[dict[str, str]] = []
            preserved: list[str] = []
            conflicts: list[dict[str, Any]] = []
            changed = False
            resolved_cdc = str(template.get("resolved_cdc") or "")
            if resolved_cdc and not do_type_attrs.get("cdc"):
                do_type_attrs["cdc"] = resolved_cdc
                do_type.attributes_json = _json_dumps(do_type_attrs)
                do_type.revision += 1
                changed = True

            existing_by_name = {node.name: node for node in existing}
            max_order = max((node.sort_order for node in existing), default=0)
            for index, definition in enumerate(template.get("attributes", []), start=1):
                name = str(definition["name"])
                attributes = {key: value for key, value in definition.items() if key != "name"}
                current = existing_by_name.get(name)
                if current:
                    current_attrs = _json_loads(current.attributes_json)
                    mismatches = {
                        key: {"current": current_attrs.get(key), "template": attributes.get(key)}
                        for key in ("bType", "fc", "type")
                        if attributes.get(key) not in (None, "") and current_attrs.get(key) != attributes.get(key)
                    }
                    if mismatches:
                        conflicts.append({"name": name, "fields": mismatches})
                    else:
                        preserved.append(name)
                    continue
                node = Iec61850ModelNode(
                    id=str(uuid.uuid4()),
                    project_id=project_id,
                    parent_id=do_type.id,
                    kind="DA_DEF",
                    name=name,
                    sort_order=max_order + index * 10,
                    attributes_json=_json_dumps(attributes),
                )
                session.add(node)
                created.append({"kind": "DA_DEF", "name": name})
                changed = True

            for dependency in template.get("dependencies", []):
                dependency_kind = str(dependency.get("kind") or "")
                dependency_id = str(dependency.get("id") or "")
                target = next(
                    (
                        node
                        for node in session.scalars(
                            select(Iec61850ModelNode).where(
                                Iec61850ModelNode.project_id == project_id,
                                Iec61850ModelNode.parent_id == do_type.parent_id,
                                Iec61850ModelNode.kind == dependency_kind,
                            )
                        ).all()
                        if str(_json_loads(node.attributes_json).get("id") or node.name) == dependency_id
                    ),
                    None,
                )
                if target is None:
                    sibling_order = session.scalar(
                        select(func.max(Iec61850ModelNode.sort_order)).where(
                            Iec61850ModelNode.parent_id == do_type.parent_id
                        )
                    )
                    target = Iec61850ModelNode(
                        id=str(uuid.uuid4()),
                        project_id=project_id,
                        parent_id=do_type.parent_id,
                        kind=dependency_kind,
                        name=dependency_id,
                        sort_order=(sibling_order or 0) + 10,
                        attributes_json=_json_dumps({"id": dependency_id}),
                    )
                    session.add(target)
                    session.flush()
                    created.append({"kind": dependency_kind, "name": dependency_id})
                    changed = True
                dependency_children = {
                    node.name: node
                    for node in session.scalars(
                        select(Iec61850ModelNode).where(Iec61850ModelNode.parent_id == target.id)
                    ).all()
                }
                child_order = max((node.sort_order for node in dependency_children.values()), default=0)
                for child_index, child in enumerate(dependency.get("children", []), start=1):
                    child_name = str(child["name"])
                    if child_name in dependency_children:
                        preserved.append(f"{dependency_id}.{child_name}")
                        continue
                    child_kind = str(child["kind"])
                    child_attrs = {key: value for key, value in child.items() if key not in {"kind", "name"}}
                    session.add(
                        Iec61850ModelNode(
                            id=str(uuid.uuid4()),
                            project_id=project_id,
                            parent_id=target.id,
                            kind=child_kind,
                            name=child_name,
                            sort_order=child_order + child_index * 10,
                            attributes_json=_json_dumps(child_attrs),
                        )
                    )
                    created.append({"kind": child_kind, "name": f"{dependency_id}.{child_name}"})
                    changed = True

            if changed:
                project.revision += 1
                project.status = "DRAFT"
                session.flush()
                self._rebuild_references_in_session(session, project_id)
            return {
                "template_id": template_id,
                "do_type_id": do_type.id,
                "cdc": str(do_type_attrs.get("cdc") or resolved_cdc),
                "primary_fc": template["primary_fc"],
                "created": created,
                "preserved": sorted(set(preserved)),
                "conflicts": conflicts,
                "changed": changed,
                "project_revision": project.revision,
            }

    @staticmethod
    def _subtree_ids(session: Session, project_id: str, node_id: str) -> list[str]:
        rows = session.execute(
            select(Iec61850ModelNode.id, Iec61850ModelNode.parent_id).where(Iec61850ModelNode.project_id == project_id)
        ).all()
        children: dict[str | None, list[str]] = defaultdict(list)
        for item_id, parent_id in rows:
            children[parent_id].append(item_id)
        result: list[str] = []
        stack = [node_id]
        while stack:
            current = stack.pop()
            result.append(current)
            stack.extend(children.get(current, []))
        return result

    def get_delete_impact(self, project_id: str, node_id: str) -> dict[str, Any]:
        with self.session_factory() as session:
            node = self._require_node(session, project_id, node_id)
            subtree = self._subtree_ids(session, project_id, node_id)
            inbound = session.scalars(
                select(Iec61850ModelReference).where(
                    Iec61850ModelReference.project_id == project_id,
                    Iec61850ModelReference.target_node_id.in_(subtree),
                    Iec61850ModelReference.source_node_id.not_in(subtree),
                )
            ).all()
            outbound_count = (
                session.scalar(
                    select(func.count(Iec61850ModelReference.id)).where(
                        Iec61850ModelReference.project_id == project_id,
                        Iec61850ModelReference.source_node_id.in_(subtree),
                    )
                )
                or 0
            )
            protected = node.kind in PROTECTED_KINDS
            return {
                "node": self._node_dict(node),
                "subtree_count": len(subtree),
                "descendant_count": max(0, len(subtree) - 1),
                "inbound_references": [
                    {
                        "id": ref.id,
                        "source_node_id": ref.source_node_id,
                        "target_node_id": ref.target_node_id,
                        "relation_type": ref.relation_type,
                    }
                    for ref in inbound
                ],
                "outbound_reference_count": outbound_count,
                "protected": protected,
                "can_delete": not protected and not inbound,
                "blocking_reason": (
                    "IEC 61850 必需结构节点不可删除"
                    if protected
                    else ("存在外部节点引用，请先解除引用" if inbound else "")
                ),
            }

    def delete_node(self, project_id: str, node_id: str, *, force: bool = False) -> dict[str, Any]:
        with self.session_factory() as session, session.begin():
            project = self._require_project(session, project_id)
            node = self._require_node(session, project_id, node_id)
            if node.kind in PROTECTED_KINDS:
                raise ValidationError("IEC 61850 必需结构节点不可删除")
            subtree = self._subtree_ids(session, project_id, node_id)
            inbound_count = (
                session.scalar(
                    select(func.count(Iec61850ModelReference.id)).where(
                        Iec61850ModelReference.target_node_id.in_(subtree),
                        Iec61850ModelReference.source_node_id.not_in(subtree),
                    )
                )
                or 0
            )
            if inbound_count and not force:
                raise ConflictError("节点仍被其他配置引用，请先解除引用或确认强制删除")
            session.execute(
                delete(Iec61850ModelReference).where(
                    or_(
                        Iec61850ModelReference.source_node_id.in_(subtree),
                        Iec61850ModelReference.target_node_id.in_(subtree),
                    )
                )
            )
            session.execute(delete(Iec61850ModelNode).where(Iec61850ModelNode.id.in_(subtree)))
            project.revision += 1
            project.status = "DRAFT"
            return {"deleted_node_id": node_id, "deleted_count": len(subtree)}

    @staticmethod
    def _rebuild_references_in_session(session: Session, project_id: str) -> int:
        """从稳定节点 ID 重建常用 SCL 引用图。"""
        session.execute(delete(Iec61850ModelReference).where(Iec61850ModelReference.project_id == project_id))
        nodes = list(session.scalars(select(Iec61850ModelNode).where(Iec61850ModelNode.project_id == project_id)).all())
        type_indexes: dict[str, dict[str, Iec61850ModelNode]] = {
            kind: {} for kind in ("LNODE_TYPE", "DO_TYPE", "DA_TYPE", "ENUM_TYPE")
        }
        by_parent: dict[str | None, list[Iec61850ModelNode]] = defaultdict(list)
        ieds: dict[str, Iec61850ModelNode] = {}
        for node in nodes:
            by_parent[node.parent_id].append(node)
            attrs = _json_loads(node.attributes_json)
            if node.kind in type_indexes:
                type_indexes[node.kind][str(attrs.get("id") or node.name)] = node
            elif node.kind == "IED":
                ieds[node.name] = node

        references: list[Iec61850ModelReference] = []

        def add(source: Iec61850ModelNode, target: Iec61850ModelNode | None, relation: str, external: str) -> None:
            if not target:
                return
            references.append(
                Iec61850ModelReference(
                    id=str(uuid.uuid4()),
                    project_id=project_id,
                    source_node_id=source.id,
                    target_node_id=target.id,
                    relation_type=relation,
                    attributes_json=_json_dumps({"external_ref": external}),
                )
            )

        for node in nodes:
            attrs = _json_loads(node.attributes_json)
            if node.kind in ("LN0", "LN") and attrs.get("lnType"):
                ref = str(attrs["lnType"])
                add(node, type_indexes["LNODE_TYPE"].get(ref), "LN_TYPE", ref)
            elif node.kind in ("DO_DEF", "SDO_DEF") and attrs.get("type"):
                ref = str(attrs["type"])
                add(node, type_indexes["DO_TYPE"].get(ref), "DO_TYPE", ref)
            elif node.kind in ("DA_DEF", "BDA_DEF") and attrs.get("type"):
                ref = str(attrs["type"])
                target_kind = "DA_TYPE" if attrs.get("bType") == "Struct" else "ENUM_TYPE"
                add(node, type_indexes[target_kind].get(ref), target_kind, ref)
            elif node.kind in ("REPORT_CONTROL", "GSE_CONTROL") and attrs.get("datSet"):
                ref = str(attrs["datSet"])
                target = next(
                    (item for item in by_parent.get(node.parent_id, []) if item.kind == "DATASET" and item.name == ref),
                    None,
                )
                add(node, target, "CONTROL_DATASET", ref)
            elif node.kind == "CONNECTED_AP" and attrs.get("iedName"):
                ref = str(attrs["iedName"])
                add(node, ieds.get(ref), "CONNECTED_AP_IED", ref)

        session.add_all(references)
        return len(references)

    def rebuild_references(self, project_id: str) -> dict[str, int]:
        with self.session_factory() as session, session.begin():
            self._require_project(session, project_id)
            return {"reference_count": self._rebuild_references_in_session(session, project_id)}

    def validate_project(self, project_id: str) -> dict[str, Any]:
        with self.session_factory() as session, session.begin():
            project = self._require_project(session, project_id)
            nodes = session.scalars(select(Iec61850ModelNode).where(Iec61850ModelNode.project_id == project_id)).all()
            by_kind = Counter(node.kind for node in nodes)
            by_parent: dict[str | None, list[Iec61850ModelNode]] = defaultdict(list)
            for node in nodes:
                by_parent[node.parent_id].append(node)
            issues: list[dict[str, Any]] = []
            type_ids: dict[str, set[str]] = defaultdict(set)
            for item in nodes:
                if item.kind in ("LNODE_TYPE", "DO_TYPE", "DA_TYPE", "ENUM_TYPE"):
                    type_attrs = _json_loads(item.attributes_json)
                    type_ids[item.kind].add(str(type_attrs.get("id") or item.name))
            ied_names = {item.name for item in nodes if item.kind == "IED"}
            datasets_by_parent = {
                parent_id: {item.name for item in siblings if item.kind == "DATASET"}
                for parent_id, siblings in by_parent.items()
            }

            def add(level: str, code: str, message: str, node: Iec61850ModelNode | None = None, field: str = ""):
                issues.append(
                    {
                        "level": level,
                        "rule_code": code,
                        "node_id": node.id if node else None,
                        "path": self._node_path(session, node) if node else project.name,
                        "field": field,
                        "message": message,
                    }
                )

            for required_kind in ("ROOT", "HEADER", "COMMUNICATION", "IED", "DATA_TYPE_TEMPLATES"):
                if not by_kind[required_kind]:
                    add("ERROR", f"STRUCTURE_{required_kind}_REQUIRED", f"缺少必需节点：{KIND_LABELS[required_kind]}")
            for singleton_kind in ("ROOT", "HEADER", "DATA_TYPE_TEMPLATES"):
                if by_kind[singleton_kind] > 1:
                    add(
                        "ERROR",
                        f"STRUCTURE_{singleton_kind}_SINGLETON",
                        f"模型中只能包含一个{KIND_LABELS[singleton_kind]}",
                    )
            for variant_issue in validate_file_variant(list(nodes), project.file_type, for_publish=False):
                add("ERROR", variant_issue["code"], variant_issue["message"])
            if not by_kind["LDEVICE"]:
                add("ERROR", "STRUCTURE_LDEVICE_REQUIRED", "至少需要一个逻辑设备")

            for node in nodes:
                attrs = _json_loads(node.attributes_json)
                if not node.name.strip():
                    add("ERROR", "NAME_REQUIRED", "节点名称不能为空", node, "name")
                for field_schema in get_kind_schema(node.kind)["fields"]:
                    key = field_schema["key"]
                    if field_schema.get("required") and key != "name" and attrs.get(key) in (None, ""):
                        add(
                            "ERROR",
                            "FIELD_REQUIRED",
                            f"{field_schema['label']}不能为空",
                            node,
                            key,
                        )
                if node.kind == "LDEVICE" and not NAME_PATTERN.fullmatch(str(attrs.get("inst", ""))):
                    add("ERROR", "LDEVICE_INST_INVALID", "逻辑设备 inst 格式不正确", node, "inst")
                if node.kind == "LN":
                    ln_class = str(attrs.get("lnClass", ""))
                    if not LN_CLASS_PATTERN.fullmatch(ln_class):
                        add("ERROR", "LN_CLASS_INVALID", "逻辑节点类应为 4 位大写字母或数字", node, "lnClass")
                    if attrs.get("inst") in (None, ""):
                        add("ERROR", "LN_INST_REQUIRED", "逻辑节点实例号不能为空", node, "inst")
                if node.kind in ("REPORT_CONTROL", "GSE_CONTROL") and not attrs.get("datSet"):
                    add("ERROR", "CONTROL_DATASET_REQUIRED", "控制块必须引用数据集", node, "datSet")
                if node.kind == "REPORT_CONTROL":
                    child_kinds = {child.kind for child in by_parent.get(node.id, [])}
                    for required_child in ("TRG_OPS", "OPT_FIELDS", "RPT_ENABLED"):
                        if required_child not in child_kinds:
                            add(
                                "ERROR",
                                f"REPORT_{required_child}_REQUIRED",
                                f"报告控制块缺少 {KIND_LABELS[required_child]}",
                                node,
                            )
                if node.kind in ("LNODE_TYPE", "DO_TYPE", "DA_TYPE", "ENUM_TYPE") and not attrs.get("id"):
                    add("ERROR", "TYPE_ID_REQUIRED", "类型定义 ID 不能为空", node, "id")
                if node.kind in ("LN0", "LN"):
                    ln_type = str(attrs.get("lnType") or "")
                    if ln_type and ln_type not in type_ids["LNODE_TYPE"]:
                        add("ERROR", "LNODE_TYPE_REFERENCE_MISSING", f"逻辑节点类型 {ln_type} 不存在", node, "lnType")
                if node.kind in ("DO_DEF", "SDO_DEF"):
                    type_ref = str(attrs.get("type") or "")
                    if type_ref and type_ref not in type_ids["DO_TYPE"]:
                        add("ERROR", "DO_TYPE_REFERENCE_MISSING", f"数据对象类型 {type_ref} 不存在", node, "type")
                if node.kind in ("DA_DEF", "BDA_DEF") and attrs.get("bType") in ("Struct", "Enum"):
                    type_ref = str(attrs.get("type") or "")
                    target_kind = "DA_TYPE" if attrs.get("bType") == "Struct" else "ENUM_TYPE"
                    if not type_ref:
                        add("ERROR", "NESTED_TYPE_REQUIRED", "Struct/Enum 基础类型必须填写类型引用", node, "type")
                    elif type_ref not in type_ids[target_kind]:
                        add("ERROR", "NESTED_TYPE_REFERENCE_MISSING", f"引用的类型 {type_ref} 不存在", node, "type")
                if node.kind == "DA_DEF" and node.name in {"q", "t", "dU"}:
                    b_type = str(attrs.get("bType") or "")
                    fc = str(attrs.get("fc") or "")
                    if node.name == "q":
                        if b_type != "Quality":
                            add("ERROR", "CDC_Q_BTYPE_INVALID", "品质属性 q 的 bType 必须为 Quality", node, "bType")
                        if attrs.get("qchg") is not True:
                            add("WARNING", "CDC_Q_QCHG_RECOMMENDED", "品质属性 q 建议启用 qchg", node, "qchg")
                    elif node.name == "t" and b_type not in {"Timestamp", "TimeStamp"}:
                        add("ERROR", "CDC_T_BTYPE_INVALID", "时间戳属性 t 的 bType 必须为 Timestamp", node, "bType")
                    elif node.name == "dU":
                        if b_type != "Unicode255":
                            add(
                                "ERROR",
                                "CDC_DU_BTYPE_INVALID",
                                "数据描述属性 dU 的 bType 必须为 Unicode255",
                                node,
                                "bType",
                            )
                        if fc != "DC":
                            add("ERROR", "CDC_DU_FC_INVALID", "数据描述属性 dU 的 FC 必须为 DC", node, "fc")
                    if node.name in {"q", "t"}:
                        primary_fc = next(
                            (
                                str(_json_loads(sibling.attributes_json).get("fc") or "")
                                for sibling in by_parent.get(node.parent_id, [])
                                if sibling.kind == "DA_DEF"
                                and sibling.name in {"stVal", "mag", "instMag", "actVal", "mxVal", "setVal"}
                                and _json_loads(sibling.attributes_json).get("fc")
                            ),
                            "",
                        )
                        if primary_fc and fc != primary_fc:
                            add(
                                "ERROR",
                                "CDC_COMMON_FC_MISMATCH",
                                f"属性 {node.name} 的 FC 应与主值一致（{primary_fc}）",
                                node,
                                "fc",
                            )
                if node.kind in ("REPORT_CONTROL", "GSE_CONTROL"):
                    dataset = str(attrs.get("datSet") or "")
                    if dataset and dataset not in datasets_by_parent.get(node.parent_id, set()):
                        add(
                            "ERROR",
                            "CONTROL_DATASET_MISSING",
                            f"引用的数据集 {dataset} 不存在于当前逻辑节点",
                            node,
                            "datSet",
                        )
                if node.kind == "CONNECTED_AP":
                    ied_name = str(attrs.get("iedName") or "")
                    if ied_name and ied_name not in ied_names:
                        add(
                            "ERROR",
                            "CONNECTED_AP_IED_MISSING",
                            f"通信配置引用的 IED {ied_name} 不存在",
                            node,
                            "iedName",
                        )
                if node.kind == "EXTENSION":
                    add(
                        "ERROR" if attrs.get("lossRisk") else "WARNING",
                        "LOSSY_EXTENSION_BLOCKED" if attrs.get("lossRisk") else "PRESERVED_EXTENSION_READ_ONLY",
                        (
                            "该扩展已确认存在有损风险，修复或明确保真策略前不能发布"
                            if attrs.get("lossRisk")
                            else "该节点为保真扩展片段；修改其父结构前请确认厂商兼容性"
                        ),
                        node,
                    )

            for logical_device in (node for node in nodes if node.kind == "LDEVICE"):
                ln0_count = sum(child.kind == "LN0" for child in by_parent.get(logical_device.id, []))
                if ln0_count != 1:
                    add("ERROR", "LN0_EXACTLY_ONE", "每个逻辑设备必须且只能包含一个 LLN0", logical_device)

            for ied in (node for node in nodes if node.kind == "IED"):
                services_nodes = [child for child in by_parent.get(ied.id, []) if child.kind == "SERVICES"]
                if len(services_nodes) != 1:
                    add("ERROR", "IED_SERVICES_EXACTLY_ONE", "每个 IED 必须且只能包含一个 Services", ied)
                    continue
                capability_names = {
                    str(_json_loads(child.attributes_json).get("tag") or child.name)
                    for child in by_parent.get(services_nodes[0].id, [])
                    if child.kind == "SERVICE_CAPABILITY"
                }
                ied_descendants = self._subtree_ids(session, project_id, ied.id)
                ied_nodes = [item for item in nodes if item.id in ied_descendants]
                if (
                    any(item.kind == "REPORT_CONTROL" for item in ied_nodes)
                    and "ConfReportControl" not in capability_names
                ):
                    add(
                        "ERROR",
                        "SERVICES_REPORT_CAPABILITY_MISSING",
                        "模型包含报告控制块，但 Services 未声明 ConfReportControl",
                        services_nodes[0],
                    )
                if any(item.kind == "GSE_CONTROL" for item in ied_nodes) and "GOOSE" not in capability_names:
                    add(
                        "ERROR",
                        "SERVICES_GOOSE_CAPABILITY_MISSING",
                        "模型包含 GOOSE 控制块，但 Services 未声明 GOOSE",
                        services_nodes[0],
                    )

            for siblings in by_parent.values():
                seen: set[tuple[str, str]] = set()
                for node in siblings:
                    key = (node.kind, node.name)
                    if key in seen:
                        add("ERROR", "SIBLING_NAME_DUPLICATE", "同级存在同类型、同名节点", node, "name")
                    seen.add(key)

            try:
                from src.modeling.interoperability import validate_interoperability
                from src.modeling.scl_serializer import SclModelSerializer

                generated = SclModelSerializer().serialize(project, list(nodes))
                interoperability = validate_interoperability(generated.xml, filename=generated.filename)
                for scl_issue in interoperability["issues"]:
                    add(
                        scl_issue["level"],
                        scl_issue["code"],
                        scl_issue["message"],
                    )
            except Exception as exc:
                add("ERROR", "SCL_SERIALIZATION_FAILED", f"SCL 生成或解析失败：{exc}")

            error_count = sum(issue["level"] == "ERROR" for issue in issues)
            warning_count = sum(issue["level"] == "WARNING" for issue in issues)
            project.validation_errors = error_count
            project.validation_warnings = warning_count
            project.status = "VALID" if error_count == 0 else "DRAFT"
            return {
                "passed": error_count == 0,
                "error_count": error_count,
                "warning_count": warning_count,
                "issues": issues,
                "validated_revision": project.revision,
                "interoperability": interoperability if "interoperability" in locals() else None,
            }

    @staticmethod
    def get_kind_schema(kind: str) -> dict[str, Any]:
        try:
            return get_kind_schema(kind)
        except KeyError as exc:
            raise NotFoundError(f"不支持的节点类型：{kind}") from exc

    @staticmethod
    def _version_dict(version: Iec61850ModelVersion) -> dict[str, Any]:
        return {
            "id": version.id,
            "project_id": version.project_id,
            "version_number": version.version_number,
            "label": version.label,
            "description": version.description,
            "status": version.status,
            "source_revision": version.source_revision,
            "created_at": _iso(version.created_at),
        }

    @staticmethod
    def _build_snapshot(
        project: Iec61850ModelProject,
        nodes: list[Iec61850ModelNode],
        references: list[Iec61850ModelReference],
    ) -> dict[str, Any]:
        return {
            "format_version": 1,
            "project": {
                "name": project.name,
                "description": project.description,
                "file_type": project.file_type,
                "standard_version": project.standard_version,
                "namespace": project.namespace,
                "modeling_mode": project.modeling_mode,
            },
            "nodes": [
                {
                    "id": node.id,
                    "parent_id": node.parent_id,
                    "kind": node.kind,
                    "name": node.name,
                    "sort_order": node.sort_order,
                    "attributes": _json_loads(node.attributes_json),
                    "revision": node.revision,
                }
                for node in nodes
            ],
            "references": [
                {
                    "id": reference.id,
                    "source_node_id": reference.source_node_id,
                    "target_node_id": reference.target_node_id,
                    "relation_type": reference.relation_type,
                    "attributes": _json_loads(reference.attributes_json),
                }
                for reference in references
            ],
        }

    def _create_version_in_session(
        self,
        session: Session,
        project: Iec61850ModelProject,
        *,
        label: str,
        description: str,
        status: str = "SNAPSHOT",
    ) -> Iec61850ModelVersion:
        nodes = list(session.scalars(select(Iec61850ModelNode).where(Iec61850ModelNode.project_id == project.id)).all())
        references = list(
            session.scalars(select(Iec61850ModelReference).where(Iec61850ModelReference.project_id == project.id)).all()
        )
        next_number = (
            session.scalar(
                select(func.max(Iec61850ModelVersion.version_number)).where(
                    Iec61850ModelVersion.project_id == project.id
                )
            )
            or 0
        ) + 1
        version = Iec61850ModelVersion(
            id=str(uuid.uuid4()),
            project_id=project.id,
            version_number=next_number,
            label=label.strip() or f"版本 V{next_number}",
            description=description.strip(),
            status=status,
            source_revision=project.revision,
            snapshot_json=_json_dumps(self._build_snapshot(project, nodes, references)),
        )
        session.add(version)
        session.flush()
        return version

    def list_versions(self, project_id: str) -> list[dict[str, Any]]:
        with self.session_factory() as session:
            self._require_project(session, project_id)
            versions = session.scalars(
                select(Iec61850ModelVersion)
                .where(Iec61850ModelVersion.project_id == project_id)
                .order_by(Iec61850ModelVersion.version_number.desc())
            ).all()
            return [self._version_dict(version) for version in versions]

    def create_version(self, project_id: str, *, label: str = "", description: str = "") -> dict[str, Any]:
        with self.session_factory() as session, session.begin():
            project = self._require_project(session, project_id)
            version = self._create_version_in_session(
                session,
                project,
                label=label,
                description=description,
            )
            return self._version_dict(version)

    def restore_version(self, project_id: str, version_id: str) -> dict[str, Any]:
        with self.session_factory() as session, session.begin():
            project = self._require_project(session, project_id)
            version = session.scalar(
                select(Iec61850ModelVersion).where(
                    Iec61850ModelVersion.id == version_id,
                    Iec61850ModelVersion.project_id == project_id,
                )
            )
            if not version:
                raise NotFoundError("模型版本不存在")
            snapshot = _json_loads(version.snapshot_json)
            if snapshot.get("format_version") != 1:
                raise ValidationError("不支持的模型快照格式")

            session.execute(delete(Iec61850ModelReference).where(Iec61850ModelReference.project_id == project_id))
            session.execute(delete(Iec61850ModelNode).where(Iec61850ModelNode.project_id == project_id))
            project_data = snapshot.get("project") or {}
            for key in ("name", "description", "file_type", "standard_version", "namespace", "modeling_mode"):
                if key in project_data:
                    setattr(project, key, project_data[key])
            for item in snapshot.get("nodes") or []:
                session.add(
                    Iec61850ModelNode(
                        id=item["id"],
                        project_id=project_id,
                        parent_id=item.get("parent_id"),
                        kind=item["kind"],
                        name=item["name"],
                        sort_order=int(item.get("sort_order", 0)),
                        attributes_json=_json_dumps(item.get("attributes")),
                        revision=int(item.get("revision", 1)),
                    )
                )
            session.flush()
            for item in snapshot.get("references") or []:
                session.add(
                    Iec61850ModelReference(
                        id=item["id"],
                        project_id=project_id,
                        source_node_id=item["source_node_id"],
                        target_node_id=item["target_node_id"],
                        relation_type=item["relation_type"],
                        attributes_json=_json_dumps(item.get("attributes")),
                    )
                )
            project.revision += 1
            project.status = "DRAFT"
            return {
                "restored_version": self._version_dict(version),
                "project_revision": project.revision,
                "node_count": len(snapshot.get("nodes") or []),
            }

    def delete_version(self, project_id: str, version_id: str) -> None:
        with self.session_factory() as session, session.begin():
            self._require_project(session, project_id)
            version = session.scalar(
                select(Iec61850ModelVersion).where(
                    Iec61850ModelVersion.id == version_id,
                    Iec61850ModelVersion.project_id == project_id,
                )
            )
            if not version:
                raise NotFoundError("模型版本不存在")
            if version.status == "PUBLISHED":
                raise ValidationError("已发布版本不可删除")
            session.delete(version)

    def generate_scl(self, project_id: str, *, file_type: str | None = None) -> dict[str, Any]:
        from src.modeling.scl_serializer import SclModelSerializer

        with self.session_factory() as session:
            project = self._require_project(session, project_id)
            nodes = list(
                session.scalars(select(Iec61850ModelNode).where(Iec61850ModelNode.project_id == project_id)).all()
            )
            target_file_type = (file_type or project.file_type).upper()
            variant_issues = validate_file_variant(nodes, target_file_type, for_publish=False)
            if variant_issues:
                raise ValidationError("目标 SCL 文件变体不满足生成契约", {"issues": variant_issues})
            result = SclModelSerializer().serialize(project, nodes, file_type=target_file_type)
            return {
                "xml": result.xml,
                "filename": result.filename,
                "size": len(result.xml.encode("utf-8")),
                "revision": project.revision,
                "status": project.status,
            }

    def generate_artifact_bundle(self, project_id: str, *, file_type: str | None = None) -> dict[str, Any]:
        from src.modeling.scl_serializer import SclModelSerializer

        with self.session_factory() as session:
            project = self._require_project(session, project_id)
            nodes = list(
                session.scalars(select(Iec61850ModelNode).where(Iec61850ModelNode.project_id == project_id)).all()
            )
            target_file_type = (file_type or project.file_type).upper()
            variant_issues = validate_file_variant(nodes, target_file_type, for_publish=False)
            if variant_issues:
                raise ValidationError("目标 SCL 文件变体不满足生成契约", {"issues": variant_issues})
            scl = SclModelSerializer().serialize(project, nodes, file_type=target_file_type)
            bundle = build_artifact_bundle(project, nodes, scl.xml, scl.filename)
            return {
                "content": bundle.content,
                "filename": bundle.filename,
                "size": len(bundle.content),
                "manifest": bundle.manifest,
                "artifacts": [artifact.metadata() for artifact in bundle.artifacts],
                "revision": project.revision,
            }

    def publish_project(self, project_id: str, *, label: str = "", description: str = "") -> dict[str, Any]:
        validation = self.validate_project(project_id)
        if not validation["passed"]:
            raise ValidationError("模型校验未通过，不能发布", validation)
        with self.session_factory() as session:
            project = self._require_project(session, project_id)
            nodes = list(
                session.scalars(select(Iec61850ModelNode).where(Iec61850ModelNode.project_id == project_id)).all()
            )
            variant_issues = validate_file_variant(nodes, project.file_type, for_publish=True)
            if variant_issues:
                raise ValidationError("当前文件变体不能发布", {"issues": variant_issues})
        generated = self.generate_artifact_bundle(project_id)
        with self.session_factory() as session, session.begin():
            project = self._require_project(session, project_id)
            session.execute(
                Iec61850ModelVersion.__table__.update()
                .where(
                    Iec61850ModelVersion.project_id == project_id,
                    Iec61850ModelVersion.status == "PUBLISHED",
                )
                .values(status="SNAPSHOT")
            )
            version = self._create_version_in_session(
                session,
                project,
                label=label or f"发布版本 r{project.revision}",
                description=description,
                status="PUBLISHED",
            )
            project.status = "PUBLISHED"
            scl_artifact = next(item for item in generated["artifacts"] if item["kind"] == "SCL")
            return {
                "version": self._version_dict(version),
                "validation": validation,
                "artifact": {**scl_artifact, "revision": generated["revision"]},
                "bundle": {key: generated[key] for key in ("filename", "size", "revision")},
                "manifest": generated["manifest"],
            }
