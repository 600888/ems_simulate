"""IEC 61850 服务端报告触发配置回归测试。"""

from pathlib import Path
from types import SimpleNamespace

from src.proto.iec61850.defs.types import RCBInfo, ReportDataEntry
from src.proto.iec61850.plugins.datamodels import builder as builder_module
from src.proto.iec61850.plugins.reports import ReportsPlugin
from src.proto.iec61850.plugins.reports import callback as report_callback_module
from src.proto.iec61850.plugins.reports import manager as report_manager_module
from src.proto.iec61850.plugins.reports.urcb import UrcbHandler
from src.proto.iec61850.plugins.scl.service.import_service import SclImportService


def test_scl_da_trigger_flags_are_preserved_in_points():
    icd_path = Path(__file__).parents[3] / "data" / "device" / "IEC61850SERVER" / "SY_ES630K.icd"

    result = SclImportService().import_file(str(icd_path))

    st_val = next(point for point in result.points.yx_points if point.reg_addr == "CTRL/krGGIO1.Alm1.stVal")
    quality = next(point for point in result.points.yx_points if point.reg_addr == "CTRL/krGGIO1.Alm1.q")
    analog = next(point for point in result.points.yc_points if point.reg_addr == "MEAS/GGIO1.AnIn1.mag.f")

    assert st_val.dchg is True
    assert quality.qchg is True
    assert analog.dchg is True


def test_server_rcb_always_exposes_gi_capability(monkeypatch):
    create_calls = []

    def create_rcb(*args):
        create_calls.append(args)
        return object()

    fake_iec61850 = SimpleNamespace(
        ReportControlBlock_create=create_rcb,
        ReportControlBlock_getRptEna=lambda _rcb: object(),
    )
    monkeypatch.setattr(report_manager_module, "HAS_IEC61850", True)
    monkeypatch.setattr(report_manager_module, "iec61850", fake_iec61850, raising=False)

    builder = SimpleNamespace(
        model=object(),
        ln_map={"LD0/LLN0": object()},
        keep_alive=[],
    )
    manager = report_manager_module.ReportManager(builder)

    success = manager.register_rcb(
        ld_inst="LD0",
        ln_name="LLN0",
        name="brcb01",
        data_set_ref="LD0/LLN0$ds1",
        trg_ops={"dchg": True, "gi": False},
    )

    assert success is True
    assert create_calls[0][6] & 0x10
    assert manager.rcb_list[0]["trg_ops"]["gi"] is True


def test_expanded_report_instances_have_unique_rpt_ids():
    icd_path = Path(__file__).parents[3] / "data" / "device" / "IEC61850SERVER" / "SY_ES630K.icd"

    result = SclImportService().import_file(str(icd_path))
    instances = [
        report
        for report in result.reports.report_controls
        if report.ld_inst == "LD0" and report.name.startswith("brcbDin")
    ]

    assert [report.name for report in instances] == [f"brcbDin{idx:02d}" for idx in range(1, 13)]
    assert [report.rpt_id for report in instances] == [f"LD0/LLN0$BR$brcbDin{idx:02d}" for idx in range(1, 13)]
    assert len({report.rpt_id for report in result.reports.report_controls}) == len(result.reports.report_controls)


def test_server_rcb_registration_auto_suffixes_duplicate_rpt_id(monkeypatch):
    create_calls = []

    fake_iec61850 = SimpleNamespace(
        ReportControlBlock_create=lambda *args: create_calls.append(args) or object(),
        ReportControlBlock_getRptEna=lambda _rcb: object(),
    )
    monkeypatch.setattr(report_manager_module, "HAS_IEC61850", True)
    monkeypatch.setattr(report_manager_module, "iec61850", fake_iec61850, raising=False)

    builder = SimpleNamespace(
        model=object(),
        ln_map={"LD0/LLN0": object()},
        keep_alive=[],
    )
    manager = report_manager_module.ReportManager(builder)

    assert manager.register_rcb(ld_inst="LD0", name="brcb01", rpt_id="shared") is True
    assert manager.register_rcb(ld_inst="LD0", name="brcb02", rpt_id="shared") is True

    assert [call[2] for call in create_calls] == ["shared", "shared02"]
    assert [rcb["rpt_id"] for rcb in manager.rcb_list] == ["shared", "shared02"]


def test_report_callback_rejects_duplicate_rpt_id(monkeypatch):
    connection = SimpleNamespace(connection=object())
    first = report_callback_module._CallbackInfo(
        rcb_ref="LD0/LLN0.BR.brcb01",
        connection=connection,
        rpt_id="shared",
    )
    monkeypatch.setitem(report_callback_module._CALLBACK_REGISTRY, first.rcb_ref, first)
    monkeypatch.setattr(report_callback_module, "HAS_IEC61850", True)

    assert (
        report_callback_module.ReportCallbackHandler.install(
            connection,
            "LD0/LLN0.BR.brcb02",
            rpt_id="shared",
            rcb_type="BRCB",
        )
        is False
    )
    assert report_callback_module._CALLBACK_REGISTRY[first.rcb_ref] is first
    assert "LD0/LLN0.BR.brcb02" not in report_callback_module._CALLBACK_REGISTRY


