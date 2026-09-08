"""Regression tests for online discovery of structured data attributes."""

from types import SimpleNamespace

import pytest
import xmltodict

from src.proto.iec61850.core.reader import Iec61850Reader
from src.proto.iec61850.model import discovery as discovery_module
from src.proto.iec61850.model.discovery import ModelDiscoveryService
from src.proto.iec61850.model.ied_model import DataSetRef, DORef, IedModel, LDModel, LNModel, RCBRef
from src.proto.iec61850.plugins.model_exporter.exporters.icd import IcdExporter


@pytest.mark.parametrize("do_name", ["Mod", "Beh", "Health", "PhyHealth", "Pos"])
def test_intrinsic_enumerated_status_value_is_integer(do_name):
    da = ModelDiscoveryService._resolve_da_info("stVal", do_name, "LLN0", 1)

    assert da.fc == "ST"
    assert da.iec_type == "integer"


def test_proxy_sps_status_value_remains_boolean():
    da = ModelDiscoveryService._resolve_da_info("stVal", "Proxy", "LPHD1", 1)

    assert da.fc == "ST"
    assert da.iec_type == "boolean"


@pytest.mark.parametrize("fc", ["ST", "MX"])
def test_online_discovery_uses_directory_fc_for_quality_and_time(monkeypatch, fc):
    """状态/测量共用 q/t 名称，必须使用在线 FC，且不增加类型探测。"""
    fake_native = SimpleNamespace(
        IED_ERROR_OK=0,
        IedConnection_getDataDirectoryFC=lambda _conn, _ref: (["dU[DC]", f"q[{fc}]", "stVal[ST]", f"t[{fc}]"], 0),
    )
    monkeypatch.setattr(discovery_module, "iec61850", fake_native)
    monkeypatch.setattr(discovery_module, "get_list_from_linked_list", list)
    service = ModelDiscoveryService()
    das = service._discover_data_attributes(object(), "LD0/MMBC1.RackState", "RackState", "MMBC1", 0)

    assert {da.name: da.fc for da in das} == {"dU": "DC", "q": fc, "stVal": "ST", "t": fc}
    assert service._description_da_cache["LD0/MMBC1.RackState"] == ("dU",)


def test_online_discovery_legacy_directory_infers_status_metadata_from_main_value(monkeypatch):
    """旧绑定没有 FC 目录时，测量 LN 中的状态 DO 也应使用 ST 品质/时标。"""
    monkeypatch.setattr(
        discovery_module,
        "iec61850",
        SimpleNamespace(
            IED_ERROR_OK=0,
            IedConnection_getDataDirectory=lambda _conn, _ref: (["q", "stVal", "t"], 0),
        ),
    )
    monkeypatch.setattr(discovery_module, "get_list_from_linked_list", list)
    das = ModelDiscoveryService()._discover_data_attributes(object(), "LD0/MMBC1.RackState", "RackState", "MMBC1", 0)
    assert all(da.fc == "ST" for da in das if da.name in ("q", "stVal", "t"))


