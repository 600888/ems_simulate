"""DataSet reference compatibility tests."""

from src.web.api.channel.iec61850 import _dataset_ref_aliases, _normalize_dataset_ref


def test_dataset_object_and_mms_refs_normalize_to_same_value():
    assert _normalize_dataset_ref("PCS01PIGO/LLN0.dsGOOSE0") == "PCS01PIGO/LLN0$dsGOOSE0"
    assert _normalize_dataset_ref("PCS01PIGO/LLN0$dsGOOSE0") == "PCS01PIGO/LLN0$dsGOOSE0"


def test_dataset_ref_aliases_include_mms_and_object_forms():
    assert _dataset_ref_aliases("PCS01PIGO/LLN0.dsGOOSE0") == (
        "PCS01PIGO/LLN0$dsGOOSE0",
        "PCS01PIGO/LLN0.dsGOOSE0",
    )
