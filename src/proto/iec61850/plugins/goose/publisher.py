"""GOOSE 发布者 - 基于 pyiec61850 实现 GOOSE 报文发布

管理单个 GoCB 的报文发布、数据集、序号、定时重发。
线程安全: _lock 保护 _entries、_st_num、_sq_num。
"""

from __future__ import annotations

import contextlib
import platform
import struct
import threading
import time
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
        self._uses_npcap_transport = False

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

        if self._comm_params is None:
            raise RuntimeError("当前 pyiec61850 不支持 GOOSE CommParameters")

        # libiec61850 consumes all Ethernet parameters when
        # GoosePublisher_create is called. Setting them on the publisher
        # afterwards is too late (and those setters do not exist in the
        # standard API).
        self._comm_params.appId = int(self._config.app_id) & 0xFFFF
        self._comm_params.vlanId = int(self._config.vlan_id) & 0x0FFF
        self._comm_params.vlanPriority = int(self._config.vlan_prio) & 0x07

        if len(self._dst_mac) != 6:
            raise ValueError(f"GOOSE 目标 MAC 必须为 6 字节: {self._dst_mac}")
        set_dst_address = getattr(iec61850, "CommParameters_setDstAddress", None)
        if callable(set_dst_address):
            set_dst_address(self._comm_params, *(int(value) & 0xFF for value in self._dst_mac))
        else:
            # Compatibility fallback for bindings exposing only the SWIG
            # unsigned-char pointer.
            import ctypes

            mac_ptr = int(self._comm_params.dstAddress)
            for index, value in enumerate(self._dst_mac):
                ctypes.memset(mac_ptr + index, int(value) & 0xFF, 1)

    def _create_publisher(self) -> None:
        """创建底层 GOOSE Publisher 对象"""
        if self._is_created:
            return

        # The bundled Windows libiec61850 uses the legacy WinPcap adapter
        # index API. With modern Npcap it can return success while no frame is
        # transmitted. Receiver/capture already use Scapy/Npcap on Windows;
        # use the same reliable transport for publishing.
        if platform.system() == "Windows":
            try:
                from scapy.all import sendp  # noqa: F401
            except ImportError as exc:
                raise RuntimeError("Windows GOOSE 发布需要安装 Scapy/Npcap") from exc
            self._publisher = object()
            self._uses_npcap_transport = True
            self._is_created = True
            return

        self._create_comm_parameters()
        self._publisher = iec61850.GoosePublisher_create(self._comm_params, self._config.interface)
        if not self._publisher:
            raise RuntimeError(f"GOOSE Publisher 创建失败, interface={self._config.interface}")

        adapter = _IecApiAdapter()

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

            # Perform one real send before reporting success. Previously the
            # API returned “started” after allocating the native object even
            # when opening the adapter or transmitting frames failed later in
            # the background thread.
            if not self.publish():
                raise RuntimeError(f"首次 GOOSE 报文发送失败，请检查 Npcap、管理员权限和网卡: {self._config.interface}")
            with self._lock:
                self._sq_num += 1

            # 启动定时重发线程
            self._retransmit_stop.clear()
            self._retransmit_thread = threading.Thread(target=self._retransmit_loop, daemon=True)
            self._retransmit_thread.start()

            log.info(f"GOOSE Publisher 已启动: goCbRef={self._config.go_cb_ref}, interface={self._config.interface}")
            return True
        except Exception as e:
            log.error(f"GOOSE Publisher 启动失败: {e}")
            self._is_running = False
            self._destroy_publisher()
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
            if not self._uses_npcap_transport:
                iec61850.GoosePublisher_destroy(self._publisher)
            self._publisher = None
        self._uses_npcap_transport = False
        self._is_created = False

    @staticmethod
    def _ber_length(length: int) -> bytes:
        if length < 0x80:
            return bytes([length])
        encoded = length.to_bytes((length.bit_length() + 7) // 8, "big")
        return bytes([0x80 | len(encoded)]) + encoded

    @classmethod
    def _ber_tlv(cls, tag: int, value: bytes) -> bytes:
        return bytes([tag]) + cls._ber_length(len(value)) + value

    @staticmethod
    def _unsigned_bytes(value: int) -> bytes:
        value = max(0, int(value))
        encoded = value.to_bytes(max(1, (value.bit_length() + 7) // 8), "big")
        if encoded[0] & 0x80:
            encoded = b"\x00" + encoded
        return encoded

    @staticmethod
    def _signed_bytes(value: int) -> bytes:
        value = int(value)
        size = max(1, (value.bit_length() + 8) // 8)
        encoded = value.to_bytes(size, "big", signed=True)
        while len(encoded) > 1 and (
            (encoded[0] == 0 and not encoded[1] & 0x80) or (encoded[0] == 0xFF and encoded[1] & 0x80)
        ):
            encoded = encoded[1:]
        return encoded

    @staticmethod
    def _utc_time(timestamp_ms: int) -> bytes:
        seconds, milliseconds = divmod(max(0, int(timestamp_ms)), 1000)
        fraction = int(milliseconds / 1000 * (1 << 24))
        return seconds.to_bytes(4, "big") + fraction.to_bytes(3, "big") + b"\x0a"

    def _encode_mms_data(self, entry: GooseDataSetEntry) -> bytes:
        if entry.iec_type == IecDataType.BOOLEAN:
            return self._ber_tlv(0x83, b"\xff" if bool(entry.value) else b"\x00")
        if entry.iec_type == IecDataType.INTEGER:
            return self._ber_tlv(0x85, self._signed_bytes(int(entry.value or 0)))
        if entry.iec_type == IecDataType.FLOAT:
            return self._ber_tlv(0x87, b"\x08" + struct.pack(">f", float(entry.value or 0.0)))
        if entry.iec_type == IecDataType.STRING:
            return self._ber_tlv(0x8A, str(entry.value or "").encode("utf-8"))
        if entry.iec_type == IecDataType.BITSTRING:
            value = int(entry.value or 0) & 0x0F
            return self._ber_tlv(0x84, bytes([4, value << 4]))
        if entry.iec_type == IecDataType.TIMESTAMP:
            return self._ber_tlv(0x91, self._utc_time(int(entry.value or 0)))
        return self._ber_tlv(0x83, b"\x00")

    def _build_goose_payload(self) -> bytes:
        now_ms = int(time.time() * 1000)
        all_data = b"".join(self._encode_mms_data(entry) for entry in self._entries)
        fields = b"".join(
            [
                self._ber_tlv(0x80, self._config.go_cb_ref.encode("utf-8")),
                self._ber_tlv(0x81, self._unsigned_bytes(self._config.time_allowed_to_live)),
                self._ber_tlv(0x82, self._config.data_set_ref.encode("utf-8")),
                self._ber_tlv(0x83, self._config.go_id.encode("utf-8")),
                self._ber_tlv(0x84, self._utc_time(now_ms)),
                self._ber_tlv(0x85, self._unsigned_bytes(self._st_num)),
                self._ber_tlv(0x86, self._unsigned_bytes(self._sq_num)),
                self._ber_tlv(0x87, b"\xff" if self._config.simulation else b"\x00"),
                self._ber_tlv(0x88, self._unsigned_bytes(self._config.conf_rev)),
                self._ber_tlv(0x89, b"\x00"),
                self._ber_tlv(0x8A, self._unsigned_bytes(len(self._entries))),
                self._ber_tlv(0xAB, all_data),
            ]
        )
        pdu = self._ber_tlv(0x61, fields)
        goose_length = 8 + len(pdu)
        header = struct.pack(">HHHH", self._config.app_id & 0xFFFF, goose_length, 0, 0)
        return header + pdu

    def _publish_with_npcap(self) -> bool:
        try:
            from scapy.all import Dot1Q, Ether, Raw, sendp

            dst = ":".join(f"{value:02x}" for value in self._dst_mac)
            if self._config.vlan_id > 0:
                frame = (
                    Ether(dst=dst)
                    / Dot1Q(prio=self._config.vlan_prio, vlan=self._config.vlan_id, type=0x88B8)
                    / Raw(self._build_goose_payload())
                )
            else:
                frame = Ether(dst=dst, type=0x88B8) / Raw(self._build_goose_payload())
            sendp(frame, iface=self._config.interface, count=1, verbose=False)
            return True
        except Exception as e:
            log.error(f"GOOSE Npcap 发布失败: interface={self._config.interface}, error={e}")
            return False

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

                if self._uses_npcap_transport:
                    result = self._publish_with_npcap()
                    if result:
                        log.debug(f"GOOSE 发布成功 (Npcap): stNum={self._st_num}, sqNum={self._sq_num}")
                    return result

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
