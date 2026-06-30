"""Regression tests for online discovery of structured data attributes."""

from types import SimpleNamespace

import pytest
import xmltodict

from src.proto.iec61850.model import discovery as discovery_module
from src.proto.iec61850.model.discovery import ModelDiscoveryService
from src.proto.iec61850.model.ied_model import DataSetRef, IedModel, LDModel, LNModel, RCBRef
from src.proto.iec61850.plugins.model_exporter.exporters.icd import IcdExporter


def test_set_mag_integer_child_is_discovered_and_registered(monkeypatch):
    """setMag is a value-bearing struct and must not be filtered as metadata."""

    directories = {
        "LD0/CTRL1.CtrlBlockPower": ["setMag"],
        "LD0/CTRL1.CtrlBlockPower.setMag": ["i"],
    }
    fake_iec61850 = SimpleNamespace(
        IED_ERROR_OK=0,
        IedConnection_getLogicalNodeDirectory=lambda _conn, _ref, _acsi: (["CtrlBlockPower"], 0),
        IedConnection_getDataDirectory=lambda _conn, ref: (directories[ref], 0),
    )
    monkeypatch.setattr(discovery_module, "iec61850", fake_iec61850, raising=False)
    monkeypatch.setattr(discovery_module, "get_list_from_linked_list", list)

    service = ModelDiscoveryService()
    discovered_do = service._discover_data_objects(
        object(),
        "LD0",
        "LD0/CTRL1",
        "CTRL1",
        10,
    )[0]
    das = discovered_do.das

    assert discovered_do.cdc == "ASG"
    assert discovered_do.frame_type == 3

    set_mag = next(da for da in das if da.name == "setMag")
    assert set_mag.path == "setMag.i"
    assert set_mag.fc == "SP"
    assert set_mag.iec_type == "integer"
    assert [(child.name, child.path) for child in set_mag.sub_das] == [("i", "setMag.i")]

    model = IedModel(
        lds=(
            LDModel(
                name="LD0",
                lns=(
                    LNModel(
                        name="CTRL1",
                        ln_class="CTRL",
                        ref="LD0/CTRL1",
                        dos=(discovered_do,),
                    ),
                ),
            ),
        )
    )
    point = model.point_refs["LD0/CTRL1.CtrlBlockPower.setMag.i"]
    assert point["ref"] == "LD0/CTRL1.CtrlBlockPower.setMag.i"
    assert point["fc"] == "SP"
    assert point["iec_type"] == "integer"
    assert point["frame_type"] == 3


