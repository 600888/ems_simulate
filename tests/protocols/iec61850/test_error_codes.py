from src.proto.iec61850.defs.error_codes import (
    IedClientErrorCode,
    describe_ied_error,
    format_ied_error,
)

EXPECTED_CODES = {
    "OK": 0,
    "NOT_CONNECTED": 1,
    "ALREADY_CONNECTED": 2,
    "CONNECTION_LOST": 3,
    "SERVICE_NOT_SUPPORTED": 4,
    "CONNECTION_REJECTED": 5,
    "OUTSTANDING_CALL_LIMIT_REACHED": 6,
    "USER_PROVIDED_INVALID_ARGUMENT": 10,
    "ENABLE_REPORT_FAILED_DATASET_MISMATCH": 11,
    "OBJECT_REFERENCE_INVALID": 12,
    "UNEXPECTED_VALUE_RECEIVED": 13,
    "TIMEOUT": 20,
    "ACCESS_DENIED": 21,
    "OBJECT_DOES_NOT_EXIST": 22,
    "OBJECT_EXISTS": 23,
    "OBJECT_ACCESS_UNSUPPORTED": 24,
    "TYPE_INCONSISTENT": 25,
    "TEMPORARILY_UNAVAILABLE": 26,
    "OBJECT_UNDEFINED": 27,
    "INVALID_ADDRESS": 28,
    "HARDWARE_FAULT": 29,
    "TYPE_UNSUPPORTED": 30,
    "OBJECT_ATTRIBUTE_INCONSISTENT": 31,
    "OBJECT_VALUE_INVALID": 32,
    "OBJECT_INVALIDATED": 33,
    "MALFORMED_MESSAGE": 34,
    "OBJECT_CONSTRAINT_CONFLICT": 35,
    "SERVICE_NOT_IMPLEMENTED": 98,
    "UNKNOWN": 99,
}


def test_ied_client_error_enum_matches_libiec61850_values():
    assert {member.name: member.value for member in IedClientErrorCode} == EXPECTED_CODES


def test_known_error_contains_code_native_name_and_chinese_meaning():
    assert format_ied_error(20) == "20(IED_ERROR_TIMEOUT（操作超时）)"
    assert describe_ied_error(22) == "IED_ERROR_OBJECT_DOES_NOT_EXIST（对象不存在）"


def test_unknown_and_missing_error_codes_are_safe_to_format():
    assert format_ied_error(123) == "123(IED_ERROR_UNRECOGNIZED（未识别的错误码 123）)"
    assert format_ied_error(None) == "None(IED_ERROR_UNAVAILABLE（底层未返回错误码）)"


def test_exception_is_not_misclassified_as_numeric_error_code():
    assert format_ied_error(RuntimeError("native call failed")) == "RuntimeError: native call failed"
