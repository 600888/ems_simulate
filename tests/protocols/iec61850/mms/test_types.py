from types import SimpleNamespace

from src.enums.points.base_point import BasePoint
from src.proto.iec61850.core import reader as reader_module
from src.proto.iec61850.defs.constants import IecType
from src.proto.iec61850.defs.mms_types import (
    BTYPE_TO_MMS_TYPE,
    MmsType,
    iec_type_from_mms_type,
    infer_mms_type_from_path,
    mms_type_from_btype,
    mms_type_from_native,
)
from src.proto.iec61850.model import discovery as discovery_module
from src.proto.iec61850.model.ied_model import DARef, DORef, IedModel, LDModel, LNModel
from src.proto.iec61850.plugins.scl.parser.scl_parser import SclParser
from src.proto.iec61850.plugins.scl.transformer.point_transformer import SclPointTransformer
from src.web.api.channel.iec61850 import _build_iec61850_tree_from_model


def test_native_mms_constants_map_one_to_one():
    for native_value, expected in enumerate(item for item in MmsType if item is not MmsType.UNKNOWN):
        assert mms_type_from_native(native_value) is expected


def test_scl_btypes_preserve_wire_level_distinctions():
    assert BTYPE_TO_MMS_TYPE["INT32"] is MmsType.INTEGER
    assert BTYPE_TO_MMS_TYPE["INT32U"] is MmsType.UNSIGNED
    assert BTYPE_TO_MMS_TYPE["Quality"] is MmsType.BIT_STRING
    assert BTYPE_TO_MMS_TYPE["Timestamp"] is MmsType.UTC_TIME
    assert BTYPE_TO_MMS_TYPE["VisString255"] is MmsType.VISIBLE_STRING
    assert BTYPE_TO_MMS_TYPE["Octet64"] is MmsType.OCTET_STRING
    assert BTYPE_TO_MMS_TYPE["Struct"] is MmsType.STRUCTURE


def test_scl_btype_lookup_is_case_insensitive():
    assert mms_type_from_btype("struct") is MmsType.STRUCTURE
    assert mms_type_from_btype("TIMESTAMP") is MmsType.UTC_TIME
    assert mms_type_from_btype("visstring255") is MmsType.VISIBLE_STRING


def test_scl_point_transformer_carries_mms_types_from_icd_templates():
    doc = SclParser().parse_string(
        """
        <SCL>
          <IED name="IED1">
            <AccessPoint name="AP1">
              <Server>
                <LDevice inst="LD0">
                  <LN0 lnClass="LLN0" lnType="LLN0Type" />
                  <LN lnClass="MMXU" inst="1" lnType="MMXUType" />
                </LDevice>
              </Server>
            </AccessPoint>
          </IED>
          <DataTypeTemplates>
            <LNodeType id="LLN0Type" lnClass="LLN0" />
            <LNodeType id="MMXUType" lnClass="MMXU">
              <DO name="TotW" type="MVType" />
            </LNodeType>
            <DOType id="MVType" cdc="MV">
              <DA name="mag" fc="MX" bType="struct" type="AnalogueValue" dchg="true" />
              <DA name="q" fc="MX" bType="QUALITY" qchg="true" />
            </DOType>
            <DAType id="AnalogueValue">
              <BDA name="f" bType="float32" />
            </DAType>
          </DataTypeTemplates>
        </SCL>
        """
    )

    result = SclPointTransformer(doc).transform()
    by_da = {point.da_name: point for point in result.yc_points}

    assert by_da["mag.f"].mms_type == MmsType.FLOAT
    assert by_da["mag.f"].iec_type == "float"
    # q/t/dU 等元数据由模型树展示，不应注册为独立轮询测点
    assert "q" not in by_da


def test_scl_point_transformer_uses_actual_integer_analogue_leaf():
    doc = SclParser().parse_string(
        """
        <SCL>
          <IED name="IED1"><AccessPoint name="AP1"><Server><LDevice inst="LD0">
            <LN0 lnClass="LLN0" lnType="LLN0Type" />
            <LN lnClass="MMXU" inst="1" lnType="MMXUType" />
          </LDevice></Server></AccessPoint></IED>
          <DataTypeTemplates>
            <LNodeType id="LLN0Type" lnClass="LLN0" />
            <LNodeType id="MMXUType" lnClass="MMXU"><DO name="Index" type="MVInt" /></LNodeType>
            <DOType id="MVInt" cdc="MV"><DA name="mag" fc="MX" bType="Struct" type="IntValue" /></DOType>
            <DAType id="IntValue"><BDA name="i" bType="INT32" /></DAType>
          </DataTypeTemplates>
        </SCL>
        """
    )

    points = SclPointTransformer(doc).transform().yc_points

    assert [(point.da_name, point.mms_type) for point in points] == [("mag.i", MmsType.INTEGER)]


