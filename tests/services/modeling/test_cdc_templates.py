"""CDC q/t/dU assistant and semantic validation tests."""

import xml.etree.ElementTree as ET

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.data.model  # noqa: F401
from src.data.model.base import Base
from src.modeling.service import Iec61850ModelingService


@pytest.fixture
def service() -> Iec61850ModelingService:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return Iec61850ModelingService(sessionmaker(engine, expire_on_commit=False))


def _project(service: Iec61850ModelingService) -> dict:
    return service.create_project(
        {
            "name": "CDC Template",
            "code": "CDC_TEMPLATE",
            "file_type": "ICD",
            "standard_version": "IEC 61850 Ed2.1",
            "ied": {"name": "CDC_IED"},
            "logical_devices": [{"inst": "LD0"}],
        }
    )


def _flatten(nodes: list[dict]) -> list[dict]:
    return [item for node in nodes for item in [node, *_flatten(node.get("children", []))]]


def _create_do_type(service: Iec61850ModelingService, *, cdc: str) -> tuple[str, str]:
    project = _project(service)
    project_id = project["project"]["id"]
    templates = next(node for node in _flatten(project["tree"]) if node["kind"] == "DATA_TYPE_TEMPLATES")
    do_type = service.create_node(
        project_id,
        {
            "parent_id": templates["id"],
            "kind": "DO_TYPE",
            "name": f"{cdc}_Type",
            "attributes": {"id": f"{cdc}_Type", "cdc": cdc},
        },
    )
    return project_id, do_type["id"]


def test_common_template_infers_mx_and_is_idempotent(service: Iec61850ModelingService):
    project_id, do_type_id = _create_do_type(service, cdc="MV")
    service.create_node(
        project_id,
        {
            "parent_id": do_type_id,
            "kind": "DA_DEF",
            "name": "mag",
            "attributes": {"bType": "FLOAT32", "fc": "MX", "dchg": True},
        },
    )

    first = service.apply_cdc_template(project_id, do_type_id, "common-quality-time-description")
    second = service.apply_cdc_template(project_id, do_type_id, "common-quality-time-description")

    assert first["primary_fc"] == "MX"
    assert {item["name"] for item in first["created"]} == {"q", "t", "dU"}
    assert second["changed"] is False
    assert second["preserved"] == ["dU", "q", "t"]
    root = ET.fromstring(service.generate_scl(project_id)["xml"])
    namespace = {"scl": "http://www.iec.ch/61850/2003/SCL"}
    attributes = {
        item.attrib["name"]: item.attrib for item in root.findall(".//scl:DOType[@id='MV_Type']/scl:DA", namespace)
    }
    assert attributes["q"]["bType"] == "Quality"
    assert attributes["q"]["fc"] == "MX"
    assert attributes["t"]["bType"] == "Timestamp"
    assert attributes["dU"] == {"name": "dU", "bType": "Unicode255", "fc": "DC"}


def test_sps_full_template_creates_main_and_common_attributes(service: Iec61850ModelingService):
    project_id, do_type_id = _create_do_type(service, cdc="SPS")

    result = service.apply_cdc_template(project_id, do_type_id, "sps")

    assert result["conflicts"] == []
    assert {item["name"] for item in result["created"]} == {"stVal", "q", "t", "dU"}
    assert service.validate_project(project_id)["passed"] is True


def test_mv_template_creates_analogue_value_dependency(service: Iec61850ModelingService):
    project_id, do_type_id = _create_do_type(service, cdc="MV")

    result = service.apply_cdc_template(project_id, do_type_id, "mv")
    nodes = _flatten(service.get_tree(project_id))

    assert any(item == {"kind": "DA_TYPE", "name": "MV_Type_AnalogueValue"} for item in result["created"])
    analogue = next(node for node in nodes if node["kind"] == "DA_TYPE" and node["name"] == "MV_Type_AnalogueValue")
    assert {child["name"] for child in analogue["children"]} == {"f", "i"}
    assert service.validate_project(project_id)["passed"] is True


def test_existing_incompatible_q_is_reported_and_not_overwritten(service: Iec61850ModelingService):
    project_id, do_type_id = _create_do_type(service, cdc="SPS")
    q = service.create_node(
        project_id,
        {
            "parent_id": do_type_id,
            "kind": "DA_DEF",
            "name": "q",
            "attributes": {"bType": "BOOLEAN", "fc": "ST"},
        },
    )

    result = service.apply_cdc_template(project_id, do_type_id, "common-quality-time-description")

    assert result["conflicts"][0]["name"] == "q"
    assert service.get_node(project_id, q["id"])["attributes"]["bType"] == "BOOLEAN"
    validation = service.validate_project(project_id)
    assert any(issue["rule_code"] == "CDC_Q_BTYPE_INVALID" for issue in validation["issues"])


def test_template_catalog_is_declarative_and_exposed(service: Iec61850ModelingService):
    templates = {item["id"]: item for item in service.list_cdc_templates()}

    assert {"common-quality-time-description", "sps", "dps", "ins", "mv"} <= templates.keys()
    assert [item["name"] for item in templates["sps"]["attributes"]] == ["stVal", "q", "t", "dU"]
