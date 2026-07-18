"""GOOSE 持久化适配层 - 隔离 DAO 调用，便于测试

将 GooseManager 中直接的 DAO 调用抽象为 PersistenceBackend 协议，
支持在测试时注入 mock 实现，避免依赖真实数据库。
"""

from __future__ import annotations

from typing import Any, Protocol


class PersistenceBackend(Protocol):
    """持久化后端协议 (可替换为 mock 实现)"""

    def save_publisher(self, channel_id: int, status: dict[str, Any]) -> int | None:
        """保存发布器。"""
        ...

    def delete_publisher_by_go_cb_ref(self, go_cb_ref: str) -> bool:
        """删除发布器BYGO控制块引用。"""
        ...


class DaoPersistenceBackend:
    """默认实现: 委托给 GoosePublisherDao"""

    def save_publisher(self, channel_id: int, status: dict[str, Any]) -> int | None:
        """保存发布器。"""
        from src.data.dao.goose_publisher_dao import GoosePublisherDao

        return GoosePublisherDao.save_publisher(channel_id, status)

    def delete_publisher_by_go_cb_ref(self, go_cb_ref: str) -> bool:
        """删除发布器BYGO控制块引用。"""
        from src.data.dao.goose_publisher_dao import GoosePublisherDao

        return GoosePublisherDao.delete_publisher_by_go_cb_ref(go_cb_ref)


class PersistenceAdapter:
    """持久化适配器

    委托给 PersistenceBackend 实现，默认使用 DaoPersistenceBackend。
    测试时可注入自定义 mock 后端。
    """

    def __init__(self, backend: PersistenceBackend | None = None):
        """绑定可选持久化后端，在后端缺失时保持 GOOSE 运行逻辑可用。"""
        self._backend = backend or DaoPersistenceBackend()

    def save_publisher(self, channel_id: int, status: dict[str, Any]) -> int | None:
        """保存发布器。"""
        return self._backend.save_publisher(channel_id, status)

    def delete_publisher_by_go_cb_ref(self, go_cb_ref: str) -> bool:
        """删除发布器BYGO控制块引用。"""
        return self._backend.delete_publisher_by_go_cb_ref(go_cb_ref)
