"""IEC 61850 control-object write regression tests."""

from types import SimpleNamespace

import pytest

from src.proto.iec61850.core import writer as writer_module
from src.proto.iec61850.core.writer import Iec61850Writer


class _Registry:
    def get_ref(self, _address):
        return "IEDLD0/GGIO1.Pos.Oper.ctlVal"

    def get_fc(self, _address):
        return "CO"

    def get_iec_type(self, _address):
        return "boolean"


class _Connection:
    connection = object()
    is_connected = True

    def ensure_connected(self):
        return True

    def reconnect_if_unhealthy(self, _reason):
        return False


class _SetMagRegistry:
    def get_ref(self, _address):
        return "LD0/CTRL1.CtrlBlockPower.setMag.i"

    def get_fc(self, _address):
        return "SP"

    def get_iec_type(self, _address):
        return "integer"

    def get_mms_type(self, _address):
        return "MMS_INTEGER"


class _SetMagConnection(_Connection):
    def get_fc_value(self, fc):
        return f"FC_{fc}"


def _fake_control_api(control_model):
    calls = []
    api = SimpleNamespace(
        MMS_BOOLEAN=2,
        MMS_FLOAT=6,
        MMS_INTEGER=4,
        MMS_UNSIGNED=5,
        CONTROL_MODEL_STATUS_ONLY=0,
        CONTROL_MODEL_DIRECT_NORMAL=1,
        CONTROL_MODEL_SBO_NORMAL=2,
        CONTROL_MODEL_DIRECT_ENHANCED=3,
        CONTROL_MODEL_SBO_ENHANCED=4,
        ControlObjectClient_create=lambda ref, _conn: calls.append(("create", ref)) or object(),
        ControlObjectClient_getCtlValType=lambda _control: 2,
        MmsValue_newBoolean=lambda value: calls.append(("value", value)) or object(),
        MmsValue_newFloat=lambda value: object(),
        MmsValue_newIntegerFromInt32=lambda value: object(),
        MmsValue_newUnsignedFromUint32=lambda value: object(),
        ControlObjectClient_getControlModel=lambda _control: control_model,
        ControlObjectClient_select=lambda _control: calls.append(("select",)) or True,
        ControlObjectClient_selectWithValue=lambda _control, _value: calls.append(("select_with_value",)) or True,
        ControlObjectClient_operate=lambda _control, _value, when: calls.append(("operate", when)) or True,
        ControlObjectClient_getLastError=lambda _control: 0,
        MmsValue_delete=lambda _value: calls.append(("delete_value",)),
        ControlObjectClient_destroy=lambda _control: calls.append(("destroy",)),
    )
    return api, calls


def test_direct_control_uses_control_object_operate(monkeypatch):
    api, calls = _fake_control_api(control_model=1)
    monkeypatch.setattr(writer_module, "iec61850", api, raising=False)

    assert Iec61850Writer(_Connection(), _Registry()).write("Pos", 1, "CO") is True
    assert ("create", "IEDLD0/GGIO1.Pos") in calls
    assert ("value", True) in calls
    assert ("operate", 0) in calls
    assert ("select",) not in calls


def test_sbo_control_selects_before_operate(monkeypatch):
    api, calls = _fake_control_api(control_model=2)
    monkeypatch.setattr(writer_module, "iec61850", api, raising=False)

    assert Iec61850Writer(_Connection(), _Registry()).write("Pos", 0, "CO") is True
    assert calls.index(("select",)) < calls.index(("operate", 0))


def test_set_mag_integer_uses_sp_and_native_integer_writer(monkeypatch):
    calls = []
    api = SimpleNamespace(
        IED_ERROR_OK=0,
        IedConnection_writeInt32Value=lambda _conn, ref, fc, value: calls.append(("write_int32", ref, fc, value)) or 0,
    )
    monkeypatch.setattr(writer_module, "iec61850", api, raising=False)

    writer = Iec61850Writer(_SetMagConnection(), _SetMagRegistry())

    assert writer.write("LD0/CTRL1.CtrlBlockPower.setMag.i", "42") is True
    assert calls == [("write_int32", "LD0/CTRL1.CtrlBlockPower.setMag.i", "FC_SP", 42)]


def test_boolean_string_false_is_not_coerced_to_true(monkeypatch):
    calls = []
    api = SimpleNamespace(
        IED_ERROR_OK=0,
        IedConnection_writeBooleanValue=lambda _conn, ref, fc, value: (
            calls.append(("write_boolean", ref, fc, value)) or 0
        ),
    )
    monkeypatch.setattr(writer_module, "iec61850", api, raising=False)
    registry = _SetMagRegistry()
    registry.get_iec_type = lambda _address: "boolean"
    registry.get_mms_type = lambda _address: "MMS_BOOLEAN"

    assert Iec61850Writer(_SetMagConnection(), registry).write("SubEna", "false", "SV") is True
    assert calls == [("write_boolean", "LD0/CTRL1.CtrlBlockPower.setMag.i", "FC_SV", False)]


def _stateful_control_api(control_model):
    api, calls = _fake_control_api(control_model)
    last_numbers = {}

    def create(ref, conn):
        calls.append(("create", ref))
        return SimpleNamespace(ref=ref, conn=conn, ctl_num=0, last_error=0)

    def select(control, *_args):
        control.ctl_num = (control.ctl_num + 1) % 256
        calls.append(("select", control.ctl_num))
        return True

    def operate(control, _value, _when):
        if control_model in (1, 3):
            control.ctl_num = (control.ctl_num + 1) % 256
        calls.append(("operate", control.ctl_num))
        key = (control.conn, control.ref)
        if last_numbers.get(key) == control.ctl_num:
            control.last_error = 32
            return False
        last_numbers[key] = control.ctl_num
        control.last_error = 0
        return True

    api.ControlObjectClient_create = create
    api.ControlObjectClient_select = select
    api.ControlObjectClient_selectWithValue = select
    api.ControlObjectClient_operate = operate
    api.ControlObjectClient_getLastError = lambda control: control.last_error
    return api, calls


