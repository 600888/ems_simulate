from types import SimpleNamespace

from src.proto.iec61850 import iec61850_client as client_module
from src.proto.iec61850.core.native_calls import call_gil_safe
from src.proto.iec61850.iec61850_client import IEC61850Client
from src.proto.iec61850.plugins import reports as reports_module
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
    class FakeConnection:
        def __init__(self, _ip, _port, model_name="", ld_name="", **_kwargs):
            self.connection = object()
            self.is_connected = False
            self.model_name = model_name
            self.ld_name = ld_name
            self._discovered_lds = []

        def connect(self, **_kwargs):
            self.is_connected = True
            return True

        def disconnect(self):
            self.is_connected = False

    monkeypatch.setattr(client_module, "HAS_IEC61850", True)
    monkeypatch.setattr(client_module, "Iec61850Connection", FakeConnection)
    monkeypatch.setattr(reports_module, "HAS_IEC61850", True)
    monkeypatch.setattr(
        client_module,
        "_register_builtin_plugins",
        lambda registry: registry.register("reports", ReportsPlugin),
    )

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


def test_report_install_subscribes_outside_callback_lock(monkeypatch):
    connection = SimpleNamespace(connection=object())
    events = []

    class FakeHandler:
        def __init__(self, *_args):
            pass

        def close(self):
            events.append("handler-close")

    class FakeSubscriber:
        def setIedConnection(self, _conn):
            pass

        def setRcbReference(self, _ref):
            pass

        def setRcbRptId(self, _rpt_id):
            pass

        def setEventHandler(self, _handler):
            pass

        def subscribe(self):
            acquired = callback_module._CALLBACK_LOCK.acquire(blocking=False)
            if acquired:
                callback_module._CALLBACK_LOCK.release()
            events.append(("subscribe-lock-free", acquired))
            return True

        def deleteEventHandler(self):
            events.append("delete")

    fake_native = SimpleNamespace(
        RCBSubscriber=FakeSubscriber,
        IedConnection_uninstallReportHandler=lambda *_args: events.append("native-uninstall"),
    )
    monkeypatch.setattr(callback_module, "HAS_IEC61850", True)
    monkeypatch.setattr(callback_module, "iec61850", fake_native, raising=False)
    monkeypatch.setattr(callback_module, "_PyRCBHandler", FakeHandler)

    assert callback_module.ReportCallbackHandler.install(
        connection,
        "LD0/LLN0.rp01",
        rpt_id="rp01",
        rcb_type="URCB",
    )

    assert events == [("subscribe-lock-free", True)]
    callback_module.ReportCallbackHandler.shutdown_all(connection)


def test_report_uninstall_waits_for_idle_before_native_cleanup(monkeypatch):
    connection = SimpleNamespace(connection=object())
    events = []

    class FakeHandler:
        def close(self):
            events.append("handler-close")

    class FakeSubscriber:
        def deleteEventHandler(self):
            events.append("delete")

    info = callback_module._CallbackInfo(
        rcb_ref="LD0/LLN0.rp01",
        connection=connection,
        handler=FakeHandler(),
        subscriber=FakeSubscriber(),
        mms_ref="LD0/LLN0.RP.rp01",
    )
    monkeypatch.setitem(callback_module._CALLBACK_REGISTRY, info.rcb_ref, info)
    monkeypatch.setattr(callback_module, "HAS_IEC61850", True)
    monkeypatch.setattr(
        callback_module,
        "iec61850",
        SimpleNamespace(IedConnection_uninstallReportHandler=lambda *_args: events.append("native-uninstall")),
        raising=False,
    )
    monkeypatch.setattr(
        callback_module.ReportCallbackHandler,
        "wait_for_idle",
        lambda owner, timeout: events.append(("idle", owner, timeout)) or True,
    )

    assert callback_module.ReportCallbackHandler.uninstall(connection, info.rcb_ref)

    assert events == [
        "handler-close",
        ("idle", connection, 3.0),
        "delete",
        ("idle", connection, 1.0),
        "native-uninstall",
    ]
