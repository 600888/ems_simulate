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

    assert {
        "ROOT",
        "HEADER",
        "COMMUNICATION",
        "IED",
        "SERVICES",
        "ACCESS_POINT",
        "SERVER",
        "LDEVICE",
        "LN0",
        "DATA_TYPE_TEMPLATES",
    } <= {node["kind"] for node in nodes}
    validation = service.validate_project(project_id)
    assert validation["passed"] is True
    assert validation["error_count"] == 0
    assert service.get_project(project_id)["status"] == "VALID"


def test_compact_tree_defers_deep_node_details(service: Iec61850ModelingService):
    result = create_project(service)
    project_id = result["project"]["id"]

    compact_tree = service.get_tree(project_id, compact=True)
    compact_nodes = flatten(compact_tree)
    root = compact_tree[0]
    deep_node = next(node for node in compact_nodes if node.get("detail_loaded") is None)

    assert root["detail_loaded"] is True
    assert "attributes" in root
    assert "attributes" not in deep_node
    assert "path" not in deep_node
    assert "project_id" not in deep_node

    detail = service.get_node(
        project_id,
        deep_node["id"],
        include_children=True,
    )
    assert detail["detail_loaded"] is True
    assert "attributes" in detail
    assert "schema" in detail
    assert "children" in detail
    assert all("attributes" in child for child in detail["children"])


def test_compact_tree_can_limit_initial_depth_and_keep_focus_path(
    service: Iec61850ModelingService,
):
    result = create_project(service)
    project_id = result["project"]["id"]
    full_nodes = flatten(result["tree"])
    target = next(node for node in full_nodes if node["kind"] == "LN0")

    shallow_tree = service.get_tree(project_id, compact=True, max_depth=1)
    shallow_nodes = flatten(shallow_tree)

    assert target["id"] not in {node["id"] for node in shallow_nodes}
    assert any(node.get("child_count", 0) > 0 and "children" not in node for node in shallow_nodes)

    focused_tree = service.get_tree(
        project_id,
        compact=True,
        max_depth=1,
        focus_id=target["id"],
    )
    focused_nodes = flatten(focused_tree)

    assert target["id"] in {node["id"] for node in focused_nodes}
    assert all("parent_id" in node for node in focused_nodes if node["id"] != focused_tree[0]["id"])


def test_compact_tree_search_returns_matches_with_ancestor_paths(
    service: Iec61850ModelingService,
):
    result = create_project(service)
    project_id = result["project"]["id"]
    target = next(node for node in flatten(result["tree"]) if node["kind"] == "LN0")

    filtered_tree = service.get_tree(
        project_id,
        compact=True,
        max_depth=1,
        keyword=target["name"],
        kind="LN0",
    )
    filtered_nodes = flatten(filtered_tree)

    assert target["id"] in {node["id"] for node in filtered_nodes}
    assert all(node["id"] == target["id"] or node["kind"] != "LN0" for node in filtered_nodes)
    assert any(node.get("children_partial") for node in filtered_nodes)
    kinds = service.get_tree_kinds(project_id)
    assert next(item for item in kinds if item["kind"] == "LN0")["count"] >= 1


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
    xml_root = ET.fromstring(service.generate_scl(project_id)["xml"])
    namespace = {"scl": "http://www.iec.ch/61850/2003/SCL"}
    subnet_xml = xml_root.find(".//scl:SubNetwork", namespace)
    connected_xml = xml_root.find(".//scl:ConnectedAP", namespace)
    parameter_xml = xml_root.find(".//scl:Address/scl:P", namespace)
    assert subnet_xml.attrib == {"name": "StationBus", "type": "8-MMS"}
    assert connected_xml.attrib == {"iedName": "PROT_IED_01", "apName": "AP1"}
    assert parameter_xml.attrib["type"] == "IP"
    assert parameter_xml.text == "192.168.1.10"