def test_scl_point_transformer_keeps_instance_specific_du_descriptions():
    doc = SclParser().parse_string(
        """
        <SCL>
          <IED name="IED1"><AccessPoint name="AP1"><Server><LDevice inst="LD0">
            <LN0 lnClass="LLN0" lnType="LLN0Type" />
            <LN lnClass="MMXU" inst="1" lnType="MMXUType">
              <DOI name="TotW"><DAI name="dU"><Val>一号有功功率</Val></DAI></DOI>
            </LN>
            <LN lnClass="MMXU" inst="2" lnType="MMXUType">
              <DOI name="TotW"><DAI name="dU"><Val>二号有功功率</Val></DAI></DOI>
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
        """
    )

    points = SclPointTransformer(doc).transform().yc_points

    assert [(point.reg_addr, point.name) for point in points] == [
        ("LD0/MMXU1.TotW.mag.f", "一号有功功率"),
        ("LD0/MMXU2.TotW.mag.f", "二号有功功率"),
    ]


def test_mms_type_keeps_legacy_iec_type_compatibility():
    assert iec_type_from_mms_type(MmsType.UNSIGNED) is IecType.INTEGER
    assert iec_type_from_mms_type(MmsType.BIT_STRING) is IecType.INTEGER
    assert iec_type_from_mms_type(MmsType.UTC_TIME) is IecType.TIMESTAMP


def test_control_and_pulse_config_paths_have_static_mms_types():
    expected_types = {
        "Oper.ctlVal": MmsType.BOOLEAN,
        "Oper.origin": MmsType.STRUCTURE,
        "Oper.ctlNum": MmsType.UNSIGNED,
        "Oper.T": MmsType.UTC_TIME,
        "Oper.Test": MmsType.BOOLEAN,
        "Oper.Check": MmsType.BIT_STRING,
        "pulseConfig": MmsType.STRUCTURE,
        "pulseConfig.onDur": MmsType.UNSIGNED,
    }

    for path, expected in expected_types.items():
        assert infer_mms_type_from_path(path) is expected


def test_nameplate_data_objects_are_structures():
    assert infer_mms_type_from_path("NamPlt") is MmsType.STRUCTURE
    assert infer_mms_type_from_path("PhyNam") is MmsType.STRUCTURE


def test_standard_enum_system_data_objects_use_integer_wire_type():
    assert infer_mms_type_from_path("Beh") is MmsType.INTEGER
    assert infer_mms_type_from_path("Health") is MmsType.INTEGER
    assert infer_mms_type_from_path("Mod") is MmsType.INTEGER


class _FakeValue:
    def __init__(self, mms_type: int, value):
        self.mms_type = mms_type
        self.value = value


def test_unknown_reader_uses_one_read_object_and_returns_runtime_type(monkeypatch):
    calls = []
    value = _FakeValue(5, 42)
    fake = SimpleNamespace(
        IED_ERROR_OK=0,
        MMS_UNSIGNED=5,
        IedConnection_readObject=lambda *_args: (calls.append("readObject") or value, 0),
        MmsValue_getType=lambda item: item.mms_type,
        MmsValue_delete=lambda _item: calls.append("delete"),
    )
    monkeypatch.setattr(reader_module, "iec61850", fake, raising=False)
    monkeypatch.setattr(reader_module, "_convert_mms_object", lambda item, _type: item.value)

    converted, actual_type = reader_module.AutoDetectReader().read_typed(object(), "LD/LN.DO.da", 0)

    assert converted == 42
    assert actual_type is MmsType.UNSIGNED
    assert calls == ["readObject", "delete"]


def test_known_boolean_reader_never_falls_back_to_read_object(monkeypatch):
    calls = []
    fake = SimpleNamespace(
        IED_ERROR_OK=0,
        IedConnection_readBooleanValue=lambda *_args: (calls.append("boolean") or True, 0),
        IedConnection_readObject=lambda *_args: calls.append("readObject"),
    )
    monkeypatch.setattr(reader_module, "iec61850", fake, raising=False)

    assert reader_module.BooleanReader().read(object(), "LD/LN.DO.stVal", 0) is True
    assert calls == ["boolean"]


