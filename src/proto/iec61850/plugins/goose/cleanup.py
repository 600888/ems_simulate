"""按 IEC 61850 通道清理全部 GOOSE 配置与运行时资源。"""

from __future__ import annotations

from typing import Any

from src.data.dao.goose_publisher_dao import GoosePublisherDao
from src.data.dao.goose_receiver_dao import GooseReceiverDao


def clear_channel_goose_resources(channel_id: int, manager: Any | None = None) -> dict[str, int]:
    """全量删除通道旧 GOOSE 资源，供 ICD 重导入和在线重发现复用。"""
    publisher_count = GoosePublisherDao.delete_by_channel(channel_id, raise_on_error=True)
    receiver_count = GooseReceiverDao.delete_by_channel(channel_id)

    runtime_publishers = 0
    runtime_receivers = 0
    if manager is not None:
        runtime_publishers = manager.delete_publishers_by_channel(channel_id, delete_from_db=False)
        runtime_receivers = manager.delete_receivers_by_channel(channel_id, delete_from_db=False)

    return {
        "publishers": publisher_count,
        "receivers": receiver_count,
        "runtime_publishers": runtime_publishers,
        "runtime_receivers": runtime_receivers,
    }
