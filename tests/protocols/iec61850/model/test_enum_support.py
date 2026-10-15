"""SCL enum domains survive expansion, caching and device-scoped lookup."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.proto.iec61850.core.registry import PointRegistry
from src.proto.iec61850.model.enum_types import EnumDefinition, EnumItem
from src.proto.iec61850.model.ied_model import DARef, IedModel
from src.proto.iec61850.model.registry_bridge import build_registry_from_model
from src.proto.iec61850.plugins.scl.parser.scl_parser import SclParser
from src.proto.iec61850.plugins.scl.parser.type_resolver import TypeResolver
from src.proto.iec61850.plugins.scl.transformer.server_model_builder import SclServerModelBuilder

SCL = """<SCL>
<IED name="IED1"><AccessPoint name="AP"><Server><LDevice inst="LD0">
<LN0 lnClass="LLN0" lnType="LNType"/>
</LDevice></Server></AccessPoint></IED>
<DataTypeTemplates>
<LNodeType id="LNType" lnClass="LLN0"><DO name="State" type="DOType"/></LNodeType>
<DOType id="DOType" cdc="ENS">
  <DA name="stVal" bType="Enum" type="VendorState" fc="ST"/>
  <DA name="cfg" bType="Struct" type="Outer" fc="CF"/>
  <SDO name="sub" type="SubDO"/>
</DOType>
<DOType id="SubDO" cdc="ENS"><SDO name="deep" type="LeafDO"/></DOType>
<DOType id="LeafDO" cdc="ENS"><DA name="stVal" bType="Enum" type="VendorState" fc="ST"/></DOType>
<DAType id="Outer"><BDA name="inner" bType="Struct" type="Inner"/></DAType>
<DAType id="Inner"><BDA name="mode" bType="Enum" type="VendorState"/></DAType>
<EnumType id="VendorState" desc="厂商状态">
  <EnumVal ord="-1">invalid</EnumVal><EnumVal ord="0">idle</EnumVal>
  <EnumVal ord="10" desc="充电">charging</EnumVal><EnumVal ord="20">discharging</EnumVal>
  <EnumVal ord="99">fault</EnumVal>
