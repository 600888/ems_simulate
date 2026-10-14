"""Import the GGIO1.CS01 SBO model without inventing control attributes."""

from pathlib import Path

import pytest

from src.enums.points.base_point import BasePoint
from src.proto.iec61850.plugins.scl.service.import_service import SclImportService
from src.proto.iec61850.plugins.scl.transformer.server_model_builder import SclServerModelBuilder
from src.web.api.channel.iec61850 import _build_iec61850_tree_from_model

_ICD = Path(__file__).resolve().parents[3] / "fixtures/iec61850/MmsTestIed_SBO_normal.icd"


def test_sbo_import_keeps_only_status_and_actual_control_value():
    result = SclImportService().import_file(str(_ICD))
    assert result.is_valid
    points = {point.da_name: point for point in result.points.yk_points}
    assert set(points) == {"stVal", "Oper.ctlVal"}
    assert points["Oper.ctlVal"].fc == "CO"
    assert points["Oper.ctlVal"].iec_type == "boolean"
    assert points["Oper.ctlVal"].mms_type == "MMS_BOOLEAN"
    assert len(result.points.yt_points) == 10
    assert all(point.fc == "SP" for point in result.points.yt_points)


def test_offline_model_registers_control_leaf_for_tree():
    result = SclImportService().import_file(str(_ICD))
    model = SclServerModelBuilder(result.doc).build()
    ref = "MMS_TEST/GGIO1.CS01.Oper.ctlVal"
    assert model.point_refs[ref]["fc"] == "CO"
    assert model.point_refs[ref]["iec_type"] == "boolean"
    do = next(do for _, _, do in model.iter_dos() if do.name == "CS01")
    oper = next(da for da in do.das if da.name == "Oper")
    assert oper.sub_das[0].name == "ctlVal"
    assert next(bda for bda in oper.sub_das if bda.name == "Check").mms_type == "MMS_BIT_STRING"
    points = [
        BasePoint(address=address, code=info["code"], fc=info["fc"], frame_type=info["frame_type"])
        for address, info in model.point_refs.items()
    ]
    tree = _build_iec61850_tree_from_model(model, points)
    node = next(item for item in tree["items"] if item["do_name"] == "CS01")
    oper_node = next(da for da in node["children"] if da["da_name"] == "Oper")
    ctl = next(bda for bda in oper_node["children"] if bda["bda_name"] == "ctlVal")
    assert ctl["point_code"] == "GGIO1.CS01.Oper.ctlVal"


@pytest.mark.parametrize("value", ["0", "status-only"])
def test_status_only_template_does_not_invent_a_control_point(value):
    xml = f"""<SCL><IED name="IED"><AccessPoint name="AP"><Server>
      <LDevice inst="LD"><LN lnClass="GGIO" inst="1" lnType="LN"/></LDevice>
      </Server></AccessPoint></IED><DataTypeTemplates>
      <LNodeType id="LN" lnClass="GGIO"><DO name="CS" type="SPC"/></LNodeType>
      <DOType id="SPC" cdc="SPC"><DA name="stVal" bType="BOOLEAN" fc="ST"/>
      <DA name="ctlModel" bType="Enum" fc="CF"><Val>{value}</Val></DA>
      </DOType></DataTypeTemplates></SCL>"""
    points = SclImportService().import_string(xml, validate=False).points.yk_points
    assert [(point.da_name, point.fc) for point in points] == [("stVal", "ST")]