def test_discovery_probes_a_readable_leaf_once_and_skips_control(monkeypatch):
    calls = []
    value = _FakeValue(6, 1.5)
    fake = SimpleNamespace(
        IED_ERROR_OK=0,
        IEC61850_FC_MX=1,
        MMS_FLOAT=6,
        IedConnection_readObject=lambda *_args: (calls.append("readObject") or value, 0),
        MmsValue_getType=lambda item: item.mms_type,
        MmsValue_delete=lambda _item: calls.append("delete"),
    )
    monkeypatch.setattr(discovery_module, "iec61850", fake, raising=False)
    service = discovery_module.ModelDiscoveryService()

    first = service._probe_mms_type(object(), "LD/LN.DO.mag.f", "MX", MmsType.FLOAT)
    second = service._probe_mms_type(object(), "LD/LN.DO.mag.f", "MX", MmsType.FLOAT)
    control = service._probe_mms_type(object(), "LD/LN.DO.Oper.ctlVal", "CO", MmsType.BOOLEAN)

    assert first is second is MmsType.FLOAT
    assert control is MmsType.BOOLEAN
    assert calls == ["readObject", "delete"]


def test_discovery_does_not_probe_deterministic_standard_leaf(monkeypatch):
    calls = []
    fake = SimpleNamespace(
        IED_ERROR_OK=0,
        IEC61850_FC_MX=1,
        IedConnection_getVariableSpecification=lambda *_args: calls.append("getSpec"),
        IedConnection_readObject=lambda *_args: calls.append("readObject"),
    )
    monkeypatch.setattr(discovery_module, "iec61850", fake, raising=False)
    service = discovery_module.ModelDiscoveryService()

    first = service._resolve_leaf_mms_type(object(), "LD/LN.DO.mag.f", "MX", MmsType.FLOAT)
    second = service._resolve_leaf_mms_type(object(), "LD/LN.DO.mag.f", "MX", MmsType.FLOAT)

    assert first is second is MmsType.FLOAT
    assert calls == []
    assert service._type_probe_stats["total"] == 1
    assert service._type_probe_stats["static"] == 1


def test_discovery_still_probes_unknown_vendor_leaf(monkeypatch):
    calls = []
    spec = object()
    fake = SimpleNamespace(
        IED_ERROR_OK=0,
        IEC61850_FC_CF=1,
        MMS_UNSIGNED=5,
        IedConnection_getVariableSpecification=lambda *_args: (calls.append("getSpec") or spec, 0),
        MmsVariableSpecification_getType=lambda _spec: 5,
        MmsVariableSpecification_destroy=lambda _spec: calls.append("destroy"),
    )
    monkeypatch.setattr(discovery_module, "iec61850", fake, raising=False)
    service = discovery_module.ModelDiscoveryService()

    resolved = service._resolve_leaf_mms_type(object(), "LD/VENDOR1.Custom.vendorCounter", "CF", MmsType.UNKNOWN)

    assert resolved is MmsType.UNSIGNED
    assert calls == ["getSpec", "destroy"]


def test_discovery_uses_generic_variable_spec_for_vendor_control_type(monkeypatch):
    calls = []
    spec = object()
    fake = SimpleNamespace(
        IED_ERROR_OK=0,
        IEC61850_FC_CO=1,
        MMS_UNSIGNED=5,
        IedConnection_getVariableSpecification=lambda *_args: (calls.append("getSpec") or spec, 0),
        MmsVariableSpecification_getType=lambda item: 5 if item is spec else -1,
        MmsVariableSpecification_destroy=lambda item: calls.append(("destroy", item)),
        IedConnection_readObject=lambda *_args: calls.append("readObject"),
    )
    monkeypatch.setattr(discovery_module, "iec61850", fake, raising=False)
    service = discovery_module.ModelDiscoveryService()

    resolved = service._probe_mms_type(
        object(),
        "LD0/VENDOR1.CustomCommand.vendorSpecificCounter",
        "CO",
        MmsType.UNKNOWN,
    )

    assert resolved is MmsType.UNSIGNED
    assert calls == ["getSpec", ("destroy", spec)]
    assert service._type_probe_stats["spec"] == 1


