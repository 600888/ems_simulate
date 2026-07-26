"""Approved XSD discovery and publish policy regressions."""

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


def _project(service: Iec61850ModelingService) -> str:
    result = service.create_project(
        {
            "name": "XSD Policy",
            "code": "XSD_POLICY",
            "file_type": "ICD",
            "standard_version": "IEC 61850 Ed2.1",
            "ied": {"name": "IED_XSD"},
            "logical_devices": [{"inst": "LD0"}],
        }
    )
    return result["project"]["id"]


def test_missing_xsd_is_visible_without_false_compliance_claim(service: Iec61850ModelingService):
    validation = service.validate_project(_project(service))

    assert validation["passed"] is True
    assert validation["interoperability"]["xsd"]["status"] == "UNAVAILABLE"
    assert any(issue["rule_code"] == "XSD_VALIDATION_UNAVAILABLE" for issue in validation["issues"])


def test_publish_can_require_approved_xsd_by_environment(
    service: Iec61850ModelingService,
    monkeypatch: pytest.MonkeyPatch,
):
    project_id = _project(service)
    monkeypatch.setenv("EMS_REQUIRE_SCL_XSD", "true")
    monkeypatch.setenv("EMS_SCL_XSD_PATH", "missing/approved/SCL.xsd")

    with pytest.raises(ValidationError, match="官方 SCL XSD"):
        service.publish_project(project_id)
