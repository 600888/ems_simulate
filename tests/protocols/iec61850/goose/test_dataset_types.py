"""GOOSE DataSet types must come from DA/BDA templates, not functional constraints."""

import pytest

from src.proto.iec61850.plugins.scl.service.import_service import SclImportService
from src.tools.icd_goose_importer import import_goose_from_icd


def _scl(do_name: str, da_name: str, fc: str, *, header: str = "") -> str:
    return f"""
    <SCL xmlns="http://www.iec.ch/61850/2003/SCL">
      {header}
      <IED name="PUB"><AccessPoint name="AP1"><Server>
        <LDevice inst="GO">
          <LN0 lnClass="LLN0" lnType="Common">
            <DataSet name="GooseDs">
              <FCDA ldInst="DATA" prefix="Meas" lnClass="GGIO" lnInst="2"
                    doName="{do_name}" daName="{da_name}" fc="{fc}"/>
            </DataSet>
            <DataSet name="PureDs">
              <FCDA ldInst="DATA" prefix="Meas" lnClass="GGIO" lnInst="2"
                    doName="{do_name}" daName="{da_name}" fc="{fc}"/>
            </DataSet>
            <GSEControl name="gcb" datSet="GooseDs" type="GOOSE"/>
            <ReportControl name="rpt" datSet="GooseDs"/>
          </LN0>
        </LDevice>
        <LDevice inst="DATA">
          <LN0 lnClass="LLN0" lnType="Common"/>
          <LN prefix="Meas" lnClass="GGIO" inst="2" lnType="Measurements"/>
        </LDevice>
      </Server></AccessPoint></IED>
      <DataTypeTemplates>
        <LNodeType id="Common" lnClass="LLN0"/>
        <LNodeType id="Measurements" lnClass="GGIO">
          <DO name="AnIn1" type="Analog"/>
          <DO name="Status" type="Status"/>
          <DO name="Phases" type="Phases"/>
        </LNodeType>
        <DOType id="Analog" cdc="MV">
          <DA name="mag" fc="MX" bType="Struct" type="AnalogValue"/>
          <DA name="setMag" fc="SG" bType="Struct" type="AnalogValue"/>
          <DA name="cVal" fc="MX" bType="Struct" type="ComplexValue"/>
          <DA name="q" fc="MX" bType="Quality"/>
          <DA name="t" fc="MX" bType="Timestamp"/>
        </DOType>
        <DOType id="Status" cdc="INS">
          <DA name="stVal" fc="ST" bType="INT32"/>
          <DA name="enabled" fc="CF" bType="BOOLEAN"/>
          <DA name="label" fc="ST" bType="VisString255"/>
          <DA name="ctlModel" fc="CF" bType="Enum"/>
        </DOType>
        <DOType id="Phases" cdc="WYE"><SDO name="phsA" type="Phase"/></DOType>
        <DOType id="Phase" cdc="WYE"><SDO name="value" type="Analog"/></DOType>
        <DAType id="AnalogValue">
          <BDA name="f" bType="FLOAT32"/>
          <BDA name="i" bType="INT32"/>
        </DAType>
        <DAType id="ComplexValue"><BDA name="mag" bType="Struct" type="AnalogValue"/></DAType>
      </DataTypeTemplates>
    </SCL>
    """


@pytest.mark.parametrize(
    ("do_name", "da_name", "fc", "expected_type", "expected_value"),
    [
        ("AnIn1", "mag.f", "MX", "float", 0.0),
        ("AnIn1", "mag.f", "SG", "float", 0.0),
        ("AnIn1", "setMag.f", "SG", "float", 0.0),
        ("AnIn1", "setMag.f", "SP", "float", 0.0),
        ("AnIn1", "mag.i", "MX", "integer", 0),
        ("AnIn1", "cVal.mag.f", "MX", "float", 0.0),
        ("Phases.phsA.value", "mag.f", "SG", "float", 0.0),
        ("AnIn1", "q", "MX", "bitstring", 0),
        ("AnIn1", "t", "MX", "timestamp", 0),
        ("Status", "stVal", "ST", "integer", 0),
        ("Status", "enabled", "CF", "boolean", False),
        ("Status", "label", "ST", "string", ""),
        ("Status", "ctlModel", "CF", "integer", 0),
    ],
)
def test_import_resolves_dataset_leaf_types(do_name, da_name, fc, expected_type, expected_value):
    result = SclImportService().import_string(_scl(do_name, da_name, fc), validate=False)
    goose = result.to_dict()["goose"]
    entry = goose["publishers"][0]["entries"][0]

    assert entry["iec_type"] == expected_type
    assert entry["value"] == expected_value
    assert type(entry["value"]) is type(expected_value)
    assert entry["fc"] == fc
    assert entry["name"] == f"DATA/MeasGGIO2.{do_name}.{da_name}"
    assert goose["subscriptions"][0]["dataset_entries"][0]["type"] == expected_type
    assert goose["pure_datasets"][0]["entries"][0]["iec_type"] == expected_type
    assert result.reports.report_controls[0].entries[0]["iec_type"] == expected_type


