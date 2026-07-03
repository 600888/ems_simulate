"""Functional-constraint mapping regression tests."""

from pyiec61850 import pyiec61850 as iec61850

from src.proto.iec61850.core.connection import Iec61850Connection


def test_writable_functional_constraints_use_native_values():
    connection = Iec61850Connection.__new__(Iec61850Connection)

    assert connection.get_fc_value("SP") == iec61850.IEC61850_FC_SP
    assert connection.get_fc_value("SE") == iec61850.IEC61850_FC_SE
    assert connection.get_fc_value("SV") == iec61850.IEC61850_FC_SV
    assert connection.get_fc_value("CF") == iec61850.IEC61850_FC_CF
