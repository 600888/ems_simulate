"""GOOSE 资源管理器 - 管理 Publisher/Receiver/Capture 的完整生命周期

不再是全局单例，由 GoosePlugin 内部持有实例。
持久化逻辑委托给 PersistenceAdapter，DAO 操作不再直接耦合。
"""

from __future__ import annotations

import contextlib
from typing import Any
import uuid

from ...defs.constants import HAS_IEC61850
from ...log import log
from .capture import GooseCaptureEngine
from .persistence import PersistenceAdapter
from .publisher import GoosePublisher
from .subscriber import GooseReceiver
from .types import (
    GooseDataSetEntry,
    IecDataType,
    PublisherConfig,
    ReceiverConfig,
)


def _scoped_key(channel_id: int | None, value: str) -> str:
    return f"{channel_id}:{value}" if channel_id is not None else value


_UNSET = object()


class GooseResourceManager:
    """GOOSE 资源管理器

    管理:
    - _publishers: dict[str, GoosePublisher]   # go_cb_ref -> publisher
    - _receivers: dict[str, GooseReceiver]     # interface -> receiver
    - _capture_engines: dict[str, GooseCaptureEngine]  # interface -> engine

    不再是全局单例，由 GoosePlugin 持有实例。
    """

    def __init__(self, persistence: PersistenceAdapter | None = None):
        self._publishers: dict[str, GoosePublisher] = {}
        self._receivers: dict[str, GooseReceiver] = {}
        self._capture_engines: dict[str, GooseCaptureEngine] = {}

        # go_cb_ref -> publisher_id 映射 (用于快速查找)
        self._gocbref_to_pid: dict[str, str] = {}
        # interface -> receiver_id 映射
        self._interface_to_rid: dict[str, str] = {}

        # runtime resource id -> channel_id 映射 (用于隔离和持久化)
        self._channel_map: dict[str, int] = {}
        self._receiver_channel_map: dict[str, int] = {}
        self._receiver_meta: dict[str, dict[str, Any]] = {}

        # 持久化适配器
        self._persistence = persistence or PersistenceAdapter()

    # ===== Publisher 管理 =====

    def create_publisher(
        self,
        interface: str = "eth0",
        go_cb_ref: str = "",
        go_id: str = "",
        data_set_ref: str = "",
        app_id: int = 0x0001,
        conf_rev: int = 1,
        time_allowed_to_live: int = 1000,
        dst_mac: list[int] | None = None,
        vlan_id: int = 0,
        vlan_prio: int = 4,
        simulation: bool = True,
        entries: list[dict[str, Any]] | None = None,
        server: Any | None = None,
        channel_id: int | None = None,
        force_recreate: bool = False,
        skip_model_rebuild: bool = False,
    ) -> dict[str, Any] | None:
        """创建 GOOSE Publisher

        Args:
            interface: 网络接口
            go_cb_ref: GOOSE 控制块引用
            go_id: GOOSE 标识符
            data_set_ref: 数据集引用
            app_id: APPID
            conf_rev: 配置修订号
            time_allowed_to_live: 存活时间 (ms)
            dst_mac: 目标 MAC 地址
            vlan_id: VLAN ID
            vlan_prio: VLAN 优先级
            simulation: 仿真模式
            entries: 数据集条目
            server: IEC61850Server 实例
            channel_id: 关联的通道 ID
            force_recreate: 强制重新创建
            skip_model_rebuild: 跳过模型重建
        """
        if not HAS_IEC61850:
            log.error("GOOSE 功能不可用 (pyiec61850 未安装)")
            return None

        lookup_key = _scoped_key(channel_id, go_cb_ref)
        # 同一通道内 GoCBRef 唯一，不同设备允许相同引用
        if go_cb_ref and lookup_key in self._gocbref_to_pid:
            if force_recreate:
                log.info(f"GOOSE Publisher 已存在但强制重新创建: go_cb_ref={go_cb_ref}")
                self.delete_publisher(self._gocbref_to_pid[lookup_key], delete_from_db=False)
            else:
                existing_id = self._gocbref_to_pid[lookup_key]
                log.warning(f"GOOSE Publisher 已存在: go_cb_ref={go_cb_ref}, id={existing_id}")
                return self.get_publisher_status(existing_id)

        try:
            config = PublisherConfig(
                interface=interface,
                go_cb_ref=go_cb_ref,
                go_id=go_id,
                data_set_ref=data_set_ref,
                app_id=app_id,
                conf_rev=conf_rev,
                time_allowed_to_live=time_allowed_to_live,
                dst_mac=dst_mac,
                vlan_id=vlan_id,
                vlan_prio=vlan_prio,
                simulation=simulation,
            )
            publisher = GoosePublisher(config)

            # 添加数据集条目
            if entries:
                for e in entries:
                    entry = GooseDataSetEntry(
                        name=e.get("name", ""),
                        value=e.get("value"),
                        iec_type=IecDataType(e.get("iec_type", "boolean")),
                    )
                    publisher.add_entry(entry)

            # 生成唯一 ID
            pub_id = lookup_key if go_cb_ref else _scoped_key(channel_id, str(uuid.uuid4()))
            self._publishers[pub_id] = publisher
            if go_cb_ref:
                self._gocbref_to_pid[lookup_key] = pub_id

            # 持久化到数据库
            if channel_id is not None:
                self._channel_map[pub_id] = channel_id
                self.save_to_db(channel_id, pub_id)

            # 注册 GSEControlBlock 到 MMS 数据模型
            if server is not None:
                try:
                    gse_name = go_cb_ref.split("$")[-1] if "$" in go_cb_ref else go_cb_ref.split("/")[-1]
                    go_ld_inst = go_cb_ref.split("/")[0] if "/" in go_cb_ref else None
                    server.add_goose_control_block(
                        name=gse_name,
                        app_id=app_id,
                        data_set_ref=data_set_ref,
                        conf_rev=conf_rev,
                        go_id=go_id,
                        min_time=10,
                        max_time=time_allowed_to_live,
                        ld_inst=go_ld_inst,
                        entries=entries,
                        dst_mac=dst_mac,
                        vlan_id=vlan_id,
                        vlan_prio=vlan_prio,
                    )
                except Exception as e:
                    log.warning(f"注册 GSEControlBlock 到 MMS 模型失败: {e}")

                if not skip_model_rebuild and hasattr(server, "apply_model_changes"):
                    try:
                        server.apply_model_changes()
                    except Exception as rebuild_err:
                        log.warning(f"重建 IedServer 以更新 MMS 命名空间失败: {rebuild_err}")

            log.info(f"GOOSE Publisher 创建成功: id={pub_id}, go_cb_ref={go_cb_ref}")
            return self.get_publisher_status(pub_id)
        except Exception as e:
            log.error(f"创建 GOOSE Publisher 异常: {e}")
            return None

    def list_publishers(self, channel_id: int | None = None) -> list[dict[str, Any]]:
        """列出所有 Publisher 状态"""
        ids = [pid for pid in self._publishers if channel_id is None or self._channel_map.get(pid) == channel_id]
        return [self.get_publisher_status(pid) or {"id": pid, "error": "状态获取失败"} for pid in ids]

    def get_publisher_status(self, publisher_id: str) -> dict[str, Any] | None:
        """获取 Publisher 状态"""
        publisher = self._publishers.get(publisher_id)
        if not publisher:
            return None

        status = publisher.get_status()
        status["id"] = publisher_id
        status["channel_id"] = self._channel_map.get(publisher_id)
        status["entries"] = publisher.get_entries()
        return status

    def update_publisher(
        self,
        publisher_id: str,
        interface: str | None = None,
        go_cb_ref: str | None = None,
        go_id: str | None = None,
        data_set_ref: str | None = None,
        app_id: int | None = None,
        conf_rev: int | None = None,
        time_allowed_to_live: int | None = None,
        dst_mac: list[int] | None | object = _UNSET,
        vlan_id: int | None = None,
        vlan_prio: int | None = None,
        simulation: bool | None = None,
    ) -> dict[str, Any] | None:
        """更新 Publisher 配置 (仅未运行时)"""
        publisher = self._publishers.get(publisher_id)
        if not publisher:
            return None

        if publisher.is_running:
            log.warning(f"GOOSE Publisher 运行中，无法更新: {publisher_id}")
            return None

        # 更新可变字段 (通过重建 config)
        config = publisher.config
        new_config = PublisherConfig(
            interface=interface if interface is not None else config.interface,
            go_cb_ref=go_cb_ref if go_cb_ref is not None else config.go_cb_ref,
            go_id=go_id if go_id is not None else config.go_id,
            data_set_ref=data_set_ref if data_set_ref is not None else config.data_set_ref,
            app_id=app_id if app_id is not None else config.app_id,
            conf_rev=conf_rev if conf_rev is not None else config.conf_rev,
            time_allowed_to_live=time_allowed_to_live
            if time_allowed_to_live is not None
            else config.time_allowed_to_live,
            dst_mac=config.dst_mac if dst_mac is _UNSET else dst_mac,
            vlan_id=vlan_id if vlan_id is not None else config.vlan_id,
            vlan_prio=vlan_prio if vlan_prio is not None else config.vlan_prio,
            simulation=simulation if simulation is not None else config.simulation,
        )

        # 需要重建 publisher (frozen config 不可变，只能重建)
        # 保持 entries 和运行状态
        entries = publisher.get_entries()

        new_publisher = GoosePublisher(new_config)
        # 恢复数据集条目
        for e in entries:
            entry = GooseDataSetEntry(
                name=e["name"],
                value=e["value"],
                iec_type=IecDataType(e.get("iec_type", "boolean")),
            )
            new_publisher.add_entry(entry)

        self._publishers[publisher_id] = new_publisher

        if new_config.go_cb_ref != config.go_cb_ref:
            channel_id = self._channel_map.get(publisher_id)
            self._gocbref_to_pid.pop(_scoped_key(channel_id, config.go_cb_ref), None)
            self._gocbref_to_pid[_scoped_key(channel_id, new_config.go_cb_ref)] = publisher_id
            if channel_id is not None:
                from src.data.dao.goose_publisher_dao import GoosePublisherDao

                GoosePublisherDao.delete_publisher_by_channel_ref(channel_id, config.go_cb_ref)

        # 持久化更新
        self._auto_persist(publisher_id)

        return self.get_publisher_status(publisher_id)

    def delete_publisher(self, publisher_id: str, delete_from_db: bool = False) -> bool:
        """删除 Publisher"""
        publisher = self._publishers.get(publisher_id)
        if not publisher:
            return False

        publisher.stop()
        go_cb_ref = publisher.go_cb_ref
        del self._publishers[publisher_id]
        channel_id = self._channel_map.pop(publisher_id, None)
        lookup_key = _scoped_key(channel_id, go_cb_ref)
        self._gocbref_to_pid.pop(lookup_key, None)

        # 从数据库删除
        if delete_from_db:
            try:
                if channel_id is not None:
                    from src.data.dao.goose_publisher_dao import GoosePublisherDao

                    GoosePublisherDao.delete_publisher_by_channel_ref(channel_id, go_cb_ref)
                else:
                    self._persistence.delete_publisher_by_go_cb_ref(go_cb_ref)
                log.info(f"GOOSE Publisher 已从数据库删除: id={publisher_id}")
            except Exception as e:
                log.warning(f"从数据库删除 GOOSE Publisher 失败: {e}")

        log.info(f"GOOSE Publisher 已删除: id={publisher_id}")
        return True

    def delete_publishers_by_channel(self, channel_id: int, delete_from_db: bool = False) -> int:
        """Stop and remove every publisher owned by a channel.

        ICD import is a full replacement operation. Keeping this operation on
        the manager avoids callers depending on its private runtime maps and
        ensures running publishers are stopped before configuration is replaced.
        """
        publisher_ids = [
            publisher_id
            for publisher_id, owner_channel_id in list(self._channel_map.items())
            if owner_channel_id == channel_id
        ]
        deleted = sum(self.delete_publisher(publisher_id, delete_from_db=False) for publisher_id in publisher_ids)

        if delete_from_db:
            from src.data.dao.goose_publisher_dao import GoosePublisherDao

            GoosePublisherDao.delete_by_channel(channel_id)

        return deleted

    def start_publisher(self, publisher_id: str) -> bool:
        """启动 Publisher"""
        publisher = self._publishers.get(publisher_id)
        if not publisher:
            return False
        return publisher.start()

    def stop_publisher(self, publisher_id: str) -> bool:
        """停止 Publisher"""
        publisher = self._publishers.get(publisher_id)
        if not publisher:
            return False
        publisher.stop()
        return True

    def publish_now(self, publisher_id: str) -> bool:
        """立即发布 GOOSE 报文"""
        publisher = self._publishers.get(publisher_id)
        if not publisher:
            return False
        return publisher.publish()

    # ===== Publisher 数据集管理 =====

    def add_publisher_entry(
        self,
        publisher_id: str,
        name: str,
        value: Any = None,
        iec_type: str = "boolean",
    ) -> dict[str, Any] | None:
        """向 Publisher 添加数据集条目"""
        publisher = self._publishers.get(publisher_id)
        if not publisher or publisher.is_running:
            return None

        entry = GooseDataSetEntry(name=name, value=value, iec_type=IecDataType(iec_type))
        publisher.add_entry(entry)

        # 持久化
        self._auto_persist(publisher_id)

        return {"publisher_id": publisher_id, "entry_count": len(publisher.get_entries())}

    def update_publisher_entry(
        self,
        publisher_id: str,
        index: int,
        value: Any,
    ) -> bool | None:
        """更新 Publisher 数据集条目值"""
        publisher = self._publishers.get(publisher_id)
        if not publisher:
            return None

        result = publisher.update_entry(index, value)

        # 持久化
        self._auto_persist(publisher_id)

        return result

    def remove_publisher_entry(self, publisher_id: str, index: int) -> bool:
        """移除 Publisher 数据集条目"""
        publisher = self._publishers.get(publisher_id)
        if not publisher or publisher.is_running:
            return False
        publisher.remove_entry(index)

        # 持久化
        self._auto_persist(publisher_id)

        return True

    def replace_publisher_entries(self, publisher_id: str, entries: list[dict[str, Any]]) -> dict[str, Any] | None:
        publisher = self._publishers.get(publisher_id)
        if not publisher or publisher.is_running:
            return None
        config = publisher.config
        replacement = GoosePublisher(config)
        for item in entries:
            replacement.add_entry(
                GooseDataSetEntry(
                    name=item["name"], value=item.get("value"), iec_type=IecDataType(item.get("iec_type", "boolean"))
                )
            )
        self._publishers[publisher_id] = replacement
        self._auto_persist(publisher_id)
        return self.get_publisher_status(publisher_id)

    def _auto_persist(self, publisher_id: str) -> None:
        """自动将 Publisher 持久化到数据库（如果有 channel_id 映射）"""
        channel_id = self._channel_map.get(publisher_id)
        if channel_id is not None:
            try:
                self.save_to_db(channel_id, publisher_id)
            except Exception as e:
                log.warning(f"自动持久化 GOOSE Publisher 失败: {e}")

    # ===== Receiver 管理 =====

    def create_receiver(
        self,
        interface: str = "eth0",
        subscriptions: list[dict[str, Any]] | None = None,
        channel_id: int | None = None,
        name: str = "default",
        description: str = "",
        auto_start: bool = False,
        db_id: int | None = None,
        runtime_id: str | None = None,
    ) -> dict[str, Any] | None:
        """创建 GOOSE Receiver"""
        if not HAS_IEC61850:
            log.error("GOOSE 功能不可用 (pyiec61850 未安装)")
            return None

        interface_key = _scoped_key(channel_id, f"{interface}:{name}")
        if interface_key in self._interface_to_rid:
            existing_id = self._interface_to_rid[interface_key]
            log.warning(f"GOOSE Receiver 已存在: interface={interface}, id={existing_id}")
            return self.get_receiver_status(existing_id)

        receiver = None
        recv_id = None
        try:
            config = ReceiverConfig(interface=interface)
            receiver = GooseReceiver(config)

            # 添加初始订阅
            if subscriptions:
                for s in subscriptions:
                    try:
                        receiver.add_subscription(
                            go_cb_ref=s.get("go_cb_ref", ""),
                            app_id=s.get("app_id"),
                            dst_mac=s.get("dst_mac"),
                            description=s.get("description", ""),
                            data_set_ref=s.get("data_set_ref", ""),
                            conf_rev=s.get("conf_rev", 0),
                            enabled=s.get("enabled", False),
                            ied_name=s.get("ied_name", ""),
                            ld_inst=s.get("ld_inst", ""),
                            ln_name=s.get("ln_name", "LLN0"),
                            dataset_entries=s.get("dataset_entries", []),
                            go_id=s.get("go_id", ""),
                        )
                    except (TypeError, ValueError) as sub_error:
                        log.warning(
                            f"跳过无效 GOOSE Subscription: go_cb_ref={s.get('go_cb_ref', '')}, error={sub_error}"
                        )

            recv_id = runtime_id or (str(db_id) if db_id is not None else _scoped_key(channel_id, str(uuid.uuid4())))
            self._receivers[recv_id] = receiver
            self._interface_to_rid[interface_key] = recv_id
            if channel_id is not None:
                self._receiver_channel_map[recv_id] = channel_id
                self._receiver_meta[recv_id] = {
                    "db_id": db_id,
                    "name": name,
                    "description": description,
                    "auto_start": auto_start,
                    "interface_key": interface_key,
                }
                self._persist_receiver(recv_id)

            log.info(f"GOOSE Receiver 创建成功: id={recv_id}, interface={interface}")
            return self.get_receiver_status(recv_id)
        except Exception as e:
            if receiver:
                with contextlib.suppress(Exception):
                    receiver.stop()
            if recv_id is not None:
                self._receivers.pop(recv_id, None)
                self._receiver_channel_map.pop(recv_id, None)
                self._receiver_meta.pop(recv_id, None)
            self._interface_to_rid.pop(interface_key, None)
            log.error(f"创建 GOOSE Receiver 异常: {e}")
            return None

    def list_receivers(self, channel_id: int | None = None) -> list[dict[str, Any]]:
        """列出所有 Receiver 状态"""
        ids = [
            rid for rid in self._receivers if channel_id is None or self._receiver_channel_map.get(rid) == channel_id
        ]
        results = []
        for receiver_id in ids:
            try:
                results.append(self.get_receiver_status(receiver_id) or {"id": receiver_id, "error": "状态获取失败"})
            except Exception as exc:
                log.error(f"获取 GOOSE Receiver 状态失败: id={receiver_id}, error={exc}")
                results.append({"id": receiver_id, "error": str(exc), "subscriptions": []})
        return results

    def get_receiver_status(self, receiver_id: str) -> dict[str, Any] | None:
        """获取 Receiver 状态"""
        receiver = self._receivers.get(receiver_id)
        if not receiver:
            return None

        status = receiver.get_status()
        status["id"] = receiver_id
        status["channel_id"] = self._receiver_channel_map.get(receiver_id)
        status.update({k: v for k, v in self._receiver_meta.get(receiver_id, {}).items() if k != "interface_key"})
        return status

    def delete_receiver(self, receiver_id: str) -> bool:
        """删除 Receiver"""
        receiver = self._receivers.get(receiver_id)
        if not receiver:
            return False

        receiver.stop()
        del self._receivers[receiver_id]
        meta = self._receiver_meta.pop(receiver_id, {})
        interface_key = meta.get("interface_key")
        if interface_key:
            self._interface_to_rid.pop(interface_key, None)
        channel_id = self._receiver_channel_map.pop(receiver_id, None)
        db_id = meta.get("db_id")
        if db_id:
            from src.data.dao.goose_receiver_dao import GooseReceiverDao

            GooseReceiverDao.delete(int(db_id), channel_id)

        log.info(f"GOOSE Receiver 已删除: id={receiver_id}")
        return True

    def delete_receivers_by_channel(self, channel_id: int, delete_from_db: bool = False) -> int:
        """停止并移除通道下全部 Receiver/Subscription 运行时资源。"""
        receiver_ids = [
            receiver_id
            for receiver_id, owner_channel_id in list(self._receiver_channel_map.items())
            if owner_channel_id == channel_id
        ]
        for receiver_id in receiver_ids:
            receiver = self._receivers.pop(receiver_id, None)
            if receiver:
                receiver.stop()
            self._receiver_channel_map.pop(receiver_id, None)
            self._receiver_meta.pop(receiver_id, None)
            for interface_key, mapped_receiver_id in list(self._interface_to_rid.items()):
                if mapped_receiver_id == receiver_id:
                    self._interface_to_rid.pop(interface_key, None)

        if delete_from_db:
            from src.data.dao.goose_receiver_dao import GooseReceiverDao

            GooseReceiverDao.delete_by_channel(channel_id)

        return len(receiver_ids)

    def update_receiver(
        self,
        receiver_id: str,
        interface: str,
        name: str = "default",
        description: str = "",
        auto_start: bool = False,
    ) -> dict[str, Any] | None:
        receiver = self._receivers.get(receiver_id)
        if not receiver or receiver.is_running:
            return None
        subscriptions = receiver.get_subscriptions()
        channel_id = self._receiver_channel_map.get(receiver_id)
        meta = self._receiver_meta.get(receiver_id, {})
        db_id = meta.get("db_id")
        old_key = meta.get("interface_key")
        if old_key:
            self._interface_to_rid.pop(old_key, None)
        self._receivers.pop(receiver_id, None)
        self._receiver_channel_map.pop(receiver_id, None)
        self._receiver_meta.pop(receiver_id, None)
        return self.create_receiver(
            interface=interface,
            subscriptions=subscriptions,
            channel_id=channel_id,
            name=name,
            description=description,
            auto_start=auto_start,
            db_id=db_id,
            runtime_id=receiver_id,
        )

    def start_receiver(self, receiver_id: str) -> bool:
        """启动 Receiver"""
        receiver = self._receivers.get(receiver_id)
        if not receiver:
            return False
        return receiver.start()

    def stop_receiver(self, receiver_id: str) -> bool:
        """停止 Receiver"""
        receiver = self._receivers.get(receiver_id)
        if not receiver:
            return False
        receiver.stop()
        return True

    # ===== Receiver 订阅管理 =====

    def import_discovered(
        self,
        discovered: list[dict[str, Any]],
        interface: str = "eth0",
        channel_id: int | None = None,
    ) -> dict[str, Any] | None:
        """将发现的远端 GOOSE 控制块导入为 Receiver 订阅 (幂等)

        在指定接口上复用/创建 Receiver，对每个发现的 GoCB 添加订阅。
        已存在的订阅 (相同 go_cb_ref) 由底层去重，不会重复添加。
        Receiver 运行中则跳过添加。
        """
        if not discovered:
            recv_id = self._interface_to_rid.get(_scoped_key(channel_id, f"{interface}:default"))
            return self.get_receiver_status(recv_id) if recv_id else None

        recv_id = self._interface_to_rid.get(_scoped_key(channel_id, f"{interface}:default"))
        if not recv_id:
            status = self.create_receiver(interface=interface, channel_id=channel_id)
            recv_id = status.get("id") if status else None
        if not recv_id:
            return None

        receiver = self._receivers.get(recv_id)
        if receiver:
            was_running = receiver.is_running
            if was_running:
                receiver.stop()
            for g in discovered:
                go_cb_ref = g.get("go_cb_ref", "")
                if go_cb_ref:
                    existing = receiver.get_subscription(go_cb_ref)
                    subscription_data = dict(
                        go_cb_ref=go_cb_ref,
                        app_id=g.get("app_id"),
                        dst_mac=g.get("dst_mac"),
                        description="auto-discovered",
                        data_set_ref=g.get("data_set_ref", ""),
                        conf_rev=g.get("conf_rev", 0),
                        enabled=bool(existing and existing.get("enabled")),
                        ied_name=g.get("ied_name", ""),
                        ld_inst=g.get("ld_inst", ""),
                        ln_name=g.get("ln_name", "LLN0"),
                        dataset_entries=g.get("dataset_entries", g.get("entries", [])),
                        go_id=g.get("go_id", ""),
                    )
                    if existing:
                        receiver.update_subscription(go_cb_ref, **subscription_data)
                    else:
                        receiver.add_subscription(**subscription_data)
            self._persist_receiver(recv_id)
            if was_running and not receiver.start():
                log.error(f"瀵煎叆 GOOSE 璁㈤槄鍚庡惎鍔?Receiver 澶辫触: id={recv_id}")
                return None
        return self.get_receiver_status(recv_id)

    def add_subscription(
        self,
        receiver_id: str,
        go_cb_ref: str,
        app_id: int | None = None,
        dst_mac: list[int] | None = None,
        description: str = "",
        data_set_ref: str = "",
        conf_rev: int = 0,
        enabled: bool = False,
        ied_name: str = "",
        ld_inst: str = "",
        ln_name: str = "LLN0",
        dataset_entries: list[dict[str, Any]] | None = None,
        go_id: str = "",
    ) -> dict[str, Any] | None:
        """向 Receiver 添加订阅"""
        receiver = self._receivers.get(receiver_id)
        if not receiver:
            return None

        if receiver.is_running:
            log.warning(f"GOOSE Receiver 运行中，无法添加订阅: {receiver_id}")
            return None

        sub = receiver.add_subscription(
            go_cb_ref,
            app_id,
            dst_mac,
            description,
            data_set_ref,
            conf_rev,
            enabled,
            ied_name,
            ld_inst,
            ln_name,
            dataset_entries,
            go_id=go_id,
        )
        self._persist_receiver(receiver_id)
        return sub.to_dict()

    def remove_subscription(self, receiver_id: str, go_cb_ref: str) -> bool:
        """从 Receiver 移除订阅"""
        receiver = self._receivers.get(receiver_id)
        if not receiver:
            return False

        if receiver.is_running:
            log.warning(f"GOOSE Receiver 运行中，无法移除订阅: {receiver_id}")
            return False

        removed = receiver.remove_subscription(go_cb_ref)
        if removed:
            # Receiver without subscriptions has no useful runtime role. Keeping it
            # indexed causes a later import to reuse stale runtime/DB identity.
            if not receiver.get_subscriptions():
                self.delete_receiver(receiver_id)
            else:
                self._persist_receiver(receiver_id)
        return removed

    def replace_subscriptions(self, receiver_id: str, subscriptions: list[dict[str, Any]]) -> dict[str, Any] | None:
        receiver = self._receivers.get(receiver_id)
        if not receiver or receiver.is_running:
            return None
        for item in list(receiver.get_subscriptions()):
            receiver.remove_subscription(item["go_cb_ref"])
        for item in subscriptions:
            receiver.add_subscription(
                item["go_cb_ref"],
                item.get("app_id"),
                item.get("dst_mac"),
                item.get("description", ""),
                item.get("data_set_ref", ""),
                item.get("conf_rev", 0),
                item.get("enabled", False),
                item.get("ied_name", ""),
                item.get("ld_inst", ""),
                item.get("ln_name", "LLN0"),
                item.get("dataset_entries", []),
                go_id=item.get("go_id", ""),
            )
        self._persist_receiver(receiver_id)
        return self.get_receiver_status(receiver_id)

    def update_subscription(
        self,
        receiver_id: str,
        current_go_cb_ref: str,
        **changes: Any,
    ) -> dict[str, Any] | None:
        """Apply subscription configuration and safely rebuild a running receiver."""
        receiver = self._receivers.get(receiver_id)
        if receiver is None:
            return None
        was_running = receiver.is_running
        if was_running:
            receiver.stop()
        result = receiver.update_subscription(current_go_cb_ref, **changes)
        if result is None:
            if was_running:
                receiver.start()
            return None
        self._persist_receiver(receiver_id)
        should_run = was_running or bool(result.get("enabled"))
        if should_run and not receiver.start():
            return None
        return self.get_receiver_status(receiver_id)

    def get_subscription_history(
        self,
        receiver_id: str,
        go_cb_ref: str,
        limit: int = 100,
    ) -> list[dict[str, Any]] | None:
        receiver = self._receivers.get(receiver_id)
        if receiver is None or receiver.get_subscription(go_cb_ref) is None:
            return None
        return receiver.get_history(go_cb_ref, limit)

    def _persist_receiver(self, receiver_id: str) -> None:
        channel_id = self._receiver_channel_map.get(receiver_id)
        receiver = self._receivers.get(receiver_id)
        if channel_id is None or receiver is None:
            return
        from src.data.dao.goose_receiver_dao import GooseReceiverDao

        meta = self._receiver_meta.get(receiver_id, {})
        db_id = GooseReceiverDao.save(
            channel_id,
            {
                **meta,
                "interface": receiver.interface,
                "subscriptions": receiver.get_subscriptions(),
            },
        )
        meta["db_id"] = db_id

    # ===== Capture 管理 =====

    def get_capture_engine(self, interface: str = "", max_packets: int = 500) -> GooseCaptureEngine:
        """获取或创建指定接口的 GOOSE 捕获引擎"""
        key = interface or "__default__"
        engine = self._capture_engines.get(key)
        if engine is None:
            engine = GooseCaptureEngine(interface=interface, max_packets=max_packets)
            self._capture_engines[key] = engine
        return engine

    def start_capture(self, interface: str = "", max_packets: int = 500) -> dict[str, Any] | None:
        """启动 GOOSE 报文捕获"""
        engine = self.get_capture_engine(interface, max_packets)
        success = engine.start()
        if success:
            return {"interface": interface or "auto", "is_running": True}
        return None

    def stop_capture(self, interface: str = "") -> bool:
        """停止 GOOSE 报文捕获"""
        key = interface or "__default__"
        engine = self._capture_engines.get(key)
        if engine:
            engine.stop()
            return True
        # 停止所有
        for eng in self._capture_engines.values():
            if eng.is_running:
                eng.stop()
        return True

    def get_captured_packets(
        self, interface: str = "", count: int = 0, filter_app_id: int | None = None
    ) -> list[dict[str, Any]]:
        """获取捕获的报文列表"""
        engine = self._capture_engines.get(interface or "__default__")
        if not engine:
            # 尝试查找正在运行的
            for eng in self._capture_engines.values():
                if eng.is_running:
                    engine = eng
                    break
        if not engine:
            return []
        return engine.get_packets(count=count, filter_app_id=filter_app_id)

    # ===== 全局管理 =====

    def stop_all(self) -> None:
        """停止所有 Publisher、Receiver 和 Capture"""
        for publisher in self._publishers.values():
            publisher.stop()
        for receiver in self._receivers.values():
            receiver.stop()
        for engine in self._capture_engines.values():
            if engine.is_running:
                engine.stop()
        log.info("所有 GOOSE 资源已停止")

    def get_all_status(self) -> dict[str, Any]:
        """获取所有 GOOSE 资源状态概览"""
        return {
            "goose_available": HAS_IEC61850,
            "publisher_count": len(self._publishers),
            "receiver_count": len(self._receivers),
            "publishers": self.list_publishers(),
            "receivers": self.list_receivers(),
        }

    # ===== 持久化 =====

    def save_to_db(self, channel_id: int, publisher_id: str) -> bool:
        """将 Publisher 配置持久化到数据库"""
        try:
            status = self.get_publisher_status(publisher_id)
            if not status:
                log.warning(f"save_to_db 失败: Publisher 未找到 id={publisher_id}")
                return False

            db_id = self._persistence.save_publisher(channel_id, status)
            if db_id:
                log.info(f"GOOSE Publisher 已持久化: id={publisher_id}, db_id={db_id}")
                return True
            return False
        except Exception as e:
            log.error(f"持久化 GOOSE Publisher 失败: {e}")
            return False
