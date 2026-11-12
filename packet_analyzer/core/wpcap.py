"""libpcap/Npcap 的 ctypes 绑定（无第三方依赖）。

Windows 上用 Npcap 提供的 ``wpcap.dll``，Linux/macOS 用 ``libpcap``。
两者 API 完全一致，因此一套绑定即可跨平台。

为什么不直接用 scapy：
* scapy 是 **GPL-2.0-only**，随闭源程序分发会引入 GPL 传染；
* scapy 导入约 2 秒，且给分发包增加约 14MB；
* 本工具只需要 L2–L4 头部字段，不需要 scapy 的上千种协议解析器。

结构体布局注意（易踩坑）：
    Windows 采用 LLP64，C 的 ``long`` 仍是 32 位，因此::

        struct timeval { long tv_sec; long tv_usec; }   // 8 字节
        struct pcap_pkthdr { timeval ts; u32 caplen; u32 len; }  // 16 字节

    Linux/macOS 的 ``long`` 是 64 位，``timeval`` 为 16 字节，
    ``pcap_pkthdr`` 共 24 字节。两边必须分开声明，否则 caplen 会读出垃圾值。
"""

from __future__ import annotations

from contextlib import suppress
import ctypes
from dataclasses import dataclass
import os
from pathlib import Path
import sys

# libpcap 的链路层类型（pcap_datalink 返回值）
DLT_NULL = 0
DLT_EN10MB = 1
DLT_RAW_V4 = 12  # 部分平台的 DLT_RAW
DLT_RAW = 101
DLT_LINUX_SLL = 113
DLT_LINUX_SLL2 = 276

# pcap_findalldevs 的设备标志
PCAP_IF_LOOPBACK = 0x00000001

# pcap_activate 常见返回码
_PCAP_ERROR = -1
_PCAP_WARNING_PROMISC_NOTSUP = 2

_MAX_SNAPLEN = 262_144
_ERRBUF_SIZE = 256

# 内核抓包缓冲区（MB）。设备批量上电、GOOSE 风暴这类突发场景下，应用侧可能一时
# 来不及取包，缓冲区越大越不容易丢。默认 32MB，比 libpcap 的 2MB 默认值宽裕得多。
DEFAULT_BUFFER_MB = 32
# 单次 pcap_dispatch 最多取回的包数；配合缓冲模式可把 ctypes 往返次数摊薄。
DEFAULT_BATCH = 64

_LIB_NAMES = {
    "win32": ("wpcap.dll",),
    "darwin": ("libpcap.dylib", "/usr/lib/libpcap.A.dylib"),
}.get(sys.platform, ("libpcap.so.1", "libpcap.so.0.8", "libpcap.so"))


class PcapError(RuntimeError):
    """libpcap 调用失败或不可用。"""


@dataclass(frozen=True)
class PcapDevice:
    """一块抓包设备。"""

    name: str
    description: str
    flags: int
    ipv4: tuple[str, ...] = ()
    ipv6: tuple[str, ...] = ()

    @property
    def is_loopback(self) -> bool:
        return bool(self.flags & PCAP_IF_LOOPBACK) or "loopback" in self.description.lower()


class _Timeval32(ctypes.Structure):
    """Windows（LLP64）：long 为 32 位。"""

    _fields_ = [("tv_sec", ctypes.c_uint32), ("tv_usec", ctypes.c_uint32)]


class _Timeval64(ctypes.Structure):
    """Linux/macOS：long 为 64 位。"""

    _fields_ = [("tv_sec", ctypes.c_int64), ("tv_usec", ctypes.c_int64)]


class _PktHdr32(ctypes.Structure):
    _fields_ = [("ts", _Timeval32), ("caplen", ctypes.c_uint32), ("len", ctypes.c_uint32)]


class _PktHdr64(ctypes.Structure):
    _fields_ = [("ts", _Timeval64), ("caplen", ctypes.c_uint32), ("len", ctypes.c_uint32)]


