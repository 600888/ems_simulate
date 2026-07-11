"""GOOSE Receiver/Subscription 持久化。"""

import json
from typing import Any

from src.common.mac_address import normalize_mac_address
from src.data.controller.db import local_session
from src.data.log import log
from src.data.model.goose_receiver import GooseReceiverConfig, GooseSubscriptionConfig


class GooseReceiverDao:
    @classmethod
    def save(cls, channel_id: int, data: dict[str, Any]) -> int:
        with local_session() as session, session.begin():
            receiver_id = data.get("db_id")
            receiver = session.get(GooseReceiverConfig, receiver_id) if receiver_id else None
            if receiver is None:
                receiver = (
                    session.query(GooseReceiverConfig)
                    .where(
                        GooseReceiverConfig.channel_id == channel_id,
                        GooseReceiverConfig.interface == data["interface"],
                        GooseReceiverConfig.name == data.get("name", "default"),
                    )
                    .first()
                )
            if receiver is None:
                receiver = GooseReceiverConfig(channel_id=channel_id, interface=data["interface"])
                session.add(receiver)
            receiver.name = data.get("name", "default")
            receiver.description = data.get("description", "")
            receiver.interface = data["interface"]
            receiver.auto_start = data.get("auto_start", False)
            session.flush()
            (
                session.query(GooseSubscriptionConfig)
                .where(GooseSubscriptionConfig.receiver_id == receiver.id)
                .delete(synchronize_session=False)
            )
            session.flush()
            for sub in data.get("subscriptions", []):
                dst_mac = normalize_mac_address(sub.get("dst_mac"))
                session.add(
                    GooseSubscriptionConfig(
                        receiver_id=receiver.id,
                        go_cb_ref=sub["go_cb_ref"],
                        app_id=sub.get("app_id"),
                        dst_mac_json=json.dumps(dst_mac) if dst_mac else None,
                        description=sub.get("description", ""),
                        data_set_ref=sub.get("data_set_ref", ""),
                        conf_rev=sub.get("conf_rev", 0),
                        enabled=sub.get("enabled", False),
                        ied_name=sub.get("ied_name", ""),
                        ld_inst=sub.get("ld_inst", ""),
                        ln_name=sub.get("ln_name", "LLN0"),
                        dataset_entries_json=json.dumps(sub.get("dataset_entries", []), ensure_ascii=False),
                    )
                )
            session.flush()
            return receiver.id

    @classmethod
    def list_by_channel(cls, channel_id: int | None = None) -> list[dict[str, Any]]:
        with local_session() as session, session.begin():
            query = session.query(GooseReceiverConfig)
            if channel_id is not None:
                query = query.where(GooseReceiverConfig.channel_id == channel_id)
            return [cls._to_dict(item) for item in query.all()]

    @classmethod
    def delete(cls, receiver_id: int, channel_id: int | None = None) -> bool:
        with local_session() as session, session.begin():
            query = session.query(GooseReceiverConfig).where(GooseReceiverConfig.id == receiver_id)
            if channel_id is not None:
                query = query.where(GooseReceiverConfig.channel_id == channel_id)
            return query.delete() > 0

    @classmethod
    def delete_by_channel(cls, channel_id: int) -> int:
        """删除通道下全部 Receiver，并显式删除其 Subscription。

        不依赖数据库外键级联，兼容未启用 SQLite foreign_keys 的旧库。
        """
        with local_session() as session, session.begin():
            receiver_ids = session.query(GooseReceiverConfig.id).where(GooseReceiverConfig.channel_id == channel_id)
            session.query(GooseSubscriptionConfig).where(GooseSubscriptionConfig.receiver_id.in_(receiver_ids)).delete(
                synchronize_session=False
            )
            return (
                session.query(GooseReceiverConfig)
                .where(GooseReceiverConfig.channel_id == channel_id)
                .delete(synchronize_session=False)
            )

    @staticmethod
    def _to_dict(receiver: GooseReceiverConfig) -> dict[str, Any]:
        return {
            "db_id": receiver.id,
            "channel_id": receiver.channel_id,
            "name": receiver.name,
            "description": receiver.description,
            "interface": receiver.interface,
            "auto_start": receiver.auto_start,
            "subscriptions": [
                {
                    "id": sub.id,
                    "go_cb_ref": sub.go_cb_ref,
                    "app_id": sub.app_id,
                    "dst_mac": GooseReceiverDao._parse_dst_mac(sub.id, sub.dst_mac_json),
                    "description": sub.description,
                    "data_set_ref": sub.data_set_ref,
                    "conf_rev": sub.conf_rev,
                    "enabled": sub.enabled,
                    "ied_name": sub.ied_name,
                    "ld_inst": sub.ld_inst,
                    "ln_name": sub.ln_name,
                    "dataset_entries": json.loads(sub.dataset_entries_json) if sub.dataset_entries_json else [],
                }
                for sub in receiver.subscriptions
            ],
        }

    @staticmethod
    def _parse_dst_mac(subscription_id: int, raw_value: str | None) -> list[int] | None:
        if not raw_value:
            return None
        try:
            return normalize_mac_address(json.loads(raw_value))
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            log.warning(f"GOOSE Subscription {subscription_id} 的 dst_mac 无效，已忽略: {exc}")
            return None
