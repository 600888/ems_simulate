"""IEC 61850 客户端错误码及中文诊断文本。

数值与 libiec61850 的 ``IedClientError`` 枚举保持一致。这里不依赖
pyiec61850 动态常量，确保本机未安装原生库时日志、API 和测试仍能解析错误码。
"""

from __future__ import annotations

from enum import IntEnum
from typing import Any


class IedClientErrorCode(IntEnum):
    """libiec61850 ``IedClientError`` 的完整枚举及中文含义。"""

    def __new__(cls, value: int, description_zh: str):
        member = int.__new__(cls, value)
        member._value_ = value
        member.description_zh = description_zh
        return member

    OK = (0, "操作成功")
    NOT_CONNECTED = (1, "尚未连接到 IED")
    ALREADY_CONNECTED = (2, "已经连接到 IED")
    CONNECTION_LOST = (3, "与 IED 的连接已丢失")
    SERVICE_NOT_SUPPORTED = (4, "IED 不支持请求的服务")
    CONNECTION_REJECTED = (5, "IED 拒绝建立连接")
    OUTSTANDING_CALL_LIMIT_REACHED = (6, "未完成调用数量已达到上限")
    USER_PROVIDED_INVALID_ARGUMENT = (10, "调用参数无效")
    ENABLE_REPORT_FAILED_DATASET_MISMATCH = (11, "启用报告失败：数据集不匹配")
    OBJECT_REFERENCE_INVALID = (12, "对象引用格式无效")
    UNEXPECTED_VALUE_RECEIVED = (13, "收到非预期的返回值")
    TIMEOUT = (20, "操作超时")
    ACCESS_DENIED = (21, "访问被拒绝")
    OBJECT_DOES_NOT_EXIST = (22, "对象不存在")
    OBJECT_EXISTS = (23, "对象已存在")
    OBJECT_ACCESS_UNSUPPORTED = (24, "不支持访问该对象")
    TYPE_INCONSISTENT = (25, "数据类型不一致")
    TEMPORARILY_UNAVAILABLE = (26, "对象或服务暂时不可用")
    OBJECT_UNDEFINED = (27, "对象未定义")
    INVALID_ADDRESS = (28, "地址无效")
    HARDWARE_FAULT = (29, "IED 硬件故障")
    TYPE_UNSUPPORTED = (30, "不支持该数据类型")
    OBJECT_ATTRIBUTE_INCONSISTENT = (31, "对象属性不一致")
    OBJECT_VALUE_INVALID = (32, "对象值无效")
    OBJECT_INVALIDATED = (33, "对象已失效")
    MALFORMED_MESSAGE = (34, "报文格式错误")
    OBJECT_CONSTRAINT_CONFLICT = (35, "对象约束冲突")
    SERVICE_NOT_IMPLEMENTED = (98, "请求的服务尚未实现")
    UNKNOWN = (99, "未知错误")

    @property
    def native_name(self) -> str:
        """返回与 pyiec61850 常量一致的枚举名称。"""

        return f"IED_ERROR_{self.name}"

    @property
    def label(self) -> str:
        """返回不含数值、适合 API 字段展示的中英文说明。"""

        return f"{self.native_name}（{self.description_zh}）"

    @classmethod
    def parse(cls, value: Any) -> IedClientErrorCode | None:
        """尽力把原生/SWIG 返回值转换成枚举，未知值返回 ``None``。"""

        try:
            return cls(int(value))
        except (TypeError, ValueError, OverflowError):
            return None


def describe_ied_error(error_code: Any) -> str:
    """返回错误码的枚举名和中文含义，不重复输出数值。"""

    member = IedClientErrorCode.parse(error_code)
    if member is not None:
        return member.label
    if error_code is None:
        return "IED_ERROR_UNAVAILABLE（底层未返回错误码）"
    try:
        numeric_code = int(error_code)
    except (TypeError, ValueError, OverflowError):
        if isinstance(error_code, BaseException):
            return f"{type(error_code).__name__}（{error_code}）"
        return f"IED_ERROR_UNPARSEABLE（无法解析的错误码：{error_code}）"
    return f"IED_ERROR_UNRECOGNIZED（未识别的错误码 {numeric_code}）"


def format_ied_error(error_code: Any) -> str:
    """格式化日志中的错误码，同时保留原值、枚举名和中文含义。"""

    if isinstance(error_code, BaseException):
        return f"{type(error_code).__name__}: {error_code}"
    try:
        numeric_code = int(error_code)
    except (TypeError, ValueError, OverflowError):
        numeric_code = error_code
    return f"{numeric_code}({describe_ied_error(error_code)})"