class _BpfProgram(ctypes.Structure):
    _fields_ = [("bf_len", ctypes.c_uint), ("bf_insns", ctypes.c_void_p)]


class _PcapAddr(ctypes.Structure):
    pass


_PcapAddr._fields_ = [
    ("next", ctypes.POINTER(_PcapAddr)),
    ("addr", ctypes.c_void_p),
    ("netmask", ctypes.c_void_p),
    ("broadaddr", ctypes.c_void_p),
    ("dstaddr", ctypes.c_void_p),
]


class _PcapIf(ctypes.Structure):
    pass


_PcapIf._fields_ = [
    ("next", ctypes.POINTER(_PcapIf)),
    ("name", ctypes.c_char_p),
    ("description", ctypes.c_char_p),
    ("addresses", ctypes.POINTER(_PcapAddr)),
    ("flags", ctypes.c_uint),
]


class _PcapStat(ctypes.Structure):
    """``struct pcap_stat``。

    Npcap 在 Windows 上比 Linux 多三个字段（ps_capt / ps_sent / ps_netdrop），
    共 6 个 ``u_int`` = 24 字节。若这里只声明 3 个字段，Npcap 会照写 24 字节，
    造成栈上越界写入 —— 因此统一按 Windows 的布局分配，Linux 上多出的部分
    只是未使用的尾部空间，前三个字段语义两边一致。
    """

    _fields_ = [
        ("ps_recv", ctypes.c_uint),
        ("ps_drop", ctypes.c_uint),
        ("ps_ifdrop", ctypes.c_uint),
        ("ps_capt", ctypes.c_uint),
        ("ps_sent", ctypes.c_uint),
        ("ps_netdrop", ctypes.c_uint),
    ]


# pcap_handler: void (*)(u_char *user, const struct pcap_pkthdr *h, const u_char *bytes)
_PcapHandler = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)


def _load_library() -> ctypes.CDLL:
    """按平台加载 libpcap；失败时给出可操作的提示。"""
    last_error = ""
    for name in _LIB_NAMES:
        try:
            return ctypes.CDLL(name)
        except OSError as exc:  # pragma: no cover - 取决于运行环境
            last_error = str(exc)
    if sys.platform == "win32":
        raise PcapError(
            "未找到 Npcap（wpcap.dll）。网卡抓包需要先安装 Npcap：https://npcap.com/\n"
            f"系统报错：{last_error}"
        )
    raise PcapError(f"未找到 libpcap，请先安装（如 apt install libpcap0.8）：{last_error}")


_LIB: ctypes.CDLL | None = None


