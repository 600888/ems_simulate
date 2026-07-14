from types import SimpleNamespace

from src.proto.iec61850 import iec61850_client as client_module
from src.proto.iec61850.core.native_calls import call_gil_safe
from src.proto.iec61850.iec61850_client import IEC61850Client
from src.proto.iec61850.plugins import reports as reports_module
from src.proto.iec61850.plugins.reports import ReportsPlugin
from src.proto.iec61850.plugins.reports import brcb as brcb_module
from src.proto.iec61850.plugins.reports import callback as callback_module
from src.proto.iec61850.plugins.reports import urcb as urcb_module
from src.proto.iec61850.plugins.reports.brcb import BrcbHandler
from src.proto.iec61850.plugins.reports.urcb import UrcbHandler


def test_gil_safe_call_prefers_binding_wrapper():
    calls = []
    native = SimpleNamespace(
        pyWrap_IedConnection_readObject=lambda *args: calls.append(("safe", args)) or "value",
        IedConnection_readObject=lambda *args: calls.append(("raw", args)) or "unsafe",
    )

    assert call_gil_safe(native, "IedConnection_readObject", "conn", "ref", "fc") == "value"
    assert calls == [("safe", ("conn", "ref", "fc"))]


def test_urcb_gi_skips_raw_dedicated_api_without_safe_wrapper(monkeypatch):
    calls = []
    monkeypatch.setattr(
        urcb_module,
        "iec61850",
        SimpleNamespace(IedConnection_triggerGIReport=lambda *_args: calls.append("raw") or 0),
        raising=False,
    )

    assert UrcbHandler._trigger_gi_direct(object(), "LD0/LLN0.rp01") is False
    assert calls == []


def test_brcb_gi_skips_raw_dedicated_api_without_safe_wrapper(monkeypatch):
    calls = []
    monkeypatch.setattr(
        brcb_module,
        "iec61850",
        SimpleNamespace(IedConnection_triggerGIReport=lambda *_args: calls.append("raw") or 0),
        raising=False,
    )

    assert BrcbHandler._trigger_gi_direct(object(), "LD0/LLN0.br01") is False
    assert calls == []


def test_urcb_gi_attribute_write_uses_safe_wrapper(monkeypatch):
    calls = []
    value = object()
    fake_native = SimpleNamespace(
        IEC61850_FC_RP=99,
        IED_ERROR_OK=0,
        MmsValue_newBoolean=lambda enabled: value if enabled else None,
        MmsValue_delete=lambda item: calls.append(("delete", item)),
        pyWrap_IedConnection_writeObject=lambda *args: calls.append(("safe", args)) or 0,
        IedConnection_writeObject=lambda *_args: calls.append(("raw",)) or 0,
    )
    monkeypatch.setattr(urcb_module, "iec61850", fake_native, raising=False)
    monkeypatch.setattr(UrcbHandler, "_gi_attribute_refs", lambda _ref: ["LD0/LLN0.rp01.GI"])

    connection = object()
    assert UrcbHandler._trigger_gi_write_object(connection, "LD0/LLN0.rp01") is True
    assert calls == [
        ("safe", (connection, "LD0/LLN0.rp01.GI", 99, value)),
        ("delete", value),
    ]


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


def test_cached_urcb_restore_primes_only_browse_association(monkeypatch):
    browse_native = object()
    report_native = object()
    browse_connection = SimpleNamespace(connection=browse_native, is_connected=True)
    report_connection = SimpleNamespace(connection=report_native, is_connected=True)
    plugin = ReportsPlugin()
    plugin._browse_connection = browse_connection
    plugin._connection = report_connection
    plugin._client = SimpleNamespace()
    events = []

    fake_native = SimpleNamespace(
        IED_ERROR_OK=0,
        IedConnection_getLogicalNodeDirectory=lambda conn, ln, acsi: events.append((conn, ln, acsi)) or (object(), 0),
    )
    monkeypatch.setattr(reports_module, "iec61850", fake_native, raising=False)
    monkeypatch.setattr(reports_module, "get_list_from_linked_list", lambda _raw: ["rpPcs1Data101"])

    cached = {
        "ref": "LC001PCS01/LLN0.rpPcs1Data101",
        "name": "rpPcs1Data101",
        "rcb_type": "URCB",
    }
    assert plugin.restore_cached_rcbs([cached]) is True

    assert events == [
        (browse_native, "LC001PCS01/LLN0", reports_module.AcsiClass.URCB),
    ]
    assert plugin._rcb_type_map[cached["ref"]] == "URCB"
    assert plugin._rcb_detail_cache[cached["ref"]] == cached


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