def test_wire_spec_restores_status_order_and_is_reused_per_ln_fc(monkeypatch):
    """字母序 q/stVal/t 必须恢复为服务端 stVal/q/t，两次 DO 查询只取一次 LN 规格。"""
    from src.proto.iec61850.model.ied_model import DARef

    def node(name, mms_type, *children):
        return SimpleNamespace(name=name, mms_type=mms_type, children=children)

    spec = node(
        "GGIO1", 1, *(node(name, 1, node("stVal", 4), node("q", 3), node("t", 14)) for name in ("State1", "State2"))
    )
    requests, destroyed = [], []

    def get_spec(_conn, ref, fc):
        requests.append((ref, fc))
        return spec, 0

    fake_native = SimpleNamespace(
        IED_ERROR_OK=0,
        IEC61850_FC_ST=0,
        MMS_STRUCTURE=1,
        MMS_INTEGER=4,
        MMS_BIT_STRING=3,
        MMS_UTC_TIME=14,
        IedConnection_getVariableSpecification=get_spec,
        MmsVariableSpecification_getType=lambda item: item.mms_type,
        MmsVariableSpecification_getName=lambda item: item.name,
        MmsVariableSpecification_getSize=lambda item: len(item.children),
        MmsVariableSpecification_getChildSpecificationByIndex=lambda item, index: item.children[index],
        MmsVariableSpecification_destroy=destroyed.append,
    )
    monkeypatch.setattr(discovery_module, "iec61850", fake_native)
    service = ModelDiscoveryService()
    attributes = [DARef(name=name, path=name, fc="ST") for name in ("q", "stVal", "t")]
    for name in ("State1", "State2"):
        das = service._apply_wire_layout(object(), f"LD0/GGIO1.{name}", attributes)
        assert [da.name for da in das] == ["stVal", "q", "t"]
        assert [da.mms_type for da in das] == ["MMS_INTEGER", "MMS_BIT_STRING", "MMS_UTC_TIME"]
    assert requests == [("LD0/GGIO1", 0)]
    assert destroyed == [spec]
    service.invalidate()
    assert not service._wire_layout_cache


def test_online_discovery_keeps_intrinsic_status_attributes(monkeypatch):
    directories = {
        "LD0/LLN0.Mod": ["stVal", "q", "t", "ctlModel", "Oper"],
        "LD0/LLN0.Mod.q": ["validity", "source", "test"],
        "LD0/LLN0.Mod.t": ["seconds", "fraction", "TimeAccuracy"],
        "LD0/LLN0.Mod.Oper": ["ctlVal", "ctlNum"],
    }
    fake_iec61850 = SimpleNamespace(
        IED_ERROR_OK=0,
        IedConnection_getDataDirectory=lambda _conn, ref: (directories.get(ref, []), 0),
    )
    monkeypatch.setattr(discovery_module, "iec61850", fake_iec61850, raising=False)
    monkeypatch.setattr(discovery_module, "get_list_from_linked_list", list)

    service = ModelDiscoveryService()
    monkeypatch.setattr(
        service,
        "_resolve_leaf_mms_type",
        lambda _conn, _ref, _fc, fallback: fallback,
    )
    das = service._discover_data_attributes(object(), "LD0/LLN0.Mod", "Mod", "LLN0", 1)
    by_name = {da.name: da for da in das}

    assert by_name["stVal"].fc == "ST"
    assert by_name["stVal"].iec_type == "integer"
    assert by_name["q"].fc == "ST"
    assert by_name["q"].iec_type == "bitstring"
    assert by_name["q"].path == "q"
    assert by_name["t"].fc == "ST"
    assert by_name["t"].iec_type == "timestamp"
    assert by_name["t"].path == "t"
    assert by_name["ctlModel"].fc == "CF"
    assert by_name["ctlModel"].iec_type == "integer"
    assert by_name["Oper"].iec_type == "integer"
    assert next(child for child in by_name["Oper"].sub_das if child.name == "ctlVal").iec_type == "integer"


def test_online_discovery_keeps_non_point_nameplate_attributes(monkeypatch):
    fake_iec61850 = SimpleNamespace(
        IED_ERROR_OK=0,
        IedConnection_getDataDirectory=lambda _conn, _ref: (["vendor", "swRev", "configRev"], 0),
    )
    monkeypatch.setattr(discovery_module, "iec61850", fake_iec61850, raising=False)
    monkeypatch.setattr(discovery_module, "get_list_from_linked_list", list)

    service = ModelDiscoveryService()
    monkeypatch.setattr(
        service,
        "_resolve_leaf_mms_type",
        lambda _conn, _ref, _fc, fallback: fallback,
    )
    das = service._discover_data_attributes(object(), "LD0/LLN0.NamPlt", "NamPlt", "LLN0", 1)
    by_name = {da.name: da for da in das}

    for da_name in ("vendor", "swRev", "configRev"):
        assert by_name[da_name].fc == "DC"
        assert by_name[da_name].iec_type == "string"


