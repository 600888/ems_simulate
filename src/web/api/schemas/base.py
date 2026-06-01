from typing import Any

from pydantic import BaseModel, field_serializer


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
    code: int = 200
    message: str = "success"
    data: Any = None

    @field_serializer("data")
    def serialize_data(self, value: Any) -> Any:
        """序列化 data 字段，处理不可序列化类型（如 method 对象）"""
        return _sanitize_for_serialization(value)