def test_batch_enable_suspends_report_dispatch_until_all_rcbs_are_registered(monkeypatch):
    plugin = ReportsPlugin()
    plugin._connection = SimpleNamespace(is_connected=True)
    events = []

    monkeypatch.setattr(
        plugin,
        "_apply_config_once",
        lambda ref, *_args: events.append(("apply", ref)) or True,
    )
    monkeypatch.setattr(
        callback_module.ReportCallbackHandler,
        "suspend_dispatch",
        lambda owner, timeout: events.append(("suspend", owner, timeout)) or True,
    )
    monkeypatch.setattr(
        callback_module.ReportCallbackHandler,
        "resume_dispatch",
        lambda owner: events.append(("resume", owner)),
    )

    refs = ["LD0/LLN0.alarm01", "LD0/LLN0.measure01", "LD0/LLN0.status01"]
    assert plugin.apply_config_batch(refs, rpt_ena=True) == [(ref, True, "") for ref in refs]
    assert events == [
        ("suspend", plugin._connection, 3.0),
        ("apply", refs[0]),
        ("apply", refs[1]),
        ("apply", refs[2]),
        ("resume", plugin._connection),
    ]


def test_batch_enable_resumes_report_dispatch_after_exception(monkeypatch):
    plugin = ReportsPlugin()
    plugin._connection = SimpleNamespace(is_connected=True)
    events = []

    monkeypatch.setattr(
        callback_module.ReportCallbackHandler,
        "suspend_dispatch",
        lambda owner, timeout: events.append("suspend") or True,
    )
    monkeypatch.setattr(
        callback_module.ReportCallbackHandler,
        "resume_dispatch",
        lambda owner: events.append("resume"),
    )
    monkeypatch.setattr(plugin, "_apply_config_once", lambda *_args: (_ for _ in ()).throw(RuntimeError("boom")))

    assert plugin.apply_config_batch(["LD0/LLN0.rp01"], rpt_ena=True) == [("LD0/LLN0.rp01", False, "boom")]
    assert events == ["suspend", "resume"]


def test_batch_disable_does_not_wait_between_rcbs(monkeypatch):
    plugin = ReportsPlugin()
    plugin._connection = SimpleNamespace(is_connected=True)
    events = []

    monkeypatch.setattr(
        plugin,
        "_apply_config_once",
        lambda ref, *_args: events.append(("apply", ref)) or True,
    )
    monkeypatch.setattr(reports_module.time, "sleep", lambda seconds: events.append(("sleep", seconds)))

    refs = ["LD0/LLN0.rp01", "LD0/LLN0.rp02"]
    assert plugin.apply_config_batch(refs, rpt_ena=False) == [(ref, True, "") for ref in refs]
    assert events == [("apply", refs[0]), ("apply", refs[1])]


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


def test_disabled_report_reuses_native_subscription(monkeypatch):
    connection = SimpleNamespace(connection=object())
    events = []

    class FakeHandler:
        def __init__(self, *_args):
            pass

        def pause(self):
            events.append("pause")

        def resume(self):
            events.append("resume")

        def close(self):
            events.append("close")

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
            events.append("subscribe")
            return True

        def deleteEventHandler(self):
            events.append("delete")

    monkeypatch.setattr(callback_module, "HAS_IEC61850", True)
    monkeypatch.setattr(callback_module, "_PyRCBHandler", FakeHandler)
    monkeypatch.setattr(
        callback_module,
        "iec61850",
        SimpleNamespace(
            RCBSubscriber=FakeSubscriber,
            IedConnection_uninstallReportHandler=lambda *_args: events.append("native-uninstall"),
        ),
        raising=False,
    )

    ref = "LD0/LLN0.rp01"
    assert callback_module.ReportCallbackHandler.install(connection, ref, rpt_id="rp01", rcb_type="URCB")
    assert callback_module.ReportCallbackHandler.deactivate(connection, ref)
    assert not callback_module.ReportCallbackHandler.is_active(ref, connection)
    assert callback_module.ReportCallbackHandler.install(connection, ref, rpt_id="rp01", rcb_type="URCB")
    assert callback_module.ReportCallbackHandler.is_active(ref, connection)

    assert events == ["subscribe", "pause", "resume"]
    callback_module.ReportCallbackHandler.shutdown_all(connection)


