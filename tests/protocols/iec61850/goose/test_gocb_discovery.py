from types import SimpleNamespace
from unittest.mock import patch

from src.proto.iec61850.model.discovery import ModelDiscoveryService
from src.proto.iec61850.model.ied_model import GoCBRef


class _Native:
    IED_ERROR_OK = 0

    def __init__(self, errors):
        self.errors = iter(errors)
        self.created = []
        self.destroyed = []

    def ClientGooseControlBlock_create(self, ref):
        block = SimpleNamespace(ref=ref)
        self.created.append(block)
        return block

    def IedConnection_getGoCBValues(self, _conn, _ref, block):
        error = next(self.errors)
        return block, error

    def ClientGooseControlBlock_destroy(self, block):
        self.destroyed.append(block)

    @staticmethod
    def ClientGooseControlBlock_getDstAddress_appid(_block):
        return 0x1001

    @staticmethod
    def ClientGooseControlBlock_getDatSet(_block):
        return "IEDLD/LLN0$dsTrip"

    @staticmethod
    def ClientGooseControlBlock_getConfRev(_block):
        return 7

    @staticmethod
    def ClientGooseControlBlock_getGoID(_block):
        return "trip"

    @staticmethod
    def IedClientError_toString(error):
        return "IED_ERROR_UNKNOWN" if error == 99 else f"IED_ERROR_{error}"


def test_gocb_read_uses_standard_acsi_reference_first():
    native = _Native([0])

    with (
        patch("src.proto.iec61850.model.discovery.iec61850", native, create=True),
        patch(
            "src.proto.iec61850.model.discovery.call_gil_safe",
            side_effect=lambda api, name, *args: getattr(api, name)(*args),
        ),
    ):
        result = ModelDiscoveryService()._read_gocb_info(object(), "IEDLD", "IEDLD/LLN0", "gocbPub1")

    assert [item.ref for item in native.created] == ["IEDLD/LLN0.gocbPub1"]
    assert result.go_cb_ref == "IEDLD/LLN0$GO$gocbPub1"
    assert result.detail_status == "complete"
    assert result.app_id == 0x1001
    assert result.data_set_ref == "IEDLD/LLN0$dsTrip"


def test_gocb_read_falls_back_to_go_reference():
    native = _Native([99, 0])

    with (
        patch("src.proto.iec61850.model.discovery.iec61850", native, create=True),
        patch(
            "src.proto.iec61850.model.discovery.call_gil_safe",
            side_effect=lambda api, name, *args: getattr(api, name)(*args),
        ),
    ):
        result = ModelDiscoveryService()._read_gocb_info(object(), "IEDLD", "IEDLD/LLN0", "gocbPub1")

    assert [item.ref for item in native.created] == [
        "IEDLD/LLN0.gocbPub1",
        "IEDLD/LLN0.GO.gocbPub1",
    ]
    assert result.detail_status == "complete"
    assert len(native.destroyed) == 2


def test_gocb_read_preserves_partial_result_and_error_details():
    native = _Native([99, 99])

    with (
        patch("src.proto.iec61850.model.discovery.iec61850", native, create=True),
        patch(
            "src.proto.iec61850.model.discovery.call_gil_safe",
            side_effect=lambda api, name, *args: getattr(api, name)(*args),
        ),
    ):
        result = ModelDiscoveryService()._read_gocb_info(object(), "IEDLD", "IEDLD/LLN0", "gocbPub1")

    assert result.detail_status == "partial"
    assert result.discovery_error_code == 99
    assert result.discovery_error == "IED_ERROR_UNKNOWN"
    assert result.attempted_refs == (
        "IEDLD/LLN0.gocbPub1",
        "IEDLD/LLN0.GO.gocbPub1",
    )


def test_gocb_cache_round_trip_keeps_discovery_fields():
    source = GoCBRef(
        name="gocbPub1",
        ref="IEDLD/LLN0.gocbPub1",
        go_cb_ref="IEDLD/LLN0$GO$gocbPub1",
        go_id="trip",
        app_id=0x1001,
        data_set_ref="IEDLD/LLN0$dsTrip",
        conf_rev=7,
        detail_status="partial",
        discovery_error_code=99,
        discovery_error="IED_ERROR_UNKNOWN",
        attempted_refs=("IEDLD/LLN0.gocbPub1",),
    )

    restored = GoCBRef.from_dict(source.to_dict())

    assert restored == source
