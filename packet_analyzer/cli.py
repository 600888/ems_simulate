"""命令行入口：在无图形环境的服务器上抓包、解析、导出日志。

界面版依赖 PySide6（Qt 6 要求 glibc ≥ 2.28），老服务器装不上；
这里只用到 ``core/``（纯 Python，无 Qt 依赖），因此任何 Python 3.8+ 都能跑。

典型用法::

    # 看有哪些网卡
    python -m packet_analyzer.cli ifaces

    # 抓 60 秒，只看 192.168.1.10 的报文，同时存 pcap 日志
    sudo ./pa --interpreter python3 capture --iface eth0 --ip 192.168.1.10 --duration 60 --log run.pcap

    # 回放已有日志
    python -m packet_analyzer.cli replay run.pcap --protocol modbus_tcp

    # 离线解析一帧十六进制
    python -m packet_analyzer.cli parse 000100000006010300000009 --protocol modbus_tcp
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
import importlib.util
import json
import os
from pathlib import Path
import queue
import signal
import sys
import threading
import time
from typing import Any

from . import APP_NAME, APP_VERSION
from .core import linklayer, pcapfile, registry, wpcap
from .core.ifaces import capture_available, list_interfaces, local_addresses
from .core.pcap import (
    FrameMeta,
    PcapCaptureEngine,
    PcapConfig,
    _flow_key,
    describe_bpf,
    infer_role,
)

# 可选依赖：(模块名, 用途, 缺失是否算失败)
# pydnp3_pure 缺失会让 DNP3 解析不出对象（功能缺失）；
# dlt645 缺失只是 DI 没有中文名（显示降级）。
OPTIONAL_DEPENDENCIES = (
    ("pydnp3_pure", "DNP3 对象解析", True),
    ("dlt645", "DL/T645 数据项中文名称", False),
)

# 每行一条的紧凑输出（现场盯流量时比表格实用）
_LINE_LOCK = threading.Lock()

# 这些编码无法表示中文，遇到就换成 UTF-8
_ASCII_ENCODINGS = {"", "ascii", "ansi_x3.4-1968", "us-ascii", "646"}


def _prepare_stdio() -> None:
    """让输出编码可预期，避免老服务器上的乱码。

    * 重定向到文件 / 管道 → UTF-8：写报告、被其它工具消费时最通用
    * 本地终端且原编码能表示中文（如 GBK）→ 保持原样，本地终端看着正常
    * 本地终端但编码是 ASCII → 退回 UTF-8
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            encoding = (getattr(stream, "encoding", "") or "").lower()
            if not stream.isatty() or encoding in _ASCII_ENCODINGS:
                stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def _say(text: str = "") -> None:
    with _LINE_LOCK:
        print(text, flush=True)


def _fmt_endpoint(ip: str, port: int) -> str:
    return f"{ip}:{port}" if port else ip


def _protocol_name(detail: dict[str, Any]) -> str:
    """parse_frame 会解析 AUTO 并在结果里给出 protocol_key，据此取名。"""
    key = str(detail.get("protocol_key") or "")
    if key and registry.is_known(key):
        return registry.PROTOCOLS[key].name
    return str(detail.get("protocol") or "未知协议")


# CSV / JSON 的统一列，抓包与回放共用，避免两边字段不一致
ROW_COLUMNS = (
    "seq", "time", "direction", "src_ip", "src_port", "dst_ip", "dst_port",
    "transport", "role", "protocol", "length", "hex", "summary",
)


def _make_row(
    seq: int,
    timestamp: float,
    direction: str,
    meta: FrameMeta,
    detail: dict[str, Any],
    raw: bytes,
    summary: str,
) -> dict[str, Any]:
    return {
        "seq": seq,
        "time": datetime.fromtimestamp(timestamp).isoformat(timespec="milliseconds"),
        "direction": direction,
        "src_ip": meta.src_ip,
        "src_port": meta.src_port,
        "dst_ip": meta.dst_ip,
        "dst_port": meta.dst_port,
        "transport": meta.transport,
        "role": meta.role,
        "protocol": _protocol_name(detail),
        "length": len(raw),
        "hex": raw.hex().upper(),
        "summary": summary,
    }