def test_report_dispatch_suspension_is_nested_and_preserves_active_state(monkeypatch):
    connection = SimpleNamespace(connection=object())
    events = []

    class FakeHandler:
        def pause(self):
            events.append("pause")

        def resume(self):
            events.append("resume")

    active = callback_module._CallbackInfo(
        rcb_ref="LD0/LLN0.rp01",
        connection=connection,
        handler=FakeHandler(),
        active=True,
    )
    inactive = callback_module._CallbackInfo(
        rcb_ref="LD0/LLN0.rp02",
        connection=connection,
        handler=FakeHandler(),
        active=False,
    )
    monkeypatch.setitem(callback_module._CALLBACK_REGISTRY, active.rcb_ref, active)
    monkeypatch.setitem(callback_module._CALLBACK_REGISTRY, inactive.rcb_ref, inactive)

    assert callback_module.ReportCallbackHandler.suspend_dispatch(connection)
    assert callback_module.ReportCallbackHandler.suspend_dispatch(connection)
    assert events == ["pause", "pause"]
    assert active.active is True
    assert inactive.active is False

    callback_module.ReportCallbackHandler.resume_dispatch(connection)
    assert events == ["pause", "pause"]
    callback_module.ReportCallbackHandler.resume_dispatch(connection)
    assert events == ["pause", "pause", "resume"]


def test_new_report_handler_starts_paused_during_bulk_registration(monkeypatch):
    connection = SimpleNamespace(connection=object())
    events = []

    class FakeHandler:
        def __init__(self, *_args):
            events.append("create")

        def pause(self):
            events.append("pause")

        def resume(self):
            events.append("resume")

        def close(self):
            pass

    class FakeSubscriber:
        def setIedConnection(self, _conn):
            pass

        def setRcbReference(self, _ref):
            pass

        def setRcbRptId(self, _rpt_id):
            pass

        def setEventHandler(self, _handler):
            events.append("bind")

        def subscribe(self):
            events.append("subscribe")
            return True

        def deleteEventHandler(self):
            pass

    monkeypatch.setattr(callback_module, "HAS_IEC61850", True)
    monkeypatch.setattr(callback_module, "_PyRCBHandler", FakeHandler)
    monkeypatch.setattr(
        callback_module,
        "iec61850",
        SimpleNamespace(
            RCBSubscriber=FakeSubscriber,
            IedConnection_uninstallReportHandler=lambda *_args: None,
        ),
        raising=False,
    )

    assert callback_module.ReportCallbackHandler.suspend_dispatch(connection)
    assert callback_module.ReportCallbackHandler.install(
        connection,
        "LD0/LLN0.rp01",
        rpt_id="rp01",
        rcb_type="URCB",
    )
    assert events == ["create", "pause", "bind", "subscribe"]

    callback_module.ReportCallbackHandler.resume_dispatch(connection)
    assert events == ["create", "pause", "bind", "subscribe", "resume"]
    callback_module.ReportCallbackHandler.shutdown_all(connection)


def test_identical_rcb_refs_are_isolated_by_connection(monkeypatch):
    events = []

    class FakeHandler:
        def __init__(self, *_args):
            pass

        def close(self):
            pass

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
            return True

        def deleteEventHandler(self):
            pass

    monkeypatch.setattr(callback_module, "HAS_IEC61850", True)
    monkeypatch.setattr(callback_module, "_PyRCBHandler", FakeHandler)
    monkeypatch.setattr(
        callback_module,
        "iec61850",
        SimpleNamespace(
            RCBSubscriber=FakeSubscriber,
            IedConnection_uninstallReportHandler=lambda conn, *_args: events.append(conn),
        ),
        raising=False,
    )

    first = SimpleNamespace(connection=object())
    second = SimpleNamespace(connection=object())
    ref = "LD0/LLN0.rp01"
    assert callback_module.ReportCallbackHandler.install(first, ref, rpt_id="rp01", rcb_type="URCB")
    assert callback_module.ReportCallbackHandler.install(second, ref, rpt_id="rp01", rcb_type="URCB")
    assert callback_module.ReportCallbackHandler.is_active(ref, first)
    assert callback_module.ReportCallbackHandler.is_active(ref, second)

    callback_module.ReportCallbackHandler.shutdown_all(first)
    assert not callback_module.ReportCallbackHandler.is_active(ref, first)
    assert callback_module.ReportCallbackHandler.is_active(ref, second)
    assert events == [first.connection]
    callback_module.ReportCallbackHandler.shutdown_all(second)
