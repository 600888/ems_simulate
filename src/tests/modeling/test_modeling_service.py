"""IEC 61850 图形化建模服务的核心闭环测试。"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.data.model  # noqa: F401
from src.data.model.base import Base
from src.modeling.service import Iec61850ModelingService
from src.web.api.exceptions import ConflictError, ValidationError


@pytest.fixture
def service() -> Iec61850ModelingService:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return Iec61850ModelingService(sessionmaker(engine, expire_on_commit=False))


def create_project(service: Iec61850ModelingService) -> dict:
    return service.create_project(
        {
            "name": "线路保护模型",
            "code": "LINE_PROTECTION_A",
            "file_type": "ICD",
            "standard_version": "IEC 61850 Ed2.1",
            "ied": {"name": "PROT_IED_01", "manufacturer": "Test", "type": "Protection"},
            "access_point_name": "AP1",
            "logical_devices": [{"inst": "LD0", "desc": "保护逻辑设备"}],
        }
    )


def flatten(nodes: list[dict]) -> list[dict]:
    result = []
    for node in nodes:
        result.append(node)
        result.extend(flatten(node.get("children", [])))
    return result


def test_create_from_scratch_builds_minimum_valid_skeleton(service: Iec61850ModelingService):
    result = create_project(service)
    project_id = result["project"]["id"]
    nodes = flatten(result["tree"])

    assert {"ROOT", "HEADER", "IED", "ACCESS_POINT", "SERVER", "LDEVICE", "LN0", "DATA_TYPE_TEMPLATES"} <= {
        node["kind"] for node in nodes
    }
    validation = service.validate_project(project_id)
    assert validation["passed"] is True
    assert validation["error_count"] == 0
    assert service.get_project(project_id)["status"] == "VALID"


def test_node_crud_and_optimistic_revision(service: Iec61850ModelingService):
    result = create_project(service)
    project_id = result["project"]["id"]
    logical_device = next(node for node in flatten(result["tree"]) if node["kind"] == "LDEVICE")

    created = service.create_node(
        project_id,
        {
            "parent_id": logical_device["id"],
            "kind": "LN",
            "name": "PTOC1",
            "attributes": {"lnClass": "PTOC", "inst": "1", "lnType": "PTOC_TYPE"},
        },
    )
    assert service.get_project(project_id)["status"] == "DRAFT"
    updated = service.update_node(
        project_id,
        created["id"],
        {
            "name": "PTOC2",
            "attributes": {"lnClass": "PTOC", "inst": "2", "lnType": "PTOC_TYPE"},
            "expected_revision": created["revision"],
        },
    )
    assert updated["name"] == "PTOC2"
    assert updated["revision"] == created["revision"] + 1

    with pytest.raises(ConflictError):
        service.update_node(
            project_id,
            created["id"],
            {"name": "STALE", "expected_revision": created["revision"]},
        )

    impact = service.get_delete_impact(project_id, created["id"])
    assert impact["can_delete"] is True
    assert service.delete_node(project_id, created["id"])["deleted_count"] == 1


def test_protected_structure_cannot_be_deleted(service: Iec61850ModelingService):
    result = create_project(service)
    project_id = result["project"]["id"]
    ln0 = next(node for node in flatten(result["tree"]) if node["kind"] == "LN0")

    impact = service.get_delete_impact(project_id, ln0["id"])
    assert impact["can_delete"] is False
    assert impact["protected"] is True
    with pytest.raises(ValidationError):
        service.delete_node(project_id, ln0["id"])


def test_singleton_child_is_rejected(service: Iec61850ModelingService):
    result = create_project(service)
    project_id = result["project"]["id"]
    root = next(node for node in flatten(result["tree"]) if node["kind"] == "ROOT")

    with pytest.raises(ConflictError):
        service.create_node(
            project_id,
            {"parent_id": root["id"], "kind": "HEADER", "name": "AnotherHeader", "attributes": {}},
        )