def test_regular_report_is_not_distributed_to_same_rpt_id(monkeypatch):
    first = report_callback_module._CallbackInfo(
        rcb_ref="LD0/LLN0.BR.brcb01",
        rpt_id="shared",
    )
    second = report_callback_module._CallbackInfo(
        rcb_ref="LD0/LLN0.BR.brcb02",
        rpt_id="shared",
    )
    monkeypatch.setitem(report_callback_module._CALLBACK_REGISTRY, first.rcb_ref, first)
    monkeypatch.setitem(report_callback_module._CALLBACK_REGISTRY, second.rcb_ref, second)
    monkeypatch.setattr(report_callback_module, "_PENDING_GI_ROUTES", {})
    monkeypatch.setattr(
        report_callback_module,
        "_parse_client_report",
        lambda *_args, **_kwargs: ReportDataEntry(rpt_id="shared"),
    )

    report_callback_module._dispatch_report(first.rcb_ref, object())

    assert len(first.data_cache) == 1
    assert len(second.data_cache) == 0


def test_enable_report_writes_instance_suffix_to_remote_rpt_id(monkeypatch):
    plugin = ReportsPlugin()
    plugin._connection = SimpleNamespace(connection=object())
    rcb_ref = "LC001BESSSYS/LLN0.rpSystemCtrlMeas02"
    plugin._rcb_type_map[rcb_ref] = "URCB"
    events = []

    monkeypatch.setattr(
        UrcbHandler,
        "get_rcb_values",
        lambda *_args: RCBInfo(rpt_id="rpSystemCtrlMeas"),
    )
    monkeypatch.setattr(
        UrcbHandler,
        "set_rpt_id",
        lambda _connection, ref, rpt_id: events.append(("rpt_id", ref, rpt_id)) or True,
    )
    monkeypatch.setattr(
        report_callback_module.ReportCallbackHandler,
        "install",
        lambda _connection, ref, **kwargs: events.append(("install", ref, kwargs["rpt_id"])) or True,
    )
    monkeypatch.setattr(
        UrcbHandler,
        "set_rpt_ena",
        lambda _connection, ref, enabled: events.append(("rpt_ena", ref, enabled)) or True,
    )

    assert plugin._enable_report(rcb_ref) is True
    assert events == [
        ("rpt_id", rcb_ref, "rpSystemCtrlMeas02"),
        ("install", rcb_ref, "rpSystemCtrlMeas02"),
        ("rpt_ena", rcb_ref, True),
    ]


def test_instance_rpt_id_is_not_double_suffixed():
    assert (
        ReportsPlugin._derive_instance_rpt_id(
            "LC001BESSSYS/LLN0.rpSystemCtrlMeas02",
            "rpSystemCtrlMeas02",
        )
        == "rpSystemCtrlMeas02"
    )


def test_urcb_callback_reference_keeps_instance_suffix():
    first = report_callback_module._normalize_ref(
        "LC001BESSSYS/LLN0.rpSystemCtrlMeas01",
        "URCB",
    )
    second = report_callback_module._normalize_ref(
        "LC001BESSSYS/LLN0.rpSystemCtrlMeas02",
        "URCB",
    )

    assert first == "LC001BESSSYS/LLN0.RP.rpSystemCtrlMeas01"
    assert second == "LC001BESSSYS/LLN0.RP.rpSystemCtrlMeas02"
    assert first != second


def test_standard_value_attributes_get_report_trigger_fallback(monkeypatch):
    fake_iec61850 = SimpleNamespace(
        TRG_OPT_DATA_CHANGED=0x01,
        TRG_OPT_QUALITY_CHANGED=0x02,
        TRG_OPT_DATA_UPDATE=0x04,
    )
    monkeypatch.setattr(builder_module, "HAS_IEC61850", True)
    monkeypatch.setattr(builder_module, "iec61850", fake_iec61850, raising=False)

    assert builder_module.IedModelBuilder._infer_da_trigger_options(["stVal"]) == 0x01
    assert builder_module.IedModelBuilder._infer_da_trigger_options(["mag", "f"]) == 0x01
    assert builder_module.IedModelBuilder._infer_da_trigger_options(["q"]) == 0x02
    assert builder_module.IedModelBuilder._infer_da_trigger_options(["t"]) == 0


def test_urcb_software_gi_uses_strict_dataset_batch_read(monkeypatch):
    """软件 GI 只能批读完整 DataSet，禁止失败后退化成逐点读取。"""
    calls = []
    datasets = SimpleNamespace(
        read_dataset_values=lambda dataset_ref, *, allow_member_fallback: (
            calls.append((dataset_ref, allow_member_fallback)) or {"IEDLD0/MMXU1.TotW.mag.f": 10.0}
        )
    )
    plugin = ReportsPlugin()
    plugin._client = SimpleNamespace(datasets=datasets)
    plugin._rcb_detail_cache["IEDLD0/LLN0.RP.urcb01"] = {
        "data_set_ref": "IEDLD0/LLN0$dsMeas",
        "rpt_id": "urcb01",
        "conf_rev": 1,
    }
    cached_entries = []
    monkeypatch.setattr(report_callback_module.ReportCallbackHandler, "mark_pending_gi", lambda _ref: None)
    monkeypatch.setattr(
        report_callback_module.ReportCallbackHandler,
        "append_cache_entry",
        lambda _ref, entry: cached_entries.append(entry) or True,
    )

    assert plugin._trigger_urcb_software_gi("IEDLD0/LLN0.RP.urcb01") is True
    assert calls == [("IEDLD0/LLN0$dsMeas", False)]
    assert cached_entries[0].data_values == {"IEDLD0/MMXU1.TotW.mag.f": 10.0}
    assert cached_entries[0].reason_codes == {"IEDLD0/MMXU1.TotW.mag.f": "gi"}
