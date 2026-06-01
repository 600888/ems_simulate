"""GOOSE 报文捕获引擎 - 原始套接字抓包 + ASN.1 解析

支持:
- 跨平台抓包 (Windows/Linux)
- 原始 GOOSE 报文解析 (Ethernet + GOOSE 头 + ASN.1 PDU)
- 环形缓冲区存储 (deque)
- 按 APPID/GoCBRef 过滤
"""

from __future__ import annotations

from collections import deque
import contextlib
from dataclasses import dataclass, field
from datetime import datetime
import platform
import socket
import struct
import threading
import time
from typing import Any, Callable, Optional, Tuple

from ...log import log
from .types import MmsType

# ===== 常量定义 =====

# GOOSE EtherType
ETHER_TYPE_GOOSE = 0x88B8
ETHER_TYPE_VLAN = 0x8100

# GOOSE PDU 标签 (ASN.1 BER-TLV)
TAG_GOOSE_PDU = 0xA1
TAG_GOCB_REF = 0x80
TAG_TIME_ALLOWED_TO_LIVE = 0x81
TAG_DATASET = 0x82
TAG_GO_ID = 0x83
TAG_ST_NUM = 0x84
TAG_SQ_NUM = 0x85
TAG_SIMULATION = 0x86
TAG_CONF_REV = 0x87
TAG_NDS_COM = 0x88
TAG_NUM_DAT_SET_ENTRIES = 0x89
TAG_ALL_DATA = 0x8A

# MMS 数据类型 (BER-TLV within ALL_DATA) - 捕获引擎中的 BER 标签
MMS_TAG_BOOLEAN = 0x09
MMS_TAG_INTEGER = 0x02
MMS_TAG_BIT_STRING = 0x03
MMS_TAG_OCTET_STRING = 0x04
MMS_TAG_VISIBLE_STRING = 0x1A
MMS_TAG_UTC_TIME = 0x11
MMS_TAG_FLOAT = 0x07
MMS_TAG_UNSIGNED = 0x06


@dataclass(frozen=True, slots=True)
class CapturedPacket:
    """单条捕获的 GOOSE 报文 (不可变值对象)"""

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
    vlan_id: int = 0
    vlan_prio: int = 0
    has_vlan: bool = False
    interface: str = ""

    @property
    def formatted_time(self) -> str:
        dt = datetime.fromtimestamp(self.timestamp)
        return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    def to_dict(self) -> dict[str, Any]:
        return {
            "src_mac": self.src_mac,
            "dst_mac": self.dst_mac,
            "timestamp": self.timestamp,
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
            "data_values": list(self.data_values),
            "hex_data": self.raw_bytes.hex(),
            "hex_string": self._format_hex(),
        }

    def _format_hex(self) -> str:
        """格式化十六进制显示 (每16字节一行)"""
        lines = []
        for i in range(0, len(self.raw_bytes), 16):
            chunk = self.raw_bytes[i : i + 16]
            hex_part = " ".join(f"{b:02x}" for b in chunk)
            ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
            lines.append(f"{i:04x}  {hex_part:<48}  {ascii_part}")
        return "\n".join(lines)


