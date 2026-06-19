"""Web API 业务异常体系

提供语义化的业务异常，配合 app.py 中的全局异常处理器，
让前端始终能拿到统一格式的 {code, message, data} 响应。

使用方式：
    from src.web.api.exceptions import NotFoundError, ValidationError

    if name not in devices:
        raise NotFoundError(f"设备 {name} 不存在")
"""

from typing import Any


class BizError(Exception):
    """业务异常基类

    Attributes:
        message: 面向用户的错误描述
        code: 业务状态码（与前端约定，200 表示成功）
        http_status: 对应的 HTTP 状态码
        data: 附加数据（可选）
    """

    def __init__(
        self,
        message: str,
        code: int = 400,
        http_status: int = 400,
        data: Any = None,
    ):
        self.message = message
        self.code = code
        self.http_status = http_status
        self.data = data
        super().__init__(message)


class ValidationError(BizError):
    """参数校验失败 / 业务规则不满足"""

    def __init__(self, message: str, data: Any = None):
        super().__init__(message, code=400, http_status=400, data=data)


class NotFoundError(BizError):
    """资源不存在（设备、通道、文件等）"""

    def __init__(self, message: str, data: Any = None):
        super().__init__(message, code=404, http_status=404, data=data)


class OperationError(BizError):
    """操作执行失败（写入失败、连接失败等）"""

    def __init__(self, message: str, data: Any = None):
        super().__init__(message, code=500, http_status=500, data=data)


class ConflictError(BizError):
    """资源冲突（重复创建、状态冲突等）"""

    def __init__(self, message: str, data: Any = None):
        super().__init__(message, code=409, http_status=409, data=data)


class ServiceUnavailableError(BizError):
    """服务不可用（初始化中、依赖未就绪等）"""

    def __init__(self, message: str, data: Any = None):
        super().__init__(message, code=503, http_status=503, data=data)


def from_key_error(exc: KeyError) -> NotFoundError:
    """将 KeyError 转换为 NotFoundError，提取可读的 key 名"""
    # KeyError 的 str 会带引号，如 "'device_name'"
    key = str(exc).strip("'\"")
    return NotFoundError(f"资源 {key} 不存在")


def from_value_error(exc: ValueError) -> ValidationError:
    """将 ValueError 转换为 ValidationError"""
    return ValidationError(str(exc))
