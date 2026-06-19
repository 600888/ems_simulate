from typing import Any

from pydantic import BaseModel, field_serializer

from src.web.api.schemas.response_codes import Code


def _sanitize_for_serialization(obj: Any) -> Any:
    """递归清洗数据，确保所有值都是可序列化的

    Pydantic V2 序列化 Any 类型时会递归处理 dict/list 中的值，
    如果遇到 method、function 等不可序列化类型会抛出异常。
    此函数将这些类型转换为安全的字符串表示。
    """
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {str(k): _sanitize_for_serialization(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_serialization(item) for item in obj]
    # method、function 等不可序列化类型
    if callable(obj):
        return f"<{type(obj).__name__}>"
    # 其他未知类型，尝试转为字符串
    try:
        str(obj)
        return str(obj)
    except Exception:
        return f"<{type(obj).__name__}>"


class BaseResponse(BaseModel):
    """统一响应模型

    约定：
    - code=200 表示成功（与前端拦截器 response.data.code !== 200 判断对齐）
    - HTTP 状态码反映传输层结果，业务 code 反映业务语义
    - 前端只需判断 code === 200 即可知道是否成功

    推荐使用工厂方法构造响应：
        return BaseResponse.success(data=...)           # 成功
        return BaseResponse.error("失败", code=500)      # 失败
    也可直接构造：BaseResponse(data=...) / BaseResponse(code=404, message="...")
    """

    code: int = Code.SUCCESS
    message: str = "success"
    data: Any = None

    @classmethod
    def success(cls, data: Any = None, message: str = "success") -> "BaseResponse":
        """构造成功响应"""
        return cls(code=Code.SUCCESS, message=message, data=data)

    @classmethod
    def error(cls, message: str, code: int = Code.INTERNAL_ERROR, data: Any = None) -> "BaseResponse":
        """构造失败响应

        Args:
            message: 错误描述（会展示给前端用户）
            code: 业务错误码，默认 500
            data: 附加数据（可选）
        """
        return cls(code=code, message=message, data=data)

    @field_serializer("data")
    def serialize_data(self, value: Any) -> Any:
        """序列化 data 字段，处理不可序列化类型（如 method 对象）"""
        return _sanitize_for_serialization(value)
