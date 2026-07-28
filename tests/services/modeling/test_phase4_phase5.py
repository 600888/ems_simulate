"""Phase 4/5 artifact, interoperability, and bounded-job acceptance tests."""

from __future__ import annotations

from hashlib import sha256
import io
import json
from pathlib import Path
import shutil
import subprocess
from threading import Event
import time
import tracemalloc
import zipfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.data.model  # noqa: F401
from src.data.model.base import Base
from src.modeling.interoperability import validate_interoperability
from src.modeling.jobs import ModelingJobManager
from src.modeling.scl_importer import SclModelImporter
from src.modeling.service import Iec61850ModelingService
from src.web.api.exceptions import ValidationError


@pytest.fixture
def service() -> Iec61850ModelingService:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return Iec61850ModelingService(sessionmaker(engine, expire_on_commit=False))


def _create_project(service: Iec61850ModelingService, *, file_type: str = "ICD") -> dict:
    return service.create_project(
        {
            "name": f"Phase 4 {file_type}",
            "code": f"PHASE4_{file_type}",
            "file_type": file_type,
            "standard_version": "IEC 61850 Ed2.1",
            "ied": {"name": "IED_PHASE4", "manufacturer": "Test", "type": "Protection"},
            "access_point_name": "AP1",
            "logical_devices": [{"inst": "LD0", "desc": "Default"}],
        }
    )


def test_file_variant_scope_is_explicit(service: Iec61850ModelingService):
    variants = {item["file_type"]: item for item in service.list_file_variants()}

    assert variants["ICD"]["publishable"] is True
    assert variants["CID"]["publishable"] is True
    assert variants["SCD"]["status"] == "PREVIEW_ONLY"
    assert variants["IID"]["status"] == "NOT_SUPPORTED"
    assert variants["SED"]["status"] == "NOT_SUPPORTED"


def test_bundle_is_deterministic_traceable_and_contains_three_artifacts(service: Iec61850ModelingService):
    project = _create_project(service)["project"]

    first = service.generate_artifact_bundle(project["id"])
    second = service.generate_artifact_bundle(project["id"])

    assert first["content"] == second["content"]
    assert {item["kind"] for item in first["artifacts"]} == {"SCL", "CFG", "CSV"}
    with zipfile.ZipFile(io.BytesIO(first["content"])) as archive:
        bundle_root = f"PHASE4_ICD-r{project['revision']}-artifacts"
        assert set(archive.namelist()) == {
            f"{bundle_root}/PHASE4_ICD.icd",
            f"{bundle_root}/PHASE4_ICD.cfg",
            f"{bundle_root}/PHASE4_ICD.csv",
            f"{bundle_root}/manifest.json",
        }
        manifest = json.loads(archive.read(f"{bundle_root}/manifest.json"))
        for artifact in manifest["artifacts"]:
            assert sha256(archive.read(f"{bundle_root}/{artifact['filename']}")).hexdigest() == artifact["sha256"]
    assert service.get_project(project["id"])["revision"] == project["revision"]


def test_imported_sample_compiles_runtime_points_without_changing_model(service: Iec61850ModelingService):
    sample = Path("tmp/testicd/simpleIO.icd")
    if not sample.is_file():
        pytest.skip("local SCL acceptance sample is not available")
    imported = service.import_scl(sample.read_bytes(), filename=sample.name, code="PHASE4_SIMPLE")
    project = imported["project"]

    bundle = service.generate_artifact_bundle(project["id"])

    with zipfile.ZipFile(io.BytesIO(bundle["content"])) as archive:
        bundle_root = f"PHASE4_SIMPLE-r{project['revision']}-artifacts"
        csv_lines = archive.read(f"{bundle_root}/PHASE4_SIMPLE.csv").decode("utf-8-sig").splitlines()
        cfg = archive.read(f"{bundle_root}/PHASE4_SIMPLE.cfg").decode("utf-8")
    assert len(csv_lines) > 1
    assert "DA(" in cfg
    assert service.get_project(project["id"])["revision"] == project["revision"]


def test_cid_generation_uses_cid_contract_not_extension_replacement(service: Iec61850ModelingService):
    project = _create_project(service, file_type="CID")["project"]

    artifact = service.generate_scl(project["id"])
    validation = service.validate_project(project["id"])

    assert artifact["filename"] == "PHASE4_CID.cid"
    assert validation["passed"] is True
    assert not any(issue["rule_code"].startswith("CID_") for issue in validation["issues"])


def test_scd_is_preview_only_and_cannot_be_published(service: Iec61850ModelingService):
    project = _create_project(service, file_type="SCD")["project"]

    assert service.generate_scl(project["id"])["filename"] == "PHASE4_SCD.scd"
    with pytest.raises(ValidationError, match="文件变体"):
        service.publish_project(project["id"])


def test_generated_scl_passes_both_application_parser_paths(service: Iec61850ModelingService):
    project = _create_project(service)["project"]
    artifact = service.generate_scl(project["id"])

    result = validate_interoperability(artifact["xml"], filename=artifact["filename"])

    assert result["passed"] is True
    assert {engine["engine"] for engine in result["engines"]} == {
        "python-elementtree",
        "modeling-import-adapter",
        "runtime-scl-parser",
    }
    assert result["xsd"]["status"] in {"UNAVAILABLE", "PASSED"}


