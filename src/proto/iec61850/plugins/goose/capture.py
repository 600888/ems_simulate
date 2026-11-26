"""GOOSE 报文捕获引擎 - 原始套接字抓包 + ASN.1 解析

支持:
- 跨平台抓包 (Windows/Linux)
- 原始 GOOSE 报文解析 (Ethernet + GOOSE 头 + ASN.1 PDU)
- 环形缓冲区存储 (deque)
- 按 APPID/GoCBRef 过滤
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
import contextlib
from dataclasses import dataclass
from datetime import datetime
import platform
import socket
import struct
import threading
import time
from typing import Any

from ...log import log

# ===== 常量定义 =====

# GOOSE EtherType
ETHER_TYPE_GOOSE = 0x88B8
ETHER_TYPE_VLAN = 0x8100
ETH_P_ALL = 0x0003
SOL_PACKET = 263
PACKET_ADD_MEMBERSHIP = 1
PACKET_MR_ALLMULTI = 2


@dataclass(frozen=True, slots=True)
class CapturedPacket:
    """Single immutable captured GOOSE Ethernet frame."""

    timestamp: float
    src_mac: str
    dst_mac: str
    raw_bytes: bytes
    length: int
    app_id: int = 0
    go_cb_ref: str = ""
    go_id: str = ""
    data_set_ref: str = ""
    st_num: int = 0
    sq_num: int = 0
    time_allowed_to_live: int = 0
    conf_rev: int = 0
    simulation: bool = False
    nds_com: bool = False
    num_entries: int = 0
    data_values: tuple[dict[str, Any], ...] = ()
    parsed_fields: tuple[dict[str, Any], ...] = ()
    vlan_id: int = 0
    vlan_prio: int = 0
    has_vlan: bool = False
    interface: str = ""
    # GOOSE 帧内事件时间 t（epoch 秒）。保留旧字段名供已有调用方使用。
    send_timestamp: float = 0.0
    receive_timestamp: float = 0.0

    @property
    def formatted_time(self) -> str:
        """返回CapturedPacket当前的formattedTIME。"""
        return datetime.fromtimestamp(self.timestamp).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    def to_dict(self) -> dict[str, Any]:
        """把CapturedPacket转换为可序列化字典。"""
        return {
            "src_mac": self.src_mac,
            "dst_mac": self.dst_mac,
            "timestamp": self.timestamp,
            "receive_timestamp": self.receive_timestamp or self.timestamp,
            "event_timestamp": self.send_timestamp,
            "send_timestamp": self.send_timestamp,
            "time": self.formatted_time,
            "length": self.length,
            "app_id": self.app_id,
            "app_id_hex": f"0x{self.app_id:04X}",
            "go_cb_ref": self.go_cb_ref,
            "go_id": self.go_id,
            "data_set_ref": self.data_set_ref,
            "st_num": self.st_num,
            "sq_num": self.sq_num,
            "time_allowed_to_live": self.time_allowed_to_live,
            "conf_rev": self.conf_rev,
            "simulation": self.simulation,
            "nds_com": self.nds_com,
            "num_dat_set_entries": self.num_entries,
            "vlan_id": self.vlan_id,
            "vlan_prio": self.vlan_prio,
            "has_vlan": self.has_vlan,
            "data_values": [dict(item) for item in self.data_values],
            "fields": [dict(item) for item in self.parsed_fields],
            "hex_data": self.raw_bytes.hex(),
        }


class _RawSocketProvider:
    """跨平台原始套接字创建"""

    @staticmethod
    def create(interface: str = "") -> socket.socket | None:
        """创建捕获套接字 (跨平台)"""
        system = platform.system().lower()

        if system in ("linux", "darwin"):
            return _RawSocketProvider._create_linux_socket(interface)
        elif system == "windows":
            return _RawSocketProvider._create_windows_socket()
        else:
            log.error(f"不支持的操作系统: {system}")
            return None

    @staticmethod
    def _create_linux_socket(interface: str) -> socket.socket | None:
        """Linux: 使用 AF_PACKET 原始套接字"""
        sock = None
        try:
            # ETH_P_ALL also receives PACKET_OUTGOING copies of locally sent frames.
            sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(ETH_P_ALL))
            if interface:
                sock.bind((interface, ETH_P_ALL))
                # Join at socket scope so external GOOSE multicast still reaches this listener.
                membership = struct.pack("=iHH8s", socket.if_nametoindex(interface), PACKET_MR_ALLMULTI, 0, b"")
                sock.setsockopt(SOL_PACKET, PACKET_ADD_MEMBERSHIP, membership)
            log.info(f"Linux 原始套接字创建成功: interface={interface or 'all'}")
            return sock
        except PermissionError:
            log.error("创建 Linux GOOSE 原始套接字需要 CAP_NET_RAW 权限")
        except Exception as e:
            log.error(f"创建 Linux 套接字失败: {e}")
        if sock is not None:
            sock.close()
        return None

    @staticmethod
    def _create_windows_socket() -> socket.socket | None:
        """Windows: 使用原始 IP 套接字 + promiscuous 模式"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_IP)

            host_ip = _RawSocketProvider._get_windows_host_ip()
            if not host_ip:
                log.warning("无法获取本机 IP，使用 0.0.0.0")
                host_ip = "0.0.0.0"

            sock.bind((host_ip, 0))

            try:
                import win32file  # noqa: F401

                sock.ioctl(0x98000001, 1)
                log.info(f"Windows 原始套接字创建成功: IP={host_ip}")
            except ImportError:
                log.warning("pywin32 未安装，无法设置混杂模式，可能无法捕获 GOOSE 组播报文")
                try:
                    sock.ioctl(socket.SIO_RCVALL, socket.RCVALL_ON)
                except (AttributeError, OSError):
                    log.warning("无法启用混杂模式，捕获可能受限")
            except Exception as e:
                log.warning(f"设置混杂模式失败: {e}")

            return sock
        except PermissionError:
            log.error("需要管理员权限才能创建原始套接字 (请以管理员身份运行)")
            return None
        except Exception as e:
            log.error(f"创建 Windows 套接字失败: {e}")
            return None

    @staticmethod
    def _get_windows_host_ip() -> str | None:
        """获取本机 IP 地址"""
        try:
            hostname = socket.gethostname()
            return socket.gethostbyname(hostname)
        except Exception:
            return None