def _print_frame_line(index: int, raw: bytes, direction: str, meta: FrameMeta, summary: str) -> None:
    stamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    arrow = "→" if direction == "TX" else "←"
    src = _fmt_endpoint(meta.src_ip, meta.src_port) or meta.transport or "?"
    dst = _fmt_endpoint(meta.dst_ip, meta.dst_port) or "-"
    _say(f"[{index:>5}] {stamp} {arrow} {src} → {dst}  {len(raw):>4}B  {summary}")


def _relinquish(path: Path) -> None:
    """把 sudo 抓包产生的文件/目录交还给调用者。

    不用这一步的话，``sudo pa.sh capture`` 会在 logs/ 下留下 root 属主的目录，
    之后普通用户既写不了 CSV，也删不掉旧日志。
    """
    if os.geteuid() != 0:
        return
    user = os.environ.get("SUDO_USER")
    if not user:
        return
    try:
        import pwd

        entry = pwd.getpwnam(user)
    except (ImportError, KeyError):
        return
    for target in (path, path.parent):
        try:
            if target.exists():
                os.chown(target, entry.pw_uid, entry.pw_gid)
        except OSError:
            pass


# -- 子命令：网卡 ---------------------------------------------------------
def cmd_ifaces(_args: argparse.Namespace) -> int:
    available, reason = capture_available()
    print(f"抓包能力：{'可用' if available else '不可用 - ' + reason}")
    interfaces = list_interfaces()
    if not interfaces:
        print("未枚举到网卡。")
        return 1
    print(f"\n共 {len(interfaces)} 块网卡：\n")
    print(f"  {'名称':<22} {'IPv4':<28} 说明")
    print(f"  {'-' * 22} {'-' * 28} {'-' * 30}")
    for item in interfaces:
        ipv4 = "/".join(item.ipv4) or "—"
        note = item.description or ""
        if item.is_loopback:
            note = f"{note}（回环）".strip()
        print(f"  {item.name:<22} {ipv4:<28} {note}")
    print("\n抓包需要 root 或 CAP_NET_RAW：sudo <本程序> capture --iface <名称>")
    return 0


# -- 子命令：抓包 ---------------------------------------------------------
def cmd_capture(args: argparse.Namespace) -> int:
    config = PcapConfig(
        interface=args.iface or _default_interface(),
        protocol=args.protocol,
        link_address_size=args.link_address_size,
        ip_filter=args.ip or "",
        port_filter=int(args.port or 0),
        master_ip=args.master_ip or "",
        promisc=not args.no_promisc,
        low_latency=bool(args.low_latency),
        buffer_mb=int(args.buffer_mb),
    )
    if not config.interface:
        print("错误：未指定网卡，且没有找到合适的默认网卡。用 `ifaces` 子命令查看。")
        return 2

    available, reason = capture_available()
    if not available:
        print(f"错误：{reason}")
        return 2

    log_path = args.log
    if args.no_log:
        log_path = ""
    elif not log_path:
        log_path = str(pcapfile.default_log_dir() / pcapfile.default_log_name(config.interface))

    print(f"{APP_NAME} v{APP_VERSION} · 命令行抓包")
    print(f"  网卡    : {config.interface}")
    print(f"  过滤    : {describe_bpf(config)}")
    protocol_name = (
        registry.PROTOCOLS[config.protocol].name if registry.is_known(config.protocol) else "自动识别"
    )
    print(f"  协议    : {protocol_name}")
    print(f"  日志    : {log_path or '不保存'}")
    if args.duration:
        print(f"  时长    : {args.duration} 秒")
    if args.count:
        print(f"  帧数    : 最多 {args.count} 帧")
    print("  Ctrl-C 停止\n")

    out_queue: queue.Queue[tuple[bytes, str, FrameMeta]] = queue.Queue()
    stats = {"frames": 0, "errors": []}

    engine = PcapCaptureEngine(
        config,
        on_frame=lambda raw, direction, meta: out_queue.put((raw, direction, meta)),
        on_error=lambda text: stats["errors"].append(text),
        log_path=log_path,
    )
    if not engine.start():
        print(f"错误：抓包启动失败 {stats['errors']}")
        return 2

    stop_flag = threading.Event()

    def _handle_signal(_signum: int, _frame: Any) -> None:
        stop_flag.set()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    deadline = time.time() + args.duration if args.duration else None
    rows: list[dict[str, Any]] = []
    started = time.time()
    try:
        while not stop_flag.is_set():
            if deadline and time.time() >= deadline:
                break
            try:
                raw, direction, meta = out_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            stats["frames"] += 1
            detail = registry.parse_frame(raw, config.protocol, role=meta.role)
            summary = str(detail.get("summary") or "")
            if not args.quiet:
                _print_frame_line(stats["frames"], raw, direction, meta, summary)
            rows.append(
                _make_row(stats["frames"], time.time(), direction, meta, detail, raw, summary)
            )
            if args.count and stats["frames"] >= args.count:
                break
    finally:
        engine.stop()

    elapsed = max(0.001, time.time() - started)
    print()
    print(f"抓包结束：{stats['frames']} 帧，用时 {elapsed:.1f}s，收包 {engine.packet_count} 个")
    if engine.kernel_dropped:
        # 内核缓冲区溢出：说明抓到的报文不完整，拿它下结论会误判
        print(
            f"警告：内核丢包 {engine.kernel_dropped} 个（缓冲区溢出）。"
            f"请调大 --buffer-mb（当前 {config.buffer_mb}MB），或关闭 --low-latency。"
        )
    if engine.parse_dropped:
        print(f"提示：{engine.parse_dropped} 个畸形帧解析失败已跳过")
    if log_path:
        log_file = Path(log_path)
        size = log_file.stat().st_size if log_file.exists() else 0
        _relinquish(log_file)
        print(f"日志：{log_path}（{engine.log_count} 帧，{size / 1024:.1f} KB）")
    if stats["errors"]:
        print(f"错误：{stats['errors']}")

    if args.csv:
        _write_csv(args.csv, rows)
        print(f"CSV：{args.csv}（{len(rows)} 行）")
    if args.json:
        Path(args.json).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"JSON：{args.json}")
    return 0


