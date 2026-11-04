"""网卡抓包引擎：直接用 libpcap/Npcap 从网卡被动抓取报文。

与 ``capture.py`` 的 TCP 直连模式互补：

* 本模块**被动**监听网卡，能看到链路上所有通讯（含设备与设备之间）。
* 抓到的 TCP 段按流做尽力而为的重组，再交给 ``FrameSplitter`` 按协议分帧。
* 支持 IP / 端口 BPF 预过滤，减少无关流量。
* 同时能抓 GOOSE 这类二层报文（以太网帧原样交给 GOOSE 解析器）。

底层不用 scapy：scapy 是 GPL-2.0，随闭源程序分发会引入 GPL 传染，
且导入需约 2 秒、增加约 14MB 体积。这里只要 L2–L4 头部，
由 ``wpcap`` 直接调 libpcap、``linklayer`` 自行解析。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import threading
import time
from typing import Any

from . import ifaces, linklayer, pcapfile, registry, wpcap

# 常见工控服务端口，用于在未指定主站时推断请求方向
SERVER_PORTS = {102, 105, 502, 2404, 20000, 4059, 4840}

# 单条流空闲多久后释放（秒）
FLOW_IDLE_TIMEOUT = 120.0
MAX_FLOWS = 512


@dataclass
class PcapConfig:
    """网卡抓包参数。"""

    interface: str = ""
    protocol: str = registry.AUTO
    link_address_size: int = 1
    ip_filter: str = ""
    port_filter: int = 0
    master_ip: str = ""
    promisc: bool = True
    # 报文日志开关：打开后把抓到的帧另存为 pcap（Wireshark 可直接打开）
    log_enabled: bool = False
    log_dir: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PcapConfig:
        allowed = set(cls.__dataclass_fields__)
        return cls(**{key: value for key, value in data.items() if key in allowed})

    def filter_list(self) -> list[str]:
        """把 IP 过滤输入拆成列表，兼容逗号、分号、空格分隔。"""
        raw = self.ip_filter.replace(";", ",").replace(" ", ",")
        return [item.strip() for item in raw.split(",") if item.strip()]

    def bpf(self) -> str:
        """构造 BPF 表达式。

        无 IP 过滤时要把 GOOSE（二层，无 IP）也纳入，否则选 GOOSE 协议抓包会一直空；
        一旦指定了 IP 过滤，GOOSE 本就无 IP 可言，自然被排除。
        """
        clauses: list[str] = []
        filters = self.filter_list()
        if filters:
            hosts = " or ".join(f"host {item}" for item in filters[:8])
            clauses.append(f"({hosts})")
        if self.port_filter:
            clauses.append(f"port {int(self.port_filter)}")
        if filters or self.port_filter:
            clauses.append("(tcp or udp)")
        else:
            clauses.append(f"(tcp or udp or (ether proto 0x{linklayer.ETHERTYPE_GOOSE:04x}))")
        return " and ".join(clauses)

    def has_filter(self) -> bool:
        """是否设置了抓包过滤条件（IP 或端口）。"""
        return bool(self.filter_list()) or bool(self.port_filter)


@dataclass
class FrameMeta:
    """抓到的应用层帧的网络元信息。"""

    src_ip: str = ""
    src_port: int = 0
    dst_ip: str = ""
    dst_port: int = 0
    transport: str = "TCP"
    role: str = registry.ROLE_REQUEST

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


FrameCallback = Any  # (bytes, str, FrameMeta) -> None
StatusCallback = Any
ErrorCallback = Any


class _Flow:
    """一条 TCP/UDP 流的分帧状态。"""

    __slots__ = ("splitter", "next_seq", "last_seen")

    def __init__(self, protocol: str, link_address_size: int):
        self.splitter = registry.FrameSplitter(protocol, link_address_size=link_address_size)
        self.next_seq: int | None = None
        self.last_seen = time.time()


def _flow_key(src_ip: str, src_port: int, dst_ip: str, dst_port: int) -> tuple[tuple[str, int], tuple[str, int]]:
    """双向流标识：把两端排序，使同一连接的两个方向得到相同 key。"""
    left = (src_ip, src_port)
    right = (dst_ip, dst_port)
    return (left, right) if left <= right else (right, left)


def infer_role(
    src_ip: str,
    src_port: int,
    dst_ip: str,
    dst_port: int,
    *,
    master_ip: str = "",
    client_endpoint: tuple[str, int] | None = None,
) -> str:
    """判定一帧是请求还是响应。

    优先级：主站 IP > TCP SYN 学到的客户端端点 > 常见服务端口 > 端口启发式。
    抽成独立函数，让实时抓包与 pcap 回放共用同一套判定。
    """
    if master_ip:
        if src_ip == master_ip:
            return registry.ROLE_REQUEST
        if dst_ip == master_ip:
            return registry.ROLE_RESPONSE

    if client_endpoint:
        # 用端点而非仅 IP 比较：本机回环抓包时两端 IP 相同
        return registry.ROLE_REQUEST if (src_ip, src_port) == client_endpoint else registry.ROLE_RESPONSE

    src_server = src_port in SERVER_PORTS
    dst_server = dst_port in SERVER_PORTS
    if dst_server and not src_server:
        return registry.ROLE_REQUEST
    if src_server and not dst_server:
        return registry.ROLE_RESPONSE
    # 兜底：客户端通常用较大的临时端口，因此目标端口更小的是请求
    return registry.ROLE_REQUEST if dst_port < src_port else registry.ROLE_RESPONSE


class PcapCaptureEngine:
    """在后台线程中从指定网卡抓包并分帧。"""

    def __init__(
        self,
        config: PcapConfig,
        *,
        on_frame: FrameCallback | None = None,
        on_status: StatusCallback | None = None,
        on_error: ErrorCallback | None = None,
        log_path: str = "",
    ):
        self.config = config
        self._on_frame = on_frame or (lambda *_: None)
        self._on_status = on_status or (lambda *_: None)
        self._on_error = on_error or (lambda *_: None)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._handle: wpcap.PcapHandle | None = None
        self._datalink: int = linklayer.DLT_EN10MB
        self._flows: dict[tuple[str, int, str, int], _Flow] = {}
        self._flows_lock = threading.Lock()
        # 双向流 → 客户端端点；由 TCP SYN 学习得到
        self._clients: dict[tuple[tuple[str, int], tuple[str, int]], tuple[str, int]] = {}
        self._local_ips: set[str] = set()
        self._frames = 0
        self._packets = 0
        self._dropped = 0
        self._failed = False
        # 报文日志：写入「引擎上报的帧」——设了抓包过滤就只含过滤后的报文
        self._wanted_log_path = log_path
        self._writer: pcapfile.PcapWriter | None = None
        self._writer_lock = threading.Lock()

    # -- 日志 -------------------------------------------------------------
    @property
    def log_path(self) -> str:
        """正在写入的日志文件路径；未开启时为已配置的目标路径。"""
        writer = self._writer
        return str(writer.path) if writer is not None else self._wanted_log_path

    @property
    def log_count(self) -> int:
        writer = self._writer
        return writer.count if writer is not None else 0

    @property
    def log_error(self) -> str:
        writer = self._writer
        return writer.error if writer is not None else ""

    def set_log(self, path: str) -> bool:
        """开启/切换日志文件。

        抓包尚未真正激活（链路类型未知）时只记下路径，由 ``_run`` 在拿到
        ``pcap_datalink()`` 后创建文件 —— 否则写出的 pcap 头 network 字段会错。
        """
        with self._writer_lock:
            if self._writer is not None:
                self._writer.close()
                self._writer = None
            self._wanted_log_path = path
        if not path:
            return True
        if self._handle is None:
            return True
        self._open_log_if_needed()
        return self._writer is not None

    def close_log(self) -> None:
        """停止写日志并落盘。

        保留 writer 对象，让界面在停止抓包后仍能读到本次写入了多少帧；
        下次开启时会换新文件。
        """
        with self._writer_lock:
            writer = self._writer
            self._wanted_log_path = ""
        if writer is not None:
            writer.close()

    # -- 状态 -------------------------------------------------------------
    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and not self._stop.is_set())

    @property
    def frame_count(self) -> int:
        return self._frames

    @property
    def packet_count(self) -> int:
        return self._packets

    # -- 生命周期 ---------------------------------------------------------
    def start(self) -> bool:
        if self.running:
            return True
        ok, reason = ifaces.capture_available()
        if not ok:
            self._on_error(reason)
            return False
        self._stop.clear()
        self._failed = False
        self._thread = threading.Thread(target=self._run, name="pcap-capture", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()
        handle = self._handle
        if handle is not None:
            handle.breakloop()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=3.0)
        if handle is not None:
            handle.close()
            self._handle = None
        with self._flows_lock:
            self._flows.clear()

    # -- 主循环 -----------------------------------------------------------
    def _run(self) -> None:
        handle: wpcap.PcapHandle | None = None
        try:
            self._local_ips = ifaces.local_addresses()
            handle = wpcap.PcapHandle(
                self.config.interface,
                promisc=self.config.promisc,
                timeout_ms=120,
                filter_text=self.config.bpf(),
            )
            self._handle = handle
            self._datalink = handle.datalink
            # 日志必须在拿到真实链路类型后再创建，否则 pcap 头里的 network 字段会错
            self._open_log_if_needed()
            self._on_status(f"抓包已启动：{self.config.interface}")
            last_cleanup = time.time()
            while not self._stop.is_set():
                result = handle.read()
                if result is not None:
                    _timestamp, raw = result
                    self._handle_packet(raw)
                now = time.time()
                if now - last_cleanup >= 1.0:
                    self._cleanup_flows()
                    last_cleanup = now
        except wpcap.PcapError as exc:
            self._failed = True
            self._on_error(str(exc))
        except Exception as exc:  # noqa: BLE001 - 后台线程必须兜底
            self._failed = True
            self._on_error(f"网卡抓包失败：{exc}")
        finally:
            if handle is not None:
                handle.close()
                self._handle = None
            self.close_log()
            if not self._failed and self._stop.is_set():
                self._on_status("抓包已停止")

    def _open_log_if_needed(self) -> None:
        """按配置打开日志文件（抓包线程内调用，此时链路类型已确定）。"""
        path = self._wanted_log_path
        if not path:
            return
        with self._writer_lock:
            if self._writer is not None and not self._writer.closed:
                return
            try:
                self._writer = pcapfile.PcapWriter(path, self._datalink)
            except pcapfile.PcapFileError as exc:
                self._wanted_log_path = ""
                self._on_error(str(exc))

    def _cleanup_flows(self) -> None:
        """回收空闲或过多的流；锁内只挑选，出锁后再冲刷，避免重入死锁。"""
        now = time.time()
        with self._flows_lock:
            stale = [key for key, flow in self._flows.items() if now - flow.last_seen > FLOW_IDLE_TIMEOUT]
            if len(self._flows) - len(stale) > MAX_FLOWS:
                alive = sorted(
                    ((key, flow) for key, flow in self._flows.items() if key not in set(stale)),
                    key=lambda item: item[1].last_seen,
                )
                overflow = len(alive) - MAX_FLOWS
                stale.extend(key for key, _flow in alive[:overflow])
            flows = [(key, self._flows.pop(key, None)) for key in stale]
            if len(self._flows) > MAX_FLOWS * 4:
                self._clients.clear()
        for key, flow in flows:
            if flow is not None:
                self._flush_flow(key, flow)

    # -- 收包 -------------------------------------------------------------
    def _handle_packet(self, raw: bytes) -> None:
        # 日志写「完整链路层帧」：pcap 的 network 字段声明的是链路类型，
        # 只有原样落盘 Wireshark 才能解出 IP/TCP/Modbus；写应用层载荷会与头部不符。
        # BPF 已在内核层过滤，因此这里拿到的就是「过滤命中的报文」。
        writer = self._writer
        if writer is not None:
            writer.write(raw, time.time())
        try:
            self._process(raw)
        except Exception:  # noqa: BLE001 - 单个畸形包不能中断抓包
            self._dropped += 1

    def _process(self, raw: bytes) -> None:
        segment = linklayer.parse_link_frame(raw, self._datalink)
        if segment is None:
            return

        if segment.is_goose:
            # 二层 GOOSE 没有 IP，整帧交给 GOOSE 解析器
            self._packets += 1
            self._emit(segment.goose_frame, "RX", FrameMeta(transport="ETH", role="Publish"))
            return

        src_ip, dst_ip = segment.src_ip, segment.dst_ip
        if not self._ip_allowed(src_ip, dst_ip):
            return

        self._packets += 1
        if not segment.transport:
            return
        sport, dport = segment.src_port, segment.dst_port
        if self.config.port_filter and self.config.port_filter not in (sport, dport):
            return

        meta = FrameMeta(
            src_ip=src_ip,
            src_port=sport,
            dst_ip=dst_ip,
            dst_port=dport,
            transport=segment.transport,
            role=registry.ROLE_REQUEST,
        )
        if segment.is_syn:
            # SYN 且非 ACK 的发送方就是客户端，据此确定请求方向
            key = _flow_key(src_ip, sport, dst_ip, dport)
            with self._flows_lock:
                self._clients[key] = (src_ip, sport)
        meta.role = self._role(src_ip, sport, dst_ip, dport)
        direction = "TX" if src_ip in self._local_ips else "RX"

        payload = segment.payload
        if not payload:
            return
        if segment.transport == "TCP":
            self._handle_tcp(src_ip, sport, dst_ip, dport, segment.seq, payload, direction, meta)
        else:
            self._handle_udp(src_ip, sport, dst_ip, dport, payload, direction, meta)

    def _ip_allowed(self, src_ip: str, dst_ip: str) -> bool:
        filters = self.config.filter_list()
        if not filters:
            return True
        # BPF 已过滤时这里只是保险；BPF 不可用时则完全依赖此处
        for item in filters:
            base = item.split("/", 1)[0]
            if base in (src_ip, dst_ip):
                return True
        return False

    def _role(self, src_ip: str, sport: int, dst_ip: str, dport: int) -> str:
        with self._flows_lock:
            client = self._clients.get(_flow_key(src_ip, sport, dst_ip, dport))
        return infer_role(
            src_ip, sport, dst_ip, dport, master_ip=self.config.master_ip, client_endpoint=client
        )

    def _handle_tcp(
        self,
        src_ip: str,
        sport: int,
        dst_ip: str,
        dport: int,
        seq: int,
        payload: bytes,
        direction: str,
        meta: FrameMeta,
    ) -> None:
        key = (src_ip, sport, dst_ip, dport)
        with self._flows_lock:
            flow = self._flows.get(key)
            if flow is None:
                flow = _Flow(self.config.protocol, self.config.link_address_size)
                self._flows[key] = flow
            flow.last_seen = time.time()

            expected = flow.next_seq
            if expected is not None:
                if seq < expected:
                    overlap = expected - seq
                    if overlap >= len(payload):
                        return
                    payload = payload[overlap:]
                elif seq > expected:
                    # 缺段：旧的字节流已不可信，重置缓冲等待重新同步
                    flow.splitter.reset()
            flow.next_seq = seq + len(payload)

            frames = flow.splitter.feed(payload)
            # Modbus RTU over TCP 没有长度字段，按 TCP 段边界断帧
            if self.config.protocol == "modbus_rtu" and flow.splitter.pending:
                frames.extend(flow.splitter.flush())

        for frame in frames:
            self._emit(frame, direction, meta)

    def _handle_udp(
        self,
        src_ip: str,
        sport: int,
        dst_ip: str,
        dport: int,
        payload: bytes,
        direction: str,
        meta: FrameMeta,
    ) -> None:
        key = (src_ip, sport, dst_ip, dport)
        with self._flows_lock:
            flow = self._flows.get(key)
            if flow is None:
                flow = _Flow(self.config.protocol, self.config.link_address_size)
                self._flows[key] = flow
            flow.last_seen = time.time()
            frames = flow.splitter.feed(payload)
            if flow.splitter.pending:
                frames.extend(flow.splitter.flush())
        for frame in frames:
            self._emit(frame, direction, meta)

    def _flush_flow(self, key: tuple[str, int, str, int], flow: _Flow) -> None:
        """冲刷一条流的残留字节（调用方已持有 flow 的所有权，无需再加锁）。"""
        frames = flow.splitter.flush()
        if not frames:
            return
        src_ip, sport, dst_ip, dport = key
        meta = FrameMeta(
            src_ip=src_ip,
            src_port=sport,
            dst_ip=dst_ip,
            dst_port=dport,
            role=self._role(src_ip, sport, dst_ip, dport),
        )
        direction = "TX" if src_ip in self._local_ips else "RX"
        for frame in frames:
            self._emit(frame, direction, meta)

    def _emit(self, raw: bytes, direction: str, meta: FrameMeta) -> None:
        if not raw:
            return
        self._frames += 1
        self._on_frame(raw, direction, meta)


def describe_bpf(config: PcapConfig) -> str:
    """给界面展示实际使用的过滤表达式。"""
    if not config.filter_list() and not config.port_filter:
        return "（无 IP / 端口过滤，抓取全部 TCP/UDP）"
    return config.bpf()