class GooseCaptureEngine:
    """GOOSE 报文捕获引擎

    功能:
    - 跨平台原始套接字抓包
    - GOOSE PDU (ASN.1 BER-TLV) 解析
    - 环形缓冲区存储 (deque)
    - 按 APPID/GoCBRef 过滤
    """

    def __init__(self, interface: str = "", max_packets: int = 500):
        """保存网卡、过滤和回调配置，并初始化抓包线程控制状态。"""
        self.interface = interface
        self._max_packets = max_packets
        self._packets: deque[CapturedPacket] = deque(maxlen=max_packets)
        self._lock = threading.Lock()
        self._capture_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._started_event = threading.Event()
        self._stop_lock = threading.Lock()
        self._stop_notifier: Callable[[], None] | None = None
        self._is_running = False
        self._packet_count = 0

        # 可选的 APPID 过滤
        self._filter_app_id: int | None = None
        # 可选的 GoCBRef 过滤
        self._filter_go_cb_ref: str = ""

        # 接收回调 (可选)
        self._callback: Callable[[CapturedPacket], None] | None = None

    # ===== 过滤设置 =====

    def set_app_id_filter(self, app_id: int | None) -> None:
        """设置 APPID 过滤 (None 表示不过滤)"""
        self._filter_app_id = app_id

    def set_go_cb_ref_filter(self, go_cb_ref: str) -> None:
        """设置 GoCBRef 过滤 (空字符串表示不过滤)"""
        self._filter_go_cb_ref = go_cb_ref

    def set_callback(self, callback: Callable[[CapturedPacket], None] | None) -> None:
        """设置捕获回调 (传入 None 清除回调)"""
        self._callback = callback

    # ===== 捕获控制 =====

    def start(self) -> bool:
        """启动 GOOSE 报文捕获"""
        if self._is_running:
            log.warning("GOOSE 捕获已在运行中")
            return True

        # signal_stop returns before cleanup. Finish the previous worker before
        # clearing its stop event or installing a new notification channel.
        if self._capture_thread and self._capture_thread.is_alive():
            if self._capture_thread is threading.current_thread():
                return False
            self._capture_thread.join(timeout=3.0)
            if self._capture_thread.is_alive():
                log.warning("GOOSE 捕获线程仍在退出中")
                return False

        self._stop_event.clear()
        self._started_event.clear()
        self._capture_thread = threading.Thread(
            target=self._capture_loop,
            daemon=True,
        )
        self._capture_thread.start()

        # Scapy/Npcap performs adapter discovery on first import and can take
        # noticeably longer than a raw AF_PACKET socket to become ready.
        startup_timeout = 5.0 if platform.system().lower() == "windows" else 0.5
        self._started_event.wait(startup_timeout)
        if not self._is_running:
            if self._capture_thread.is_alive():
                self.signal_stop()
                self._capture_thread.join(timeout=2.0)
            return False

        log.info(f"GOOSE 报文捕获已启动: interface={self.interface or 'any'}")
        return True

    def stop(self) -> None:
        """停止 GOOSE 报文捕获 (阻塞版本)"""
        self.signal_stop()
        if (
            self._capture_thread
            and self._capture_thread.is_alive()
            and self._capture_thread is not threading.current_thread()
        ):
            self._capture_thread.join(timeout=3.0)
        self._is_running = False
        log.info("GOOSE 报文捕获已停止")

    def signal_stop(self) -> None:
        """发出停止通知并唤醒捕获等待，不阻塞调用线程。"""
        with self._stop_lock:
            already_stopped = self._stop_event.is_set()
            self._stop_event.set()
            self._is_running = False
            if not already_stopped and self._stop_notifier is not None:
                self._stop_notifier()

    @property
    def is_running(self) -> bool:
        """判断GooseCaptureEngine是否处于运行状态。"""
        return self._is_running

    # ===== 数据访问 =====

    def get_packets(self, count: int = 0, filter_app_id: int | None = None) -> list[dict[str, Any]]:
        """获取捕获的报文列表"""
        with self._lock:
            packets = list(self._packets)

        if filter_app_id is not None:
            packets = [p for p in packets if p.app_id == filter_app_id]

        if count > 0:
            packets = packets[-count:]

        return [p.to_dict() for p in packets]

    def get_statistics(self) -> dict[str, Any]:
        """获取捕获统计信息"""
        with self._lock:
            total = len(self._packets)
            app_ids: dict[int, int] = {}
            go_cb_refs: dict[str, int] = {}
            for pkt in self._packets:
                if pkt.app_id:
                    app_ids[pkt.app_id] = app_ids.get(pkt.app_id, 0) + 1
                if pkt.go_cb_ref:
                    go_cb_refs[pkt.go_cb_ref] = go_cb_refs.get(pkt.go_cb_ref, 0) + 1

        return {
            "is_running": self._is_running,
            "total_captured": self._packet_count,
            "buffer_size": total,
            "max_buffer_size": self._max_packets,
            "interface": self.interface,
            "app_ids": [{"app_id": k, "app_id_hex": f"0x{k:04X}", "count": v} for k, v in sorted(app_ids.items())],
            "go_cb_refs": [{"go_cb_ref": k, "count": v} for k, v in sorted(go_cb_refs.items(), key=lambda x: -x[1])],
        }

    def clear(self) -> None:
        """清空已捕获的报文"""
        with self._lock:
            self._packets.clear()
            self._packet_count = 0

    def get_status(self) -> dict[str, Any]:
        """获取捕获器状态"""
        return {
            "interface": self.interface,
            "is_running": self._is_running,
            "max_packets": self._max_packets,
            "packet_count": self._packet_count,
            "filter_app_id": self._filter_app_id,
            "filter_go_cb_ref": self._filter_go_cb_ref,
        }

    # ===== 捕获核心 =====

    def _capture_loop(self) -> None:
        """捕获主循环"""
        if platform.system().lower() == "windows" and self._capture_loop_scapy():
            return

        sock = None
        try:
            sock = _RawSocketProvider.create(self.interface)
            if sock is None:
                log.error("创建捕获套接字失败")
                return

            self._is_running = True
            self._started_event.set()  # 通知 start() 线程启动成功

            while not self._stop_event.is_set():
                try:
                    if hasattr(sock, "settimeout"):
                        sock.settimeout(1.0)
                    raw_data = sock.recv(65535)
                    self._process_packet(raw_data)
                except TimeoutError:
                    continue
                except OSError as e:
                    if not self._stop_event.is_set():
                        log.warning(f"捕获套接字异常: {e}")
                    break

        except Exception as e:
            log.error(f"捕获循环异常: {e}")
        finally:
            self._is_running = False
            self._started_event.set()
            self._stop_event.set()
            if sock:
                with contextlib.suppress(Exception):
                    sock.close()

    def _capture_loop_scapy(self) -> bool:
        """使用 Scapy 持续捕获 GOOSE 以太网帧，并把解析结果送入统一回调。"""
        try:
            from scapy.all import Raw, conf, sniff
            from scapy.automaton import ObjectPipe
        except ImportError:
            log.error("Windows GOOSE 抓包需要安装 Scapy/Npcap，原始 IP socket 无法捕获 EtherType 0x88B8")
            return False

        capture_socket = None
        stop_pipe = None
        try:
            # Capture and stop notifications share Scapy's selectable handles,
            # including Windows events. No timeout or incoming frame is needed
            # to wake an idle capture, and the Npcap handle stays open.
            capture_socket = conf.L2listen(iface=self.interface or None)
            stop_pipe = ObjectPipe("GOOSE capture stop")
            # Both handles must use the same selector (Npcap's Windows events
            # selector supports ObjectPipe as well).
            stop_pipe.select = capture_socket.select
            with self._stop_lock:
                if self._stop_event.is_set():
                    return True
                self._stop_notifier = lambda: stop_pipe.send(Raw(b"\x00"))
                self._is_running = True
                self._started_event.set()

            sniff(
                opened_socket={capture_socket: "capture", stop_pipe: "stop"},
                prn=lambda pkt: self._process_packet(bytes(pkt)) if pkt.sniffed_on == "capture" else None,
                stop_filter=lambda _pkt: self._stop_event.is_set(),
                store=False,
            )
            return True
        except Exception as e:
            log.error(f"Windows Scapy/Npcap GOOSE 抓包失败: {e}")
            return False
        finally:
            with self._stop_lock:
                self._stop_notifier = None
                self._is_running = False
                self._started_event.set()
            if stop_pipe is not None:
                with contextlib.suppress(Exception):
                    stop_pipe.close()
            if capture_socket is not None:
                with contextlib.suppress(Exception):
                    capture_socket.close()

    def _process_packet(self, raw_data: bytes) -> None:
        """处理捕获的原始数据包"""
        if len(raw_data) < 14:
            return

        # 解析以太网帧头
        dst_mac = ":".join(f"{b:02X}" for b in raw_data[0:6])
        src_mac = ":".join(f"{b:02X}" for b in raw_data[6:12])
        eth_type = (raw_data[12] << 8) | raw_data[13]

        # 检查 VLAN
        offset = 14
        vlan_id = 0
        vlan_prio = 0
        has_vlan = False

        if eth_type == ETHER_TYPE_VLAN and len(raw_data) >= 18:
            has_vlan = True
            vlan_info = (raw_data[14] << 8) | raw_data[15]
            vlan_prio = (vlan_info >> 13) & 0x07
            vlan_id = vlan_info & 0x0FFF
            eth_type = (raw_data[16] << 8) | raw_data[17]
            offset = 18

        # 检查是否是 GOOSE 报文
        if eth_type != ETHER_TYPE_GOOSE:
            return

        # 解析 GOOSE 头
        if len(raw_data) <= offset + 8:
            return

        app_id = (raw_data[offset] << 8) | raw_data[offset + 1]

        # APPID 过滤
        if self._filter_app_id is not None and app_id != self._filter_app_id:
            return

        # 协议解析由独立解析器负责；抓包引擎只保存捕获结果。
        from src.device.core.message.parsers.goose import parse_goose

        parsed = parse_goose(raw_data)
        go_cb_ref = parsed.get("go_cb_ref")
        if not parsed["valid"] or not parsed["complete"] or not go_cb_ref:
            return

        # GoCBRef 过滤
        if self._filter_go_cb_ref and self._filter_go_cb_ref not in go_cb_ref:
            return

        # 创建不可变报文记录
        # 同一状态的重传帧携带相同的事件时间 t。
        now_ts = time.time()
        goose_time = parsed.get("goose_timestamp")
        send_ts = 0.0
        if isinstance(goose_time, dict):
            seconds = goose_time.get("unix_seconds")
            fraction = goose_time.get("fraction")
            if isinstance(seconds, (int, float)):
                send_ts = float(seconds) + float(fraction or 0)
        packet = CapturedPacket(
            timestamp=now_ts,
            receive_timestamp=now_ts,
            send_timestamp=send_ts,
            src_mac=src_mac,
            dst_mac=dst_mac,
            raw_bytes=raw_data,
            length=len(raw_data),
            app_id=app_id,
            go_cb_ref=go_cb_ref,
            go_id=parsed.get("go_id", ""),
            data_set_ref=parsed.get("data_set_ref", ""),
            st_num=parsed.get("st_num", 0),
            sq_num=parsed.get("sq_num", 0),
            time_allowed_to_live=parsed.get("time_allowed_to_live", 0),
            conf_rev=parsed.get("conf_rev", 0),
            simulation=parsed.get("simulation", False),
            nds_com=parsed.get("nds_com", False),
            num_entries=parsed.get("num_entries", 0),
            data_values=tuple(parsed["objects"]),
            parsed_fields=tuple(parsed["fields"]),
            vlan_id=vlan_id,
            vlan_prio=vlan_prio,
            has_vlan=has_vlan,
            interface=self.interface,
        )

        # 存储
        with self._lock:
            self._packets.append(packet)
            self._packet_count += 1

        # 回调
        if self._callback:
            try:
                self._callback(packet)
            except Exception as e:
                log.error(f"捕获回调异常: {e}")


# 兼容旧名 (过渡期)
GooseCapture = GooseCaptureEngine
GooseCapturedPacket = CapturedPacket

GOOSE_CAPTURE_AVAILABLE = True