def _default_interface() -> str:
    for item in list_interfaces():
        if item.ipv4 and not item.is_loopback:
            return item.id
    interfaces = list_interfaces()
    return interfaces[0].id if interfaces else ""


def _write_csv(path: str, rows: list[dict[str, Any]]) -> None:
    with Path(path).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ROW_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


# -- 子命令：回放日志 -----------------------------------------------------
def cmd_replay(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not path.exists():
        print(f"错误：文件不存在 {path}")
        return 2
    try:
        linktype, records = pcapfile.read_pcap(path)
    except pcapfile.PcapFileError as exc:
        print(f"错误：{exc}")
        return 2

    local_ips = local_addresses()
    clients: dict[tuple[tuple[str, int], tuple[str, int]], tuple[str, int]] = {}
    parsed: list[tuple[float, bytes, str, FrameMeta]] = []
    for record in records:
        segment = linklayer.parse_link_frame(record.data, linktype)
        if segment is None:
            continue
        if segment.is_goose:
            parsed.append(
                (record.timestamp, segment.goose_frame, "RX", FrameMeta(transport="ETH", role="Publish"))
            )
            continue
        if segment.is_syn:
            clients[_flow_key(segment.src_ip, segment.src_port, segment.dst_ip, segment.dst_port)] = (
                segment.src_ip,
                segment.src_port,
            )
        role = infer_role(
            segment.src_ip,
            segment.src_port,
            segment.dst_ip,
            segment.dst_port,
            master_ip=args.master_ip or "",
            client_endpoint=clients.get(
                _flow_key(segment.src_ip, segment.src_port, segment.dst_ip, segment.dst_port)
            ),
        )
        direction = "TX" if role == registry.ROLE_REQUEST else "RX"
        if segment.src_ip in local_ips and segment.dst_ip not in local_ips:
            direction = "TX"
        elif segment.dst_ip in local_ips and segment.src_ip not in local_ips:
            direction = "RX"
        parsed.append(
            (
                record.timestamp,
                segment.payload,
                direction,
                FrameMeta(
                    src_ip=segment.src_ip,
                    src_port=segment.src_port,
                    dst_ip=segment.dst_ip,
                    dst_port=segment.dst_port,
                    transport=segment.transport,
                    role=role,
                ),
            )
        )

    print(f"日志：{path.name}（{len(records)} 个链路帧，链路类型 {linktype}）\n")
    shown = 0
    rows: list[dict[str, Any]] = []
    for timestamp, payload, direction, meta in parsed:
        if not payload:
            continue
        detail = registry.parse_frame(payload, args.protocol, role=meta.role)
        summary = str(detail.get("summary") or "")
        if args.ip and args.ip not in (meta.src_ip, meta.dst_ip):
            continue
        if args.port and int(args.port) not in (meta.src_port, meta.dst_port):
            continue
        if args.search and args.search.lower() not in summary.lower():
            continue
        shown += 1
        if not args.quiet:
            _print_frame_line(shown, payload, direction, meta, summary)
        rows.append(_make_row(shown, timestamp, direction, meta, detail, payload, summary))
    print(f"\n共 {shown} 帧应用层报文" + ("（已按条件过滤）" if any([args.ip, args.port, args.search]) else ""))
    if args.csv:
        _write_csv(args.csv, rows)
        print(f"CSV：{args.csv}")
    if args.json:
        Path(args.json).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"JSON：{args.json}")
    return 0