@pytest.mark.parametrize("control_model", [1, 2, 3, 4])
def test_repeated_control_preserves_command_numbers(monkeypatch, control_model):
    api, calls = _stateful_control_api(control_model)
    monkeypatch.setattr(writer_module, "iec61850", api, raising=False)
    writer = Iec61850Writer(_Connection(), _Registry())

    assert writer.write("Pos", 1, "CO") is True
    assert writer.write("Pos", 1, "CO") is True
    assert writer.write("Pos", 0, "CO") is True
    assert [call[1] for call in calls if call[0] == "operate"] == [1, 2, 3]
    assert len([call for call in calls if call[0] == "create"]) == 1
    assert len([call for call in calls if call[0] == "delete_value"]) == 3


def test_control_reports_access_error_even_when_operate_returns_true(monkeypatch):
    api, calls = _fake_control_api(control_model=1)
    api.ControlObjectClient_getLastError = lambda _control: 21
    api.ControlObjectClient_getLastApplError = lambda _control: SimpleNamespace(error=0, addCause=19, ctlNum=1)
    api.ADD_CAUSE_BLOCKED_BY_INTERLOCKING = 19
    monkeypatch.setattr(writer_module, "iec61850", api, raising=False)
    writer = Iec61850Writer(_Connection(), _Registry())

    assert writer.write("Pos", 1, "CO") is False
    assert "IED_ERROR_ACCESS_DENIED" in writer.last_error
    assert "ADD_CAUSE_BLOCKED_BY_INTERLOCKING" in writer.last_error
    assert "IEDLD0/GGIO1.Pos" in writer.last_error


def test_control_cache_is_released_before_connection_destroy_and_recreated(monkeypatch):
    from pyiec61850 import pyiec61850 as native

    from src.proto.iec61850.core.connection import Iec61850Connection

    api, calls = _stateful_control_api(control_model=1)
    monkeypatch.setattr(writer_module, "iec61850", api, raising=False)
    monkeypatch.setattr(native, "IedConnection_close", lambda _conn: calls.append(("close_connection",)))
    monkeypatch.setattr(native, "IedConnection_destroy", lambda _conn: calls.append(("destroy_connection",)))
    connection = Iec61850Connection("127.0.0.1", 102)
    connection._connection = object()
    connection._is_connected = True
    monkeypatch.setattr(connection, "ensure_connected", lambda: connection.is_connected)
    writer = Iec61850Writer(connection, _Registry())

    assert writer.write("Pos", 1, "CO") is True
    assert ("destroy",) not in calls
    connection.disconnect()

    assert calls.index(("destroy",)) < calls.index(("close_connection",))
    assert calls.index(("destroy",)) < calls.index(("destroy_connection",))
    connection._connection = object()
    connection._is_connected = True
    assert writer.write("Pos", 1, "CO") is True
    assert len([call for call in calls if call[0] == "create"]) == 2
    connection.disconnect()
    assert calls.count(("destroy",)) == 2


def test_failed_operate_keeps_sequence_for_next_attempt(monkeypatch):
    api, calls = _stateful_control_api(control_model=1)
    operate = api.ControlObjectClient_operate

    def fail_first(control, value, when):
        result = operate(control, value, when)
        if control.ctl_num == 1:
            control.last_error = 26
            return False
        return result

    api.ControlObjectClient_operate = fail_first
    monkeypatch.setattr(writer_module, "iec61850", api, raising=False)
    writer = Iec61850Writer(_Connection(), _Registry())

    assert writer.write("Pos", 1, "CO") is False
    assert "IED_ERROR_TEMPORARILY_UNAVAILABLE" in writer.last_error
    assert writer.write("Pos", 1, "CO") is True
    assert writer.last_error is None
    assert [call[1] for call in calls if call[0] == "operate"] == [1, 2]


def test_control_numbers_are_independent_for_each_object(monkeypatch):
    api, calls = _stateful_control_api(control_model=1)
    monkeypatch.setattr(writer_module, "iec61850", api, raising=False)
    registry = _Registry()
    registry.get_ref = lambda address: f"IEDLD0/GGIO1.{address}.Oper.ctlVal"
    writer = Iec61850Writer(_Connection(), registry)

    for address in ("Pos1", "Pos2", "Pos1"):
        assert writer.write(address, 1, "CO") is True

    assert [call[1] for call in calls if call[0] == "operate"] == [1, 1, 2]


def test_failed_connection_cleanup_releases_cached_controls(monkeypatch):
    from pyiec61850 import pyiec61850 as native

    from src.proto.iec61850.core.connection import Iec61850Connection

    api, calls = _stateful_control_api(control_model=1)
    monkeypatch.setattr(writer_module, "iec61850", api, raising=False)
    monkeypatch.setattr(native, "IedConnection_destroy", lambda _conn: calls.append(("destroy_connection",)))
    connection = Iec61850Connection("127.0.0.1", 102)
    connection._connection = object()
    connection._is_connected = True
    monkeypatch.setattr(connection, "ensure_connected", lambda: True)
    writer = Iec61850Writer(connection, _Registry())
    assert writer.write("Pos", 1, "CO") is True

    connection._cleanup_connection()

    assert calls.index(("destroy",)) < calls.index(("destroy_connection",))
