"""标准 pcap 报文日志的读写（无第三方依赖）。

日志采用 libpcap 的经典格式，好处是：

* **Wireshark / tshark 可直接打开**，现场分析不用额外工具；
* 本工具也能读回来回放（``read_pcap``），日志不会变成死数据；
* 格式极简（24 字节文件头 + 每包 16 字节记录头），不引入任何依赖。

文件布局（全部小端，本程序写出的字节序由 magic 声明）::

    全局头 24 字节:
        magic(4) 0xA1B2C3D4=微秒  0xA1B23C4D=纳秒
        version_major(2) version_minor(2)
        thiszone(4) sigfigs(4) snaplen(4) network(4)=链路类型
    每包:
        ts_sec(4) ts_usec(4) incl_len(4) orig_len(4) + 帧数据

抓包线程写盘会影响收包，因此写入走缓冲 + 定时 flush，
并用锁保证「停止抓包时把尾部数据刷干净」。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import struct
import sys
import threading
import time

MAGIC_MICRO = 0xA1B2C3D4
MAGIC_NANO = 0xA1B23C4D
_MAGIC_SWAPPED_MICRO = 0xD4C3B2A1
_MAGIC_SWAPPED_NANO = 0x4D3CB2A1
_VERSION = (2, 4)
DEFAULT_SNAPLEN = 65535

# 每写多少字节刷一次盘；过小伤性能，过大则异常退出时丢数据
_FLUSH_BYTES = 64 * 1024


class PcapFileError(RuntimeError):
    """pcap 文件读写失败。"""


def default_log_name(interface: str = "", now: datetime | None = None) -> str:
    """生成日志文件名，带网卡名与时间戳。"""
    stamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    # 设备名形如 \Device\NPF_{GUID}，只取可读部分并去掉非法字符
    tail = interface.replace("\\", "/").rstrip("/").split("/")[-1]
    tail = "".join(char for char in tail if char.isalnum() or char in "-_")[:24]
    return f"{tail}_{stamp}.pcap" if tail else f"capture_{stamp}.pcap"


@dataclass
class PcapRecord:
    """从 pcap 文件读回的一帧。"""

    timestamp: float
    data: bytes


class PcapWriter:
    """把抓到的帧写成 pcap 日志。

    可在抓包线程中并发调用 ``write``，内部缓冲后批量落盘。
    """

    def __init__(self, path: str | Path, linktype: int, *, snaplen: int = DEFAULT_SNAPLEN):
        self.path = Path(path)
        self.linktype = int(linktype)
        self.snaplen = int(snaplen)
        self._lock = threading.Lock()
        self._pending = 0
        self._count = 0
        self._closed = False
        self._error = ""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._file = self.path.open("wb")
        except OSError as exc:
            raise PcapFileError(f"无法创建日志文件：{exc}") from exc
        try:
            self._file.write(
                struct.pack(
                    "<IHHiIII",
                    MAGIC_MICRO,
                    *_VERSION,
                    0,
                    0,
                    self.snaplen,
                    self.linktype,
                )
            )
            self._file.flush()
        except OSError as exc:
            self._file.close()
            raise PcapFileError(f"写入日志文件头失败：{exc}") from exc

    # -- 写入 -------------------------------------------------------------
    def write(self, data: bytes, timestamp: float | None = None) -> bool:
        """追加一帧。失败时记录原因并返回 False，不抛异常打断抓包。"""
        if self._closed or not data:
            return False
        stamp = time.time() if timestamp is None else float(timestamp)
        seconds = int(stamp)
        micros = int((stamp - seconds) * 1_000_000)
        if micros >= 1_000_000:  # 浮点误差兜底
            seconds += 1
            micros -= 1_000_000
        payload = data[: self.snaplen]
        with self._lock:
            if self._closed:
                return False
            try:
                self._file.write(
                    struct.pack("<IIII", seconds, micros, len(payload), len(data)) + payload
                )
            except OSError as exc:
                self._error = f"写日志失败：{exc}"
                return False
            self._count += 1
            self._pending += len(payload) + 16
            if self._pending >= _FLUSH_BYTES:
                self._flush_locked()
            return True

    def _flush_locked(self) -> None:
        try:
            self._file.flush()
        except OSError as exc:
            self._error = f"刷新日志失败：{exc}"
        self._pending = 0

    def flush(self) -> None:
        with self._lock:
            if not self._closed:
                self._flush_locked()

    # -- 状态 -------------------------------------------------------------
    @property
    def count(self) -> int:
        return self._count

    @property
    def error(self) -> str:
        return self._error

    @property
    def closed(self) -> bool:
        return self._closed

    def size(self) -> int:
        """当前日志大小（含尚未落盘的缓冲，反映真实写入量）。"""
        if self._closed:
            try:
                return self.path.stat().st_size
            except OSError:
                return 0
        try:
            return int(self._file.tell())
        except (OSError, ValueError):
            return 0

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            try:
                self._file.flush()
                self._file.close()
            except OSError as exc:
                self._error = f"关闭日志失败：{exc}"

    def __enter__(self) -> PcapWriter:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def read_pcap(path: str | Path) -> tuple[int, list[PcapRecord]]:
    """读取 pcap 文件，返回 (链路类型, 记录列表)。

    同时支持两种字节序与微秒/纳秒两种精度，便于回放其它工具生成的日志。
    """
    try:
        blob = Path(path).read_bytes()
    except OSError as exc:
        raise PcapFileError(f"无法读取文件：{exc}") from exc
    if len(blob) < 24:
        raise PcapFileError("文件过短，不是有效的 pcap 文件")

    magic = struct.unpack("<I", blob[:4])[0]
    if magic in (MAGIC_MICRO, MAGIC_NANO):
        endian = "<"
        nanos = magic == MAGIC_NANO
    elif magic in (_MAGIC_SWAPPED_MICRO, _MAGIC_SWAPPED_NANO):
        endian = ">"
        nanos = magic == _MAGIC_SWAPPED_NANO
    else:
        raise PcapFileError("文件头不是 pcap 格式（可能是 pcapng，请另存为 pcap）")

    _major, _minor, _zone, _sigfigs, _snaplen, linktype = struct.unpack(endian + "HHiIII", blob[4:24])
    records: list[PcapRecord] = []
    offset = 24
    total = len(blob)
    while offset + 16 <= total:
        seconds, fraction, incl_len, _orig_len = struct.unpack(endian + "IIII", blob[offset : offset + 16])
        offset += 16
        if incl_len > _snaplen and _snaplen:
            raise PcapFileError(f"包长度异常（{incl_len} > snaplen {_snaplen}），文件可能已损坏")
        if offset + incl_len > total:
            break  # 末尾被截断（例如抓包程序异常退出），保留已读到的部分
        data = blob[offset : offset + incl_len]
        offset += incl_len
        divisor = 1_000_000_000 if nanos else 1_000_000
        records.append(PcapRecord(timestamp=seconds + fraction / divisor, data=data))
    return linktype, records


def is_pcap_file(path: str | Path) -> bool:
    """按 magic 判断是否是 pcap（不依赖扩展名）。"""
    try:
        with Path(path).open("rb") as handle:
            head = handle.read(4)
    except OSError:
        return False
    if len(head) < 4:
        return False
    return struct.unpack("<I", head)[0] in (MAGIC_MICRO, MAGIC_NANO, _MAGIC_SWAPPED_MICRO, _MAGIC_SWAPPED_NANO)


def default_log_dir() -> Path:
    """日志默认目录：程序所在目录下的 logs/。

    开发态取项目目录，打包后取 exe 所在目录 —— 用户从快捷方式启动时
    工作目录并不可靠，不能拿 cwd 当基准。
    """
    frozen = getattr(sys, "frozen", False)
    base = Path(sys.executable).resolve().parent if frozen else Path(__file__).resolve().parents[1]
    return base / "logs"