# -- 子命令：解析单帧 -----------------------------------------------------
def cmd_parse(args: argparse.Namespace) -> int:
    text = args.hex.replace(" ", "").replace(",", "").replace("0x", "").replace("0X", "")
    try:
        raw = bytes.fromhex(text)
    except ValueError as exc:
        print(f"错误：十六进制格式不对（{exc}）")
        return 2
    detail = registry.parse_frame(raw, args.protocol, role=args.role)
    print(f"协议：{_protocol_name(detail)}")
    print(f"摘要：{detail.get('summary', '')}")
    if args.json:
        Path(args.json).write_text(json.dumps(detail, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"JSON：{args.json}")
        return 0
    fields = detail.get("fields") or []
    if fields:
        print()
        for field in fields:
            offset = field.get("offset", "")
            name = field.get("name", "")
            value = field.get("value", "")
            note = field.get("note", "")
            print(f"  [{offset:>4}] {name:<22} {str(value):<24} {note}")
    return 0


# -- 子命令：自检 ---------------------------------------------------------
def cmd_selftest(_args: argparse.Namespace) -> int:
    samples_file = Path(__file__).resolve().parent / "samples" / "samples.json"
    try:
        samples = json.loads(samples_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"[FAIL] 读取样例失败：{exc}")
        return 1

    failures = 0
    total = 0
    for key, item in samples.items():
        for field in ("request", "response"):
            hex_text = item.get(field)
            if not hex_text:
                continue
            total += 1
            raw = bytes.fromhex(hex_text.replace(" ", ""))
            try:
                detail = registry.parse_frame(raw, key, role=field)
                summary = str(detail.get("summary") or "")
                # 只把"解析失败"算问题；数据不完整之类的警告照常展示但不判失败，
                # 否则样例里故意截断的帧会让自检永远红着。
                ok = bool(summary) and "错误" not in summary
                print(f"[{'OK  ' if ok else 'FAIL'}] {key:<10} {field:<8} {len(raw):>3}B  {summary}")
                for warning in detail.get("warnings") or []:
                    print(f"       警告：{warning}")
                failures += 0 if ok else 1
            except Exception as exc:  # noqa: BLE001 - 自检要覆盖所有样例
                print(f"[FAIL] {key:<10} {field:<8} 解析异常：{exc}")
                failures += 1

    # 可选依赖单独检查：缺 pydnp3_pure 会让 DNP3 只剩帧头、解析不出对象，
    # 这种"功能缺失"必须报错；缺 dlt645 只是数据项没中文名，提示即可。
    environment_failures = 0
    for module, purpose, required in OPTIONAL_DEPENDENCIES:
        present = importlib.util.find_spec(module) is not None
        if present:
            print(f"[OK  ] 可选依赖 {module:<12} {purpose}")
        elif required:
            print(f"[FAIL] 可选依赖 {module:<12} 缺失 → {purpose}不可用，请检查分发包是否完整")
            environment_failures += 1
        else:
            print(f"[WARN] 可选依赖 {module:<12} 缺失 → {purpose}（不影响解析）")

    available, reason = capture_available()
    interfaces = list_interfaces()
    print()
    print(f"[{'OK  ' if available else 'WARN'}] 抓包能力：{'可用' if available else reason}")
    print(f"       可抓包网卡 {len(interfaces)} 块：" + ", ".join(item.name for item in interfaces[:8]))
    print()
    print(f"Python {sys.version.split()[0]} / {sys.platform}")
    try:
        from .ui import qtcompat

        print(f"图形界面：{qtcompat.platform_note()}")
    except ImportError:
        print("图形界面：不可用（未安装 Qt 绑定，命令行功能不受影响）")

    total_failures = failures + environment_failures
    if total_failures:
        print(f"自检失败：{failures} 帧解析异常，{environment_failures} 项依赖缺失")
        return 1
    print("自检通过")
    return 0


# -- 入口 ----------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pa",
        description=f"{APP_NAME} v{APP_VERSION} 命令行版（无需图形环境）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例：\n"
        "  pa ifaces\n"
        "  sudo pa capture --iface eth0 --ip 192.168.1.10 --duration 60\n"
        "  pa replay run.pcap --protocol modbus_tcp\n"
        "  pa parse 000100000006010300000009 --protocol modbus_tcp\n",
    )
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {APP_VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("ifaces", help="列出本机网卡与抓包能力").set_defaults(func=cmd_ifaces)
    sub.add_parser("selftest", help="验证解析器与抓包环境").set_defaults(func=cmd_selftest)

    cap = sub.add_parser("capture", help="从网卡实时抓包")
    cap.add_argument("--iface", help="网卡名（默认选第一个有 IPv4 的非回环网卡）")
    cap.add_argument("--ip", help="IP 过滤，多个用逗号分隔（命中源或目的）")
    cap.add_argument("--port", type=int, help="端口过滤，如 502 / 2404")
    cap.add_argument("--protocol", default=registry.AUTO, choices=list(registry.PROTOCOLS), help="协议")
    cap.add_argument("--master-ip", help="主站/客户端 IP，用于判定请求方向")
    cap.add_argument("--link-address-size", type=int, default=1, help="IEC101 链路地址长度")
    cap.add_argument("--duration", type=float, help="抓包时长（秒），不填则一直抓到 Ctrl-C")
    cap.add_argument("--count", type=int, help="抓够多少帧后停止")
    cap.add_argument("--log", help="pcap 日志路径（默认存到程序目录 logs/）")
    cap.add_argument("--no-log", action="store_true", help="不写 pcap 日志")
    cap.add_argument("--no-promisc", action="store_true", help="关闭混杂模式，只收本机流量")
    cap.add_argument(
        "--low-latency",
        action="store_true",
        help="低延迟模式：每包立即交付，抓包 CPU 约高 5 倍（默认按约 20ms 批量交付）",
    )
    cap.add_argument(
        "--buffer-mb",
        type=int,
        default=wpcap.DEFAULT_BUFFER_MB,
        help=f"内核抓包缓冲区（MB），默认 {wpcap.DEFAULT_BUFFER_MB}；突发丢包时调大",
    )
    cap.add_argument("--csv", help="同时导出 CSV 到指定路径")
    cap.add_argument("--json", help="同时导出 JSON 到指定路径")
    cap.add_argument("--quiet", action="store_true", help="不逐帧打印，只输出汇总")
    cap.set_defaults(func=cmd_capture)

    rep = sub.add_parser("replay", help="回放 pcap 日志并重新解析")
    rep.add_argument("file", help="pcap 文件路径")
    rep.add_argument("--protocol", default=registry.AUTO, choices=list(registry.PROTOCOLS), help="协议")
    rep.add_argument("--ip", help="只看含该 IP 的报文")
    rep.add_argument("--port", type=int, help="只看含该端口的报文")
    rep.add_argument("--master-ip", help="主站/客户端 IP")
    rep.add_argument("--search", help="按解析摘要关键字过滤")
    rep.add_argument("--csv", help="导出 CSV")
    rep.add_argument("--json", help="导出 JSON")
    rep.add_argument("--quiet", action="store_true", help="不逐帧打印")
    rep.set_defaults(func=cmd_replay)

    par = sub.add_parser("parse", help="解析一帧十六进制报文")
    par.add_argument("hex", help="十六进制报文，可带空格")
    par.add_argument("--protocol", default=registry.AUTO, choices=list(registry.PROTOCOLS), help="协议")
    par.add_argument("--role", default=registry.ROLE_REQUEST, help="按请求还是响应解析")
    par.add_argument("--json", help="把完整解析结果写入 JSON")
    par.set_defaults(func=cmd_parse)

    return parser


def main(argv: list[str] | None = None) -> int:
    _prepare_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        print("\n已中断")
        return 130


if __name__ == "__main__":
    sys.exit(main())