def test_set_mag_report_model_exports_resolvable_fcda(tmp_path):
    """The report FCDA, DOType and DAType must describe the same SP leaf."""

    set_mag = discovery_module.DARef(
        name="setMag",
        path="setMag.i",
        fc="SP",
        iec_type="integer",
        sub_das=(discovery_module.DARef(name="i", path="setMag.i", fc="SP", iec_type="integer"),),
    )
    ctrl_do = discovery_module.DORef(
        name="CtrlBlockPower",
        ref="LD0/CTRL1.CtrlBlockPower",
        cdc="ASG",
        frame_type=3,
        das=(set_mag,),
    )
    dataset = DataSetRef(
        name="dsSystemCtrlMeas",
        ref="LD0/LLN0.dsSystemCtrlMeas",
        members=({"ref": "LD0/CTRL1.CtrlBlockPower.setMag.i", "fc": "SP"},),
    )
    report = RCBRef(
        name="rpSystemCtrlMeas01",
        ref="LD0/LLN0.rpSystemCtrlMeas01",
        rcb_type="URCB",
        dat_set="dsSystemCtrlMeas",
        intg_pd=300000,
    )
    model = IedModel(
        host="127.0.0.1",
        lds=(
            LDModel(
                name="LD0",
                lns=(
                    LNModel(
                        name="LLN0",
                        ln_class="LLN0",
                        ref="LD0/LLN0",
                        datasets=(dataset,),
                        rcb_list=(report,),
                    ),
                    LNModel(
                        name="CTRL1",
                        ln_class="CTRL",
                        ref="LD0/CTRL1",
                        dos=(ctrl_do,),
                    ),
                ),
            ),
        ),
    )

    output = tmp_path / "set_mag_report.icd"
    IcdExporter().export(model, str(output), ied_name="TESTIED")
    scl = xmltodict.parse(output.read_text(encoding="utf-8"))["SCL"]

    ldevice = scl["IED"]["AccessPoint"]["Server"]["LDevice"]
    ln0 = ldevice["LN0"]
    fcda = ln0["DataSet"]["FCDA"]
    report_control = ln0["ReportControl"]
    assert fcda["@doName"] == "CtrlBlockPower"
    assert fcda["@daName"] == "setMag.i"
    assert fcda["@fc"] == "SP"
    assert report_control["@datSet"] == "dsSystemCtrlMeas"

    templates = scl["DataTypeTemplates"]
    lnode_types = templates["LNodeType"]
    if isinstance(lnode_types, dict):
        lnode_types = [lnode_types]
    ctrl_lnode_type = next(item for item in lnode_types if item["@lnClass"] == "CTRL")
    do_entry = ctrl_lnode_type["DO"]
    if isinstance(do_entry, list):
        do_entry = next(item for item in do_entry if item["@name"] == "CtrlBlockPower")

    do_types = templates["DOType"]
    if isinstance(do_types, dict):
        do_types = [do_types]
    do_type = next(item for item in do_types if item["@id"] == do_entry["@type"])
    assert do_type["@cdc"] == "ASG"
    da_entry = do_type["DA"]
    if isinstance(da_entry, list):
        da_entry = next(item for item in da_entry if item["@name"] == "setMag")
    assert da_entry["@fc"] == "SP"
    assert da_entry["@bType"] == "Struct"

    da_types = templates["DAType"]
    if isinstance(da_types, dict):
        da_types = [da_types]
    da_type = next(item for item in da_types if item["@id"] == da_entry["@type"])
    assert da_type["BDA"] == {"@name": "i", "@bType": "INT32"}


def test_export_rejects_report_fcda_missing_from_type_templates(tmp_path):
    """Never write a report data set that points at a missing DA/BDA."""

    broken_do = discovery_module.DORef(
        name="CtrlBlockPower",
        ref="LD0/CTRL1.CtrlBlockPower",
        cdc="ASG",
        frame_type=3,
        das=(discovery_module.DARef(name="q", path="q", fc="MX", iec_type="integer"),),
    )
    dataset = DataSetRef(
        name="dsSystemCtrlMeas",
        ref="LD0/LLN0.dsSystemCtrlMeas",
        members=({"ref": "LD0/CTRL1.CtrlBlockPower.setMag.i", "fc": "SP"},),
    )
    model = IedModel(
        lds=(
            LDModel(
                name="LD0",
                lns=(
                    LNModel(
                        name="LLN0",
                        ln_class="LLN0",
                        ref="LD0/LLN0",
                        datasets=(dataset,),
                        rcb_list=(
                            RCBRef(
                                name="rpSystemCtrlMeas01",
                                ref="LD0/LLN0.rpSystemCtrlMeas01",
                                rcb_type="URCB",
                                dat_set="dsSystemCtrlMeas",
                            ),
                        ),
                    ),
                    LNModel(
                        name="CTRL1",
                        ln_class="CTRL",
                        ref="LD0/CTRL1",
                        dos=(broken_do,),
                    ),
                ),
            ),
        )
    )
    output = tmp_path / "broken_set_mag_report.icd"

    with pytest.raises(ValueError, match=r"missing DA .*setMag\.i"):
        IcdExporter().export(model, str(output), ied_name="TESTIED")
    assert not output.exists()
