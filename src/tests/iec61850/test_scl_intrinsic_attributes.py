"""SCL intrinsic DA registration metadata regression tests."""

from pathlib import Path

from src.proto.iec61850.iec61850_server import IEC61850Server
from src.proto.iec61850.plugins.scl.service.import_service import SclImportService
from src.proto.iec61850.plugins.scl.transformer.server_model_builder import SclServerModelBuilder

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _pcs_attributes() -> dict[str, dict]:
    result = SclImportService().import_file(
        str(PROJECT_ROOT / "data" / "device" / "s" / "PCS01_102.icd"),
        validate=False,
    )
    return {item["ref"]: item for item in SclServerModelBuilder(result.doc).iter_leaf_attributes(result.ied_name)}


def test_enum_status_objects_keep_integer_value_quality_and_timestamp():
    attributes = _pcs_attributes()

    for logical_node in ("LLN0", "GGIO1", "GGIO2"):
        for data_object in ("Mod", "Beh", "Health"):
            prefix = f"PCS01PIGO/{logical_node}.{data_object}"
            assert attributes[f"{prefix}.stVal"]["iec_type"] == "integer"
            assert attributes[f"{prefix}.stVal"]["fc"] == "ST"
            assert attributes[f"{prefix}.q"] == {
                "ref": f"{prefix}.q",
                "frame_type": 3 if data_object == "Mod" else 1,
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
