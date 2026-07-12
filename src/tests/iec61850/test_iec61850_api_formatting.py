from src.web.api.channel.iec61850 import _format_goose_app_id


def test_format_goose_app_id_accepts_integer_and_scl_hex_strings():
    assert _format_goose_app_id(0x1001) == "0x1001"
    assert _format_goose_app_id("1001") == "0x1001"
    assert _format_goose_app_id("0x0001") == "0x0001"


def test_format_goose_app_id_does_not_crash_on_missing_or_unknown_values():
    assert _format_goose_app_id(None) == ""
    assert _format_goose_app_id("") == ""
    assert _format_goose_app_id("vendor-app-id") == "vendor-app-id"
