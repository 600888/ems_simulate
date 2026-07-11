"""
GOOSE Publisher 数据访问层

提供 GOOSE Publisher 和 Entry 的持久化 CRUD 操作。
"""

import json
from typing import Any

from src.data.controller.db import local_session
from src.data.log import log
from src.data.model.goose_publisher import GooseEntry, GoosePublisher


class GoosePublisherDao:
    """GOOSE Publisher 数据访问对象"""

    # ===== Publisher CRUD =====

    @classmethod
    def save_publisher(cls, channel_id: int, pub_data: dict[str, Any]) -> int | None:
        """保存 GOOSE Publisher 配置到数据库

        Args:
            channel_id: 通道 ID
            pub_data: Publisher 配置字典 (来自 get_publisher_status 或 create_publisher)

        Returns:
            数据库记录 ID，失败返回 None
        """
        try:
            with local_session() as session, session.begin():
                existing = (
                    session.query(GoosePublisher)
                    .where(
                        GoosePublisher.channel_id == channel_id,
                        GoosePublisher.go_cb_ref == pub_data.get("go_cb_ref", ""),
                    )
                    .first()
                )

                dst_mac = pub_data.get("dst_mac")
                dst_mac_list = None
                if dst_mac and isinstance(dst_mac, str):
                    # "01:0C:CD:01:00:01" 或 "01-0C-CD-01-00-01" -> list
                    import re

                    parts = re.split(r"[-:]", dst_mac.strip())
                    if len(parts) == 6:
                        dst_mac_list = json.dumps([int(p, 16) for p in parts])
                elif isinstance(dst_mac, list):
                    dst_mac_list = json.dumps(dst_mac)

                if existing:
                    # 更新已有记录
                    existing.interface = pub_data.get("interface", "eth0")
                    existing.go_id = pub_data.get("go_id", "")
                    existing.data_set_ref = pub_data.get("data_set_ref", "")
                    existing.app_id = pub_data.get("app_id", 1)
                    existing.conf_rev = pub_data.get("conf_rev", 1)
                    existing.time_allowed_to_live = pub_data.get("time_allowed_to_live", 1000)
                    existing.dst_mac_json = dst_mac_list
                    existing.vlan_id = pub_data.get("vlan_id", 0)
                    existing.vlan_prio = pub_data.get("vlan_prio", 4)
                    existing.simulation = pub_data.get("simulation", True)
                    existing.name = pub_data.get("name", "")
                    existing.description = pub_data.get("description", "")
                    existing.auto_start = pub_data.get("auto_start", False)

                    # 替换条目
                    entries = pub_data.get("entries", [])
                    cls._replace_entries(session, existing.id, entries)
                    session.flush()
                    return existing.id
                else:
                    # 创建新记录
                    publisher = GoosePublisher(
                        channel_id=channel_id,
                        interface=pub_data.get("interface", "eth0"),
                        go_cb_ref=pub_data.get("go_cb_ref", ""),
                        go_id=pub_data.get("go_id", ""),
                        data_set_ref=pub_data.get("data_set_ref", ""),
                        app_id=pub_data.get("app_id", 1),
                        conf_rev=pub_data.get("conf_rev", 1),
                        time_allowed_to_live=pub_data.get("time_allowed_to_live", 1000),
                        dst_mac_json=dst_mac_list,
                        vlan_id=pub_data.get("vlan_id", 0),
                        vlan_prio=pub_data.get("vlan_prio", 4),
                        simulation=pub_data.get("simulation", True),
                        name=pub_data.get("name", ""),
                        description=pub_data.get("description", ""),
                        auto_start=pub_data.get("auto_start", False),
                    )
                    session.add(publisher)
                    session.flush()

                    entries = pub_data.get("entries", [])
                    for i, e in enumerate(entries):
                        entry = GooseEntry(
                            publisher_id=publisher.id,
                            name=e.get("name", ""),
                            value=_serialize_value(e.get("value")),
                            iec_type=e.get("iec_type", "boolean"),
                            sort_order=i,
                        )
                        session.add(entry)
                    session.flush()
                    return publisher.id
        except Exception as e:
            log.error(f"保存 GOOSE Publisher 失败: {e}")
            return None

    @classmethod
    def delete_publisher_by_go_cb_ref(cls, go_cb_ref: str) -> bool:
        """根据 go_cb_ref 删除 Publisher (级联删除 entries)"""
        try:
            with local_session() as session, session.begin():
                count = session.query(GoosePublisher).where(GoosePublisher.go_cb_ref == go_cb_ref).delete()
                return count > 0
        except Exception as e:
            log.error(f"删除 GOOSE Publisher 失败: {e}")
            return False

    @classmethod
    def delete_publisher_by_channel_ref(cls, channel_id: int, go_cb_ref: str) -> bool:
        try:
            with local_session() as session, session.begin():
                count = (
                    session.query(GoosePublisher)
                    .where(GoosePublisher.channel_id == channel_id, GoosePublisher.go_cb_ref == go_cb_ref)
                    .delete()
                )
                return count > 0
        except Exception as e:
            log.error(f"删除通道 GOOSE Publisher 失败: {e}")
            return False

    @classmethod
    def delete_publisher_by_id(cls, publisher_id: int) -> bool:
        """根据 ID 删除 Publisher (级联删除 entries)"""
        try:
            with local_session() as session, session.begin():
                count = session.query(GoosePublisher).where(GoosePublisher.id == publisher_id).delete()
                return count > 0
        except Exception as e:
            log.error(f"删除 GOOSE Publisher 失败: {e}")
            return False

    @classmethod
    def delete_by_channel(cls, channel_id: int, *, raise_on_error: bool = False) -> int:
        """删除通道下的所有 GOOSE Publisher 配置"""
        try:
            with local_session() as session, session.begin():
                publisher_ids = session.query(GoosePublisher.id).where(GoosePublisher.channel_id == channel_id)
                # Do not rely on database-level FK cascade. Some existing SQLite
                # databases were created without foreign_keys enabled.
                session.query(GooseEntry).where(GooseEntry.publisher_id.in_(publisher_ids)).delete(
                    synchronize_session=False
                )
                count = (
                    session.query(GoosePublisher)
                    .where(GoosePublisher.channel_id == channel_id)
                    .delete(synchronize_session=False)
                )
                return count
        except Exception as e:
            log.error(f"删除通道 GOOSE Publisher 失败: {e}")
            if raise_on_error:
                raise
            return 0

    _PURE_DATASET_PREFIX = "__pure__"

    @classmethod
    def save_pure_dataset(
        cls,
        channel_id: int,
        ld_inst: str,
        _ds_name: str,
        data_set_ref: str,
        entries: list[dict[str, Any]],
    ) -> int | None:
        """保存纯 DataSet 配置到数据库

        Args:
            channel_id: 通道 ID
            ld_inst: 逻辑设备实例名
            ds_name: DataSet 名称
            data_set_ref: DataSet 引用路径
            entries: 数据集条目列表 [{name, value, iec_type}]

        Returns:
            数据库记录 ID
        """
        try:
            pure_go_cb_ref = f"{cls._PURE_DATASET_PREFIX}{data_set_ref}"
            with local_session() as session, session.begin():
                existing = (
                    session.query(GoosePublisher)
                    .where(
                        GoosePublisher.channel_id == channel_id,
                        GoosePublisher.go_cb_ref == pure_go_cb_ref,
                    )
                    .first()
                )
                if existing:
                    existing.data_set_ref = data_set_ref
                    existing.go_id = ld_inst
                    cls._replace_entries(session, existing.id, entries)
                    session.flush()
                    return existing.id
                publisher = GoosePublisher(
                    channel_id=channel_id,
                    interface="",
                    go_cb_ref=pure_go_cb_ref,
                    go_id=ld_inst,
                    data_set_ref=data_set_ref,
                    app_id=0,
                    conf_rev=1,
                    time_allowed_to_live=1000,
                    dst_mac_json=None,
                    vlan_id=0,
                    vlan_prio=4,
                    simulation=False,
                )
                session.add(publisher)
                session.flush()
                for i, e in enumerate(entries):
                    entry = GooseEntry(
                        publisher_id=publisher.id,
                        name=e.get("name", ""),
                        value=_serialize_value(e.get("value")),
                        iec_type=e.get("iec_type", "boolean"),
                        sort_order=i,
                    )
                    session.add(entry)
                session.flush()
                return publisher.id
        except Exception as e:
            log.error(f"保存纯 DataSet 失败: {e}")
            return None

    @classmethod
    def get_pure_datasets_by_channel(cls, channel_id: int) -> list[dict[str, Any]]:
        """获取通道下所有纯 DataSet 配置"""
        try:
            with local_session() as session, session.begin():
                publishers = (
                    session.query(GoosePublisher)
                    .where(
                        GoosePublisher.channel_id == channel_id,
                        GoosePublisher.go_cb_ref.startswith(cls._PURE_DATASET_PREFIX),
                    )
                    .all()
                )
                results = []
                for p in publishers:
                    entries = [
                        {"name": e.name, "value": e._parse_value(), "iec_type": e.iec_type}
                        for e in sorted(p.entries, key=lambda x: x.sort_order)
                    ]
                    results.append(
                        {
                            "ld_inst": p.go_id,
                            "ds_name": p.data_set_ref.split("$")[-1] if "$" in p.data_set_ref else p.data_set_ref,
                            "data_set_ref": p.data_set_ref,
                            "entries": entries,
                            "_db_id": p.id,
                            "_channel_id": p.channel_id,
                        }
                    )
                return results
        except Exception as e:
            log.error(f"获取纯 DataSet 配置失败: {e}")
            return []

    @classmethod
    def get_all_pure_datasets(cls) -> list[dict[str, Any]]:
        """获取所有纯 DataSet 配置"""
        try:
            with local_session() as session, session.begin():
                publishers = (
                    session.query(GoosePublisher)
                    .where(GoosePublisher.go_cb_ref.startswith(cls._PURE_DATASET_PREFIX))
                    .all()
                )
                results = []
                for p in publishers:
                    entries = [
                        {"name": e.name, "value": e._parse_value(), "iec_type": e.iec_type}
                        for e in sorted(p.entries, key=lambda x: x.sort_order)
                    ]
                    results.append(
                        {
                            "ld_inst": p.go_id,
                            "ds_name": p.data_set_ref.split("$")[-1] if "$" in p.data_set_ref else p.data_set_ref,
                            "data_set_ref": p.data_set_ref,
                            "entries": entries,
                            "_db_id": p.id,
                            "_channel_id": p.channel_id,
                        }
                    )
                return results
        except Exception as e:
            log.error(f"获取所有纯 DataSet 配置失败: {e}")
            return []

    @classmethod
    def is_pure_dataset(cls, go_cb_ref: str) -> bool:
        """判断是否为纯 DataSet 标记"""
        return go_cb_ref.startswith(cls._PURE_DATASET_PREFIX)

    @classmethod
    def get_by_channel(cls, channel_id: int) -> list[dict[str, Any]]:
        """获取通道下的所有 GOOSE Publisher 配置（排除纯 DataSet）"""
        try:
            with local_session() as session, session.begin():
                publishers = (
                    session.query(GoosePublisher)
                    .where(
                        GoosePublisher.channel_id == channel_id,
                        ~GoosePublisher.go_cb_ref.startswith(cls._PURE_DATASET_PREFIX),
                    )
                    .all()
                )
                return [cls._publisher_to_config(p) for p in publishers]
        except Exception as e:
            log.error(f"获取通道 GOOSE Publisher 失败: {e}")
            return []

    @classmethod
    def get_all(cls) -> list[dict[str, Any]]:
        """获取所有 GOOSE Publisher 配置（排除纯 DataSet）"""
        try:
            with local_session() as session, session.begin():
                publishers = (
                    session.query(GoosePublisher)
                    .where(~GoosePublisher.go_cb_ref.startswith(cls._PURE_DATASET_PREFIX))
                    .all()
                )
                return [cls._publisher_to_config(p) for p in publishers]
        except Exception as e:
            log.error(f"获取所有 GOOSE Publisher 失败: {e}")
            return []

    @classmethod
    def _publisher_to_config(cls, publisher: GoosePublisher) -> dict[str, Any]:
        """将数据库记录转换为 create_publisher 兼容的配置字典"""
        dst_mac = None
        if publisher.dst_mac_json:
            dst_mac = json.loads(publisher.dst_mac_json)

        entries = []
        for e in sorted(publisher.entries, key=lambda x: x.sort_order):
            entries.append(
                {
                    "name": e.name,
                    "value": e._parse_value(),
                    "iec_type": e.iec_type,
                }
            )

        return {
            "interface": publisher.interface,
            "go_cb_ref": publisher.go_cb_ref,
            "go_id": publisher.go_id,
            "data_set_ref": publisher.data_set_ref,
            "app_id": publisher.app_id,
            "conf_rev": publisher.conf_rev,
            "time_allowed_to_live": publisher.time_allowed_to_live,
            "dst_mac": dst_mac,
            "vlan_id": publisher.vlan_id,
            "vlan_prio": publisher.vlan_prio,
            "simulation": publisher.simulation,
            "name": publisher.name,
            "description": publisher.description,
            "auto_start": publisher.auto_start,
            "entries": entries,
            "_db_id": publisher.id,
            "_channel_id": publisher.channel_id,
        }

    @classmethod
    def _replace_entries(cls, session, publisher_id: int, entries: list[dict[str, Any]]):
        """替换 Publisher 的所有数据集条目"""
        session.query(GooseEntry).where(GooseEntry.publisher_id == publisher_id).delete()
        for i, e in enumerate(entries):
            entry = GooseEntry(
                publisher_id=publisher_id,
                name=e.get("name", ""),
                value=_serialize_value(e.get("value")),
                iec_type=e.get("iec_type", "boolean"),
                sort_order=i,
            )
            session.add(entry)


def _serialize_value(value: Any) -> str | None:
    """将 Python 值序列化为 JSON 字符串"""
    if value is None:
        return None
    try:
        return json.dumps(value)
    except (TypeError, ValueError):
        return str(value)
