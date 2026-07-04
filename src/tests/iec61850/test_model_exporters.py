"""IEC 61850 多格式模型导出的回归测试。"""

from __future__ import annotations

import json
from types import SimpleNamespace
import xml.etree.ElementTree as ET

import pytest

from src.proto.iec61850.model import DARef, DORef, IedModel, LDModel, LNModel
from src.proto.iec61850.plugins.model_exporter import ModelExporterPlugin
from src.proto.iec61850.plugins.model_exporter.exporters import get_exporter


@pytest.fixture
def ied_model() -> IedModel:
    da = DARef(name="stVal", path="stVal", fc="ST", iec_type="BOOLEAN")
    do = DORef(name="Mod", ref="IED1LD0/LLN0.Mod", cdc="SPS", frame_type=0, das=(da,))
    ln = LNModel(name="LLN0", ln_class="LLN0", ref="IED1LD0/LLN0", dos=(do,))
    ld = LDModel(name="IED1LD0", inst="LD0", lns=(ln,))
    return IedModel(host="127.0.0.1", port=102, discover_time="2026-06-29 08:00:00", lds=(ld,))


@pytest.mark.parametrize(
    ("export_type", "extension"),
    [("icd", ".icd"), ("json", ".json"), ("xml", ".xml"), ("csv", ".csv"), ("tree", ".txt")],
)
def test_plugin_exports_all_registered_formats(tmp_path, ied_model, export_type, extension):
    plugin = ModelExporterPlugin()
    plugin._client = SimpleNamespace(model=ied_model, _registry=None)
    output_path = tmp_path / f"model{extension}"

    result = plugin.export(export_type, str(output_path), ied_name="IED1")

    assert result == str(output_path)
    assert output_path.is_file()
    assert output_path.stat().st_size > 0


def test_exported_files_have_expected_content(tmp_path, ied_model):
    paths = {export_type: tmp_path / f"model.{export_type}" for export_type in ("icd", "json", "xml", "csv", "tree")}

    for export_type, path in paths.items():
        get_exporter(export_type).export(ied_model, str(path), ied_name="IED1")

    assert ET.parse(paths["icd"]).getroot().tag.endswith("}SCL")
    assert ET.parse(paths["xml"]).getroot().tag == "ServerModel"
    assert json.loads(paths["json"].read_text(encoding="utf-8"))["host"] == "127.0.0.1"
    assert "逻辑设备(LD)" in paths["csv"].read_text(encoding="utf-8-sig")
    assert "IEC 61850 Server Model" in paths["tree"].read_text(encoding="utf-8")
