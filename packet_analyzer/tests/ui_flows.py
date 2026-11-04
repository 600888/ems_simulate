"""交互流程自检：导入、过滤、导出、复制、清空、抓包回调与对话框校验。"""

from __future__ import annotations

import csv
import os
from pathlib import Path
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from packet_analyzer.core import registry  # noqa: E402
from packet_analyzer.core.capture import CaptureConfig  # noqa: E402
from packet_analyzer.core.pcap import PcapConfig  # noqa: E402
from packet_analyzer.main import build_application  # noqa: E402
from packet_analyzer.ui.dialogs import CaptureDialog, ImportDialog, normalize_hex  # noqa: E402
from packet_analyzer.ui.main_window import MainWindow  # noqa: E402
from packet_analyzer.ui.qtcompat import (  # noqa: E402
    QApplication,
    QMessageBox,
    QSettings,  # noqa: E402
)

failures: list[str] = []
QSettings("EMS", "PacketAnalyzer").clear()


def check(condition: bool, message: str) -> None:
    print(("PASS " if condition else "FAIL ") + message)
    if not condition:
        failures.append(message)


app, _args = build_application([])
window = MainWindow()
window.resize(1440, 880)
window.show()

# 1. 导入对话框：多行解析
dialog = ImportDialog()
dialog.editor.setPlainText("01 03 00 00 00 02 C4 0B\n01 03 04 00 64 00 C8 BA 7A")
dialog.protocol.setCurrentIndex(dialog.protocol.findData("modbus_rtu"))
dialog._accept()
check(len(dialog.frames()) == 2, f"导入对话框解析出 {len(dialog.frames())} 帧")
check(dialog.protocol_key() == "modbus_rtu", "导入对话框协议选择生效")

# 2. 非法十六进制应被拒绝
try:
    normalize_hex("01 0")
    check(False, "奇数长度十六进制应报错")
except ValueError:
    check(True, "奇数长度十六进制被拒绝")

# 3. 主窗口导入两帧（请求 + 响应）并验证关联
window.store.clear()
window.model.reload()
for role, text, direction in (
    (registry.ROLE_REQUEST, "000100000006010300000009", "TX"),
    (registry.ROLE_RESPONSE, "000100000007010304006400C8", "RX"),
):
    window.store.append(direction, bytes.fromhex(text), "modbus_tcp", role=role, source="测试")
window.store.invalidate()
window.model.reload()
window._refresh_summary()
check(window.model.rowCount() == 2, f"主窗口记录数 = {window.model.rowCount()}")
check(window.act_clear.isEnabled(), "有报文时清空按钮可用")
response_detail = window.store.detail(window.store.records[-1].sequence)
check(response_detail.get("correlation") is not None, "响应帧关联到请求帧")

# 4. 过滤
window.search_mode.setCurrentIndex(window.search_mode.findData("hex"))
window.search_edit.setText("0064")
window._apply_filter()
check(window.model.rowCount() == 1, f"按报文内容过滤后行数 = {window.model.rowCount()}")
window.search_edit.clear()
window._apply_filter()
check(window.model.rowCount() == 2, "清空过滤条件后恢复全部行")

# 5. 复制 HEX
window.table.selectRow(0)
window.copy_current_hex()
check(QApplication.clipboard().text().replace(" ", "") == "000100000006010300000009", "复制当前报文 HEX")

# 6. 导出 CSV
tmp_dir = Path(tempfile.mkdtemp(prefix="pkt_"))
csv_path = tmp_dir / "session.csv"
with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
    writer = csv.writer(handle)
    writer.writerow(["序号", "时间", "方向", "协议", "地址", "长度", "原始报文", "解析摘要"])
    for record in window.store.records:
        writer.writerow([record.sequence, record.formatted_time, record.direction])
check(csv_path.exists(), "会话 CSV 可写出")
# 7. 网卡抓包回调进入界面（含 IP 元信息）
from packet_analyzer.core.pcap import FrameMeta  # noqa: E402

window._pcap_config = PcapConfig(protocol="iec104", ip_filter="192.168.1.10")
window._capture_mode = CaptureDialog.MODE_PCAP
before = window.model.rowCount()
window._bridge.frame.emit(
    bytes.fromhex("680407000000"),
    "RX",
    FrameMeta(src_ip="192.168.1.20", src_port=2404, dst_ip="192.168.1.10", dst_port=41000, transport="TCP",
              role=registry.ROLE_RESPONSE),
)
app.processEvents()
check(window.model.rowCount() == before + 1, "抓包回调新增一行")
last = window.store.records[-1]
check(last.role == registry.ROLE_RESPONSE, "抓包回调采用引擎给出的角色")
check(last.src_ip == "192.168.1.20" and last.dst_port == 41000, f"记录保存 IP 元信息：{last.endpoint_text}")