def test_generated_icd_is_accepted_by_independent_libiec61850_tool(service: Iec61850ModelingService, tmp_path: Path):
    java = shutil.which("java")
    generator = Path("tmp/testicd/genconfig.jar").resolve()
    if not java or not generator.is_file():
        pytest.skip("libiec61850 Java interoperability tool is not available")
    project = _create_project(service)["project"]
    artifact = service.generate_scl(project["id"])
    source = tmp_path / artifact["filename"]
    target = tmp_path / "generated.cfg"
    source.write_text(artifact["xml"], encoding="utf-8")

    completed = subprocess.run(
        [java, "-jar", str(generator), str(source), str(target)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert target.is_file()
    assert "MODEL(" in target.read_text(encoding="utf-8")


def test_job_progress_is_monotonic_bounded_and_running_job_can_be_cancelled():
    manager = ModelingJobManager(max_workers=1, max_pending_jobs=1)
    started = Event()
    release = Event()

    def handler(progress, cancel_check):
        progress("parse", 1, 4, "Parsing")
        started.set()
        release.wait(timeout=2)
        cancel_check()
        return {"unexpected": True}

    try:
        job = manager.submit("TEST", handler, input_size=1024)
        assert started.wait(timeout=2)
        running = manager.get(job["id"])
        assert running and running["progress"] == 25
        with pytest.raises(RuntimeError, match="queue is full"):
            manager.submit("OVER_CAPACITY", handler)
        manager.cancel(job["id"])
        release.set()
        deadline = time.monotonic() + 2
        final = manager.get(job["id"])
        while final and final["status"] not in {"CANCELLED", "FAILED", "COMPLETED"} and time.monotonic() < deadline:
            time.sleep(0.01)
            final = manager.get(job["id"])
        assert final and final["status"] == "CANCELLED"
        assert final["progress"] >= running["progress"]
    finally:
        manager.shutdown()


def test_importer_honors_cooperative_cancellation():
    content = (
        '<SCL xmlns="http://www.iec.ch/61850/2003/SCL"><Header id="CANCEL"/>' + '<Private type="x"/>' * 1100 + "</SCL>"
    ).encode()
    checks = 0

    def cancel_check():
        nonlocal checks
        checks += 1
        if checks >= 2:
            raise RuntimeError("cancelled")

    with pytest.raises(RuntimeError, match="cancelled"):
        SclModelImporter().parse(content, cancel_check=cancel_check)


def test_importer_uses_standard_fcda_reference_as_node_name():
    content = b"""
    <SCL xmlns="http://www.iec.ch/61850/2003/SCL">
      <Header id="FCDA_NAME"/>
      <IED name="PCS001">
        <AccessPoint name="S1">
          <Server>
            <LDevice inst="CTRL">
              <LN0 lnClass="LLN0" inst="" lnType="LLN0_TYPE">
                <DataSet name="dsAlarm">
                  <FCDA ldInst="CTRL" prefix="kr" lnClass="GGIO"
                        lnInst="1" doName="Alm1" fc="ST"/>
                </DataSet>
              </LN0>
              <LN prefix="kr" lnClass="GGIO" inst="1" lnType="GGIO_TYPE"/>
            </LDevice>
          </Server>
        </AccessPoint>
      </IED>
    </SCL>
    """

    result = SclModelImporter().parse(content, filename="fcda.icd")
    fcda = next(node for node in result.nodes if node["kind"] == "FCDA")

    assert fcda["name"] == "krGGIO1.Alm1"
    assert fcda["attributes"]["fc"] == "ST"


def test_importer_exposes_inherited_quality_and_timestamp_without_rewriting_scl(
    service: Iec61850ModelingService,
):
    content = b"""
    <SCL xmlns="http://www.iec.ch/61850/2003/SCL">
      <Header id="INHERITED_DA"/>
      <IED name="BAMS">
        <AccessPoint name="S1"><Server><LDevice inst="CTMP01">
          <LN lnClass="MMCL" inst="1" lnType="MMCL_TYPE">
            <DOI name="Temp001"><DAI name="dU"><Val>temperature</Val></DAI></DOI>
          </LN>
        </LDevice></Server></AccessPoint>
      </IED>
      <DataTypeTemplates>
        <LNodeType id="MMCL_TYPE" lnClass="MMCL">
          <DO name="Temp001" type="TEMP_TYPE"/>
        </LNodeType>
        <DOType id="TEMP_TYPE" cdc="MV">
          <DA name="mag" fc="MX" bType="FLOAT32"/>
          <DA name="q" fc="MX" bType="Quality"/>
          <DA name="t" fc="MX" bType="Timestamp"/>
          <DA name="dU" fc="DC" bType="Unicode255"/>
        </DOType>
      </DataTypeTemplates>
    </SCL>
    """

    parsed = SclModelImporter().parse(content, filename="bams.icd")
    doi = next(node for node in parsed.nodes if node["kind"] == "DOI")
    children = [node for node in parsed.nodes if node["parent_id"] == doi["id"] and node["kind"] == "DAI"]

    assert {node["name"] for node in children} == {"dU", "q", "t"}
    assert all(node["attributes"].get("_templateInherited") is True for node in children if node["name"] in {"q", "t"})

    imported = service.import_scl(
        content,
        filename="bams.icd",
        code="INHERITED_DA",
    )
    generated = service.generate_scl(imported["project"]["id"])["xml"]
    doi_xml = generated.split('<DOI name="Temp001">', 1)[1].split("</DOI>", 1)[0]
    assert '<DAI name="dU">' in doi_xml
    assert '<DAI name="q"' not in doi_xml
    assert '<DAI name="t"' not in doi_xml


def test_large_sample_has_bounded_regression_budget():
    sample = Path("tmp/testicd/TEMPLATE_114.icd")
    if not sample.is_file():
        pytest.skip("large local acceptance sample is not available")
    content = sample.read_bytes()
    tracemalloc.start()
    started = time.perf_counter()
    result = SclModelImporter().parse(content, filename=sample.name)
    elapsed = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert result.summary["node_count"] > 0
    assert elapsed < 15
    assert peak < 256 * 1024 * 1024
