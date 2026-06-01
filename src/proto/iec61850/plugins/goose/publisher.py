"""GOOSE 发布者 - 基于 pyiec61850 实现 GOOSE 报文发布

管理单个 GoCB 的报文发布、数据集、序号、定时重发。
线程安全: _lock 保护 _entries、_st_num、_sq_num。
"""

from __future__ import annotations

import contextlib
import threading
from typing import Any

from ...defs.constants import HAS_IEC61850
from ...log import log
from .types import (
    DEFAULT_SQ_NUM,
    DEFAULT_ST_NUM,
    GOOSE_MULTICAST_MAC_PREFIX,
    GooseDataSetEntry,
    IecDataType,
    PublisherConfig,
)

if HAS_IEC61850:
    from pyiec61850 import pyiec61850 as iec61850


class _IecApiAdapter:
    """pyiec61850 API 兼容适配器

    封装 _call_iec 的版本兼容逻辑，处理不同 pyiec61850 绑定之间的
    函数命名差异 (如 setAppid vs setAppId)。
    """

    def __init__(self, publisher_obj: Any):
        self._pub = publisher_obj

    def call(self, name: str, *args) -> tuple[bool, Any]:
        """安全调用 iec61850 函数，自动大小写兜底

        Returns:
            (called, result) - called=True 表示调用成功
        """
        func = getattr(iec61850, name, None)
        if func is not None:
            return True, func(*args)

        # 尝试大小写变体
        alt_names = [
            name + "d",
            name[:-1],
            name.replace("Id", "ID"),
            name.replace("ID", "Id"),
            name.replace("id", "Id"),
            name.replace("Id", "id"),
        ]
        for alt in alt_names:
            if alt != name:
                func = getattr(iec61850, alt, None)
                if func:
                    return True, func(*args)
        return False, None