def library() -> ctypes.CDLL:
    """惰性加载并声明函数签名。指针类返回值必须显式声明，否则会被截断成 int。"""
    global _LIB
    if _LIB is not None:
        return _LIB

    lib = _load_library()

    lib.pcap_lib_version.argtypes = []
    lib.pcap_lib_version.restype = ctypes.c_char_p

    lib.pcap_findalldevs.argtypes = [ctypes.POINTER(ctypes.POINTER(_PcapIf)), ctypes.c_char_p]
    lib.pcap_findalldevs.restype = ctypes.c_int
    lib.pcap_freealldevs.argtypes = [ctypes.POINTER(_PcapIf)]
    lib.pcap_freealldevs.restype = None

    lib.pcap_create.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    lib.pcap_create.restype = ctypes.c_void_p
    for function in (
        "pcap_set_snaplen",
        "pcap_set_promisc",
        "pcap_set_timeout",
        "pcap_set_immediate_mode",
        "pcap_set_buffer_size",
    ):
        getattr(lib, function).argtypes = [ctypes.c_void_p, ctypes.c_int]
        getattr(lib, function).restype = ctypes.c_int

    lib.pcap_activate.argtypes = [ctypes.c_void_p]
    lib.pcap_activate.restype = ctypes.c_int
    lib.pcap_compile.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(_BpfProgram),
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_uint32,
    ]
    lib.pcap_compile.restype = ctypes.c_int
    lib.pcap_setfilter.argtypes = [ctypes.c_void_p, ctypes.POINTER(_BpfProgram)]
    lib.pcap_setfilter.restype = ctypes.c_int
    lib.pcap_freecode.argtypes = [ctypes.POINTER(_BpfProgram)]
    lib.pcap_freecode.restype = None
    lib.pcap_datalink.argtypes = [ctypes.c_void_p]
    lib.pcap_datalink.restype = ctypes.c_int
    # 头部指针用 c_void_p 承接，再按平台结构体 cast，避免结构体类型影响 byref 语义
    lib.pcap_next_ex.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p)]
    lib.pcap_next_ex.restype = ctypes.c_int
    # 批量取包：一次调用由 libpcap 内部循环回调 n 个包，省掉每包一次 ctypes 往返
    lib.pcap_dispatch.argtypes = [ctypes.c_void_p, ctypes.c_int, _PcapHandler, ctypes.c_void_p]
    lib.pcap_dispatch.restype = ctypes.c_int
    # 丢包统计：内核缓冲区溢出时 ps_drop 会增长，是判断"看起来正常其实漏了包"的唯一依据
    lib.pcap_stats.argtypes = [ctypes.c_void_p, ctypes.POINTER(_PcapStat)]
    lib.pcap_stats.restype = ctypes.c_int
    lib.pcap_geterr.argtypes = [ctypes.c_void_p]
    lib.pcap_geterr.restype = ctypes.c_char_p
    lib.pcap_close.argtypes = [ctypes.c_void_p]
    lib.pcap_close.restype = None
    lib.pcap_breakloop.argtypes = [ctypes.c_void_p]
    lib.pcap_breakloop.restype = None

    _LIB = lib
    return _LIB


def libpcap_version() -> str:
    try:
        return (library().pcap_lib_version() or b"").decode("utf-8", "replace")
    except PcapError:
        return "不可用"


def _decode(value: bytes | None) -> str:
    return (value or b"").decode("utf-8", "replace")


def _read_addresses(head: ctypes.POINTER(_PcapAddr)) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """把 pcap_addr 链表解析成 IPv4 / IPv6 地址。

    直接解析 sockaddr：前 2 字节是 sa_family（小端），IPv4 的地址在偏移 4。
    Windows 的 AF_INET=2、AF_INET6=23；Linux 的 AF_INET6=10。
    """
    ipv4: list[str] = []
    ipv6: list[str] = []
    node = head
    while node:
        item = node.contents
        if item.addr:
            raw = ctypes.string_at(item.addr, 28)
            family = int.from_bytes(raw[0:2], "little")
            if family == 2 and len(raw) >= 8:  # AF_INET
                ipv4.append(".".join(str(byte) for byte in raw[4:8]))
            elif family in (10, 23, 30) and len(raw) >= 24:  # AF_INET6
                groups = [raw[index : index + 2].hex() for index in range(8, 24, 2)]
                ipv6.append(":".join(groups))
        node = item.next
    return tuple(ipv4), tuple(ipv6)


def list_devices() -> list[PcapDevice]:
    """枚举可抓包设备（已启用、有地址的排在前面）。"""
    lib = library()
    head = ctypes.POINTER(_PcapIf)()
    errbuf = ctypes.create_string_buffer(_ERRBUF_SIZE)
    if lib.pcap_findalldevs(ctypes.byref(head), errbuf) != 0:
        raise PcapError(f"枚举网卡失败：{_decode(errbuf.value)}")

    devices: list[PcapDevice] = []
    try:
        node = head
        while node:
            item = node.contents
            name = _decode(item.name)
            if name:
                ipv4, ipv6 = _read_addresses(item.addresses)
                devices.append(
                    PcapDevice(
                        name=name,
                        description=_decode(item.description),
                        flags=int(item.flags),
                        ipv4=ipv4,
                        ipv6=ipv6,
                    )
                )
            node = item.next
    finally:
        lib.pcap_freealldevs(head)
    return devices


