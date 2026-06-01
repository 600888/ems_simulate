"""GOOSE 持久化适配层 - 隔离 DAO 调用，便于测试

将 GooseManager 中直接的 DAO 调用抽象为 PersistenceBackend 协议，
支持在测试时注入 mock 实现，避免依赖真实数据库。
"""

from __future__ import annotations

from typing import Any, Protocol


class PersistenceBackend(Protocol):
    """持久化后端协议 (可替换为 mock 实现)"""

    def save_publisher(self, channel_id: int, status: dict[str, Any]) -> int | None: ...
    def delete_publisher_by_go_cb_ref(self, go_cb_ref: str) -> bool: ...
    def delete_by_channel(self, channel_id: int) -> int: ...
    def get_by_channel(self, channel_id: int) -> list[dict[str, Any]]: ...
    def get_all(self) -> list[dict[str, Any]]: ...
    def get_all_pure_datasets(self) -> list[dict[str, Any]]: ...
    def save_pure_dataset(
        self,
        channel_id: int,
        ld_inst: str,
        ds_name: str,
        data_set_ref: str,
        entries: list[dict[str, Any]],
    ) -> int | None: ...
    def get_pure_datasets_by_channel(self, channel_id: int) -> list[dict[str, Any]]: ...
    def is_pure_dataset(self, go_cb_ref: str) -> bool: ...
    def delete_publisher_by_id(self, publisher_id: int) -> bool: ...


class DaoPersistenceBackend:
    """默认实现: 委托给 GoosePublisherDao"""

    def save_publisher(self, channel_id: int, status: dict[str, Any]) -> int | None:
        from src.data.dao.goose_publisher_dao import GoosePublisherDao

        return GoosePublisherDao.save_publisher(channel_id, status)

    def delete_publisher_by_go_cb_ref(self, go_cb_ref: str) -> bool:
        from src.data.dao.goose_publisher_dao import GoosePublisherDao

        return GoosePublisherDao.delete_publisher_by_go_cb_ref(go_cb_ref)

    def delete_by_channel(self, channel_id: int) -> int:
        from src.data.dao.goose_publisher_dao import GoosePublisherDao

        return GoosePublisherDao.delete_by_channel(channel_id)

    def get_by_channel(self, channel_id: int) -> list[dict[str, Any]]:
        from src.data.dao.goose_publisher_dao import GoosePublisherDao

        return GoosePublisherDao.get_by_channel(channel_id)

    def get_all(self) -> list[dict[str, Any]]:
        from src.data.dao.goose_publisher_dao import GoosePublisherDao

        return GoosePublisherDao.get_all()

    def get_all_pure_datasets(self) -> list[dict[str, Any]]:
        from src.data.dao.goose_publisher_dao import GoosePublisherDao

        return GoosePublisherDao.get_all_pure_datasets()

    def save_pure_dataset(
        self,
        channel_id: int,
        ld_inst: str,
        ds_name: str,
        data_set_ref: str,
        entries: list[dict[str, Any]],
    ) -> int | None:
        from src.data.dao.goose_publisher_dao import GoosePublisherDao

        return GoosePublisherDao.save_pure_dataset(
            channel_id,
            ld_inst,
            ds_name,
            data_set_ref,
            entries,
        )

    def get_pure_datasets_by_channel(self, channel_id: int) -> list[dict[str, Any]]:
        from src.data.dao.goose_publisher_dao import GoosePublisherDao

        return GoosePublisherDao.get_pure_datasets_by_channel(channel_id)

    def is_pure_dataset(self, go_cb_ref: str) -> bool:
        from src.data.dao.goose_publisher_dao import GoosePublisherDao

        return GoosePublisherDao.is_pure_dataset(go_cb_ref)

    def delete_publisher_by_id(self, publisher_id: int) -> bool:
        from src.data.dao.goose_publisher_dao import GoosePublisherDao

        return GoosePublisherDao.delete_publisher_by_id(publisher_id)


class PersistenceAdapter:
    """持久化适配器

    委托给 PersistenceBackend 实现，默认使用 DaoPersistenceBackend。
    测试时可注入自定义 mock 后端。
    """

    def __init__(self, backend: PersistenceBackend | None = None):
        self._backend = backend or DaoPersistenceBackend()

    def save_publisher(self, channel_id: int, status: dict[str, Any]) -> int | None:
        return self._backend.save_publisher(channel_id, status)

    def delete_publisher_by_go_cb_ref(self, go_cb_ref: str) -> bool:
        return self._backend.delete_publisher_by_go_cb_ref(go_cb_ref)

    def delete_by_channel(self, channel_id: int) -> int:
        return self._backend.delete_by_channel(channel_id)

    def get_by_channel(self, channel_id: int) -> list[dict[str, Any]]:
        return self._backend.get_by_channel(channel_id)

    def get_all(self) -> list[dict[str, Any]]:
        return self._backend.get_all()

    def get_all_pure_datasets(self) -> list[dict[str, Any]]:
        return self._backend.get_all_pure_datasets()

    def save_pure_dataset(
        self,
        channel_id: int,
        ld_inst: str,
        ds_name: str,
        data_set_ref: str,
        entries: list[dict[str, Any]],
    ) -> int | None:
        return self._backend.save_pure_dataset(
            channel_id,
            ld_inst,
            ds_name,
            data_set_ref,
            entries,
        )

    def get_pure_datasets_by_channel(self, channel_id: int) -> list[dict[str, Any]]:
        return self._backend.get_pure_datasets_by_channel(channel_id)

    def is_pure_dataset(self, go_cb_ref: str) -> bool:
        return self._backend.is_pure_dataset(go_cb_ref)

    def delete_publisher_by_id(self, publisher_id: int) -> bool:
        return self._backend.delete_publisher_by_id(publisher_id)
