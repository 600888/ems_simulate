from types import SimpleNamespace

from src.enums.points.base_point import BasePoint
from src.proto.iec61850.core import reader as reader_module
from src.proto.iec61850.defs.constants import IecType
from src.proto.iec61850.defs.mms_types import (
    BTYPE_TO_MMS_TYPE,
    MmsType,
    iec_type_from_mms_type,
    mms_type_from_native,
)
from src.proto.iec61850.model import discovery as discovery_module
from src.proto.iec61850.model.ied_model import DARef, DORef, IedModel, LDModel, LNModel
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


def test_mms_type_keeps_legacy_iec_type_compatibility():
    assert iec_type_from_mms_type(MmsType.UNSIGNED) is IecType.INTEGER
    assert iec_type_from_mms_type(MmsType.BIT_STRING) is IecType.INTEGER
    assert iec_type_from_mms_type(MmsType.UTC_TIME) is IecType.TIMESTAMP


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
                                        path="mag.f",
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