</EnumType>
</DataTypeTemplates></SCL>"""


def build_model(xml=SCL):
    return SclServerModelBuilder(SclParser().parse_string(xml)).build(ied_name="IED1")


def test_custom_enum_nested_bda_and_sdo_keep_actual_domains():
    doc = SclParser().parse_string(SCL)
    leaves = {item["path"]: item for item in TypeResolver(doc).collect_all_das("DOType", "ENS")}
    assert leaves["cfg.inner.mode"]["typeId"] == "VendorState"
    assert leaves["cfg.inner.mode"]["fc"] == "CF"
    assert leaves["sub.deep.stVal"]["typeId"] == "VendorState"
    model = SclServerModelBuilder(doc).build()
    for path, fc in [("stVal", "ST"), ("cfg.inner.mode", "CF"), ("sub.deep.stVal", "ST")]:
        attribute = model.find_attribute(f"LD0/LLN0.State.{path}", fc)
        assert attribute.b_type == "Enum"
        assert attribute.mms_type == "MMS_INTEGER"
        assert model.value_metadata(attribute)["enum_ref"] == "VendorState"
    assert model.get_enum("VendorState").items[2] == EnumItem(10, "charging", "充电")
    assert model.get_enum("VendorState").desc == "厂商状态"


def test_json_round_trip_and_legacy_cache():
    model = build_model()
    _ = model.point_refs
    restored = IedModel.from_dict(json.loads(json.dumps(model.to_dict())))
    assert restored.enum_types == model.enum_types
    assert restored.find_attribute("LD0/LLN0.State.cfg.inner.mode", "CF").type_id == "VendorState"
    assert restored.revision == model.revision
    assert IedModel.from_dict({"logicalDevices": []}).enum_types == ()
    assert DARef.from_dict({"name": "stVal", "iecType": "integer"}).b_type == ""


def test_same_type_id_is_scoped_to_its_model_and_changes_revision():
    a = build_model()
    b = build_model(SCL.replace('ord="10"', 'ord="11"'))
    a.validate_enum_value("LD0/LLN0.State.stVal", 10, "ST")
    with pytest.raises(ValueError, match="不属于枚举"):
        b.validate_enum_value("LD0/LLN0.State.stVal", 10, "ST")
    assert a.revision != b.revision


@pytest.mark.parametrize("value", [True, False, 1.5, 10.0, "10", "charging", 17])
def test_enum_rejects_coercion_and_unknown_members(value):
    with pytest.raises(ValueError):
        build_model().validate_enum_value("LD0/LLN0.State.stVal", value, "ST")


@pytest.mark.parametrize("value", [-1, 0, 10, 20, 99])
def test_actual_ordinals_are_not_array_indexes(value):
    build_model().validate_enum_value("LD0/LLN0.State.stVal", value, "ST")


def test_registry_replacement_does_not_reuse_previous_enum():
    registry = PointRegistry()
    build_registry_from_model(build_model(), registry)
    registry.validate_enum_value("LD0/LLN0.State.stVal", 20, "ST")
    build_registry_from_model(build_model(SCL.replace('ord="20"', 'ord="21"')), registry)
    with pytest.raises(ValueError):
        registry.validate_enum_value("LD0/LLN0.State.stVal", 20, "ST")
    registry.clear()
    registry.validate_enum_value("LD0/LLN0.State.stVal", 20, "ST")


@pytest.mark.parametrize(
    "xml, message",
    [
        (SCL.replace('ord="10"', 'ord="bad"'), "ord 必须是整数"),
        (SCL.replace('ord="10"', 'ord="0"'), "重复 ord"),
        (SCL.replace('<EnumVal ord="10"', "<EnumVal"), "ord 必须是整数"),
        (SCL.replace("</DataTypeTemplates>", '<EnumType id="VendorState"/></DataTypeTemplates>'), "重复的 EnumType"),
    ],
)
def test_invalid_enum_does_not_silently_become_zero(xml, message):
    with pytest.raises(ValueError, match=message):
        SclParser().parse_string(xml)


def test_missing_and_empty_enum_definitions_are_explicit():
    model = build_model(SCL.replace('type="VendorState"', 'type="MissingType"'))
    attribute = model.find_attribute("LD0/LLN0.State.stVal", "ST")
    assert "枚举定义未提供" in model.value_metadata(attribute)["enum_error"]
    with pytest.raises(ValueError, match="枚举定义未提供"):
        model.validate_enum_value("LD0/LLN0.State.stVal", 0, "ST")
    with pytest.raises(ValueError, match="没有选项"):
        EnumDefinition("Empty").validate_value(0)


def test_legacy_enum_without_type_keeps_numeric_fallback():
    model = build_model(SCL.replace('type="VendorState"', 'type=""'))
    model.validate_enum_value("LD0/LLN0.State.stVal", 20, "ST")


def test_cycle_is_reported_instead_of_losing_nested_bdas():
    with pytest.raises(ValueError, match="循环引用"):
        build_model(
            SCL.replace('name="mode" bType="Enum" type="VendorState"', 'name="mode" bType="Struct" type="Outer"')
        )


def test_selected_ied_does_not_mix_foreign_logical_devices():
    xml = SCL.replace(
        "<DataTypeTemplates>",
        """
    <IED name="IED2"><AccessPoint name="AP"><Server><LDevice inst="OtherLD">
    <LN0 lnClass="LLN0" lnType="LNType"/></LDevice></Server></AccessPoint></IED>
    <DataTypeTemplates>""",
    )
    assert [ld.name for ld in build_model(xml).lds] == ["LD0"]


def test_virtual_enum_registry_metadata_does_not_register_a_polling_point():
    registry = PointRegistry()
    registry.set_value_model(build_model())
    address = "LD0/LLN0.State.cfg.inner.mode"
    assert registry.get_ref(address) == address
    assert registry.get_fc(address) == "CF"
    assert registry.get_iec_type(address) == "integer"
    assert registry.get_mms_type(address) == "MMS_INTEGER"
    assert registry.point_refs == {}


def test_enum_writer_sends_integer_to_native_mms_and_rejects_unknown_value(monkeypatch):
    from src.proto.iec61850.core import writer as writer_module
    from src.proto.iec61850.core.writer import Iec61850Writer

    registry = PointRegistry()
    registry.set_value_model(build_model())
    address = "LD0/LLN0.State.cfg.inner.mode"
    native_write = Mock(return_value=0)
    monkeypatch.setattr(
        writer_module,
        "iec61850",
        SimpleNamespace(
            IedConnection_writeInt32Value=native_write,
            IED_ERROR_OK=0,
        ),
    )
    connection = SimpleNamespace(
        connection=object(),
        is_connected=True,
        ensure_connected=lambda: True,
        get_fc_value=lambda fc: f"FC_{fc}",
        reconnect_if_unhealthy=lambda _: False,
    )
    writer = Iec61850Writer(connection, registry)
    assert writer.write(address, 20)
    native_write.assert_called_once_with(connection.connection, address, "FC_CF", 20)
    assert type(native_write.call_args.args[3]) is int
    assert not writer.write(address, 17)
    assert "不属于枚举" in writer.last_error
    assert native_write.call_count == 1


@pytest.mark.parametrize("ordinal", [2**31, -(2**31) - 1])
def test_ordinals_cannot_overflow_native_int32(ordinal):
    with pytest.raises(ValueError, match="INT32"):
        EnumDefinition("Overflow", (EnumItem(ordinal, "overflow"),)).validate_value(ordinal)


def test_native_server_config_uses_control_model_api_and_checks_readback(monkeypatch):
    from src.proto.iec61850 import iec61850_server as server_module
    from src.proto.iec61850.iec61850_server import IEC61850Server

    model = build_model(
        SCL.replace('name="stVal" bType="Enum"', 'name="ctlModel" bType="Enum"')
        .replace('fc="ST"', 'fc="CF"')
        .replace('ord="20"', 'ord="3"')
    )
    server = object.__new__(IEC61850Server)
    server.scl_model = model
    server._server = object()
    server._is_running = True
    native_attribute, native_do = object(), object()
    server._builder = SimpleNamespace(
        resolve_da=lambda address: (native_attribute, address), _do_map={"LD0/LLN0.State": native_do}
    )
    server._log_manager = Mock()
    api = SimpleNamespace(
        IedServer_updateCtlModel=Mock(),
        IedServer_updateInt32AttributeValue=Mock(),
        IedServer_getInt32AttributeValue=Mock(return_value=3),
    )
    monkeypatch.setattr(server_module, "iec61850", api)
    address = "LD0/LLN0.State.ctlModel"
    assert server.set_enum_attribute(address, 3, "CF")
    api.IedServer_updateCtlModel.assert_called_once_with(server._server, native_do, 3)
    api.IedServer_updateInt32AttributeValue.assert_not_called()
    api.IedServer_getInt32AttributeValue.return_value = 0
    with pytest.raises(ValueError, match="读回不一致"):
        server.set_enum_attribute(address, 3, "CF")
