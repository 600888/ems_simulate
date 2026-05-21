"""
IEC 61850 GOOSE 管理器

统一管理所有 GOOSE Publisher 和 Receiver 实例，
提供 CRUD、启停控制、状态查询等功能。

设计模式: Singleton + Manager，通过 app.state.goose_manager 挂载到 FastAPI。
"""

import uuid
from typing import Any, Dict, List, Optional

from src.proto.iec61850.log import log

try:
    from src.proto.iec61850.goose_publisher import (
        GoosePublisher,
        GooseDataSetEntry,
        HAS_IEC61850,
    )
    from src.proto.iec61850.goose_subscriber import (
        GooseReceiver,
        GooseSubscription,
        HAS_IEC61850 as HAS_IEC61850_SUB,
    )
    GOOSE_AVAILABLE = HAS_IEC61850 and HAS_IEC61850_SUB
except ImportError:
    GOOSE_AVAILABLE = False
    log.warning("pyiec61850 未安装，GOOSE 功能不可用")


class GooseManager:
    """GOOSE 资源管理器

    管理 GOOSE Publisher 和 Receiver 的完整生命周期。
    """

    def __init__(self):
        self._publishers: Dict[str, GoosePublisher] = {}   # id -> publisher
        self._receivers: Dict[str, GooseReceiver] = {}     # id -> receiver

        # go_cb_ref -> publisher_id 映射 (用于快速查找)
        self._gocbref_to_pid: Dict[str, str] = {}
        # interface -> receiver_id 映射
        self._interface_to_rid: Dict[str, str] = {}

        # go_cb_ref -> channel_id 映射 (用于持久化)
        self._channel_map: Dict[str, int] = {}

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
        dst_mac: Optional[List[int]] = None,
        vlan_id: int = 0,
        vlan_prio: int = 4,
        simulation: bool = True,
        entries: Optional[List[Dict[str, Any]]] = None,
        server: Optional[Any] = None,
        channel_id: Optional[int] = None,
        force_recreate: bool = False,
        skip_model_rebuild: bool = False,
    ) -> Optional[Dict[str, Any]]:
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
            server: IEC61850Server 实例，提供后会在 MMS 数据模型中创建 GSEControlBlock 节点
            channel_id: 关联的通道 ID，提供后会持久化到数据库
            force_recreate: 如果为 True，当 go_cb_ref 已存在时先删除再重新创建
            skip_model_rebuild: 如果为 True，跳过 apply_model_changes 调用，
                               由调用方统一触发服务器重建（ICD 导入时使用）
        """
        if not GOOSE_AVAILABLE:
            log.error("GOOSE 功能不可用 (pyiec61850 未安装)")
            return None

        # 检查 go_cb_ref 是否已存在
        if go_cb_ref and go_cb_ref in self._gocbref_to_pid:
            if force_recreate:
                log.info(f"GOOSE Publisher 已存在但强制重新创建: go_cb_ref={go_cb_ref}")
                self.delete_publisher(go_cb_ref, delete_from_db=False)
            else:
                existing_id = self._gocbref_to_pid[go_cb_ref]
                log.warning(f"GOOSE Publisher 已存在: go_cb_ref={go_cb_ref}, id={existing_id}")
                return self.get_publisher_status(existing_id)

        try:
            publisher = GoosePublisher(
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

            # 添加数据集条目
            if entries:
                for e in entries:
                    entry = GooseDataSetEntry(
                        name=e.get("name", ""),
                        value=e.get("value"),
                        iec_type=e.get("iec_type", "boolean"),
                    )
                    publisher.add_entry(entry)

            # 生成唯一 ID
            pub_id = go_cb_ref or str(uuid.uuid4())
            self._publishers[pub_id] = publisher
            if go_cb_ref:
                self._gocbref_to_pid[go_cb_ref] = pub_id

            # 持久化到数据库
            if channel_id is not None:
                self._channel_map[go_cb_ref] = channel_id
                self.save_to_db(channel_id, go_cb_ref)

            # 注册 GSEControlBlock 到 MMS 数据模型（同时传递 entries 用于 DataSet FCDA）
            if server is not None:
                try:
                    gse_name = go_cb_ref.split("$")[-1] if "$" in go_cb_ref else go_cb_ref.split("/")[-1]
                    # 从 go_cb_ref 中提取 LD 实例名
                    # go_cb_ref 格式: "LD0/LLN0$GO$gcb1" -> ld_inst="LD0"
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

                # 应用模型变更：若 IedServer 已运行，重建以更新 MMS 命名空间
                # skip_model_rebuild=True 时跳过，由调用方统一触发服务器重建
                if not skip_model_rebuild and hasattr(server, 'apply_model_changes'):
                    try:
                        server.apply_model_changes()
                    except Exception as rebuild_err:
                        log.warning(f"重建 IedServer 以更新 MMS 命名空间失败: {rebuild_err}")

            log.info(f"GOOSE Publisher 创建成功: id={pub_id}, go_cb_ref={go_cb_ref}")
            return self.get_publisher_status(pub_id)
        except Exception as e:
            log.error(f"创建 GOOSE Publisher 异常: {e}")
            return None

    def list_publishers(self) -> List[Dict[str, Any]]:
        """列出所有 Publisher 状态"""
        return [
            self.get_publisher_status(pid) or {"id": pid, "error": "状态获取失败"}
            for pid in self._publishers
        ]

    def get_publisher_status(self, publisher_id: str) -> Optional[Dict[str, Any]]:
        """获取 Publisher 状态"""
        publisher = self._publishers.get(publisher_id)
        if not publisher:
            return None

        status = publisher.get_status()
        status["id"] = publisher_id
        status["entries"] = publisher.get_entries()
        return status

    def update_publisher(
        self,
        publisher_id: str,
        go_id: Optional[str] = None,
        conf_rev: Optional[int] = None,
        time_allowed_to_live: Optional[int] = None,
        simulation: Optional[bool] = None,
    ) -> Optional[Dict[str, Any]]:
        """更新 Publisher 配置 (仅未运行时)"""
        publisher = self._publishers.get(publisher_id)
        if not publisher:
            return None

        if publisher.is_running:
            log.warning(f"GOOSE Publisher 运行中，无法更新: {publisher_id}")
            return None

        if go_id is not None:
            publisher.go_id = go_id
        if conf_rev is not None:
            publisher.conf_rev = conf_rev
        if time_allowed_to_live is not None:
            publisher.time_allowed_to_live = time_allowed_to_live
        if simulation is not None:
            publisher.simulation = simulation

        # 持久化更新
        self._auto_persist(publisher_id)

        return self.get_publisher_status(publisher_id)

    def delete_publisher(self, publisher_id: str, delete_from_db: bool = False) -> bool:
        """删除 Publisher

        Args:
            publisher_id: Publisher ID (go_cb_ref)
            delete_from_db: 是否同时从数据库删除持久化记录
        """
        publisher = self._publishers.get(publisher_id)
        if not publisher:
            return False

        publisher.stop()
        go_cb_ref = publisher.go_cb_ref
        del self._publishers[publisher_id]
        if go_cb_ref in self._gocbref_to_pid:
            del self._gocbref_to_pid[go_cb_ref]
        if go_cb_ref in self._channel_map:
            del self._channel_map[go_cb_ref]

        # 从数据库删除
        if delete_from_db:
            try:
                from src.data.dao.goose_publisher_dao import GoosePublisherDao
                GoosePublisherDao.delete_publisher_by_go_cb_ref(go_cb_ref)
                log.info(f"GOOSE Publisher 已从数据库删除: id={publisher_id}")
            except Exception as e:
                log.warning(f"从数据库删除 GOOSE Publisher 失败: {e}")

        log.info(f"GOOSE Publisher 已删除: id={publisher_id}")
        return True

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
    ) -> Optional[Dict[str, Any]]:
        """向 Publisher 添加数据集条目"""
        publisher = self._publishers.get(publisher_id)
        if not publisher:
            return None

        entry = GooseDataSetEntry(name=name, value=value, iec_type=iec_type)
        publisher.add_entry(entry)

        # 持久化
        self._auto_persist(publisher_id)

        return {"publisher_id": publisher_id, "entry_count": len(publisher.get_entries())}

    def update_publisher_entry(
        self,
        publisher_id: str,
        index: int,
        value: Any,
    ) -> Optional[bool]:
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
        if not publisher:
            return False
        publisher.remove_entry(index)

        # 持久化
        self._auto_persist(publisher_id)

        return True

    def _auto_persist(self, go_cb_ref: str) -> None:
        """自动将 Publisher 持久化到数据库（如果有 channel_id 映射）"""
        channel_id = self._channel_map.get(go_cb_ref)
        if channel_id is not None:
            try:
                self.save_to_db(channel_id, go_cb_ref)
            except Exception as e:
                log.warning(f"自动持久化 GOOSE Publisher 失败: {e}")

    # ===== 持久化管理 =====

    def save_to_db(self, channel_id: int, go_cb_ref: str) -> bool:
        """将 Publisher 配置持久化到数据库

        Args:
            channel_id: 通道 ID
            go_cb_ref: GOOSE 控制块引用
        """
        try:
            from src.data.dao.goose_publisher_dao import GoosePublisherDao

            status = self.get_publisher_status(go_cb_ref)
            if not status:
                log.warning(f"save_to_db 失败: Publisher 未找到 go_cb_ref={go_cb_ref}")
                return False

            db_id = GoosePublisherDao.save_publisher(channel_id, status)
            if db_id:
                log.info(f"GOOSE Publisher 已持久化: go_cb_ref={go_cb_ref}, db_id={db_id}")
                return True
            return False
        except Exception as e:
            log.error(f"持久化 GOOSE Publisher 失败: {e}")
            return False

    def delete_publisher_from_db(self, go_cb_ref: str) -> bool:
        """从数据库删除 Publisher 持久化记录"""
        try:
            from src.data.dao.goose_publisher_dao import GoosePublisherDao
            result = GoosePublisherDao.delete_publisher_by_go_cb_ref(go_cb_ref)
            if result:
                log.info(f"GOOSE Publisher 已从数据库删除: {go_cb_ref}")
            return result
        except Exception as e:
            log.error(f"从数据库删除 GOOSE Publisher 失败: {e}")
            return False

    def delete_all_by_channel(self, channel_id: int) -> int:
        """删除通道下所有 GOOSE Publisher 持久化记录"""
        try:
            from src.data.dao.goose_publisher_dao import GoosePublisherDao
            count = GoosePublisherDao.delete_by_channel(channel_id)
            log.info(f"已删除通道 {channel_id} 的 {count} 个 GOOSE Publisher 持久化记录")
            return count
        except Exception as e:
            log.error(f"删除通道 GOOSE Publisher 持久化记录失败: {e}")
            return 0

    def load_from_db(
        self,
        channel_id: Optional[int] = None,
        server: Optional[Any] = None,
        server_map: Optional[Dict[int, Any]] = None,
    ) -> int:
        """从数据库加载 GOOSE Publisher 到内存

        Args:
            channel_id: 可选，只加载指定通道的 Publisher
            server: 可选，IEC61850Server 实例（指定单个服务器）
            server_map: 可选，{channel_id: IEC61850Server} 字典，
                       用于 startup 时将 Publisher 注册到对应的 MMS 服务器

        Returns:
            加载的 Publisher 数量
        """
        try:
            from src.data.dao.goose_publisher_dao import GoosePublisherDao

            # ===== 1. 恢复纯 DataSet =====
            # 重要：必须在 IedServer 启动前注册，否则 IedServer_create 后
            # 再添加 DataSet 会导致 MMS 命名空间不一致，客户端连接时崩溃
            pure_ds_loaded = 0
            try:
                pure_datasets = GoosePublisherDao.get_all_pure_datasets()
                for ds_info in pure_datasets:
                    ds_channel_id = ds_info.get("_channel_id")
                    effective_server = server_map.get(ds_channel_id) if server_map else None
                    if effective_server is None:
                        effective_server = server
                    if effective_server is None:
                        # 找不到 server，暂存到 server_map 中的待注册队列
                        if server_map:
                            pending_srv = next(iter(server_map.values()), None)
                            if pending_srv and hasattr(pending_srv, '_pending_goose_registrations'):
                                pending_srv._pending_goose_registrations.append({
                                    "_type": "dataset",
                                    "ld_inst": ds_info["ld_inst"],
                                    "ds_name": ds_info["ds_name"],
                                    "data_set_ref": ds_info["data_set_ref"],
                                    "entries": ds_info.get("entries", []),
                                })
                                log.info(f"纯 DataSet '{ds_info.get('ds_name', '')}' 已暂存到待注册队列")
                        continue
                    try:
                        effective_server.register_dataset(
                            ld_inst=ds_info["ld_inst"],
                            ds_name=ds_info["ds_name"],
                            data_set_ref=ds_info["data_set_ref"],
                            entries=ds_info.get("entries", []),
                        )
                        pure_ds_loaded += 1
                    except Exception as ds_err:
                        log.warning(f"从数据库恢复纯 DataSet 失败 ({ds_info.get('ds_name', '')}): {ds_err}")
                if pure_ds_loaded > 0:
                    log.info(f"从数据库恢复了 {pure_ds_loaded} 个纯 DataSet")
            except Exception as pure_load_err:
                log.warning(f"从数据库恢复纯 DataSet 失败: {pure_load_err}")


            # ===== 2. 恢复 GOOSE Publisher =====
            if channel_id is not None:
                configs = GoosePublisherDao.get_by_channel(channel_id)
            else:
                configs = GoosePublisherDao.get_all()

            loaded_count = 0
            for cfg in configs:
                go_cb_ref = cfg.get("go_cb_ref", "")
                if not go_cb_ref:
                    continue

                # 跳过已加载的
                if go_cb_ref in self._gocbref_to_pid:
                    continue

                try:
                    # 恢复内存中的 Publisher
                    publisher = GoosePublisher(
                        interface=cfg.get("interface", "eth0"),
                        go_cb_ref=go_cb_ref,
                        go_id=cfg.get("go_id", ""),
                        data_set_ref=cfg.get("data_set_ref", ""),
                        app_id=cfg.get("app_id", 0x0001),
                        conf_rev=cfg.get("conf_rev", 1),
                        time_allowed_to_live=cfg.get("time_allowed_to_live", 1000),
                        dst_mac=cfg.get("dst_mac"),
                        vlan_id=cfg.get("vlan_id", 0),
                        vlan_prio=cfg.get("vlan_prio", 4),
                        simulation=cfg.get("simulation", True),
                    )

                    # 添加数据集条目（跳过重复名称，兼容旧数据）
                    seen_names: set = set()
                    for e in cfg.get("entries", []):
                        name = e.get("name", "")
                        if not name or name in seen_names:
                            continue
                        seen_names.add(name)
                        entry = GooseDataSetEntry(
                            name=name,
                            value=e.get("value"),
                            iec_type=e.get("iec_type", "boolean"),
                        )
                        publisher.add_entry(entry)

                    # 注册到管理器
                    pub_id = go_cb_ref
                    self._publishers[pub_id] = publisher
                    self._gocbref_to_pid[go_cb_ref] = pub_id

                    # 记录 channel_id 映射
                    db_channel_id = cfg.get("_channel_id")
                    if db_channel_id is not None:
                        self._channel_map[go_cb_ref] = db_channel_id

                    # 注册 GSEControlBlock（传递 entries 确保 DataSet 目录完整）
                    effective_server = server
                    if effective_server is None and server_map is not None:
                        db_channel_id = cfg.get("_channel_id")
                        if db_channel_id is not None:
                            effective_server = server_map.get(db_channel_id)

                    gse_name = go_cb_ref.split("$")[-1] if "$" in go_cb_ref else go_cb_ref.split("/")[-1]
                    go_ld_inst = go_cb_ref.split("/")[0] if "/" in go_cb_ref else None
                    gocb_kwargs = dict(
                        name=gse_name,
                        app_id=cfg.get("app_id", 0x0001),
                        data_set_ref=cfg.get("data_set_ref", ""),
                        conf_rev=cfg.get("conf_rev", 1),
                        go_id=cfg.get("go_id", ""),
                        min_time=10,
                        max_time=cfg.get("time_allowed_to_live", 1000),
                        ld_inst=go_ld_inst,
                        entries=cfg.get("entries", []),
                        dst_mac=cfg.get("dst_mac"),
                        vlan_id=cfg.get("vlan_id", 0),
                        vlan_prio=cfg.get("vlan_prio", 4),
                    )

                    if effective_server is not None:
                        try:
                            gocb_result = effective_server.add_goose_control_block(**gocb_kwargs)
                            if not gocb_result:
                                log.warning(
                                    f"从数据库恢复 GSEControlBlock 失败: "
                                    f"go_cb_ref={go_cb_ref}, name={gse_name}, "
                                    f"add_goose_control_block 返回 False"
                                )
                        except Exception as gse_err:
                            log.warning(f"从数据库恢复时注册 GSEControlBlock 失败: {gse_err}")
                    else:
                        # effective_server 为 None：将 GoCB 配置暂存到 server_map 中
                        # 每个 server 的待注册队列，待设备启动时统一注册
                        # 如果 server_map 中有任何一个 server，将配置存入第一个
                        # （更精确的做法是按 channel_id 匹配，但此处 server_map
                        #   已无法找到对应 server，退而求其次）
                        log.warning(
                            f"load_from_db: 找不到 channel_id={cfg.get('_channel_id')} 对应的 "
                            f"IEC61850Server，GoCB '{gse_name}' 将暂存为待注册配置，"
                            f"待服务器启动时自动注册"
                        )
                        # 尝试存入 server_map 中的第一个 server 的待注册队列
                        pending_server = None
                        if server_map:
                            # 优先匹配 channel_id 对应的 server
                            db_ch_id = cfg.get("_channel_id")
                            if db_ch_id is not None and db_ch_id in server_map:
                                pending_server = server_map[db_ch_id]
                            else:
                                # 回退：使用 server_map 中第一个 server
                                pending_server = next(iter(server_map.values()), None)
                        if pending_server is not None and hasattr(pending_server, '_pending_goose_registrations'):
                            gocb_kwargs["_type"] = "gocb"
                            pending_server._pending_goose_registrations.append(gocb_kwargs)
                            log.info(f"GoCB '{gse_name}' 已暂存到待注册队列 (server={pending_server.ied_name})")

                    loaded_count += 1
                except Exception as e:
                    log.error(f"从数据库恢复 Publisher 失败: {go_cb_ref}, {e}")

            log.info(f"从数据库加载了 {loaded_count} 个 GOOSE Publisher")

            # ===== 3. 应用模型变更 =====
            # 如果在 IedServer 运行时注册了 DataSet/GSEControlBlock，
            # MMS 命名空间需要重建才能让客户端发现新节点。
            if server_map:
                for sid, srv in server_map.items():
                    if hasattr(srv, 'apply_model_changes'):
                        try:
                            rebuilt = srv.apply_model_changes()
                            if rebuilt:
                                log.info(f"IEC61850 服务器 (channel={sid}) IedServer 已重建以更新 MMS 命名空间")
                        except Exception as rebuild_err:
                            log.warning(f"重建 IedServer (channel={sid}) 失败: {rebuild_err}")
            elif server and hasattr(server, 'apply_model_changes'):
                try:
                    server.apply_model_changes()
                except Exception as rebuild_err:
                    log.warning(f"重建 IedServer 失败: {rebuild_err}")

            return loaded_count
        except Exception as e:
            log.error(f"从数据库加载 GOOSE Publisher 失败: {e}")
            return 0

    # ===== Receiver 管理 =====

    def create_receiver(
        self,
        interface: str = "eth0",
        subscriptions: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        """创建 GOOSE Receiver"""
        if not GOOSE_AVAILABLE:
            log.error("GOOSE 功能不可用 (pyiec61850 未安装)")
            return None

        # 检查同一接口是否已有 Receiver
        if interface in self._interface_to_rid:
            existing_id = self._interface_to_rid[interface]
            log.warning(f"GOOSE Receiver 已存在: interface={interface}, id={existing_id}")
            return self.get_receiver_status(existing_id)

        try:
            receiver = GooseReceiver(interface=interface)

            # 添加初始订阅
            if subscriptions:
                for s in subscriptions:
                    receiver.add_subscription(
                        go_cb_ref=s.get("go_cb_ref", ""),
                        app_id=s.get("app_id"),
                        dst_mac=s.get("dst_mac"),
                        description=s.get("description", ""),
                    )

            # 使用接口名作为 ID
            recv_id = interface
            self._receivers[recv_id] = receiver
            self._interface_to_rid[interface] = recv_id

            log.info(f"GOOSE Receiver 创建成功: id={recv_id}, interface={interface}")
            return self.get_receiver_status(recv_id)
        except Exception as e:
            log.error(f"创建 GOOSE Receiver 异常: {e}")
            return None

    def list_receivers(self) -> List[Dict[str, Any]]:
        """列出所有 Receiver 状态"""
        return [
            self.get_receiver_status(rid) or {"id": rid, "error": "状态获取失败"}
            for rid in self._receivers
        ]

    def get_receiver_status(self, receiver_id: str) -> Optional[Dict[str, Any]]:
        """获取 Receiver 状态"""
        receiver = self._receivers.get(receiver_id)
        if not receiver:
            return None

        status = receiver.get_status()
        status["id"] = receiver_id
        return status

    def delete_receiver(self, receiver_id: str) -> bool:
        """删除 Receiver"""
        receiver = self._receivers.get(receiver_id)
        if not receiver:
            return False

        interface = receiver.interface
        receiver.stop()
        del self._receivers[receiver_id]
        if interface in self._interface_to_rid:
            del self._interface_to_rid[interface]

        log.info(f"GOOSE Receiver 已删除: id={receiver_id}")
        return True

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

    def add_subscription(
        self,
        receiver_id: str,
        go_cb_ref: str,
        app_id: Optional[int] = None,
        dst_mac: Optional[List[int]] = None,
        description: str = "",
    ) -> Optional[Dict[str, Any]]:
        """向 Receiver 添加订阅"""
        receiver = self._receivers.get(receiver_id)
        if not receiver:
            return None

        if receiver.is_running:
            log.warning(f"GOOSE Receiver 运行中，无法添加订阅: {receiver_id}")
            return None

        sub = receiver.add_subscription(go_cb_ref, app_id, dst_mac, description)
        return sub.to_dict()

    def remove_subscription(self, receiver_id: str, go_cb_ref: str) -> bool:
        """从 Receiver 移除订阅"""
        receiver = self._receivers.get(receiver_id)
        if not receiver:
            return False

        if receiver.is_running:
            log.warning(f"GOOSE Receiver 运行中，无法移除订阅: {receiver_id}")
            return False

        return receiver.remove_subscription(go_cb_ref)

    # ===== 全局管理 =====

    def stop_all(self) -> None:
        """停止所有 Publisher 和 Receiver"""
        for publisher in self._publishers.values():
            publisher.stop()
        for receiver in self._receivers.values():
            receiver.stop()
        log.info("所有 GOOSE 资源已停止")

    def get_all_status(self) -> Dict[str, Any]:
        """获取所有 GOOSE 资源状态概览"""
        return {
            "goose_available": GOOSE_AVAILABLE,
            "publisher_count": len(self._publishers),
            "receiver_count": len(self._receivers),
            "publishers": self.list_publishers(),
            "receivers": self.list_receivers(),
        }


# 全局单例
_goose_manager: Optional[GooseManager] = None


def get_goose_manager() -> GooseManager:
    """获取全局 GooseManager 单例"""
    global _goose_manager
    if _goose_manager is None:
        _goose_manager = GooseManager()
    return _goose_manager
