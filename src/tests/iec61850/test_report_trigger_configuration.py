"""IEC 61850 服务端报告触发配置回归测试。"""

from pathlib import Path
from types import SimpleNamespace

from src.proto.iec61850.plugins.datamodels import builder as builder_module
from src.proto.iec61850.plugins.reports import manager as report_manager_module
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
