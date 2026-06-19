"""统一业务错误码定义

约定：
- code=200 表示成功（与前端拦截器 response.data.code !== 200 判断对齐）
- HTTP 状态码反映传输层结果，业务 code 反映业务语义
- 前端只需判断 code === 200 即可知道是否成功
"""

from enum import IntEnum


class Code(IntEnum):
    """业务状态码"""

    # 成功
    SUCCESS = 200

    # 通用错误
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    METHOD_NOT_ALLOWED = 405
    CONFLICT = 409
    VALIDATION_ERROR = 422
    INTERNAL_ERROR = 500
    SERVICE_UNAVAILABLE = 503

    # 业务细分码（4xxx 段）
    DEVICE_NOT_FOUND = 4001
    CHANNEL_NOT_FOUND = 4002
    POINT_NOT_FOUND = 4003
    FILE_NOT_FOUND = 4004

    DEVICE_OPERATION_FAILED = 5001
    CHANNEL_OPERATION_FAILED = 5002
    POINT_OPERATION_FAILED = 5003
    IEC61850_ERROR = 5004
    GOOSE_ERROR = 5005


# 默认错误消息映射
DEFAULT_MESSAGES = {
    Code.BAD_REQUEST: "请求参数错误",
    Code.UNAUTHORIZED: "未授权",
    Code.FORBIDDEN: "禁止访问",
    Code.NOT_FOUND: "资源不存在",
    Code.METHOD_NOT_ALLOWED: "请求方法不被允许",
    Code.CONFLICT: "资源冲突",
    Code.VALIDATION_ERROR: "参数校验失败",
    Code.INTERNAL_ERROR: "服务器内部错误",
    Code.SERVICE_UNAVAILABLE: "服务不可用",
}