def test_report_control_serializes_complete_children_and_preserves_zero(service: Iec61850ModelingService):
    result = create_project(service)
    project_id = result["project"]["id"]
    ln0 = next(node for node in flatten(result["tree"]) if node["kind"] == "LN0")
    dataset = service.create_node(
        project_id,
        {"parent_id": ln0["id"], "kind": "DATASET", "name": "dsEvents", "attributes": {}},
    )
    assert dataset["name"] == "dsEvents"
    report = service.create_node(
        project_id,
        {
            "parent_id": ln0["id"],
            "kind": "REPORT_CONTROL",
            "name": "urcbEvents",
            "attributes": {"datSet": "dsEvents", "confRev": 0, "buffered": False, "bufTime": 0},
        },
    )
    service.create_node(
        project_id,
        {
            "parent_id": report["id"],
            "kind": "TRG_OPS",
            "name": "TrgOps",
            "attributes": {"dchg": True, "qchg": True, "dupd": False, "period": False, "gi": True},
        },
    )
    service.create_node(
        project_id,
        {
            "parent_id": report["id"],
            "kind": "OPT_FIELDS",
            "name": "OptFields",
            "attributes": {"seqNum": True, "timeStamp": True, "reasonCode": True},
        },
    )
    service.create_node(
        project_id,
        {
            "parent_id": report["id"],
            "kind": "RPT_ENABLED",
            "name": "RptEnabled",
            "attributes": {"max": 8},
        },
    )

    xml_root = ET.fromstring(service.generate_scl(project_id)["xml"])
    ns = {"scl": "http://www.iec.ch/61850/2003/SCL"}
    report_xml = xml_root.find(".//scl:ReportControl", ns)
    assert report_xml is not None
    assert report_xml.attrib["confRev"] == "0"
    assert report_xml.attrib["buffered"] == "false"
    assert report_xml.find("scl:TrgOps", ns).attrib["dupd"] == "false"
    assert report_xml.find("scl:OptFields", ns).attrib["reasonCode"] == "true"
    assert report_xml.find("scl:RptEnabled", ns).attrib["max"] == "8"


@pytest.mark.parametrize(
    ("sample_name", "project_code"),
    [
        ("simpleIO.icd", "SIMPLE_IO_IMPORTED"),
        ("KG_BAMS_real.icd", "KG_BAMS_REAL_IMPORTED"),
        ("GOOSE发布.icd", "GOOSE_IMPORTED"),
    ],
)
def test_import_preview_and_roundtrip_real_sample(
    service: Iec61850ModelingService,
    sample_name: str,
    project_code: str,
):
    from pathlib import Path

    sample = Path("tmp/testicd") / sample_name
    if not sample.exists():
        pytest.skip("本地黄金样例未提供")
    preview = service.preview_import(sample.read_bytes(), filename=sample.name)
    assert preview["summary"]["by_kind"]["SERVICES"] >= 1

    imported = service.import_scl(sample.read_bytes(), filename=sample.name, code=project_code)
    artifact = service.generate_scl(imported["project"]["id"])
    root = ET.fromstring(artifact["xml"])
    ns = {"scl": "http://www.iec.ch/61850/2003/SCL"}
    assert root.find("scl:Header", ns).attrib["nameStructure"] == "IEDName"
    original = ET.fromstring(sample.read_bytes())
    assert len(root.findall(".//scl:ReportControl", ns)) == len(original.findall(".//scl:ReportControl", ns))
    assert len(root.findall(".//scl:GSEControl", ns)) == len(original.findall(".//scl:GSEControl", ns))
    assert len(root.findall(".//scl:Services/*", ns)) == len(original.findall(".//scl:Services/*", ns))


def test_import_rejects_truncated_xml(service: Iec61850ModelingService):
    with pytest.raises(ValidationError, match="XML"):
        service.preview_import(b'>\n<EnumVal ord="1">bad</EnumVal>', filename="broken.icd")


def test_selected_profiles_seed_declared_service_capabilities(service: Iec61850ModelingService):
    result = service.create_project(
        {
            "name": "GOOSE 发布模型",
            "code": "GOOSE_PROFILE_MODEL",
            "file_type": "ICD",
            "standard_version": "IEC 61850 Ed2",
            "ied": {"name": "GOOSE_IED"},
            "logical_devices": [{"inst": "LD0"}],
            "profiles": ["generic-goose-publisher", "generic-reporting"],
        }
    )
    root = ET.fromstring(service.generate_scl(result["project"]["id"])["xml"])
    ns = {"scl": "http://www.iec.ch/61850/2003/SCL"}
    assert root.find(".//scl:Services/scl:GOOSE", ns).attrib["max"] == "32"
    assert root.find(".//scl:Services/scl:ConfReportControl", ns).attrib["max"] == "100"
    assert root.find(".//scl:LN[@lnClass='LPHD']", ns) is not None
