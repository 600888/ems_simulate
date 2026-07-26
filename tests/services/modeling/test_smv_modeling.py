"""SampledValueControl and Communication/SMV modeling regressions."""

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


def _flatten(nodes: list[dict]) -> list[dict]:
    return [item for node in nodes for item in [node, *_flatten(node.get("children", []))]]


def _create_smv_project(service: Iec61850ModelingService) -> tuple[str, list[dict]]:
    result = service.create_project(
        {
            "name": "Generic SMV",
            "code": "GENERIC_SMV",
            "file_type": "ICD",
            "standard_version": "IEC 61850 Ed2.1",
            "profiles": ["generic-smv-publisher"],
            "ied": {"name": "MU_IED"},
            "logical_devices": [{"inst": "MU"}],
        }
    )
    return result["project"]["id"], _flatten(result["tree"])


def _add_dataset_and_sampled_value_control(
    service: Iec61850ModelingService,
    project_id: str,
    nodes: list[dict],
    *,
    include_options: bool = True,
) -> dict:
    templates = next(node for node in nodes if node["kind"] == "DATA_TYPE_TEMPLATES")
    lphd_type = next(
        node for node in nodes if node["kind"] == "LNODE_TYPE" and node["attributes"].get("lnClass") == "LPHD"
    )
    do_type = service.create_node(
        project_id,
        {
            "parent_id": templates["id"],
            "kind": "DO_TYPE",
            "name": "SampleType",
            "attributes": {"id": "SampleType", "cdc": "SAV"},
        },
    )
    service.create_node(
        project_id,
        {
            "parent_id": do_type["id"],
            "kind": "DA_DEF",
            "name": "instMag",
            "attributes": {"bType": "FLOAT32", "fc": "MX", "dchg": True},
        },
    )
    service.create_node(
        project_id,
        {
            "parent_id": lphd_type["id"],
            "kind": "DO_DEF",
            "name": "Sample",
            "attributes": {"type": "SampleType"},
        },
    )
    ln0 = next(node for node in nodes if node["kind"] == "LN0")
    dataset = service.create_node(
        project_id,
        {
            "parent_id": ln0["id"],
            "kind": "DATASET",
            "name": "dsSampledValues",
            "attributes": {},
        },
    )
    service.create_node(
        project_id,
        {
            "parent_id": dataset["id"],
            "kind": "FCDA",
            "name": "LPHD1.Sample.instMag",
            "attributes": {
                "ldInst": "MU",
                "prefix": "",
                "lnClass": "LPHD",
                "lnInst": "1",
                "doName": "Sample",
                "daName": "instMag",
                "fc": "MX",
            },
        },
    )
    control = service.create_node(
        project_id,
        {
            "parent_id": ln0["id"],
            "kind": "SAMPLED_VALUE_CONTROL",
            "name": "MSVCB01",
            "attributes": {
                "smvID": "MU_IED_MU01",
                "datSet": "dsSampledValues",
                "confRev": 1,
                "smpRate": 4000,
                "nofASDU": 1,
                "multicast": True,
                "securityEnable": "None",
            },
        },
    )
    if include_options:
        service.create_node(
            project_id,
            {
                "parent_id": control["id"],
                "kind": "SMV_OPTS",
                "name": "SmvOpts",
                "attributes": {
                    "refreshTime": False,
                    "sampleSynchronized": True,
                    "sampleRate": True,
                    "dataSet": True,
                    "security": False,
                    "timestamp": False,
                },
            },
        )
    return control


def _add_smv_communication_binding(
    service: Iec61850ModelingService,
    project_id: str,
    nodes: list[dict],
    *,
    cb_name: str = "MSVCB01",
) -> dict:
    connected_ap = next(node for node in nodes if node["kind"] == "CONNECTED_AP")
    binding = service.create_node(
        project_id,
        {
            "parent_id": connected_ap["id"],
            "kind": "SMV",
            "name": "SMV_MU_MSVCB01",
            "attributes": {"ldInst": "MU", "cbName": cb_name},
        },
    )
    address = service.create_node(
        project_id,
        {
            "parent_id": binding["id"],
            "kind": "ADDRESS",
            "name": "Address",
            "attributes": {},
        },
    )
    for index, (parameter_type, value) in enumerate(
        (
            ("MAC-Address", "01-0C-CD-04-00-01"),
            ("APPID", "4001"),
            ("VLAN-PRIORITY", "4"),
            ("VLAN-ID", "001"),
        )
    ):
        service.create_node(
            project_id,
            {
                "parent_id": address["id"],
                "kind": "P",
                "name": f"{parameter_type}_{index}",
                "attributes": {"type": parameter_type, "value": value},
            },
        )
    return binding


def test_smv_profile_exposes_capabilities_and_serializes_control(service: Iec61850ModelingService):
    project_id, nodes = _create_smv_project(service)
    control = _add_dataset_and_sampled_value_control(service, project_id, nodes)
    _add_smv_communication_binding(service, project_id, nodes)

    validation = service.validate_project(project_id)
    root = ET.fromstring(service.generate_scl(project_id)["xml"])
    namespace = {"scl": "http://www.iec.ch/61850/2003/SCL"}
    serialized = root.find(".//scl:SampledValueControl", namespace)

    assert validation["passed"] is True
    assert serialized is not None
    assert serialized.attrib["smvID"] == "MU_IED_MU01"
    assert serialized.attrib["datSet"] == "dsSampledValues"
    assert serialized.find("scl:SmvOpts", namespace).attrib["sampleSynchronized"] == "true"
    assert root.find(".//scl:Communication//scl:SMV", namespace).attrib["cbName"] == "MSVCB01"
    schema = service.get_node(project_id, control["id"])["schema"]
    dataset_field = next(field for field in schema["fields"] if field["key"] == "datSet")
    assert dataset_field["options"] == ["dsSampledValues"]


def test_sampled_value_control_requires_smv_options(service: Iec61850ModelingService):
    project_id, nodes = _create_smv_project(service)
    _add_dataset_and_sampled_value_control(service, project_id, nodes, include_options=False)

    validation = service.validate_project(project_id)

    assert any(issue["rule_code"] == "SAMPLED_VALUE_CONTROL_SMV_OPTS_REQUIRED" for issue in validation["issues"])
    assert validation["passed"] is False


def test_sampled_value_control_round_trips_through_importer(service: Iec61850ModelingService):
    project_id, nodes = _create_smv_project(service)
    _add_dataset_and_sampled_value_control(service, project_id, nodes)
    artifact = service.generate_scl(project_id)

    preview = service.preview_import(artifact["xml"].encode("utf-8"), filename=artifact["filename"])

    assert preview["summary"]["by_kind"]["SAMPLED_VALUE_CONTROL"] == 1
    assert preview["summary"]["by_kind"]["SMV_OPTS"] == 1


def test_smv_communication_binding_must_resolve_control_block(service: Iec61850ModelingService):
    project_id, nodes = _create_smv_project(service)
    _add_dataset_and_sampled_value_control(service, project_id, nodes)
    _add_smv_communication_binding(service, project_id, nodes, cb_name="MissingSVCB")

    validation = service.validate_project(project_id)

    assert any(issue["rule_code"] == "COMMUNICATION_CONTROL_BLOCK_MISSING" for issue in validation["issues"])