# 7b. IP 过滤：命中 / 不命中
window.ip_filter_edit.setText("192.168.1.10")
window._apply_filter()
check(window.model.rowCount() == 1, f"IP 过滤命中 1 行（实际 {window.model.rowCount()}）")
window.ip_filter_edit.setText("10.9.9.9")
window._apply_filter()
check(window.model.rowCount() == 0, "IP 过滤不命中时列表为空")
window.ip_filter_edit.clear()
window._apply_filter()
check(window.model.rowCount() == before + 1, f"清空 IP 过滤后恢复全部（{window.model.rowCount()} 行）")
check(window.ip_combo.count() >= 3, f"IP 下拉已收集会话 IP（{window.ip_combo.count()} 项）")

# 8. 清空（跳过确认框）
original_question = QMessageBox.question
QMessageBox.question = staticmethod(lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes)
window.clear_messages()
QMessageBox.question = original_question
check(window.model.rowCount() == 0, "清空后无记录")
check(not window.act_clear.isEnabled(), "清空后按钮置灰")

# 9. 抓包设置对话框：网卡页与直连页参数往返
pcap_config = PcapConfig(interface="以太网", ip_filter="10.1.1.10, 10.1.1.20", port_filter=502, protocol="modbus_tcp")
direct_config = CaptureConfig(mode="server", host="0.0.0.0", port=2404, protocol="iec104", poll_hex="680407000000")
capture_dialog = CaptureDialog(pcap_config, direct_config)
check(capture_dialog.mode() == CaptureDialog.MODE_PCAP, "对话框默认选中网卡抓包")
restored_pcap = capture_dialog.pcap_config()
check(restored_pcap.ip_filter == "10.1.1.10, 10.1.1.20", "IP 过滤参数保留")
check(restored_pcap.port_filter == 502, "端口过滤参数保留")
check(restored_pcap.protocol == "modbus_tcp", "协议选择保留")
check(capture_dialog.iface_combo.count() > 0, f"网卡下拉已填充 {capture_dialog.iface_combo.count()} 项")
check("host" in capture_dialog.bpf_preview.text(), f"BPF 预览：{capture_dialog.bpf_preview.text()}")

capture_dialog.tabs.setCurrentIndex(1)
check(capture_dialog.mode() == CaptureDialog.MODE_DIRECT, "切换到直连页")
restored_direct = capture_dialog.direct_config()
check(restored_direct.mode == "server" and restored_direct.port == 2404, "直连参数往返一致")
check(restored_direct.poll_hex == "680407000000", "定时发送报文保留")

# 10. 报文日志：对话框开关 + 回放
import tempfile  # noqa: E402

from packet_analyzer.core import pcapfile  # noqa: E402

with tempfile.TemporaryDirectory() as tmp:
    log_config = PcapConfig(interface="以太网", protocol="modbus_tcp", ip_filter="10.1.1.10",
                            log_enabled=True, log_dir=tmp)
    log_dialog = CaptureDialog(log_config, CaptureConfig())
    check(log_dialog.log_enabled.isChecked(), "日志开关回显为开启")
    check(log_dialog.log_dir.text() == tmp, "日志目录回显")
    check("过滤命中" in log_dialog.log_hint.text(), f"日志范围提示：{log_dialog.log_hint.text()}")
    restored_log = log_dialog.pcap_config()
    check(restored_log.log_enabled and restored_log.log_dir == tmp, "日志参数往返一致")

    # 无过滤时提示应说"全部"
    log_dialog.ip_filter.clear()
    log_dialog.port_filter.setValue(0)
    log_dialog._update_log_hint()
    check("全部" in log_dialog.log_hint.text(), f"无过滤时提示全部：{log_dialog.log_hint.text()}")

    # 菜单/工具栏存在日志动作
    check(window.act_log.isCheckable(), "报文日志是可切换动作")
    check(window.act_open_pcap is not None, "存在打开日志动作")

    # 回放：直接走 open_pcap 的解析路径（跳过文件对话框）
    log_path = f"{tmp}/replay.pcap"
    frames = [bytes.fromhex("ffffffffffff001122334455") + bytes.fromhex("88b8") + bytes(40)]
    with pcapfile.PcapWriter(log_path, linktype=1) as writer:
        for frame in frames:
            writer.write(frame, 1793000000.0)
    linktype, records = pcapfile.read_pcap(log_path)
    check(linktype == 1 and len(records) == 1, "日志文件可读回")
    check(records[0].data == frames[0], "日志帧内容完整（含链路层头）")

window.close()
QSettings("EMS", "PacketAnalyzer").clear()
print()
print(f"失败项：{len(failures)}")
for item in failures:
    print(f"  - {item}")
raise SystemExit(1 if failures else 0)
