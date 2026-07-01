"""IEC 61850 control-object write regression tests."""

from types import SimpleNamespace

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