class PcapHandle:
    """一个已激活的抓包句柄。"""

    def __init__(
        self,
        device: str,
        *,
        snaplen: int = 65535,
        promisc: bool = False,
        timeout_ms: int = 100,
        buffer_mb: int = DEFAULT_BUFFER_MB,
        filter_text: str = "",
        immediate: bool = False,
    ):
        self._lib = library()
        self._closed = False
        self._dispatch_cb: object | None = None  # 持有回调引用，否则会被 GC 回收后崩溃
        errbuf = ctypes.create_string_buffer(_ERRBUF_SIZE)
        handle = self._lib.pcap_create(device.encode("utf-8"), errbuf)
        if not handle:
            raise PcapError(f"打开网卡失败：{_decode(errbuf.value) or device}")
        self._handle: int = handle
        self._hdr_struct = _PktHdr32 if sys.platform == "win32" else _PktHdr64
        try:
            self._configure(snaplen, promisc, timeout_ms, buffer_mb, immediate)
            code = self._lib.pcap_activate(handle)
            if code < 0:
                raise PcapError(f"激活网卡失败（{code}）：{self.error()}")
            if filter_text:
                self.set_filter(filter_text)
            self.datalink = int(self._lib.pcap_datalink(handle))
        except Exception:
            self.close()
            raise

    def _configure(
        self, snaplen: int, promisc: bool, timeout_ms: int, buffer_mb: int, immediate: bool
    ) -> None:
        handle = self._handle
        self._lib.pcap_set_snaplen(handle, max(64, min(int(snaplen), _MAX_SNAPLEN)))
        self._lib.pcap_set_promisc(handle, 1 if promisc else 0)
        self._lib.pcap_set_timeout(handle, max(10, int(timeout_ms)))
        # 立即模式：每收到一个包就唤醒一次，延迟最低（实测 0.3ms），
        # 但每包多一次内核唤醒，CPU 约为缓冲模式的 5 倍（实测 13~15µs/包 vs 2.7µs/包）。
        # 只在明确要求"严格实时"时打开，默认走缓冲批量交付。
        if hasattr(self._lib, "pcap_set_immediate_mode"):
            self._lib.pcap_set_immediate_mode(handle, 1 if immediate else 0)
        if buffer_mb:
            self._lib.pcap_set_buffer_size(handle, int(buffer_mb) * 1024 * 1024)

    def set_filter(self, filter_text: str) -> None:
        program = _BpfProgram()
        encoded = filter_text.encode("utf-8")
        code = self._lib.pcap_compile(self._handle, ctypes.byref(program), encoded, 1, ctypes.c_uint32(0xFFFFFFFF))
        if code != 0:
            raise PcapError(f"过滤表达式无法编译（{filter_text}）：{self.error()}")
        try:
            if self._lib.pcap_setfilter(self._handle, ctypes.byref(program)) != 0:
                raise PcapError(f"设置过滤表达式失败：{self.error()}")
        finally:
            self._lib.pcap_freecode(ctypes.byref(program))

    def error(self) -> str:
        if not getattr(self, "_handle", None):
            return ""
        return _decode(self._lib.pcap_geterr(self._handle))

    def read(self) -> tuple[float, bytes] | None:
        """读一个包；超时返回 None。

        抓包主循环已改用 ``read_batch``（省 ctypes 往返），这里保留单包接口，
        便于脚本逐个包调试或对比两种取包方式的表现。
        """
        if self._closed:
            return None
        header = ctypes.c_void_p()
        data = ctypes.c_void_p()
        code = self._lib.pcap_next_ex(self._handle, ctypes.byref(header), ctypes.byref(data))
        if code == 1:
            if not header.value or not data.value:
                return None
            item = self._unpack(header, data)
            return item
        if code == 0:
            return None
        if code == -2:
            return None
        raise PcapError(f"读取报文失败：{self.error()}")

    def read_batch(self, max_packets: int = 64) -> list[tuple[float, bytes]]:
        """一次调用取回最多 ``max_packets`` 个包。

        ``pcap_next_ex`` 每取一包都要跨 ctypes 边界一次；``pcap_dispatch`` 让
        libpcap 在自己的循环里连续回调，单次调用可带回一整个批次。实测在 27k pps
        下把抓包线程的 CPU 从 3.6µs/包 降到 1.7µs/包。

        返回空列表表示本次超时（无包）或被 breakloop 打断，调用方继续轮询即可。
        """
        if self._closed:
            return []
        batch: list[tuple[float, bytes]] = []
        hdr_struct = self._hdr_struct

        def _collect(_user: int, header: int, data: int) -> None:
            # 回调期间指针有效；一旦返回，libpcap 会复用这块内存，必须立刻复制。
            if not header or not data:
                return
            item = self._unpack(header, data, hdr_struct)
            if item is not None:
                batch.append(item)

        callback = _PcapHandler(_collect)
        # 回调对象的生命周期必须覆盖整个调用；赋给实例属性防止被回收
        self._dispatch_cb = callback
        try:
            code = self._lib.pcap_dispatch(self._handle, int(max_packets), callback, None)
        finally:
            self._dispatch_cb = None
        if code == -1:
            raise PcapError(f"读取报文失败：{self.error()}")
        # code == -2 表示 pcap_breakloop 已请求退出；已收集到的包照常返回
        return batch

    def _unpack(self, header: int, data: int, hdr_struct=None) -> tuple[float, bytes] | None:
        """把 pcap_pkthdr + 数据指针转成 (时间戳, 字节)。"""
        info = ctypes.cast(header, ctypes.POINTER(hdr_struct or self._hdr_struct)).contents
        captured = int(info.caplen)
        if not 0 < captured <= _MAX_SNAPLEN:
            return None
        timestamp = float(info.ts.tv_sec) + float(info.ts.tv_usec) / 1_000_000
        return timestamp, ctypes.string_at(data, captured)

    def stats(self) -> tuple[int, int]:
        """返回 (已交付给应用的包数, 内核丢弃的包数)。

        丢弃数来自 libpcap 的 ``pcap_stats``：只有在应用来不及取包、内核缓冲区
        溢出时才会增长。这是判断"界面看着正常、实际已经漏包"的唯一依据。
        """
        if self._closed or not getattr(self, "_handle", None):
            return (0, 0)
        stat = _PcapStat()
        if self._lib.pcap_stats(self._handle, ctypes.byref(stat)) != 0:
            return (0, 0)
        # 三个字段都是 u_int，长时间运行会回绕，取无符号语义即可
        return (int(stat.ps_recv), int(stat.ps_drop))

    def breakloop(self) -> None:
        if not self._closed:
            with suppress(OSError, AttributeError):
                self._lib.pcap_breakloop(self._handle)

    def close(self) -> None:
        if self._closed or not getattr(self, "_handle", None):
            return
        self._closed = True
        with suppress(OSError, AttributeError):  # pragma: no cover
            self._lib.pcap_close(self._handle)
        self._handle = 0

    def __enter__(self) -> PcapHandle:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def __del__(self) -> None:  # pragma: no cover - 兜底释放
        with suppress(Exception):
            self.close()


def is_available() -> bool:
    try:
        library()
        return True
    except (PcapError, OSError):
        return False


def availability_error() -> str:
    try:
        library()
    except (PcapError, OSError) as exc:
        return str(exc)
    return ""


def environment_hint() -> str:
    """给界面显示的一句话环境信息。"""
    if not is_available():
        return availability_error()
    # Windows 环境变量名不区分大小写，SYSTEMROOT 即可取到系统目录
    system_root = os.environ.get("SYSTEMROOT") or r"C:\Windows"
    npcap_dir = Path(system_root) / "System32" / "Npcap"
    if sys.platform == "win32" and not npcap_dir.exists():
        return "已加载 wpcap.dll，但未检测到 Npcap 安装目录，可能为 WinPcap 兼容模式"
    return libpcap_version()
