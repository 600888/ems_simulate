"""统一在线模型 — 一次发现，多处消费

IedModel 是 IED 在线模型的标准不可变表示，替代:
- DataModelsPlugin 的 PointRegistry (扁平字典)
- 旧 ModelExporter 的嵌套 dataclass 导出

设计约束:
- 发现完成后不可变 (frozen=True)
- 自带序列化能力 (to_dict)
- 可派生 PointRegistry 和导出器的全部信息
- 使用 tuple 保证子元素不可变
"""

from .cache import ModelCache
from .ied_model import (
    DARef,
    DataSetRef,
    DORef,
    GoCBRef,
    IedModel,
    LDModel,
    LNModel,
    RCBRef,
)

__all__ = [
    "DARef",
    "DORef",
    "DataSetRef",
    "GoCBRef",
    "IedModel",
    "LDModel",
    "LNModel",
    "RCBRef",
    "ModelCache",
]
