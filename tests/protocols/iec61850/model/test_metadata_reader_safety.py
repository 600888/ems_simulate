from contextlib import contextmanager

from src.proto.iec61850.core import metadata as metadata_module
from src.proto.iec61850.core import reader as reader_module


class FakeMmsValue:
    def __init__(self, value_type: int, value: int):
        self.value_type = value_type
        self.value = value


class FakeIec61850:
    IED_ERROR_OK = 0
    MMS_BIT_STRING = 1
    MMS_INTEGER = 2
    MMS_UNSIGNED = 3
    MMS_FLOAT = 4
    MMS_BOOLEAN = 5
    MMS_UTC_TIME = 17
    MMS_DATA_ACCESS_ERROR = 15

    def __init__(self, value: FakeMmsValue | list[FakeMmsValue]):
        self.values = value if isinstance(value, list) else [value]
        self.deleted = []
        self.bit_string_reads = 0
        self.utc_time_reads = 0
        self.read_fcs = []

    def IedConnection_readObject(self, conn, ref, fc):
        self.read_fcs.append(fc)
        index = min(len(self.read_fcs) - 1, len(self.values) - 1)
        return [self.values[index], self.IED_ERROR_OK]

    @staticmethod
    def MmsValue_getType(value):
        return value.value_type

    def MmsValue_getBitStringAsInteger(self, value):
        self.bit_string_reads += 1
        return value.value

    def MmsValue_getUtcTimeInMs(self, value):
        self.utc_time_reads += 1
        return value.value

    @staticmethod
    def MmsValue_getDataAccessError(value):
        return value.value

    def MmsValue_delete(self, value):
        self.deleted.append(value)


class FakeConnection:
    is_connected = True

    def __init__(self):
        self.raw_connection = object()
        self.native_operations = 0

    @staticmethod
    def get_fc_value(fc):
        return fc

    @contextmanager
    def native_operation(self):
        self.native_operations += 1
        yield self.raw_connection


def test_quality_reader_checks_type_and_releases_value(monkeypatch):
    value = FakeMmsValue(FakeIec61850.MMS_BIT_STRING, 0x123)
    fake_iec = FakeIec61850(value)
    monkeypatch.setattr(metadata_module, "iec61850", fake_iec, raising=False)

    result = metadata_module.MetadataReader().read_quality(FakeConnection(), "LD0/GGIO1.Ind1", fc="ST")

    assert result.raw_packed == 0x123
    assert fake_iec.bit_string_reads == 1
    assert fake_iec.deleted == [value]


def test_quality_reader_rejects_wrong_mms_type_without_native_decode(monkeypatch):
    value = FakeMmsValue(FakeIec61850.MMS_INTEGER, 123)
    fake_iec = FakeIec61850(value)
    monkeypatch.setattr(metadata_module, "iec61850", fake_iec, raising=False)

    result = metadata_module.MetadataReader().read_quality(FakeConnection(), "LD0/GGIO1.Ind1", fc="ST")

    assert not result.is_readable
    assert fake_iec.bit_string_reads == 0
    assert fake_iec.deleted == [value, value]


def test_timestamp_reader_checks_type_and_releases_value(monkeypatch):
    value = FakeMmsValue(FakeIec61850.MMS_UTC_TIME, 1_700_000_000_123)
    fake_iec = FakeIec61850(value)
    monkeypatch.setattr(metadata_module, "iec61850", fake_iec, raising=False)

    result = metadata_module.MetadataReader().read_timestamp(FakeConnection(), "LD0/GGIO1.Ind1", fc="ST")

    assert result.unix_timestamp_ms == 1_700_000_000_123
    assert fake_iec.utc_time_reads == 1
    assert fake_iec.deleted == [value]


def test_timestamp_strategy_uses_typed_read_object_and_releases_value(monkeypatch):
    value = FakeMmsValue(FakeIec61850.MMS_UTC_TIME, 1_700_000_000_123)
    fake_iec = FakeIec61850(value)
    monkeypatch.setattr(reader_module, "iec61850", fake_iec, raising=False)

    result = reader_module.TimestampReader().read(object(), "LD0/GGIO1.Ind1.t", "ST")

    assert result == 1_700_000_000_123
    assert fake_iec.utc_time_reads == 1
    assert fake_iec.deleted == [value]


def test_timestamp_strategy_rejects_wrong_type_without_native_decode(monkeypatch):
    value = FakeMmsValue(FakeIec61850.MMS_INTEGER, 123)
    fake_iec = FakeIec61850(value)
    monkeypatch.setattr(reader_module, "iec61850", fake_iec, raising=False)

    result = reader_module.TimestampReader().read(object(), "LD0/GGIO1.Ind1.t", "ST")

    assert result is None
    assert fake_iec.utc_time_reads == 0
    assert fake_iec.deleted == [value]


def test_metadata_reader_retries_alternate_fc_after_data_access_error(monkeypatch):
    access_error = FakeMmsValue(FakeIec61850.MMS_DATA_ACCESS_ERROR, 4)
    quality = FakeMmsValue(FakeIec61850.MMS_BIT_STRING, 0x20)
    fake_iec = FakeIec61850([access_error, quality])
    monkeypatch.setattr(metadata_module, "iec61850", fake_iec, raising=False)

    result = metadata_module.MetadataReader().read_quality(FakeConnection(), "LD0/GGIO1.Ind1", fc="ST")

    assert result.raw_packed == 0x20
    assert fake_iec.read_fcs == ["ST", "MX"]
    assert fake_iec.deleted == [access_error, quality]