class GoosePublisher:
    """IEC 61850 GOOSE 发布者

    功能:
    - 创建 GOOSE 控制块 (GoCB) 并发布 GOOSE 报文
    - 支持数据集动态添加/修改
    - 支持 stNum/sqNum 自动管理
    - 支持定时重发 (TAL)

    典型用法:
        config = PublisherConfig(interface="eth0", go_cb_ref="LD0/LLN0$GO$gcb1")
        publisher = GoosePublisher(config)
        publisher.add_entry(GooseDataSetEntry("stVal", True, IecDataType.BOOLEAN))
        publisher.start()
        publisher.publish()
        ...
        publisher.stop()
    """

    def __init__(self, config: PublisherConfig):
        if not HAS_IEC61850:
            raise RuntimeError("pyiec61850 未安装，无法创建 GOOSE Publisher")

        self._config = config
        self._entries: list[GooseDataSetEntry] = []
        self._st_num: int = DEFAULT_ST_NUM
        self._sq_num: int = DEFAULT_SQ_NUM

        # 计算默认组播 MAC
        self._dst_mac = config.dst_mac or (
            GOOSE_MULTICAST_MAC_PREFIX + [(config.app_id >> 8) & 0xFF, config.app_id & 0xFF]
        )

        # 底层状态
        self._publisher: Any = None
        self._comm_params: Any = None
        self._is_running = False
        self._is_created = False

        # 定时重发
        self._retransmit_interval = config.time_allowed_to_live / 2000.0
        self._retransmit_stop = threading.Event()
        self._retransmit_thread: threading.Thread | None = None

        # 线程锁
        self._lock = threading.Lock()

    # ===== 配置属性 (只读) =====

    @property
    def config(self) -> PublisherConfig:
        return self._config

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def st_num(self) -> int:
        return self._st_num

    @property
    def sq_num(self) -> int:
        return self._sq_num

    @property
    def dst_mac(self) -> list[int]:
        return self._dst_mac

    # 兼容旧属性访问 (过渡期)
    @property
    def interface(self) -> str:
        return self._config.interface

    @property
    def go_cb_ref(self) -> str:
        return self._config.go_cb_ref

    @property
    def go_id(self) -> str:
        return self._config.go_id

    @property
    def data_set_ref(self) -> str:
        return self._config.data_set_ref

    @property
    def app_id(self) -> int:
        return self._config.app_id

    @property
    def conf_rev(self) -> int:
        return self._config.conf_rev

    @property
    def time_allowed_to_live(self) -> int:
        return self._config.time_allowed_to_live

    @property
    def simulation(self) -> bool:
        return self._config.simulation

    @property
    def vlan_id(self) -> int:
        return self._config.vlan_id

    @property
    def vlan_prio(self) -> int:
        return self._config.vlan_prio

    # ===== 数据集管理 =====

    def add_entry(self, entry: GooseDataSetEntry) -> None:
        """添加数据集条目 (同名检查)"""
        with self._lock:
            if any(e.name == entry.name for e in self._entries):
                raise ValueError(f"数据集条目名称已存在: {entry.name}")
            self._entries.append(entry)
            self._is_created = False

    def remove_entry(self, index: int) -> None:
        with self._lock:
            if 0 <= index < len(self._entries):
                self._entries.pop(index)
                self._is_created = False

    def update_entry(self, index: int, value: Any) -> bool:
        """更新条目值，返回 True 表示值有变化 (触发 stNum 递增)

        当值变化时:
        - stNum 自动递增，sqNum 重置
        - 如果 Publisher 正在运行，立即发送 GOOSE 报文（IEC 61850 要求）
        """
        changed = False
        with self._lock:
            if 0 <= index < len(self._entries):
                old_entry = self._entries[index]
                if old_entry.value != value:
                    self._entries[index] = GooseDataSetEntry(
                        name=old_entry.name, value=value, iec_type=old_entry.iec_type
                    )
                    self._st_num += 1
                    self._sq_num = 0
                    changed = True

        if changed and self._is_running:
            try:
                self.publish()
            except Exception as e:
                log.error(f"更新条目值后立即发布 GOOSE 失败: {e}")

        return changed

    def get_entries(self) -> list[dict[str, Any]]:
        return [
            {"index": i, "name": e.name, "value": e.value, "iec_type": e.iec_type.value}
            for i, e in enumerate(self._entries)
        ]

    # ===== 底层创建 =====

    def _create_comm_parameters(self) -> None:
        """创建 CommParameters 对象"""
        if self._comm_params:
            return

        try:
            self._comm_params = iec61850.CommParameters()
        except AttributeError:
            try:
                self._comm_params = iec61850.CommParameters_create()
            except AttributeError:
                self._comm_params = None

    def _create_publisher(self) -> None:
        """创建底层 GOOSE Publisher 对象"""
        if self._is_created:
            return

        self._create_comm_parameters()
        self._publisher = iec61850.GoosePublisher_create(self._comm_params, self._config.interface)
        if not self._publisher:
            raise RuntimeError(f"GOOSE Publisher 创建失败, interface={self._config.interface}")

        adapter = _IecApiAdapter(self._publisher)

        # 设置 GOOSE 控制块属性
        if self._config.go_cb_ref:
            adapter.call("GoosePublisher_setGoCbRef", self._publisher, self._config.go_cb_ref)
        if self._config.go_id:
            adapter.call("GoosePublisher_setGoID", self._publisher, self._config.go_id)
        if self._config.data_set_ref:
            adapter.call("GoosePublisher_setDataSetRef", self._publisher, self._config.data_set_ref)

        adapter.call("GoosePublisher_setConfRev", self._publisher, self._config.conf_rev)
        adapter.call("GoosePublisher_setTimeAllowedToLive", self._publisher, self._config.time_allowed_to_live)
        adapter.call("GoosePublisher_setStNum", self._publisher, self._st_num)
        adapter.call("GoosePublisher_setSqNum", self._publisher, self._sq_num)
        adapter.call("GoosePublisher_setSimulation", self._publisher, self._config.simulation)

        # 设置目标 MAC
        if len(self._dst_mac) == 6:
            adapter.call("GoosePublisher_setDstMac", self._publisher, self._dst_mac)

        # 设置 APPID (大小写兼容)
        ok, _ = adapter.call("GoosePublisher_setAppid", self._publisher, self._config.app_id)
        if not ok:
            adapter.call("GoosePublisher_setAppId", self._publisher, self._config.app_id)

        # 设置 VLAN
        if self._config.vlan_id > 0:
            ok, _ = adapter.call(
                "GoosePublisher_setVlanTag", self._publisher, self._config.vlan_id, self._config.vlan_prio
            )
            if not ok:
                adapter.call("GoosePublisher_setVlanId", self._publisher, self._config.vlan_id)
                adapter.call("GoosePublisher_setVlanPriority", self._publisher, self._config.vlan_prio)

        self._is_created = True

    def _entry_to_mms_value(self, entry: GooseDataSetEntry) -> Any:
        """将 GooseDataSetEntry 转换为 MmsValue"""
        if entry.iec_type == IecDataType.BOOLEAN:
            return iec61850.MmsValue_newBoolean(bool(entry.value))
        elif entry.iec_type == IecDataType.INTEGER:
            return iec61850.MmsValue_newIntegerFromInt32(int(entry.value or 0))
        elif entry.iec_type == IecDataType.FLOAT:
            return iec61850.MmsValue_newFloat(float(entry.value or 0.0))
        elif entry.iec_type == IecDataType.STRING:
            return iec61850.MmsValue_newVisibleString(str(entry.value or ""))
        elif entry.iec_type == IecDataType.BITSTRING:
            return iec61850.MmsValue_newBitString(4)
        elif entry.iec_type == IecDataType.TIMESTAMP:
            return iec61850.MmsValue_newUtcTimeByMsTime(int(entry.value or 0))
        else:
            return iec61850.MmsValue_newBoolean(False)

    # ===== 生命周期 =====

    def start(self) -> bool:
        """启动 GOOSE Publisher (含定时重发)"""
        if self._is_running:
            return True

        try:
            self._create_publisher()
            self._is_running = True

            # 启动定时重发线程
            self._retransmit_stop.clear()
            self._retransmit_thread = threading.Thread(target=self._retransmit_loop, daemon=True)
            self._retransmit_thread.start()

            log.info(f"GOOSE Publisher 已启动: goCbRef={self._config.go_cb_ref}, interface={self._config.interface}")
            return True
        except Exception as e:
            log.error(f"GOOSE Publisher 启动失败: {e}")
            self._is_running = False
            return False

    def stop(self) -> None:
        """停止 GOOSE Publisher"""
        self._is_running = False
        self._retransmit_stop.set()

        if self._retransmit_thread and self._retransmit_thread.is_alive():
            self._retransmit_thread.join(timeout=2.0)

        self._destroy_publisher()
        log.info(f"GOOSE Publisher 已停止: goCbRef={self._config.go_cb_ref}")

    def _destroy_publisher(self) -> None:
        """销毁底层 Publisher"""
        if self._publisher:
            iec61850.GoosePublisher_destroy(self._publisher)
            self._publisher = None
        self._is_created = False

    def _retransmit_loop(self) -> None:
        """定时重发循环 (按照 IEC 61850 规范，GOOSE 应周期性重发)"""
        while not self._retransmit_stop.is_set():
            try:
                self.publish()
                with self._lock:
                    self._sq_num += 1
            except Exception as e:
                log.error(f"GOOSE 重发失败: {e}")

            self._retransmit_stop.wait(self._retransmit_interval)

    def publish(self) -> bool:
        """立即发布 GOOSE 报文"""
        if not self._is_running or not self._publisher:
            return False

        with self._lock:
            try:
                # 重建 Publisher (如果有变化)
                if not self._is_created:
                    self._destroy_publisher()
                    self._create_publisher()

                # 创建 LinkedList 并填充 MMS 值
                data_set_values = iec61850.LinkedList_create()
                if not data_set_values:
                    log.error("GOOSE 发布失败: 无法创建值列表")
                    return False

                try:
                    for entry in self._entries:
                        mms_val = self._entry_to_mms_value(entry)
                        if mms_val:
                            iec61850.LinkedList_add(data_set_values, mms_val)

                    # 更新序号
                    iec61850.GoosePublisher_setStNum(self._publisher, self._st_num)
                    iec61850.GoosePublisher_setSqNum(self._publisher, self._sq_num)

                    # 发布
                    result = iec61850.GoosePublisher_publish(self._publisher, data_set_values)
                finally:
                    try:
                        iec61850.LinkedList_destroyDeep(data_set_values, iec61850.MmsValue_delete)
                    except Exception:
                        with contextlib.suppress(Exception):
                            iec61850.LinkedList_destroy(data_set_values)

                if result == 0:
                    log.debug(f"GOOSE 发布成功: stNum={self._st_num}, sqNum={self._sq_num}")
                    return True
                else:
                    log.warning(f"GOOSE 发布失败: goCbRef={self._config.go_cb_ref}, result={result}")
                    return False
            except Exception as e:
                log.error(f"GOOSE 发布异常: {e}")
                return False

    def get_status(self) -> dict[str, Any]:
        """获取 Publisher 状态信息"""
        return {
            "go_cb_ref": self._config.go_cb_ref,
            "go_id": self._config.go_id,
            "data_set_ref": self._config.data_set_ref,
            "app_id": self._config.app_id,
            "conf_rev": self._config.conf_rev,
            "st_num": self._st_num,
            "sq_num": self._sq_num,
            "time_allowed_to_live": self._config.time_allowed_to_live,
            "interface": self._config.interface,
            "simulation": self._config.simulation,
            "is_running": self._is_running,
            "dst_mac": ":".join(f"{b:02X}" for b in self._dst_mac),
            "vlan_id": self._config.vlan_id,
            "vlan_prio": self._config.vlan_prio,
            "entry_count": len(self._entries),
        }
