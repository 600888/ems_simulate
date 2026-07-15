"""IEC 61850 图形化建模服务的核心闭环测试。"""

import xml.etree.ElementTree as ET

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


def test_scl_generation_is_parseable_and_uses_project_extension(service: Iec61850ModelingService):
    result = create_project(service)
    artifact = service.generate_scl(result["project"]["id"])

    root = ET.fromstring(artifact["xml"])
    namespace = {"scl": "http://www.iec.ch/61850/2003/SCL"}
    assert root.tag.endswith("}SCL")
    assert root.find("scl:Header", namespace) is not None
    assert root.find("scl:IED", namespace).attrib["name"] == "PROT_IED_01"
    assert root.find(".//scl:LDevice", namespace).attrib["inst"] == "LD0"
    assert root.find(".//scl:LN0", namespace).attrib["lnClass"] == "LLN0"
    assert artifact["filename"] == "LINE_PROTECTION_A.icd"


def test_version_snapshot_can_restore_full_tree(service: Iec61850ModelingService):
    result = create_project(service)
    project_id = result["project"]["id"]
    original_count = result["project"]["node_count"]
    logical_device = next(node for node in flatten(result["tree"]) if node["kind"] == "LDEVICE")
    version = service.create_version(project_id, label="初始骨架", description="恢复测试")

    service.create_node(
        project_id,
        {
            "parent_id": logical_device["id"],
            "kind": "LN",
            "name": "PTOC1",
            "attributes": {"lnClass": "PTOC", "inst": "1"},
        },
    )
    assert len(flatten(service.get_tree(project_id))) == original_count + 1

    restored = service.restore_version(project_id, version["id"])
    assert restored["node_count"] == original_count
    assert len(flatten(service.get_tree(project_id))) == original_count
    assert all(node["name"] != "PTOC1" for node in flatten(service.get_tree(project_id)))


def test_publish_creates_protected_published_version(service: Iec61850ModelingService):
    result = create_project(service)
    project_id = result["project"]["id"]

    published = service.publish_project(project_id, label="现场发布版")
    assert published["validation"]["passed"] is True
    assert published["artifact"]["filename"] == "LINE_PROTECTION_A.icd"
    assert service.get_project(project_id)["status"] == "PUBLISHED"
    versions = service.list_versions(project_id)
    assert versions[0]["status"] == "PUBLISHED"

    with pytest.raises(ValidationError):
        service.delete_version(project_id, versions[0]["id"])


def test_communication_tree_is_serialized_to_scl(service: Iec61850ModelingService):
    result = create_project(service)
    project_id = result["project"]["id"]
    root_node = next(node for node in flatten(result["tree"]) if node["kind"] == "ROOT")
    communication = service.create_node(
        project_id,
        {"parent_id": root_node["id"], "kind": "COMMUNICATION", "name": "Communication", "attributes": {}},
    )
    subnet = service.create_node(
        project_id,
        {
            "parent_id": communication["id"],
            "kind": "SUBNETWORK",
            "name": "StationBus",
            "attributes": {"type": "8-MMS", "bitRate": 100, "multiplier": "M"},
        },
    )
    connected = service.create_node(
        project_id,
        {
            "parent_id": subnet["id"],
            "kind": "CONNECTED_AP",
            "name": "PROT_IED_01_AP1",
            "attributes": {"iedName": "PROT_IED_01", "apName": "AP1"},
        },
    )
    address = service.create_node(
        project_id,
        {"parent_id": connected["id"], "kind": "ADDRESS", "name": "Address", "attributes": {}},
    )
    service.create_node(
        project_id,
        {
            "parent_id": address["id"],
            "kind": "P",
            "name": "IP",
            "attributes": {"type": "IP", "value": "192.168.1.10"},
        },
    )

    xml_root = ET.fromstring(service.generate_scl(project_id)["xml"])
    namespace = {"scl": "http://www.iec.ch/61850/2003/SCL"}
    subnet_xml = xml_root.find(".//scl:SubNetwork", namespace)
    connected_xml = xml_root.find(".//scl:ConnectedAP", namespace)
    parameter_xml = xml_root.find(".//scl:Address/scl:P", namespace)
    assert subnet_xml.attrib == {"name": "StationBus", "type": "8-MMS"}
    assert connected_xml.attrib == {"iedName": "PROT_IED_01", "apName": "AP1"}
    assert parameter_xml.attrib["type"] == "IP"
    assert parameter_xml.text == "192.168.1.10"
