import sys
from types import ModuleType
from unittest.mock import patch

from src.proto.iec61850.core import mms_value
from src.proto.iec61850.plugins.reports import callback
from src.proto.iec61850.plugins.reports.callback import (
    _infer_report_value_type,
    _select_report_value_ref,
)
from src.proto.iec61850.plugins.reports.report_tree import ReportTreeBuilder, stringify_value


class FakeValue:
    def __init__(self, mms_type, value):
        self.mms_type = mms_type
        self.value = value

    def __str__(self):
        return "<Swig Object of type 'sMmsValue *'>"


class FakeIec61850:
    MMS_STRUCTURE = 1
    MMS_ARRAY = 2
    MMS_FLOAT = 3
    MMS_INTEGER = 4
    MMS_UNSIGNED = 5
    MMS_BOOLEAN = 6
    MMS_BIT_STRING = 7
    MMS_VISIBLE_STRING = 8
    MMS_STRING = 9
    MMS_UTC_TIME = 10

    @staticmethod
    def MmsValue_getType(value):
        return value.mms_type

    @staticmethod
    def MmsValue_getTypeString(value):
        names = {
            1: "structure",
            2: "array",
            3: "float",
            4: "integer",
            5: "unsigned",
            6: "boolean",
        }
        return names.get(value.mms_type, "unknown")

    @staticmethod
    def MmsValue_getArraySize(value):
        return len(value.value)

    @staticmethod
    def MmsValue_getElement(value, index):
        return value.value[index]

    @staticmethod
    def MmsValue_toFloat(value):
        return float(value.value)

    @staticmethod
    def MmsValue_toInt32(value):
        return int(value.value)

    @staticmethod
    def MmsValue_toUint32(value):
        return int(value.value)

    @staticmethod
    def MmsValue_getBoolean(value):
        return bool(value.value)

    @staticmethod
    def MmsValue_toString(value):
        return str(value.value)

    @staticmethod
    def ClientReport_getDataSetValues(report):
        return report

    @staticmethod
    def ClientReport_getDataReference(report, index):
        return "PCS001MEAS/dcGGIO1$MX$AnIn1"


def test_prefers_full_dataset_member_over_do_only_report_reference():
    data_ref = "PCS001MEAS/dcGGIO1$MX$AnIn1"
    dataset_ref = "PCS001MEAS/dcGGIO1.AnIn1.mag.f"

    selected = _select_report_value_ref(data_ref, dataset_ref)

    assert selected == dataset_ref
    assert _infer_report_value_type(selected) == "float"


def test_recursively_converts_analogue_report_structure_without_swig_values():
    value = FakeValue(
        FakeIec61850.MMS_STRUCTURE,
        [
            FakeValue(FakeIec61850.MMS_STRUCTURE, [FakeValue(FakeIec61850.MMS_FLOAT, 12.5)]),
            FakeValue(FakeIec61850.MMS_INTEGER, 0),
            FakeValue(FakeIec61850.MMS_UNSIGNED, 1000),
        ],
    )

    fake_package = ModuleType("pyiec61850")
    fake_package.pyiec61850 = FakeIec61850
    with patch.object(mms_value, "HAS_IEC61850", True), patch.dict(sys.modules, {"pyiec61850": fake_package}):
        converted = mms_value.mms_value_to_python(value, "float")

    assert converted == [[12.5], 0, 1000]
    assert "Swig Object" not in str(converted)


def test_legacy_swig_value_uses_runtime_type_instead_of_float_first_guess():
    value = FakeValue(FakeIec61850.MMS_INTEGER, 7)
    fake_package = ModuleType("pyiec61850")
    fake_package.pyiec61850 = FakeIec61850

    with patch.object(mms_value, "HAS_IEC61850", True), patch.dict(sys.modules, {"pyiec61850": fake_package}):
        converted = stringify_value(value)

    assert converted == 7
    assert isinstance(converted, int)


def test_report_callback_and_tree_keep_dcggio_analogue_as_mag_f():
    analogue = FakeValue(
        FakeIec61850.MMS_STRUCTURE,
        [
            FakeValue(FakeIec61850.MMS_STRUCTURE, [FakeValue(FakeIec61850.MMS_FLOAT, 12.5)]),
            FakeValue(FakeIec61850.MMS_INTEGER, 0),
            FakeValue(FakeIec61850.MMS_UNSIGNED, 1000),
        ],
    )
    report = FakeValue(FakeIec61850.MMS_ARRAY, [analogue])
    dataset_members = ["PCS001MEAS/dcGGIO1.AnIn1.mag.f"]
    fake_package = ModuleType("pyiec61850")
    fake_package.pyiec61850 = FakeIec61850

    with (
        patch.object(mms_value, "HAS_IEC61850", True),
        patch.object(callback, "iec61850", FakeIec61850, create=True),
        patch.dict(sys.modules, {"pyiec61850": fake_package}),
    ):
        entry = callback._parse_client_report(report, "PCS001MEAS/LLN0.RP.rcb", dataset_members)

    assert entry is not None
    assert entry.data_values == {"PCS001MEAS/dcGGIO1.AnIn1.mag.f": [[12.5], 0, 1000]}

    tree = ReportTreeBuilder().build({"data_values": entry.data_values})
    do_node = tree[0]["children"][0]["children"][0]
    mag_node = next(child for child in do_node["children"] if child["label"] == "mag")
    assert mag_node["children"][0]["label"] == "f"
    assert mag_node["children"][0]["value"] == 12.5
