"""DNP3 补充对象处理器（不依赖主项目）。

复制自主项目 ``src/proto/dnp3/objects.py``，仅调整模块注释。
``pydnp3_pure`` 固定版本缺少 G52（延迟）对象组，这里通过 ``@register_handler``
在导入时注册，供 ``parse_dnp3`` 解析 G52V1/G52V2。

保持与本工具其它解析器一致：导入本模块即有注册副作用，所以调用方需
``from . import dnp3_objects  # noqa: F401``。
"""

from __future__ import annotations

from dataclasses import dataclass

from pydnp3_pure.app.constants import Qualifier
from pydnp3_pure.objects.base import ObjectGroupHandler
from pydnp3_pure.objects.registry import register_handler
from pydnp3_pure.util.buffer import ReadBuffer, WriteBuffer


@dataclass(slots=True)
class DelayValue:
    value: int


@register_handler
class Group52Handler(ObjectGroupHandler):
    """G52V1 restart delay in seconds and G52V2 fine delay in milliseconds."""

    @property
    def group(self) -> int:
        """返回对象组号 G52。"""
        return 52

    @property
    def supported_variations(self) -> tuple[int, ...]:
        """返回该组支持的变体（V1 重启延迟秒、V2 精细毫秒）。"""
        return (1, 2)

    def parse(
        self,
        variation: int,
        qualifier: Qualifier,
        count: int,
        start: int,
        buf: ReadBuffer,
    ) -> list[DelayValue]:
        """从缓冲区解析 G52 延迟对象。"""
        return [DelayValue(buf.read_uint16()) for _ in range(count)]

    def serialize(
        self,
        variation: int,
        qualifier: Qualifier,
        points: list[DelayValue],
        buf: WriteBuffer,
    ) -> None:
        """将 G52 延迟对象序列化到缓冲区。"""
        for point in points:
            buf.write_uint16(point.value)

    def point_size(self, variation: int) -> int:
        """返回单个延迟对象的固定字节数。"""
        return 2
