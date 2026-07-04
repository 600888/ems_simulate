"""Functional-constraint mapping regression tests."""

from unittest.mock import patch

from pyiec61850 import pyiec61850 as iec61850

from src.proto.iec61850.core.connection import Iec61850Connection, Iec61850Timeouts


def test_writable_functional_constraints_use_native_values():
    connection = Iec61850Connection.__new__(Iec61850Connection)

    assert connection.get_fc_value("SP") == iec61850.IEC61850_FC_SP
    assert connection.get_fc_value("SE") == iec61850.IEC61850_FC_SE
    assert connection.get_fc_value("SV") == iec61850.IEC61850_FC_SV
    assert connection.get_fc_value("CF") == iec61850.IEC61850_FC_CF


def test_connect_applies_both_connect_and_request_timeouts():
    native_connection = object()
    timeouts = Iec61850Timeouts(connect_ms=1200, request_ms=2300)
    connection = Iec61850Connection("127.0.0.1", 102, model_name="IED", timeouts=timeouts)

    with (
        patch.object(iec61850, "IedConnection_create", return_value=native_connection),
        patch.object(iec61850, "IedConnection_setConnectTimeout") as set_connect_timeout,
        patch.object(iec61850, "IedConnection_setRequestTimeout") as set_request_timeout,
        patch.object(iec61850, "IedConnection_connect", return_value=iec61850.IED_ERROR_OK),
    ):
        assert connection.connect(auto_discover=False) is True

    set_connect_timeout.assert_called_once_with(native_connection, 1200)
    set_request_timeout.assert_called_once_with(native_connection, 2300)