def test_legacy_icd_import_preserves_resolved_type(tmp_path):
    path = tmp_path / "analog.icd"
    path.write_text(_scl("AnIn1", "setMag.f", "SG"), encoding="utf-8")

    goose = import_goose_from_icd(str(path))

    assert goose["publishers"][0]["entries"][0]["iec_type"] == "float"
    assert type(goose["publishers"][0]["entries"][0]["value"]) is float
    assert goose["pure_datasets"][0]["entries"][0]["iec_type"] == "float"


def test_dataset_type_resolution_with_ied_name_prefix():
    result = SclImportService().import_string(
        _scl("AnIn1", "setMag.f", "SG", header='<Header nameStructure="IEDName"/>'), validate=False
    )

    entry = result.to_dict()["goose"]["publishers"][0]["entries"][0]

    assert entry["name"] == "PUBDATA/MeasGGIO2.AnIn1.setMag.f"
    assert entry["iec_type"] == "float"


def test_dataset_type_lookup_is_scoped_to_ied():
    xml = _scl("AnIn1", "mag.f", "SG")
    publisher = xml[xml.index('<IED name="PUB">') : xml.index("</IED>") + len("</IED>")]
    other = publisher.replace('name="PUB"', 'name="OTHER"').replace('lnType="Measurements"', 'lnType="OtherType"')
    xml = xml.replace("<DataTypeTemplates>", f"{other}<DataTypeTemplates>").replace(
        '<LNodeType id="Common"',
        '<LNodeType id="OtherType" lnClass="GGIO"><DO name="AnIn1" type="OtherAnalog"/></LNodeType>'
        '<DOType id="OtherAnalog" cdc="MV"><DA name="mag" bType="Struct" type="OtherValue"/></DOType>'
        '<DAType id="OtherValue"><BDA name="f" bType="INT32"/></DAType><LNodeType id="Common"',
    )

    result = SclImportService().import_string(xml, validate=False)
    publishers = result.to_dict()["goose"]["publishers"]

    assert [item["entries"][0]["iec_type"] for item in publishers] == ["float", "integer"]
    assert [item.entries[0]["iec_type"] for item in result.reports.report_controls] == ["float", "integer"]


def test_missing_templates_use_attribute_path_before_fc():
    xml = _scl("AnIn1", "mag.f", "SG")
    xml = xml[: xml.index("<DataTypeTemplates>")] + "<DataTypeTemplates/></SCL>"

    result = SclImportService().import_string(xml, validate=False)

    assert result.to_dict()["goose"]["publishers"][0]["entries"][0]["iec_type"] == "float"


def test_imported_float_is_encoded_as_float_in_goose_packet():
    from src.proto.iec61850.plugins.goose.capture import GooseCaptureEngine
    from src.proto.iec61850.plugins.goose.publisher import GoosePublisher
    from src.proto.iec61850.plugins.goose.types import GooseDataSetEntry, IecDataType, PublisherConfig

    result = SclImportService().import_string(_scl("AnIn1", "setMag.f", "SG"), validate=False)
    imported = result.to_dict()["goose"]["publishers"][0]
    publisher = GoosePublisher(PublisherConfig(go_cb_ref=imported["go_cb_ref"], data_set_ref=imported["data_set_ref"]))
    entry = imported["entries"][0]
    publisher.add_entry(GooseDataSetEntry(entry["name"], 12.5, IecDataType(entry["iec_type"])))
    ethernet_frame = bytes.fromhex("010ccd010001 020304050607 88b8") + publisher._build_goose_payload()
    capture = GooseCaptureEngine(interface="test")

    capture._process_packet(ethernet_frame)

    received = capture.get_packets()[0]["data_values"][0]
    assert received["type"] == "float"
    assert received["value"] == 12.5
