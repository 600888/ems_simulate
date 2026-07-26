"""Cross-layer IEC 61850 modeling validation regressions."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.data.model  # noqa: F401
from src.data.model.base import Base
from src.modeling.service import Iec61850ModelingService
from src.web.api.exceptions import ValidationError


@pytest.fixture
def service() -> Iec61850ModelingService:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return Iec61850ModelingService(sessionmaker(engine, expire_on_commit=False))


def _flatten(nodes: list[dict]) -> list[dict]:
    return [item for node in nodes for item in [node, *_flatten(node.get("children", []))]]


def _project(service: Iec61850ModelingService) -> tuple[str, list[dict]]:
    result = service.create_project(
        {
            "name": "Semantic Validation",
            "code": "SEMANTIC_VALIDATION",
            "file_type": "ICD",
            "standard_version": "IEC 61850 Ed2.1",
            "ied": {"name": "IED1"},
            "logical_devices": [{"inst": "LD0"}],
        }
    )
    return result["project"]["id"], _flatten(result["tree"])


def _add_lphd_data_object(service: Iec61850ModelingService, project_id: str, nodes: list[dict]) -> None:
    templates = next(node for node in nodes if node["kind"] == "DATA_TYPE_TEMPLATES")
    lphd_type = next(
        node for node in nodes if node["kind"] == "LNODE_TYPE" and node["attributes"].get("lnClass") == "LPHD"
    )
    do_type = service.create_node(
        project_id,
        {
            "parent_id": templates["id"],
            "kind": "DO_TYPE",
            "name": "LPHD_Hz_Type",
            "attributes": {"id": "LPHD_Hz_Type", "cdc": "MV"},
        },
    )
    service.create_node(
        project_id,
        {
            "parent_id": do_type["id"],
            "kind": "DA_DEF",
            "name": "mag",
            "attributes": {"bType": "FLOAT32", "fc": "MX", "dchg": True},
        },
    )
    service.create_node(
        project_id,
        {
            "parent_id": lphd_type["id"],
            "kind": "DO_DEF",
            "name": "Hz",
            "attributes": {"type": "LPHD_Hz_Type"},
        },
    )


def _add_fcda(
    service: Iec61850ModelingService,
    project_id: str,
    nodes: list[dict],
    *,
    do_name: str = "Hz",
    da_name: str = "mag",
    fc: str = "MX",
) -> dict:
    ln0 = next(node for node in nodes if node["kind"] == "LN0")
    dataset = service.create_node(
        project_id,
        {
            "parent_id": ln0["id"],
            "kind": "DATASET",
            "name": "dsMeasurements",
            "attributes": {},
        },
    )
    return service.create_node(
        project_id,
        {
            "parent_id": dataset["id"],
            "kind": "FCDA",
            "name": "LPHD1.Hz.mag",
            "attributes": {
                "ldInst": "LD0",
                "prefix": "",
                "lnClass": "LPHD",
                "lnInst": "1",
                "doName": do_name,
                "daName": da_name,
                "fc": fc,
            },
        },
    )


def test_fcda_resolves_instance_type_and_functional_constraint(service: Iec61850ModelingService):
    project_id, nodes = _project(service)
    _add_lphd_data_object(service, project_id, nodes)
    _add_fcda(service, project_id, nodes)

    validation = service.validate_project(project_id)

    assert not any(issue["rule_code"].startswith("FCDA_") for issue in validation["issues"])


@pytest.mark.parametrize(
    ("do_name", "da_name", "fc", "expected_code"),
    [
        ("Missing", "mag", "MX", "FCDA_DATA_OBJECT_MISSING"),
        ("Hz", "missing", "MX", "FCDA_DATA_ATTRIBUTE_MISSING"),
        ("Hz", "mag", "ST", "FCDA_FUNCTIONAL_CONSTRAINT_MISMATCH"),
    ],
)
def test_fcda_rejects_unresolved_or_inconsistent_targets(
    service: Iec61850ModelingService,
    do_name: str,
    da_name: str,
    fc: str,
    expected_code: str,
):
    project_id, nodes = _project(service)
    _add_lphd_data_object(service, project_id, nodes)
    _add_fcda(service, project_id, nodes, do_name=do_name, da_name=da_name, fc=fc)

    validation = service.validate_project(project_id)

    assert any(issue["rule_code"] == expected_code for issue in validation["issues"])
    assert validation["passed"] is False


def test_logical_node_class_must_match_referenced_lnode_type(service: Iec61850ModelingService):
    project_id, nodes = _project(service)
    lphd_type = next(
        node for node in nodes if node["kind"] == "LNODE_TYPE" and node["attributes"].get("lnClass") == "LPHD"
    )
    service.update_node(
        project_id,
        lphd_type["id"],
        {
            "attributes": {**lphd_type["attributes"], "lnClass": "MMXU"},
            "expected_revision": lphd_type["revision"],
        },
    )

    validation = service.validate_project(project_id)

    assert any(issue["rule_code"] == "LNODE_TYPE_CLASS_MISMATCH" for issue in validation["issues"])


def test_duplicate_type_ids_are_rejected(service: Iec61850ModelingService):
    project_id, nodes = _project(service)
    templates = next(node for node in nodes if node["kind"] == "DATA_TYPE_TEMPLATES")
    for name in ("FirstDAType", "SecondDAType"):
        service.create_node(
            project_id,
            {
                "parent_id": templates["id"],
                "kind": "DA_TYPE",
                "name": name,
                "attributes": {"id": "DuplicatedDAType"},
            },
        )

    validation = service.validate_project(project_id)

    assert any(issue["rule_code"] == "TYPE_ID_DUPLICATE" for issue in validation["issues"])


def test_gse_control_cannot_be_created_under_regular_ln(service: Iec61850ModelingService):
    project_id, nodes = _project(service)
    lphd = next(node for node in nodes if node["kind"] == "LN" and node["attributes"].get("lnClass") == "LPHD")

    with pytest.raises(ValidationError, match="不能添加"):
        service.create_node(
            project_id,
            {
                "parent_id": lphd["id"],
                "kind": "GSE_CONTROL",
                "name": "gcbInvalid",
                "attributes": {"datSet": "ds1", "appID": "gcbInvalid", "confRev": 1},
            },
        )


def test_reference_fields_offer_contextual_model_choices(service: Iec61850ModelingService):
    project_id, nodes = _project(service)
    _add_lphd_data_object(service, project_id, nodes)
    fcda = _add_fcda(service, project_id, nodes)
    refreshed = _flatten(service.get_tree(project_id))
    lphd = next(node for node in refreshed if node["kind"] == "LN" and node["attributes"].get("lnClass") == "LPHD")

    ln_schema = service.get_node(project_id, lphd["id"])["schema"]
    fcda_schema = service.get_node(project_id, fcda["id"])["schema"]
    ln_type_field = next(field for field in ln_schema["fields"] if field["key"] == "lnType")
    do_name_field = next(field for field in fcda_schema["fields"] if field["key"] == "doName")
    da_name_field = next(field for field in fcda_schema["fields"] if field["key"] == "daName")

    assert ln_type_field["component"] == "select"
    assert ln_type_field["options"] == ["SEMANTIC_VALIDATION_LPHD"]
    assert do_name_field["options"] == ["Hz"]
    assert da_name_field["options"] == ["mag"]


def test_report_optional_children_are_not_required_for_valid_scl(service: Iec61850ModelingService):
    project_id, nodes = _project(service)
    _add_lphd_data_object(service, project_id, nodes)
    _add_fcda(service, project_id, nodes)
    services = next(node for node in nodes if node["kind"] == "SERVICES")
    ln0 = next(node for node in nodes if node["kind"] == "LN0")
    service.create_node(
        project_id,
        {
            "parent_id": services["id"],
            "kind": "SERVICE_CAPABILITY",
            "name": "ConfReportControl",
            "attributes": {"tag": "ConfReportControl", "max": 10},
        },
    )
    service.create_node(
        project_id,
        {
            "parent_id": ln0["id"],
            "kind": "REPORT_CONTROL",
            "name": "brcbMeasurements",
            "attributes": {
                "datSet": "dsMeasurements",
                "rptID": "brcbMeasurements",
                "buffered": True,
                "confRev": 1,
            },
        },
    )

    validation = service.validate_project(project_id)

    assert validation["passed"] is True
    assert not any(issue["rule_code"].startswith("REPORT_") for issue in validation["issues"])


def test_dataset_member_candidates_are_derived_from_instance_and_type_model(
    service: Iec61850ModelingService,
):
    project_id, nodes = _project(service)
    _add_lphd_data_object(service, project_id, nodes)
    ln0 = next(node for node in nodes if node["kind"] == "LN0")
    dataset = service.create_node(
        project_id,
        {
            "parent_id": ln0["id"],
            "kind": "DATASET",
            "name": "dsBatch",
            "attributes": {},
        },
    )

    discovery = service.get_dataset_member_candidates(project_id, dataset["id"])

    candidate = next(item for item in discovery["candidates"] if item["reference"] == "LD0/LPHD1.Hz.mag")
    assert candidate["fc"] == "MX"
    assert candidate["b_type"] == "FLOAT32"
    assert candidate["existing"] is False
    assert discovery["summary"] == {
        "candidate_count": 2,
        "existing_count": 0,
        "invalid_count": 0,
    }


def test_dataset_members_are_created_atomically_and_duplicates_are_skipped(
    service: Iec61850ModelingService,
):
    project_id, nodes = _project(service)
    _add_lphd_data_object(service, project_id, nodes)
    ln0 = next(node for node in nodes if node["kind"] == "LN0")
    dataset = service.create_node(
        project_id,
        {
            "parent_id": ln0["id"],
            "kind": "DATASET",
            "name": "dsBatch",
            "attributes": {},
        },
    )
    candidate_id = service.get_dataset_member_candidates(project_id, dataset["id"])["candidates"][0]["id"]

    first = service.create_dataset_members(project_id, dataset["id"], [candidate_id, candidate_id])
    second = service.create_dataset_members(project_id, dataset["id"], [candidate_id])
    refreshed = service.get_dataset_member_candidates(project_id, dataset["id"])

    assert first["created_count"] == 1
    assert first["skipped_count"] == 0
    assert second["created_count"] == 0
    assert second["skipped_count"] == 1
    assert refreshed["summary"]["existing_count"] == 1
    assert refreshed["candidates"][0]["existing"] is True
    assert refreshed["existing_members"][0]["valid"] is True


def test_invalid_dataset_member_can_be_repaired_from_current_candidates(
    service: Iec61850ModelingService,
):
    project_id, nodes = _project(service)
    _add_lphd_data_object(service, project_id, nodes)
    fcda = _add_fcda(
        service,
        project_id,
        nodes,
        do_name="Missing",
        da_name="mag",
        fc="MX",
    )
    dataset_id = fcda["parent_id"]
    discovery = service.get_dataset_member_candidates(project_id, dataset_id)
    candidate_id = discovery["candidates"][0]["id"]

    assert discovery["summary"]["invalid_count"] == 1
    assert discovery["existing_members"][0]["valid"] is False

    repaired = service.repair_dataset_member(
        project_id,
        dataset_id,
        fcda["id"],
        candidate_id,
    )
    refreshed = service.get_dataset_member_candidates(project_id, dataset_id)

    assert repaired["attributes"]["doName"] == "Hz"
    assert refreshed["summary"]["invalid_count"] == 0
    assert refreshed["existing_members"][0]["valid"] is True


def test_dataset_supports_do_level_and_da_level_fcda_members(
    service: Iec61850ModelingService,
):
    project_id, nodes = _project(service)
    _add_lphd_data_object(service, project_id, nodes)
    ln0 = next(node for node in nodes if node["kind"] == "LN0")
    dataset = service.create_node(
        project_id,
        {
            "parent_id": ln0["id"],
            "kind": "DATASET",
            "name": "dsMixedGranularity",
            "attributes": {},
        },
    )
    candidates = service.get_dataset_member_candidates(project_id, dataset["id"])["candidates"]
    do_candidate = next(
        candidate
        for candidate in candidates
        if candidate["selection_level"] == "DO" and candidate["data_object"] == "Hz"
    )
    da_candidate = next(
        candidate
        for candidate in candidates
        if candidate["selection_level"] == "DA" and candidate["data_attribute"] == "mag"
    )

    result = service.create_dataset_members(
        project_id,
        dataset["id"],
        [do_candidate["id"], da_candidate["id"]],
    )
    members = service.get_dataset_member_candidates(project_id, dataset["id"])["existing_members"]
    xml = service.generate_scl(project_id)["xml"]

    assert result["created_count"] == 2
    assert {str(member["attributes"].get("daName") or "") for member in members} == {
        "",
        "mag",
    }
    assert 'doName="Hz" fc="MX"' in xml
    assert 'doName="Hz" daName="mag" fc="MX"' in xml


def test_existing_dataset_members_can_be_reordered(
    service: Iec61850ModelingService,
):
    project_id, nodes = _project(service)
    _add_lphd_data_object(service, project_id, nodes)
    ln0 = next(node for node in nodes if node["kind"] == "LN0")
    dataset = service.create_node(
        project_id,
        {
            "parent_id": ln0["id"],
            "kind": "DATASET",
            "name": "dsReorder",
            "attributes": {},
        },
    )
    candidates = service.get_dataset_member_candidates(
        project_id,
        dataset["id"],
    )["candidates"]
    do_candidate = next(candidate for candidate in candidates if candidate["selection_level"] == "DO")
    da_candidate = next(candidate for candidate in candidates if candidate["selection_level"] == "DA")
    service.create_dataset_members(
        project_id,
        dataset["id"],
        [do_candidate["id"], da_candidate["id"]],
    )

    result = service.create_dataset_members(
        project_id,
        dataset["id"],
        [],
        [da_candidate["id"], do_candidate["id"]],
    )
    refreshed = service.get_dataset_member_candidates(
        project_id,
        dataset["id"],
    )

    assert result["created_count"] == 0
    assert result["reordered_count"] == 2
    assert [member["candidate_id"] for member in refreshed["existing_members"]] == [
        da_candidate["id"],
        do_candidate["id"],
    ]