def test_scaled_value_config_is_cf_structure_and_not_a_business_point(monkeypatch):
    directories = {
        "LD0/GGIO1.AnIn1": ["mag", "sVC"],
        "LD0/GGIO1.AnIn1.mag": ["f"],
        "LD0/GGIO1.AnIn1.sVC": ["scaleFactor", "offset"],
    }
    fake_iec61850 = SimpleNamespace(
        IED_ERROR_OK=0,
        IedConnection_getDataDirectory=lambda _conn, ref: (directories.get(ref, []), 0),
    )
    monkeypatch.setattr(discovery_module, "iec61850", fake_iec61850, raising=False)
    monkeypatch.setattr(discovery_module, "get_list_from_linked_list", list)

    service = ModelDiscoveryService()
    monkeypatch.setattr(
        service,
        "_resolve_leaf_mms_type",
        lambda _conn, _ref, _fc, fallback: fallback,
    )
    das = service._discover_data_attributes(object(), "LD0/GGIO1.AnIn1", "AnIn1", "GGIO1", 0)
    svc = next(da for da in das if da.name == "sVC")

    assert svc.fc == "CF"
    assert svc.iec_type == "float"
    assert svc.mms_type is discovery_module.MmsType.STRUCTURE
    assert [(child.name, child.iec_type, child.mms_type) for child in svc.sub_das] == [
        ("scaleFactor", "float", discovery_module.MmsType.FLOAT),
        ("offset", "float", discovery_module.MmsType.FLOAT),
    ]

    model = IedModel(
        lds=(
            LDModel(
                name="LD0",
                lns=(
                    LNModel(
                        name="GGIO1",
                        dos=(DORef(name="AnIn1", ref="LD0/GGIO1.AnIn1", frame_type=0, das=tuple(das)),),
                    ),
                ),
            ),
        )
    )
    assert all(".sVC" not in address for address in model.point_refs)


def test_direct_model_read_does_not_duplicate_qualified_ied_domain():
    connection = SimpleNamespace(model_name="PCS01", _discovered_lds=())
    reader = Iec61850Reader(connection)

    assert reader._build_ref("PCS01PIGO/GGIO1.AnIn1.sVC.scaleFactor") == "PCS01PIGO/GGIO1.AnIn1.sVC.scaleFactor"
    assert reader._build_ref("PIGO/GGIO1.AnIn1.sVC.offset") == "PCS01PIGO/GGIO1.AnIn1.sVC.offset"


def test_direct_model_read_trusts_discovered_domain_over_configured_model_name():
    connection = SimpleNamespace(model_name="ZCA-110", _discovered_lds=("PCS01PIGO",))
    reader = Iec61850Reader(connection)

    assert reader._build_ref("PCS01PIGO/GGIO1.AnIn1.sVC.scaleFactor") == "PCS01PIGO/GGIO1.AnIn1.sVC.scaleFactor"


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


def test_control_object_does_not_get_synthetic_quality_or_timestamp(monkeypatch):
    """FC=CO objects must not expose synthetic q/t metadata."""

    directories = {
        "LD0/GGIO1.Pos": ["Oper"],
        "LD0/GGIO1.Pos.Oper": ["Check", "Test", "ctlVal"],
    }
    fake_iec61850 = SimpleNamespace(
        IED_ERROR_OK=0,
        IedConnection_getDataDirectory=lambda _conn, ref: (directories[ref], 0),
    )
    monkeypatch.setattr(discovery_module, "iec61850", fake_iec61850, raising=False)
    monkeypatch.setattr(discovery_module, "get_list_from_linked_list", list)

    service = ModelDiscoveryService()
    das = service._discover_data_attributes(
        object(),
        "LD0/GGIO1.Pos",
        "Pos",
        "GGIO1",
        2,
    )

    assert {da.name for da in das} == {"Oper", "dU"}
    oper = next(da for da in das if da.name == "Oper")
    assert oper.fc == "CO"
    assert oper.path == "Oper.ctlVal"
    assert [(child.name, child.fc) for child in oper.sub_das] == [
        ("Check", "CO"),
        ("Test", "CO"),
        ("ctlVal", "CO"),
    ]


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
