import asyncio

from src.proto.iec61850.defs.types import ReportDataEntry
from src.proto.iec61850.plugins.reports import callback
from src.web.api.channel import report as report_api
from src.web.api.schemas.report import ReportDataRequest


def test_cache_state_does_not_serialize_report_values(monkeypatch):
    info = callback._CallbackInfo(rcb_ref="LD0/LLN0.rp01")
    monkeypatch.setitem(callback._CALLBACK_REGISTRY, info.rcb_ref, info)

    assert callback.ReportCallbackHandler.get_cache_state(info.rcb_ref) == (0, 0)

    entry = ReportDataEntry(uid=42, data_values={"LD0/GGIO1.Ind1": [[43.0], 0, 0]})
    info.data_cache.append(entry)

    assert callback.ReportCallbackHandler.get_cache_state(info.rcb_ref) == (1, 42)


def test_report_data_short_circuits_when_latest_uid_is_unchanged(monkeypatch):
    class FakeReports:
        @staticmethod
        def get_report_data_state(_rcb_ref):
            return 7, 42

        @staticmethod
        def get_report_data(*_args, **_kwargs):
            raise AssertionError("unchanged poll must not serialize report values")

    monkeypatch.setattr(report_api, "_get_reports_plugin", lambda *_args: FakeReports())
    body = ReportDataRequest(
        channel_id=1,
        rcb_ref="LD0/LLN0.rp01",
        limit=100,
        known_latest_uid=42,
    )

    response = asyncio.run(report_api.get_report_data(body, object()))

    assert response.data == {
        "data": [],
        "total": 7,
        "latest_uid": 42,
        "unchanged": True,
    }
