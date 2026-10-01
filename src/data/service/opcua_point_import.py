"""Atomic import of OPC UA point metadata and server variable definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, func, or_, select

from src.data.controller.db import local_session
from src.data.model.channel import Channel
from src.data.model.opcua_config import OpcUaConfig
from src.data.model.opcua_node import OpcUaNode
from src.data.model.opcua_point import OpcUaPoint
from src.proto.opcua.point_excel import ExcelError, ParsedPoints, export_point_excel, parse_point_excel


class PointImportError(ValueError):
    def __init__(self, message: str, errors: list[ExcelError] | None = None, conflicts: list[dict] | None = None):
        super().__init__(message)
        self.errors = errors or []
        self.conflicts = conflicts or []


@dataclass
class ImportInspection:
    parsed: ParsedPoints
    errors: list[ExcelError]
    conflicts: list[dict[str, Any]]
    role: str

    def to_dict(self) -> dict[str, Any]:
        counts = {
            sheet: sum(row["sheet"] == sheet for row in self.parsed.rows) for sheet in ("遥测", "遥信", "遥控", "遥调")
        }
        return {
            "sha256": self.parsed.sha256,
            "total": len(self.parsed.rows),
            "counts": counts,
            "errors": [error.to_dict() for error in self.errors],
            "conflicts": self.conflicts,
            "role": self.role,
        }


_POINT_FIELDS = (
    "point_type",
    "point_code",
    "point_name",
    "attribute_code",
    "node_id",
    "namespace_uri",
    "data_type",
    "sampling_interval_ms",
    "unit",
    "scale_mul",
    "scale_add",
    "upper_limit",
    "lower_limit",
    "initial_value",
    "reverse",
    "command_type",
    "related_code",
)


def _inspect_session(session, channel_id: int, parsed: ParsedPoints) -> ImportInspection:
    channel = session.get(Channel, channel_id)
    if channel is None or channel.protocol_type != 7 or channel.conn_type not in (1, 2):
        raise PointImportError("OPC UA 通道不存在")
    role = "client" if channel.conn_type == 1 else "server"
    existing_points = session.scalars(select(OpcUaPoint).where(OpcUaPoint.channel_id == channel_id)).all()
    by_code = {point.point_code: point for point in existing_points}
    by_node = {point.node_id: point for point in existing_points}
    node_defs = session.scalars(select(OpcUaNode).where(OpcUaNode.channel_id == channel_id)).all()
    node_by_id = {node.node_id: node for node in node_defs}
    errors = list(parsed.errors)
    conflicts: list[dict[str, Any]] = []
    incoming_by_code = {row["point_code"]: row for row in parsed.rows if row.get("point_code")}
    model = session.get(OpcUaConfig, channel_id)
    configured_uri = model.namespace_uri if model else None
    existing_uris = {node.namespace_uri for node in node_defs}
    incoming_uris = {row["namespace_uri"] for row in parsed.rows if row.get("namespace_uri")}
    if role == "server" and len(incoming_uris) > 1:
        errors.append(ExcelError("*", 0, "命名空间URI", "M1 服务端一次导入只支持一个命名空间 URI"))

    for row in parsed.rows:
        sheet, excel_row = row["sheet"], row["excel_row"]
        code, node_id, namespace_uri = row.get("point_code"), row.get("node_id"), row.get("namespace_uri")
        if role == "server" and node_id:
            if not node_id.startswith("ns=2;s="):
                errors.append(ExcelError(sheet, excel_row, "NodeId", "M1 服务端 NodeId 必须采用 ns=2;s=..."))
            if namespace_uri and configured_uri and namespace_uri != configured_uri:
                errors.append(ExcelError(sheet, excel_row, "命名空间URI", "与服务端已配置的命名空间 URI 不一致"))
            if namespace_uri and existing_uris and namespace_uri not in existing_uris:
                errors.append(ExcelError(sheet, excel_row, "命名空间URI", "与现有节点的命名空间 URI 不一致"))
        if code and code in by_code:
            conflicts.append({"sheet": sheet, "row": excel_row, "field": "测点编码", "value": code})
        if node_id and node_id in by_node:
            owner = by_node[node_id]
            if owner.point_code != code:
                errors.append(ExcelError(sheet, excel_row, "NodeId", f"已由测点 {owner.point_code} 使用"))
        if role == "server" and node_id in node_by_id and (not code or code not in by_code):
            conflicts.append({"sheet": sheet, "row": excel_row, "field": "NodeId", "value": node_id})
        related = row.get("related_code")
        if related:
            expected_type = 1 if row["point_type"] == 2 else 0
            target = incoming_by_code.get(related) or by_code.get(related)
            if isinstance(target, OpcUaPoint):
                actual_type = target.point_type
            else:
                actual_type = target.get("point_type") if target else None
            if actual_type != expected_type:
                field = "关联遥信编码" if expected_type == 1 else "关联遥测编码"
                errors.append(ExcelError(sheet, excel_row, field, "关联测点不存在或类型不匹配"))
    for point in existing_points:
        if point.point_code in incoming_by_code or not point.related_code:
            continue
        target = incoming_by_code.get(point.related_code)
        if target and target["point_type"] != (1 if point.point_type == 2 else 0):
            errors.append(ExcelError("*", 0, "测点编码", f"覆盖将使已有测点 {point.point_code} 的反馈点类型不匹配"))
    return ImportInspection(parsed, errors, conflicts, role)


class OpcUaPointImportService:
    @staticmethod
    def clear(channel_id: int) -> dict[str, int]:
        with local_session() as session, session.begin():
            channel = session.get(Channel, channel_id)
            if channel is None or channel.protocol_type != 7:
                raise ValueError("OPC UA 通道不存在")
            count = (
                session.scalar(
                    select(func.count())
                    .select_from(OpcUaPoint)
                    .where(
                        OpcUaPoint.channel_id == channel_id,
                    )
                )
                or 0
            )
            if channel.conn_type == 2:
                point_node_ids = select(OpcUaPoint.node_id).where(OpcUaPoint.channel_id == channel_id)
                session.execute(
                    delete(OpcUaNode).where(OpcUaNode.channel_id == channel_id, OpcUaNode.node_id.in_(point_node_ids))
                )
            session.execute(delete(OpcUaPoint).where(OpcUaPoint.channel_id == channel_id))
        return {"deleted": count}

    @staticmethod
    def get_point(channel_id: int, point_code: str) -> dict[str, Any] | None:
        with local_session() as session:
            point = session.scalar(
                select(OpcUaPoint).where(OpcUaPoint.channel_id == channel_id, OpcUaPoint.point_code == point_code)
            )
            return {field: getattr(point, field) for field in _POINT_FIELDS} if point else None

    @staticmethod
    def export(channel_id: int) -> bytes:
        with local_session() as session:
            channel = session.get(Channel, channel_id)
            if channel is None or channel.protocol_type != 7:
                raise ValueError("OPC UA 通道不存在")
            records = session.scalars(
                select(OpcUaPoint)
                .where(OpcUaPoint.channel_id == channel_id)
                .order_by(OpcUaPoint.point_type, OpcUaPoint.point_code)
            ).all()
            points = [
                {"id": point.id, **{field: getattr(point, field) for field in _POINT_FIELDS}} for point in records
            ]
        return export_point_excel(points)

    @staticmethod
    def has_points(channel_id: int) -> bool:
        with local_session() as session:
            return session.scalar(select(OpcUaPoint.id).where(OpcUaPoint.channel_id == channel_id).limit(1)) is not None

    @staticmethod
    def list_points(
        channel_id: int, *, point_type: int | None = None, search: str = "", offset: int = 0, limit: int = 100
    ) -> dict[str, Any]:
        if point_type is not None and point_type not in (0, 1, 2, 3):
            raise ValueError("点位类型必须在 0 到 3 之间")
        if not 0 <= offset <= 100000 or not 1 <= limit <= 500:
            raise ValueError("分页参数超出范围")
        with local_session() as session:
            criteria = [OpcUaPoint.channel_id == channel_id]
            if point_type is not None:
                criteria.append(OpcUaPoint.point_type == point_type)
            if search:
                pattern = f"%{search[:128]}%"
                criteria.append(
                    or_(
                        OpcUaPoint.point_code.like(pattern),
                        OpcUaPoint.point_name.like(pattern),
                        OpcUaPoint.node_id.like(pattern),
                    )
                )
            total = session.scalar(select(func.count()).select_from(OpcUaPoint).where(*criteria)) or 0
            records = session.scalars(
                select(OpcUaPoint)
                .where(*criteria)
                .order_by(OpcUaPoint.point_type, OpcUaPoint.point_code)
                .offset(offset)
                .limit(limit)
            ).all()
            return {
                "total": total,
                "offset": offset,
                "limit": limit,
                "points": [
                    {"id": point.id, **{field: getattr(point, field) for field in _POINT_FIELDS}} for point in records
                ],
            }

    @staticmethod
    def delete_point(channel_id: int, point_code: str) -> bool:
        with local_session() as session, session.begin():
            channel = session.get(Channel, channel_id)
            if channel is None or channel.protocol_type != 7:
                raise ValueError("OPC UA 通道不存在")
            point = session.scalar(
                select(OpcUaPoint).where(OpcUaPoint.channel_id == channel_id, OpcUaPoint.point_code == point_code)
            )
            if point is None:
                return False
            dependent = session.scalar(
                select(OpcUaPoint.id)
                .where(OpcUaPoint.channel_id == channel_id, OpcUaPoint.related_code == point_code)
                .limit(1)
            )
            if dependent is not None:
                raise ValueError("测点仍被遥控或遥调点引用")
            if channel.conn_type == 2:
                node = session.scalar(
                    select(OpcUaNode).where(OpcUaNode.channel_id == channel_id, OpcUaNode.node_id == point.node_id)
                )
                if node is not None:
                    session.delete(node)
            session.delete(point)
        return True

    @staticmethod
    def preview(channel_id: int, content: bytes) -> ImportInspection:
        parsed = parse_point_excel(content)
        with local_session() as session:
            return _inspect_session(session, channel_id, parsed)

    @staticmethod
    def apply(channel_id: int, content: bytes, expected_sha256: str, mode: str) -> dict[str, Any]:
        if mode not in {"add", "overwrite"}:
            raise PointImportError("冲突策略必须为 add 或 overwrite")
        parsed = parse_point_excel(content)
        if parsed.sha256 != expected_sha256:
            raise PointImportError("文件内容与预检时不一致，请重新预检")
        with local_session() as session, session.begin():
            inspection = _inspect_session(session, channel_id, parsed)
            if inspection.errors:
                raise PointImportError("点表预检失败", inspection.errors, inspection.conflicts)
            if mode == "add" and inspection.conflicts:
                raise PointImportError("点表与现有测点冲突", conflicts=inspection.conflicts)
            if not parsed.rows:
                raise PointImportError("点表没有可导入的测点")

            existing = session.scalars(select(OpcUaPoint).where(OpcUaPoint.channel_id == channel_id)).all()
            by_code = {point.point_code: point for point in existing}
            nodes = session.scalars(select(OpcUaNode).where(OpcUaNode.channel_id == channel_id)).all()
            by_node = {node.node_id: node for node in nodes}
            if inspection.role == "server":
                uri = parsed.rows[0]["namespace_uri"]
                config = session.get(OpcUaConfig, channel_id)
                if config is None:
                    config = OpcUaConfig(channel_id=channel_id)
                    session.add(config)
                if not config.namespace_uri:
                    config.namespace_uri = uri

            created = updated = 0
            for row in parsed.rows:
                payload = {field: row[field] for field in _POINT_FIELDS}
                point = by_code.get(row["point_code"])
                if point is None:
                    point = OpcUaPoint(channel_id=channel_id, **payload)
                    session.add(point)
                    created += 1
                else:
                    old_node_id = point.node_id
                    if inspection.role == "server" and old_node_id != row["node_id"]:
                        old_node = by_node.pop(old_node_id, None)
                        if old_node is not None:
                            session.delete(old_node)
                    for field, value in payload.items():
                        setattr(point, field, value)
                    updated += 1
                if inspection.role == "server":
                    definition = by_node.get(row["node_id"])
                    values = {
                        "namespace_uri": row["namespace_uri"],
                        "browse_name": row["point_name"],
                        "data_type": row["data_type"],
                        "initial_value": row["initial_value"],
                        "writable": row["point_type"] in (2, 3),
                    }
                    if definition is None:
                        definition = OpcUaNode(channel_id=channel_id, node_id=row["node_id"], **values)
                        session.add(definition)
                        by_node[row["node_id"]] = definition
                    else:
                        for key, value in values.items():
                            setattr(definition, key, value)
        return {
            "created": created,
            "updated": updated,
            "total": len(parsed.rows),
            "sha256": parsed.sha256,
            "role": inspection.role,
            "schema_version": 1,
        }
