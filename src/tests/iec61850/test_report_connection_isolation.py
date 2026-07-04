from types import SimpleNamespace

from src.proto.iec61850.core.native_calls import call_gil_safe
from src.proto.iec61850.iec61850_client import IEC61850Client
from src.proto.iec61850.plugins.reports import ReportsPlugin
from src.proto.iec61850.plugins.reports import callback as callback_module


def test_gil_safe_call_prefers_binding_wrapper():
    calls = []
    native = SimpleNamespace(
        pyWrap_IedConnection_readObject=lambda *args: calls.append(("safe", args)) or "value",
        IedConnection_readObject=lambda *args: calls.append(("raw", args)) or "unsafe",
    )

    assert call_gil_safe(native, "IedConnection_readObject", "conn", "ref", "fc") == "value"
    assert calls == [("safe", ("conn", "ref", "fc"))]


def test_client_uses_a_dedicated_report_connection(monkeypatch):
    client = IEC61850Client(ip="127.0.0.1", port=102, model_name="IED")
    calls = []

    monkeypatch.setattr(client._conn, "connect", lambda **_kwargs: calls.append("main-connect") or True)
    monkeypatch.setattr(client._report_conn, "connect", lambda **_kwargs: calls.append("report-connect") or True)
    monkeypatch.setattr(client._report_conn, "disconnect", lambda: calls.append("report-disconnect"))
    monkeypatch.setattr(client._conn, "disconnect", lambda: calls.append("main-disconnect"))
    monkeypatch.setattr(client.reports, "prepare_disconnect", lambda: calls.append("reports-drained"))

    assert client._report_conn is not client._conn
    assert client.reports._connection is client._report_conn
    assert client.connect(auto_discover=False) is True
    client.disconnect()

    assert calls == [
        "main-connect",
        "report-connect",
        "reports-drained",
        "report-disconnect",
        "main-disconnect",
    ]


def test_shutdown_all_only_removes_callbacks_for_own_connection(monkeypatch):
    first_connection = SimpleNamespace(connection=object())
    second_connection = SimpleNamespace(connection=object())
    first = callback_module._CallbackInfo(rcb_ref="LD0/LLN0.rp01", connection=first_connection)
    second = callback_module._CallbackInfo(rcb_ref="LD1/LLN0.rp01", connection=second_connection)
    monkeypatch.setitem(callback_module._CALLBACK_REGISTRY, first.rcb_ref, first)
    monkeypatch.setitem(callback_module._CALLBACK_REGISTRY, second.rcb_ref, second)

    callback_module.ReportCallbackHandler.shutdown_all(first_connection)

    assert first.rcb_ref not in callback_module._CALLBACK_REGISTRY
    assert callback_module._CALLBACK_REGISTRY[second.rcb_ref] is second


def test_prepare_disconnect_disables_reports_before_uninstall(monkeypatch):
    connection = SimpleNamespace(is_connected=True)
    plugin = ReportsPlugin()
    plugin._connection = connection
    events = []

    monkeypatch.setattr(
        callback_module.ReportCallbackHandler,
        "get_active_rcbs",
        lambda owner: [{"rcb_ref": "LD0/LLN0.rp01"}] if owner is connection else [],
    )
    monkeypatch.setattr(
        plugin,
        "_set_rpt_ena_raw",
        lambda ref, enabled: events.append(("disable", ref, enabled)) or True,
    )
    monkeypatch.setattr(
        callback_module.ReportCallbackHandler,
        "wait_for_idle",
        lambda owner, timeout: events.append(("idle", owner, timeout)) or True,
    )
    monkeypatch.setattr(
        callback_module.ReportCallbackHandler,
        "shutdown_all",
        lambda owner: events.append(("uninstall", owner)),
    )

    plugin.prepare_disconnect()

    assert events == [
        ("disable", "LD0/LLN0.rp01", False),
        ("idle", connection, 3.0),
        ("uninstall", connection),
    ]
