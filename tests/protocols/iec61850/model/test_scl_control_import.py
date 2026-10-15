"""Status-only SCL templates must not invent control attributes."""

import pytest

from src.proto.iec61850.plugins.scl.service.import_service import SclImportService


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
