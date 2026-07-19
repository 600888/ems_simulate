"""Deep-copy IEC 61850 resources owned by a channel."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import asdict, dataclass
from pathlib import Path

from src.data.controller.db import local_session
from src.data.model.goose_publisher import GooseEntry, GoosePublisher
from src.data.model.goose_receiver import GooseReceiverConfig, GooseSubscriptionConfig
from src.data.service.channel_service import ChannelService


@dataclass(frozen=True)
class Iec61850CopyResult:
    """Summary returned to the copy-device API."""

    model_copied: bool = False
    model_path: str | None = None
    model_hash: str | None = None
    publisher_count: int = 0
    dataset_count: int = 0
    receiver_count: int = 0
    subscription_count: int = 0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class Iec61850CopyService:
    """Copy the model file and persistent GOOSE resources for one device.

    Runtime publishers/receivers are intentionally not started here.  A copied
    device is created in the stopped state, just like devices copied for the
    other protocols.
    """

    PROTOCOL_ID = 4

    @classmethod
    def clone_for_channel(
        cls,
        source_channel: dict,
        target_channel_id: int,
        target_device_id: int,
        target_device_name: str,
    ) -> Iec61850CopyResult:
        if source_channel.get("protocol_type") != cls.PROTOCOL_ID:
            return Iec61850CopyResult()

        copied_model_path: Path | None = None
        try:
            copied_model_path, model_hash = cls._copy_model_file(
                source_channel,
                target_channel_id,
                target_device_id,
                target_device_name,
            )
            counts = cls._clone_persistent_resources(source_channel["id"], target_channel_id)
            return Iec61850CopyResult(
                model_copied=copied_model_path is not None,
                model_path=str(copied_model_path) if copied_model_path else None,
                model_hash=model_hash,
                **counts,
            )
        except Exception:
            if copied_model_path is not None:
                with suppress(Exception):
                    ChannelService.update_channel(
                        target_channel_id,
                        icd_path=None,
                        icd_file_hash=None,
                    )
                cls._remove_copied_model(copied_model_path)
            raise

    @staticmethod
    def _copy_model_file(
        source_channel: dict,
        target_channel_id: int,
        target_device_id: int,
        target_device_name: str,
    ) -> tuple[Path | None, str | None]:
        raw_path = source_channel.get("icd_path")
        if not raw_path:
            return None, None

        source_path = Path(raw_path)
        if not source_path.is_file():
            raise FileNotFoundError(f"IEC 61850 模型文件不存在: {source_path}")

        from src.proto.iec61850.plugins.scl.service.file_manager import SclFileManager

        file_manager = SclFileManager()
        actual_hash = file_manager.compute_hash_from_file(str(source_path))
        expected_hash = str(source_channel.get("icd_file_hash") or "").strip()
        if expected_hash and actual_hash != expected_hash:
            raise ValueError(f"IEC 61850 模型文件校验失败: {source_path.name}")

        destination = Path(
            file_manager.save_to_device_dir(
                source_path=str(source_path),
                device_name=target_device_name,
                # Channel IDs make the destination collision-free even when
                # two devices happen to have the same display name.
                original_filename=f"{source_path.stem}_ch{target_channel_id}{source_path.suffix}",
                device_id=target_device_id,
                channel_id=target_channel_id,
            )
        )
        copied_hash = file_manager.compute_hash_from_file(str(destination))
        if copied_hash != actual_hash:
            Iec61850CopyService._remove_copied_model(destination)
            raise ValueError(f"IEC 61850 模型文件复制后校验失败: {destination.name}")

        if not ChannelService.set_icd_path(target_channel_id, str(destination), copied_hash):
            Iec61850CopyService._remove_copied_model(destination)
            raise RuntimeError("更新复制设备的 IEC 61850 模型关联失败")
        return destination, copied_hash

    @staticmethod
    def _remove_copied_model(model_path: Path) -> None:
        for path in (model_path, Path(f"{model_path}.sha256"), Path(f"{model_path}.meta")):
            with suppress(OSError):
                path.unlink(missing_ok=True)
        with suppress(OSError):
            model_path.parent.rmdir()

    @staticmethod
    def _clone_persistent_resources(source_channel_id: int, target_channel_id: int) -> dict[str, int]:
        publisher_count = 0
        dataset_count = 0
        receiver_count = 0
        subscription_count = 0

        # One transaction keeps Publisher/Entry and Receiver/Subscription
        # ownership consistent even when any individual row cannot be copied.
        with local_session() as session, session.begin():
            publishers = (
                session.query(GoosePublisher)
                .where(GoosePublisher.channel_id == source_channel_id)
                .order_by(GoosePublisher.id)
                .all()
            )
            for source in publishers:
                target = GoosePublisher(
                    channel_id=target_channel_id,
                    interface=source.interface,
                    go_cb_ref=source.go_cb_ref,
                    go_id=source.go_id,
                    data_set_ref=source.data_set_ref,
                    app_id=source.app_id,
                    conf_rev=source.conf_rev,
                    time_allowed_to_live=source.time_allowed_to_live,
                    dst_mac_json=source.dst_mac_json,
                    vlan_id=source.vlan_id,
                    vlan_prio=source.vlan_prio,
                    simulation=source.simulation,
                    name=source.name,
                    description=source.description,
                    auto_start=source.auto_start,
                )
                session.add(target)
                session.flush()
                for entry in sorted(source.entries, key=lambda item: item.sort_order):
                    session.add(
                        GooseEntry(
                            publisher_id=target.id,
                            name=entry.name,
                            value=entry.value,
                            iec_type=entry.iec_type,
                            sort_order=entry.sort_order,
                        )
                    )
                if source.go_cb_ref.startswith("__pure__"):
                    dataset_count += 1
                else:
                    publisher_count += 1

            receivers = (
                session.query(GooseReceiverConfig)
                .where(GooseReceiverConfig.channel_id == source_channel_id)
                .order_by(GooseReceiverConfig.id)
                .all()
            )
            for source in receivers:
                target = GooseReceiverConfig(
                    channel_id=target_channel_id,
                    name=source.name,
                    description=source.description,
                    interface=source.interface,
                    auto_start=source.auto_start,
                )
                session.add(target)
                session.flush()
                receiver_count += 1
                for subscription in source.subscriptions:
                    session.add(
                        GooseSubscriptionConfig(
                            receiver_id=target.id,
                            go_cb_ref=subscription.go_cb_ref,
                            app_id=subscription.app_id,
                            dst_mac_json=subscription.dst_mac_json,
                            description=subscription.description,
                            data_set_ref=subscription.data_set_ref,
                            conf_rev=subscription.conf_rev,
                            enabled=subscription.enabled,
                            ied_name=subscription.ied_name,
                            ld_inst=subscription.ld_inst,
                            ln_name=subscription.ln_name,
                            dataset_entries_json=subscription.dataset_entries_json,
                            go_id=subscription.go_id,
                        )
                    )
                    subscription_count += 1

        return {
            "publisher_count": publisher_count,
            "dataset_count": dataset_count,
            "receiver_count": receiver_count,
            "subscription_count": subscription_count,
        }

    @staticmethod
    def hydrate_runtime_resources(channel_id: int, manager) -> dict[str, int]:
        """Expose copied GOOSE configuration immediately without starting it."""
        if manager is None:
            return {"publishers": 0, "receivers": 0}

        from src.data.dao.goose_publisher_dao import GoosePublisherDao
        from src.data.dao.goose_receiver_dao import GooseReceiverDao

        publisher_count = 0
        for config in GoosePublisherDao.get_by_channel(channel_id):
            result = manager.create_publisher(
                interface=config.get("interface", "eth0"),
                go_cb_ref=config.get("go_cb_ref", ""),
                go_id=config.get("go_id", ""),
                data_set_ref=config.get("data_set_ref", ""),
                app_id=config.get("app_id", 1),
                conf_rev=config.get("conf_rev", 1),
                time_allowed_to_live=config.get("time_allowed_to_live", 1000),
                dst_mac=config.get("dst_mac"),
                vlan_id=config.get("vlan_id", 0),
                vlan_prio=config.get("vlan_prio", 4),
                simulation=config.get("simulation", True),
                entries=config.get("entries", []),
                channel_id=channel_id,
                skip_model_rebuild=True,
            )
            if result:
                publisher_count += 1
                # create_publisher persists its runtime status. Restore the
                # descriptive and auto-start fields that are DB-only today.
                GoosePublisherDao.save_publisher(channel_id, config)

        receiver_count = 0
        for config in GooseReceiverDao.list_by_channel(channel_id):
            result = manager.create_receiver(
                interface=config.get("interface", ""),
                subscriptions=config.get("subscriptions", []),
                channel_id=channel_id,
                name=config.get("name", "default"),
                description=config.get("description", ""),
                auto_start=config.get("auto_start", False),
                db_id=config.get("db_id"),
            )
            if result:
                receiver_count += 1

        return {"publishers": publisher_count, "receivers": receiver_count}
