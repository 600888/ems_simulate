"""SCL intrinsic DA registration metadata regression tests."""

from src.proto.iec61850.iec61850_server import IEC61850Server
from src.proto.iec61850.plugins.scl.service.import_service import SclImportService
from src.proto.iec61850.plugins.scl.transformer.server_model_builder import SclServerModelBuilder

_INTRINSIC_SCL = """
<SCL>
  <Header nameStructure="IEDName" />
  <IED name="PCS01"><AccessPoint name="AP1"><Server><LDevice inst="PIGO">
    <LN0 lnClass="LLN0" lnType="CommonType" />
    <LN lnClass="LPHD" inst="1" lnType="LphdType" />
    <LN lnClass="GGIO" inst="1" lnType="GgioType" />
  </LDevice></Server></AccessPoint></IED>
  <DataTypeTemplates>
    <LNodeType id="CommonType" lnClass="LLN0">
      <DO name="Mod" type="EncType" />
      <DO name="NamPlt" type="NameplateType" />
    </LNodeType>
    <LNodeType id="LphdType" lnClass="LPHD">
      <DO name="PhyHealth" type="EnsType" />
      <DO name="Proxy" type="SpsType" />
    </LNodeType>
    <LNodeType id="GgioType" lnClass="GGIO"><DO name="AnIn2" type="MvType" /></LNodeType>
    <DOType id="EncType" cdc="INC">
      <DA name="stVal" fc="ST" bType="INT32" dchg="true" />
      <DA name="q" fc="ST" bType="Quality" qchg="true" />
      <DA name="t" fc="ST" bType="Timestamp" />
      <DA name="ctlModel" fc="CF" bType="Enum" />
    </DOType>
    <DOType id="EnsType" cdc="ENS">
      <DA name="stVal" fc="ST" bType="INT32" dchg="true" />
      <DA name="q" fc="ST" bType="Quality" qchg="true" />
      <DA name="t" fc="ST" bType="Timestamp" />
    </DOType>
    <DOType id="SpsType" cdc="SPS">
      <DA name="stVal" fc="ST" bType="BOOLEAN" dchg="true" />
    </DOType>
    <DOType id="NameplateType" cdc="LPL">
      <DA name="vendor" fc="DC" bType="VisString255" />
    </DOType>
    <DOType id="MvType" cdc="MV">
      <DA name="mag" fc="MX" bType="Struct" type="AnalogueValue" dchg="true" />
      <DA name="sVC" fc="CF" bType="Struct" type="ScaledConfig" />
    </DOType>
    <DAType id="AnalogueValue"><BDA name="f" bType="FLOAT32" /></DAType>
    <DAType id="ScaledConfig"><BDA name="scaleFactor" bType="FLOAT32" /></DAType>
  </DataTypeTemplates>
</SCL>
"""


def _pcs_attributes() -> dict[str, dict]:
    result = SclImportService().import_string(_INTRINSIC_SCL, validate=False)
    return {item["ref"]: item for item in SclServerModelBuilder(result.doc).iter_leaf_attributes(result.ied_name)}


def test_enum_status_objects_keep_integer_value_quality_and_timestamp():
    attributes = _pcs_attributes()

    prefix = "PCS01PIGO/LLN0.Mod"
    assert attributes[f"{prefix}.stVal"]["iec_type"] == "integer"
    assert attributes[f"{prefix}.stVal"]["fc"] == "ST"
    assert attributes[f"{prefix}.q"] == {
        "ref": f"{prefix}.q",
        "frame_type": 3,
        "fc": "ST",
        "iec_type": "bitstring",
        "mms_type": "MMS_BIT_STRING",
        "dchg": False,
        "qchg": True,
        "dupd": False,
    }
    assert attributes[f"{prefix}.t"]["iec_type"] == "timestamp"
    assert attributes[f"{prefix}.t"]["fc"] == "ST"


def test_non_business_intrinsic_attributes_are_kept_in_native_model_catalog():
    attributes = _pcs_attributes()

    assert attributes["PCS01PIGO/LLN0.Mod.ctlModel"]["iec_type"] == "integer"
    assert attributes["PCS01PIGO/LPHD1.PhyHealth.stVal"]["iec_type"] == "integer"
    assert attributes["PCS01PIGO/LPHD1.PhyHealth.q"]["iec_type"] == "bitstring"
    assert attributes["PCS01PIGO/LPHD1.PhyHealth.t"]["iec_type"] == "timestamp"
    assert attributes["PCS01PIGO/LPHD1.Proxy.stVal"]["iec_type"] == "boolean"
    assert attributes["PCS01PIGO/LLN0.NamPlt.vendor"]["iec_type"] == "string"
    assert attributes["PCS01PIGO/GGIO1.AnIn2.sVC.scaleFactor"]["iec_type"] == "float"


def test_server_load_model_collects_instance_du_for_device_start_path():
    result = SclImportService().import_string(
        """
        <SCL>
          <IED name="IED1"><AccessPoint name="AP1"><Server><LDevice inst="LD0">
            <LN0 lnClass="LLN0" lnType="LLN0Type" />
            <LN lnClass="MMXU" inst="1" lnType="MMXUType">
              <DOI name="TotW"><DAI name="dU"><Val>一号有功功率</Val></DAI></DOI>
            </LN>
          </LDevice></Server></AccessPoint></IED>
          <DataTypeTemplates>
            <LNodeType id="LLN0Type" lnClass="LLN0" />
            <LNodeType id="MMXUType" lnClass="MMXU"><DO name="TotW" type="MVType" /></LNodeType>
            <DOType id="MVType" cdc="MV">
              <DA name="mag" fc="MX" bType="Struct" type="AnalogueValue" />
              <DA name="dU" fc="DC" bType="VisString255" />
            </DOType>
            <DAType id="AnalogueValue"><BDA name="f" bType="FLOAT32" /></DAType>
          </DataTypeTemplates>
        </SCL>
        """,
        validate=False,
    )
    server = IEC61850Server(model_name="IED1", ied_name="IED1")
    try:
        assert server.load_model("unused.icd", scl_result=result)
        assert server._du_descriptions == {"LD0/MMXU1.TotW": "一号有功功率"}
    finally:
        server.destroy()
