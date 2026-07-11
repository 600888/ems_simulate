"""GOOSE Receiver/Subscription 持久化。"""

import json
from typing import Any

from src.data.controller.db import local_session
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
                session.add(
                    GooseSubscriptionConfig(
                        receiver_id=receiver.id,
                        go_cb_ref=sub["go_cb_ref"],
                        app_id=sub.get("app_id"),
                        dst_mac_json=json.dumps(sub["dst_mac"]) if sub.get("dst_mac") else None,
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
                    "dst_mac": json.loads(sub.dst_mac_json) if sub.dst_mac_json else None,
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