class _GoosePduParser:
    """GOOSE PDU (ASN.1 BER-TLV) 解析器"""

    @staticmethod
    def parse(data: bytes, offset: int) -> dict[str, Any]:
        """解析 GOOSE PDU，返回解析后的字段字典"""
        result: dict[str, Any] = {
            "go_cb_ref": "",
            "go_id": "",
            "data_set_ref": "",
            "st_num": 0,
            "sq_num": 0,
            "time_allowed_to_live": 0,
            "conf_rev": 0,
            "simulation": False,
            "nds_com": False,
            "num_entries": 0,
            "data_values": [],
        }

        if offset >= len(data):
            return result

        if data[offset] != TAG_GOOSE_PDU:
            log.debug(f"GOOSE PDU 起始标签不符合预期: 0x{data[offset]:02X}")
            return result

        offset += 1
        pdu_length, offset = _GoosePduParser._read_ber_length(data, offset)
        if pdu_length is None or pdu_length < 0:
            return result

        pdu_end = offset + pdu_length
        if pdu_end > len(data):
            pdu_end = len(data)

        while offset < pdu_end:
            tag = data[offset]
            offset += 1

            field_length, offset = _GoosePduParser._read_ber_length(data, offset)
            if field_length is None:
                break

            field_end = offset + field_length
            if field_end > len(data):
                break

            if tag == TAG_GOCB_REF:
                result["go_cb_ref"] = data[offset:field_end].decode("utf-8", errors="replace")
            elif tag == TAG_TIME_ALLOWED_TO_LIVE:
                result["time_allowed_to_live"] = _GoosePduParser._parse_ber_integer(data, offset, field_end)
            elif tag == TAG_DATASET:
                result["data_set_ref"] = data[offset:field_end].decode("utf-8", errors="replace")
            elif tag == TAG_GO_ID:
                result["go_id"] = data[offset:field_end].decode("utf-8", errors="replace")
            elif tag == TAG_ST_NUM:
                result["st_num"] = _GoosePduParser._parse_ber_integer(data, offset, field_end)
            elif tag == TAG_SQ_NUM:
                result["sq_num"] = _GoosePduParser._parse_ber_integer(data, offset, field_end)
            elif tag == TAG_SIMULATION:
                result["simulation"] = data[offset] != 0
            elif tag == TAG_CONF_REV:
                result["conf_rev"] = _GoosePduParser._parse_ber_integer(data, offset, field_end)
            elif tag == TAG_NDS_COM:
                result["nds_com"] = data[offset] != 0
            elif tag == TAG_NUM_DAT_SET_ENTRIES:
                result["num_entries"] = _GoosePduParser._parse_ber_integer(data, offset, field_end)
            elif tag == TAG_ALL_DATA:
                result["data_values"] = _GoosePduParser._parse_ber_all_data(data, offset, field_end)

            offset = field_end

        return result

    @staticmethod
    def _read_ber_length(data: bytes, offset: int) -> tuple[int | None, int]:
        """读取 BER-TLV 长度字段"""
        if offset >= len(data):
            return None, offset

        first = data[offset]
        offset += 1

        if first & 0x80:
            num_bytes = first & 0x7F
            if num_bytes == 0:
                return None, offset
            if offset + num_bytes > len(data):
                return None, offset
            length = 0
            for _ in range(num_bytes):
                length = (length << 8) | data[offset]
                offset += 1
            return length, offset
        else:
            return first, offset

    @staticmethod
    def _parse_ber_integer(data: bytes, start: int, end: int) -> int:
        """解析 BER 编码的整数"""
        value = 0
        for i in range(start, end):
            value = (value << 8) | data[i]
        return value

    @staticmethod
    def _parse_ber_all_data(data: bytes, start: int, end: int) -> list[dict[str, Any]]:
        """解析 ALL_DATA (SEQUENCE OF Data)"""
        values: list[dict[str, Any]] = []
        offset = start

        while offset < end:
            if offset >= end:
                break

            mms_tag = data[offset]
            offset += 1

            mms_length, offset = _GoosePduParser._read_ber_length(data, offset)
            if mms_length is None:
                break

            field_end = offset + mms_length
            if field_end > end:
                break

            entry: dict[str, Any] = {"type": "unknown", "value": None}

            if mms_tag == MMS_TAG_BOOLEAN:
                entry["type"] = "boolean"
                entry["value"] = bool(data[offset])
            elif mms_tag == MMS_TAG_INTEGER:
                entry["type"] = "integer"
                entry["value"] = _GoosePduParser._parse_ber_integer(data, offset, field_end)
            elif mms_tag == MMS_TAG_BIT_STRING:
                entry["type"] = "bitstring"
                data[offset] if mms_length > 0 else 0
                val = 0
                for i in range(offset + 1, field_end):
                    val = (val << 8) | data[i]
                entry["value"] = val
            elif mms_tag == MMS_TAG_OCTET_STRING:
                entry["type"] = "octet_string"
                entry["value"] = data[offset:field_end].hex()
            elif mms_tag == MMS_TAG_VISIBLE_STRING:
                entry["type"] = "string"
                entry["value"] = data[offset:field_end].decode("utf-8", errors="replace")
            elif mms_tag == MMS_TAG_UTC_TIME:
                entry["type"] = "timestamp"
                entry["value"] = _GoosePduParser._parse_ber_integer(data, offset, field_end)
            elif mms_tag == MMS_TAG_FLOAT:
                entry["type"] = "float"
                if mms_length >= 4:
                    entry["value"] = round(struct.unpack(">f", data[offset : offset + 4])[0], 6)
                else:
                    entry["value"] = 0.0
            elif mms_tag == MMS_TAG_UNSIGNED:
                entry["type"] = "unsigned"
                entry["value"] = _GoosePduParser._parse_ber_integer(data, offset, field_end)
            else:
                entry["type"] = f"unknown(0x{mms_tag:02X})"
                entry["value"] = data[offset:field_end].hex()

            values.append(entry)
            offset = field_end

        return values


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
        try:
            sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x0003))
            if interface:
                sock.bind((interface, 0))
            log.info(f"Linux 原始套接字创建成功: interface={interface or 'all'}")
            return sock
        except PermissionError:
            log.error("需要 root 权限才能创建原始套接字")
            return None
        except Exception as e:
            log.error(f"创建 Linux 套接字失败: {e}")
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
                import win32file

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
        self.interface = interface
        self._max_packets = max_packets
        self._packets: deque[CapturedPacket] = deque(maxlen=max_packets)
        self._lock = threading.Lock()
        self._capture_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
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

        self._stop_event.clear()
        self._capture_thread = threading.Thread(
            target=self._capture_loop,
            daemon=True,
        )
        self._capture_thread.start()

        # 等待线程启动
        self._stop_event.wait(0.5)
        if not self._is_running:
            if self._capture_thread.is_alive():
                self._stop_event.set()
                self._capture_thread.join(timeout=2.0)
            return False

        log.info(f"GOOSE 报文捕获已启动: interface={self.interface or 'any'}")
        return True

    def stop(self) -> None:
        """停止 GOOSE 报文捕获 (阻塞版本)"""
        self._stop_event.set()
        if self._capture_thread and self._capture_thread.is_alive():
            self._capture_thread.join(timeout=3.0)
        self._is_running = False
        log.info("GOOSE 报文捕获已停止")

    def signal_stop(self) -> None:
        """信号停止捕获 (非阻塞，仅设置停止标记)"""
        self._stop_event.set()
        self._is_running = False

    @property
    def is_running(self) -> bool:
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
        sock = None
        try:
            sock = _RawSocketProvider.create(self.interface)
            if sock is None:
                log.error("创建捕获套接字失败")
                return

            self._is_running = True
            self._stop_event.set()  # 通知 start() 线程启动成功

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
            self._stop_event.set()
            if sock:
                with contextlib.suppress(Exception):
                    sock.close()

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
        if len(raw_data) < offset + 8:
            return

        app_id = (raw_data[offset] << 8) | raw_data[offset + 1]

        # APPID 过滤
        if self._filter_app_id is not None and app_id != self._filter_app_id:
            return

        # 解析 GOOSE PDU
        pdu_start = offset + 8
        parsed = _GoosePduParser.parse(raw_data, pdu_start)

        # GoCBRef 过滤
        if self._filter_go_cb_ref and self._filter_go_cb_ref not in parsed["go_cb_ref"]:
            return

        # 创建不可变报文记录
        packet = CapturedPacket(
            timestamp=time.time(),
            src_mac=src_mac,
            dst_mac=dst_mac,
            raw_bytes=raw_data,
            length=len(raw_data),
            app_id=app_id,
            go_cb_ref=parsed["go_cb_ref"],
            go_id=parsed["go_id"],
            data_set_ref=parsed["data_set_ref"],
            st_num=parsed["st_num"],
            sq_num=parsed["sq_num"],
            time_allowed_to_live=parsed["time_allowed_to_live"],
            conf_rev=parsed["conf_rev"],
            simulation=parsed["simulation"],
            nds_com=parsed["nds_com"],
            num_entries=parsed["num_entries"],
            data_values=tuple(parsed["data_values"]),
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
