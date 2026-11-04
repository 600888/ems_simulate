"""程序入口。

用法：
    python packet_analyzer/main.py              # 正常启动
    python packet_analyzer/main.py --demo       # 载入内置样例便于快速体验
    python packet_analyzer/main.py --selftest   # 无界面自检（验证打包产物）
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from packet_analyzer import APP_NAME, APP_VERSION  # noqa: E402
from packet_analyzer.core import registry  # noqa: E402
from packet_analyzer.ui import qtcompat, theme  # noqa: E402
from packet_analyzer.ui.main_window import MainWindow, samples_path  # noqa: E402
from packet_analyzer.ui.qtcompat import QApplication, QFont  # noqa: E402

DEMO_FRAMES = [
    ("goose", "request", registry.ROLE_REQUEST),
    ("mms", "request", registry.ROLE_REQUEST),
    ("iec101", "request", registry.ROLE_REQUEST),
    ("dlt645", "request", registry.ROLE_REQUEST),
    ("iec104", "request", registry.ROLE_REQUEST),
    ("iec104", "response", registry.ROLE_RESPONSE),
    ("modbus_tcp", "request", registry.ROLE_REQUEST),
    ("modbus_tcp", "response", registry.ROLE_RESPONSE),
    ("dnp3", "request", registry.ROLE_REQUEST),
    ("dnp3", "response", registry.ROLE_RESPONSE),
]


def _run_selftest() -> int:
    """不开界面，逐帧解析内置样例并检查可选依赖。用于验证打包产物。"""
    print(f"{APP_NAME} v{APP_VERSION} 自检")
    print(f"解释器: {sys.executable}")
    print(f"打包模式: {'frozen' if getattr(sys, 'frozen', False) else 'source'}")
    print(f"样例文件: {samples_path()}")

    try:
        samples = json.loads(samples_path().read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"[FAIL] 无法读取样例文件: {exc}")
        return 1

    failures = 0
    for key, item in samples.items():
        for field, role in (("request", "Request"), ("response", "Response")):
            text = item.get(field) or ""
            if not text:
                continue
            detail = registry.parse_frame(bytes.fromhex(text.replace(" ", "")), key, role=role)
            status = "OK  " if detail["valid"] else "FAIL"
            if not detail["valid"]:
                failures += 1
            print(f"[{status}] {key:10s} {field:8s} {len(detail['raw_hex'].split()):3d}B  {detail['summary']}")

    try:
        from dlt645.model.data.data_handler import get_data_item

        name = getattr(get_data_item(0x00010000), "name", "")
        print(f"[OK  ] DL/T645 DI 名称库可用: 0x00010000 -> {name}")
    except (ImportError, AttributeError, ValueError) as exc:
        print(f"[WARN] DL/T645 DI 名称库不可用（仅影响 DI 中文名显示）: {exc}")

    from packet_analyzer.core.ifaces import capture_available, capture_runtime_info, list_interfaces

    available, reason = capture_available()
    interfaces = list_interfaces()
    print(f"[{'OK  ' if available else 'WARN'}] 网卡抓包: {'可用' if available else reason}")
    if available:
        print(f"       {capture_runtime_info()}")
    print(f"       可抓包网卡 {len(interfaces)} 块: " + ", ".join(item.name for item in interfaces[:6]))

    print()
    print("自检通过" if failures == 0 else f"自检失败：{failures} 帧解析异常")
    return 0 if failures == 0 else 1


def _run_capture_test() -> int:
    """在回环网卡上真实抓一次 Modbus 往返，验证抓包链路与报文日志。"""
    import socket
    import tempfile
    import threading
    import time

    from packet_analyzer.core.ifaces import list_interfaces
    from packet_analyzer.core.pcap import PcapCaptureEngine, PcapConfig
    from packet_analyzer.core.pcapfile import read_pcap

    interface = next((item.id for item in list_interfaces() if item.is_loopback), "")
    if not interface:
        print("[FAIL] 未找到回环网卡，无法自测抓包")
        return 1
    print(f"抓包自测：网卡={interface}")

    log_dir = tempfile.mkdtemp(prefix="packet-analyzer-log-")
    log_path = str(Path(log_dir) / "selftest.pcap")

    frames: list[object] = []
    errors: list[str] = []
    engine = PcapCaptureEngine(
        PcapConfig(interface=interface, protocol="modbus_tcp", ip_filter="127.0.0.1"),
        on_frame=lambda raw, direction, meta: frames.append((raw, direction, meta)),
        on_error=errors.append,
        log_path=log_path,
    )
    if not engine.start():
        print(f"[FAIL] 抓包启动失败：{errors}")
        return 1
    time.sleep(1.5)

    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    request = bytes.fromhex("000100000006010300000009")
    response = bytes.fromhex("000100000007010304006400C8")

    def serve() -> None:
        conn, _addr = server.accept()
        conn.recv(1024)
        time.sleep(0.15)
        conn.sendall(response)
        time.sleep(0.3)
        conn.close()
        server.close()

    threading.Thread(target=serve, daemon=True).start()
    client = socket.create_connection(("127.0.0.1", port))
    client.sendall(request)
    time.sleep(0.8)
    client.close()

    deadline = time.time() + 5
    while time.time() < deadline and len(frames) < 2:
        time.sleep(0.05)
    engine.stop()

    payloads = [item[0] for item in frames]  # type: ignore[index]
    ok = request in payloads and response in payloads
    matched = [item for item in frames if item[0] in (request, response)]  # type: ignore[index]
    for raw, direction, meta in matched:  # type: ignore[misc]
        print(
            f"  OK   {direction} {meta.src_ip}:{meta.src_port} -> {meta.dst_ip}:{meta.dst_port} "
            f"role={meta.role} len={len(raw)}"
        )
    others = len(frames) - len(matched)
    if others:
        print(f"  （另有 {others} 帧其它流量，IP 过滤未限定端口时属正常）")
    if errors:
        print(f"[WARN] 抓包错误：{errors}")

    # 顺带验证报文日志：文件能写、能读回、帧是完整链路帧
    log_ok = False
    try:
        linktype, records = read_pcap(log_path)
        log_ok = bool(records) and engine.log_count > 0
        print(
            f"  {'OK  ' if log_ok else 'FAIL'} 报文日志 {len(records)} 帧 / 写入 {engine.log_count} 帧"
            f"，链路类型={linktype}，{Path(log_path).stat().st_size} 字节"
        )
        if records and linktype == 0:
            # 链路类型为 DLT_NULL 时，帧应以 4 字节地址族开头
            print(f"       首帧前 4 字节：{records[0].data[:4].hex()}（回环地址族应为 02000000）")
    except (OSError, ValueError) as exc:
        print(f"  FAIL 报文日志校验失败：{exc}")
    finally:
        try:
            Path(log_path).unlink(missing_ok=True)
            Path(log_dir).rmdir()
        except OSError:
            pass

    if not ok:
        print(f"抓包自测失败：仅收到 {len(frames)} 帧")
        return 1
    if not log_ok:
        print("抓包自测失败：报文日志未正确写入")
        return 1
    print("抓包自测通过（含报文日志）")
    return 0


def build_application(argv: list[str]) -> tuple[QApplication, argparse.Namespace]:
    parser = argparse.ArgumentParser(description=f"{APP_NAME} v{APP_VERSION}")
    parser.add_argument("--demo", action="store_true", help="启动后载入内置样例报文")
    parser.add_argument("--screenshot", metavar="PATH", help="渲染主窗口截图后退出（用于自检）")
    parser.add_argument("--selftest", action="store_true", help="不启动界面，验证解析与打包完整性")
    parser.add_argument(
        "--capture-test",
        action="store_true",
        help="配合 --selftest 使用：在回环网卡上真实抓一次报文，验证抓包链路",
    )
    args, qt_args = parser.parse_known_args(argv)

    # Qt5 必须显式开启高 DPI；Qt6 默认已开，此行是空操作
    qtcompat.enable_high_dpi()
    app = QApplication([sys.argv[0], *qt_args])
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("EMS")
    app.setStyle("Fusion")
    app.setFont(QFont(theme.UI_FAMILY.split(",")[0].strip("'"), 9))
    app.setStyleSheet(theme.STYLE)
    return app, args


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--capture-test" in argv and "--selftest" not in argv:
        return _run_capture_test()
    if "--selftest" in argv:
        code = _run_selftest()
        if "--capture-test" in argv:
            code = max(code, _run_capture_test())
        return code
    app, args = build_application(argv)
    window = MainWindow()
    if args.demo:
        for key, field, role in DEMO_FRAMES:
            window.load_sample(key, field, role)
    window.show()
    if args.screenshot:
        app.processEvents()
        window.grab().save(args.screenshot)
        return 0
    return qtcompat.run_app(app)


if __name__ == "__main__":
    raise SystemExit(main())
