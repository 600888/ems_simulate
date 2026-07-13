from types import SimpleNamespace

from src.proto.iec61850.defs.types import RCBInfo
from src.proto.iec61850.plugins.reports import ReportsPlugin, UrcbHandler
from src.proto.iec61850.plugins.reports import brcb as brcb_module
from src.proto.iec61850.plugins.reports import callback as callback_module


def test_brcb_parser_reads_owner_and_reservation_time(monkeypatch):
    native = SimpleNamespace(
        ClientReportControlBlock_getRptEna=lambda _rcb: True,
        ClientReportControlBlock_getOwner=lambda _rcb: object(),
        ClientReportControlBlock_getResvTms=lambda _rcb: -1,
    )
    monkeypatch.setattr(brcb_module, "iec61850", native, raising=False)
    monkeypatch.setattr(brcb_module, "mms_value_to_python", lambda _value: "192.0.2.10")

    info = brcb_module.BrcbHandler._parse_rcb(object(), "LD0/LLN0.brcb01", "BRCB")

    assert info.rpt_ena is True
    assert info.owner == "192.0.2.10"
    assert info.resv_tms == -1


def test_rcb_dict_marks_only_external_reservation_as_locked(monkeypatch):
    plugin = ReportsPlugin()
    info = RCBInfo(ref="LD0/LLN0.brcb01", rcb_type="BRCB", rpt_ena=True, resv_tms=30)

    monkeypatch.setattr(callback_module.ReportCallbackHandler, "is_active", lambda _ref, *_args: False)
    external = plugin._rcb_info_to_dict(info)
    assert external["reserved"] is True
    assert external["locked"] is True

    monkeypatch.setattr(callback_module.ReportCallbackHandler, "is_active", lambda _ref, *_args: True)
    local = plugin._rcb_info_to_dict(info)
    assert local["reserved"] is True
    assert local["locked"] is False


def test_refresh_rcb_states_uses_live_urcb_resv(monkeypatch):
    plugin = ReportsPlugin()
    plugin._browse_connection = SimpleNamespace(is_connected=True)
    monkeypatch.setattr(plugin, "restore_cached_rcbs", lambda _rcbs: True)
    live = RCBInfo(
        ref="LD0/LLN0.urcb01",
        rcb_type="URCB",
        rpt_ena=False,
        resv=True,
        owner="192.0.2.20",
    )
    monkeypatch.setattr(UrcbHandler, "get_rcb_values", lambda *_args: live)
    monkeypatch.setattr(callback_module.ReportCallbackHandler, "is_active", lambda _ref, *_args: False)

    result = plugin.refresh_rcb_states([{"ref": live.ref, "rcb_type": "URCB", "name": "urcb01", "rpt_ena": False}])

    assert result[0]["resv"] is True
    assert result[0]["reserved"] is True
    assert result[0]["locked"] is True
    assert result[0]["owner"] == "192.0.2.20"


def test_refresh_rcb_states_skips_per_rcb_reads_when_cache_prime_fails(monkeypatch):
    plugin = ReportsPlugin()
    plugin._browse_connection = SimpleNamespace(is_connected=True)
    monkeypatch.setattr(plugin, "restore_cached_rcbs", lambda _rcbs: False)
    monkeypatch.setattr(
        UrcbHandler,
        "get_rcb_values",
        lambda *_args: (_ for _ in ()).throw(AssertionError("must not read stale RCB refs")),
    )
    cached = [{"ref": "OLD/LLN0.rp01", "rcb_type": "URCB", "rpt_ena": False}]

    assert plugin.refresh_rcb_states(cached) == cached