def test_online_discovery_resolves_vendor_structure_without_name_mapping(monkeypatch):
    directories = {
        "LD0/VENDOR1.Custom": ["vendorBlob"],
        "LD0/VENDOR1.Custom.vendorBlob": ["counter", "enabled"],
    }
    type_by_ref_fc = {
        ("LD0/VENDOR1.Custom.vendorBlob", "CF"): 1,
        ("LD0/VENDOR1.Custom.vendorBlob.counter", "CF"): 5,
        ("LD0/VENDOR1.Custom.vendorBlob.enabled", "CF"): 2,
    }

    def get_spec(_conn, ref, fc):
        mms_type = type_by_ref_fc.get((ref, fc))
        return ((ref, mms_type), 0) if mms_type is not None else (None, 1)

    fake = SimpleNamespace(
        IED_ERROR_OK=0,
        IEC61850_FC_CO="CO",
        IEC61850_FC_CF="CF",
        IEC61850_FC_MX="MX",
        IEC61850_FC_ST="ST",
        MMS_STRUCTURE=1,
        MMS_BOOLEAN=2,
        MMS_UNSIGNED=5,
        IedConnection_getDataDirectory=lambda _conn, ref: (directories.get(ref, []), 0),
        IedConnection_getVariableSpecification=get_spec,
        MmsVariableSpecification_getType=lambda spec: spec[1],
        MmsVariableSpecification_destroy=lambda _spec: None,
    )
    monkeypatch.setattr(discovery_module, "iec61850", fake, raising=False)
    monkeypatch.setattr(discovery_module, "get_list_from_linked_list", list)

    service = discovery_module.ModelDiscoveryService()
    das = service._discover_data_attributes(object(), "LD0/VENDOR1.Custom", "Custom", "VENDOR1", 2)
    vendor_blob = next(da for da in das if da.name == "vendorBlob")

    assert vendor_blob.fc == "CF"
    assert vendor_blob.mms_type is MmsType.STRUCTURE
    assert {bda.name: bda.mms_type for bda in vendor_blob.sub_das} == {
        "counter": MmsType.UNSIGNED,
        "enabled": MmsType.BOOLEAN,
    }


def test_online_discovery_resolves_control_and_pulse_config_bda_types(monkeypatch):
    directories = {
        "LD0/CSWI1.Pos": ["Oper", "pulseConfig"],
        "LD0/CSWI1.Pos.Oper": ["ctlVal", "origin", "ctlNum", "T", "Test", "Check"],
        "LD0/CSWI1.Pos.pulseConfig": ["cmdQual", "onDur", "offDur", "numPls"],
    }
    fake = SimpleNamespace(
        IED_ERROR_OK=0,
        IedConnection_getDataDirectory=lambda _conn, ref: (directories.get(ref, []), 0),
    )
    monkeypatch.setattr(discovery_module, "iec61850", fake, raising=False)
    monkeypatch.setattr(discovery_module, "get_list_from_linked_list", list)

    service = discovery_module.ModelDiscoveryService()
    das = service._discover_data_attributes(object(), "LD0/CSWI1.Pos", "Pos", "CSWI1", 2)
    by_name = {da.name: da for da in das}

    oper = by_name["Oper"]
    assert oper.fc == "CO"
    assert oper.mms_type is MmsType.STRUCTURE
    assert {bda.name: bda.mms_type for bda in oper.sub_das} == {
        "ctlVal": MmsType.BOOLEAN,
        "origin": MmsType.STRUCTURE,
        "ctlNum": MmsType.UNSIGNED,
        "T": MmsType.UTC_TIME,
        "Test": MmsType.BOOLEAN,
        "Check": MmsType.BIT_STRING,
    }

    pulse_config = by_name["pulseConfig"]
    assert pulse_config.fc == "CF"
    assert pulse_config.mms_type is MmsType.STRUCTURE
    assert {bda.name: bda.mms_type for bda in pulse_config.sub_das} == {
        "cmdQual": MmsType.INTEGER,
        "onDur": MmsType.UNSIGNED,
        "offDur": MmsType.UNSIGNED,
        "numPls": MmsType.UNSIGNED,
    }


def test_tree_api_exposes_do_da_and_bda_mms_types():
    model = IedModel(
        lds=(
            LDModel(
                name="LD0",
                lns=(
                    LNModel(
                        name="MMXU1",
                        dos=(
                            DORef(
                                name="TotW",
                                ref="LD0/MMXU1.TotW",
                                frame_type=0,
                                das=(
                                    DARef(
                                        name="mag",
                                        path="mag",
                                        fc="MX",
                                        iec_type="float",
                                        mms_type=MmsType.STRUCTURE,
                                        sub_das=(
                                            DARef(
                                                name="f",
                                                path="mag.f",
                                                fc="MX",
                                                iec_type="float",
                                                mms_type=MmsType.FLOAT,
                                            ),
                                        ),
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        )
    )

    point = BasePoint(
        address="LD0/MMXU1.TotW.mag.f",
        code="MMXU1.TotW.mag.f",
        frame_type=0,
        fc="MX",
    )
    tree = _build_iec61850_tree_from_model(model, [point], category="DataModel")
    do_node = tree["items"][0]
    da_node = do_node["children"][0]

    assert do_node["mms_type"] == MmsType.FLOAT
    assert da_node["mms_type"] == MmsType.STRUCTURE
    assert da_node["children"][0]["mms_type"] == MmsType.FLOAT
    assert "point_code" in da_node["children"][0]
