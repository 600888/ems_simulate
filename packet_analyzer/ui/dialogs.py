"""导入报文、抓包参数与手动发送对话框。"""

from __future__ import annotations

import ipaddress
from pathlib import Path
import re

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..core import registry
from ..core.capture import CaptureConfig
from ..core.ifaces import capture_available, capture_runtime_info, list_interfaces
from ..core.pcap import PcapConfig, describe_bpf
from ..core.pcapfile import default_log_dir
from . import theme


def protocol_combo(current: str = registry.AUTO) -> QComboBox:
    combo = QComboBox()
    for key, label in registry.CHOICES:
        combo.addItem(label, key)
    index = combo.findData(current)
    combo.setCurrentIndex(max(index, 0))
    return combo


def role_combo() -> QComboBox:
    combo = QComboBox()
    combo.addItem("请求 / 命令", registry.ROLE_REQUEST)
    combo.addItem("响应 / 上送", registry.ROLE_RESPONSE)
    combo.addItem("按行交替（请求、响应）", "__alternate__")
    return combo


def normalize_hex(text: str) -> bytes:
    cleaned = re.sub(r"[^0-9A-Fa-f]", "", text or "")
    if len(cleaned) % 2:
        raise ValueError("十六进制字符个数必须为偶数")
    if not cleaned:
        raise ValueError("没有可解析的十六进制内容")
    return bytes.fromhex(cleaned)


class ImportDialog(QDialog):
    """粘贴或从文件导入报文。"""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("导入报文")
        self.resize(680, 460)
        self.setStyleSheet(theme.STYLE)
        self._frames: list[bytes] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        tip = QLabel(
            "支持空格、换行、逗号或 0x 前缀。勾选「每行一帧」时按行拆分，"
            "取消勾选则把全部内容视为一帧。"
        )
        tip.setWordWrap(True)
        tip.setStyleSheet(f"color:{theme.TEXT_SECONDARY};")
        layout.addWidget(tip)

        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("例如：01 03 00 00 00 02 C4 0B")
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self.editor.setFont(mono)
        layout.addWidget(self.editor, 1)

        options = QHBoxLayout()
        options.setSpacing(10)
        options.addWidget(QLabel("协议"))
        self.protocol = protocol_combo()
        self.protocol.setMinimumWidth(170)
        options.addWidget(self.protocol)
        options.addSpacing(6)
        options.addWidget(QLabel("方向"))
        self.role = role_combo()
        self.role.setMinimumWidth(120)
        options.addWidget(self.role)
        options.addSpacing(6)
        self.per_line = QCheckBox("每行一帧")
        self.per_line.setChecked(True)
        options.addWidget(self.per_line)
        options.addStretch(1)
        layout.addLayout(options)

        buttons = QHBoxLayout()
        load = QPushButton("从文件导入…")
        load.clicked.connect(self._load_file)
        buttons.addWidget(load)
        buttons.addStretch(1)
        box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_button = box.button(QDialogButtonBox.StandardButton.Ok)
        ok_button.setText("解析")
        ok_button.setProperty("accent", "primary")
        box.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        box.accepted.connect(self._accept)
        box.rejected.connect(self.reject)
        buttons.addWidget(box)
        layout.addLayout(buttons)

    # -- 数据 -------------------------------------------------------------
    def frames(self) -> list[bytes]:
        return self._frames

    def protocol_key(self) -> str:
        return str(self.protocol.currentData())

    def role_value(self) -> str:
        return str(self.role.currentData())

    # -- 交互 -------------------------------------------------------------
    def _load_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择报文文件",
            "",
            "报文文件 (*.txt *.hex *.log *.dat *.bin);;所有文件 (*.*)",
        )
        if not path:
            return
        file = Path(path)
        try:
            if file.suffix.lower() == ".bin":
                data = file.read_bytes()
                self.editor.setPlainText(data.hex(" ").upper())
                self.per_line.setChecked(False)
            else:
                text = file.read_text(encoding="utf-8", errors="ignore")
                self.editor.setPlainText(text)
                self.per_line.setChecked(True)
        except OSError as exc:
            QMessageBox.warning(self, "读取失败", f"无法读取文件：{exc}")

    def _accept(self) -> None:
        text = self.editor.toPlainText()
        if not text.strip():
            QMessageBox.warning(self, "内容为空", "请先粘贴或导入报文内容。")
            return
        chunks = [line for line in text.splitlines() if line.strip()] if self.per_line.isChecked() else [text]
        frames: list[bytes] = []
        for index, chunk in enumerate(chunks, start=1):
            try:
                frames.append(normalize_hex(chunk))
            except ValueError as exc:
                QMessageBox.warning(self, "格式错误", f"第 {index} 行：{exc}")
                return
        if not frames:
            QMessageBox.warning(self, "内容为空", "没有解析到有效报文。")
            return
        self._frames = frames
        self.accept()


class CaptureDialog(QDialog):
    """抓包参数配置。

    两种方式：
    * 网卡抓包（默认）—— 从选定网卡被动抓取链路上的全部报文，支持 IP/端口过滤
    * 直连设备 —— 主动连接或监听 TCP，可定时发送轮询报文
    """

    MODE_PCAP = "pcap"
    MODE_DIRECT = "direct"

    def __init__(
        self,
        config: PcapConfig,
        direct_config: CaptureConfig | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("抓包设置")
        self.setStyleSheet(theme.STYLE)
        self.setMinimumWidth(560)
        self._direct_config = direct_config or CaptureConfig()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_pcap_tab(config), "网卡抓包（推荐）")
        self.tabs.addTab(self._build_direct_tab(self._direct_config), "直连设备")
        layout.addWidget(self.tabs)

        self.hint = QLabel("")
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet(f"color:{theme.TEXT_SECONDARY}; font-size:11px;")
        layout.addWidget(self.hint)
        self.tabs.currentChanged.connect(self._update_hint)
        self._update_hint()

        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        box.button(QDialogButtonBox.StandardButton.Ok).setText("开始")
        box.button(QDialogButtonBox.StandardButton.Ok).setProperty("accent", "primary")
        box.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        box.accepted.connect(self._accept)
        box.rejected.connect(self.reject)
        layout.addWidget(box)

    # -- 网卡抓包页 -------------------------------------------------------
    def _build_pcap_tab(self, config: PcapConfig) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 12, 4, 4)
        layout.setSpacing(10)

        nic_row = QHBoxLayout()
        nic_row.setSpacing(8)
        self.iface_combo = QComboBox()
        self.iface_combo.setMinimumWidth(360)
        self.iface_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        nic_row.addWidget(self.iface_combo, 1)
        refresh = QPushButton("刷新")
        refresh.setToolTip("重新枚举本机网卡")
        refresh.clicked.connect(self._reload_interfaces)
        nic_row.addWidget(refresh)
        layout.addWidget(QLabel("网卡"))
        layout.addLayout(nic_row)

        self.iface_hint = QLabel("")
        self.iface_hint.setWordWrap(True)
        self.iface_hint.setStyleSheet(f"color:{theme.TEXT_SECONDARY}; font-size:11px;")
        layout.addWidget(self.iface_hint)

        filter_group = QGroupBox("过滤条件")
        filter_form = QFormLayout(filter_group)
        filter_form.setSpacing(9)
        self.ip_filter = QLineEdit(config.ip_filter)
        self.ip_filter.setPlaceholderText("例如：192.168.1.10, 192.168.1.20（留空抓全部）")
        self.ip_filter.setToolTip("命中源或目的 IP 即保留；多个用逗号分隔")
        filter_form.addRow("IP 过滤", self.ip_filter)
        self.port_filter = QSpinBox()
        self.port_filter.setRange(0, 65535)
        self.port_filter.setSpecialValueText("不限")
        self.port_filter.setValue(int(config.port_filter))
        self.port_filter.setToolTip("只看指定端口（如 Modbus 502、IEC104 2404），0 表示不限")
        filter_form.addRow("端口过滤", self.port_filter)
        self.master_ip = QLineEdit(config.master_ip)
        self.master_ip.setPlaceholderText("可选：主站/客户端 IP，用于判定请求方向")
        filter_form.addRow("主站 IP", self.master_ip)
        layout.addWidget(filter_group)

        self.bpf_preview = QLabel("")
        self.bpf_preview.setWordWrap(True)
        self.bpf_preview.setStyleSheet(
            f"color:{theme.TEXT_REGULAR}; background:{theme.FILL}; border-radius:4px;"
            "padding:6px 9px; font-size:11px;"
        )
        layout.addWidget(self.bpf_preview)
        self.ip_filter.textChanged.connect(self._update_bpf_preview)
        self.port_filter.valueChanged.connect(self._update_bpf_preview)

        common = QFormLayout()
        common.setSpacing(9)
        self.protocol = protocol_combo(config.protocol)
        common.addRow("协议", self.protocol)
        self.link_size = QSpinBox()
        self.link_size.setRange(1, 2)
        self.link_size.setValue(int(config.link_address_size))
        self.link_size.setToolTip("IEC 101 链路地址长度，通常为 1")
        common.addRow("IEC101 链路地址长度", self.link_size)
        self.promisc = QCheckBox("混杂模式（接收本网段全部流量）")
        self.promisc.setChecked(bool(config.promisc))
        self.promisc.setToolTip(
            "取消勾选则只接收发往本机的流量。\n"
            "要做设备与设备之间的旁路分析时保持勾选。"
        )
        common.addRow("", self.promisc)
        layout.addLayout(common)

        log_group = QGroupBox("报文日志")
        log_layout = QFormLayout(log_group)
        log_layout.setSpacing(9)
        self.log_enabled = QCheckBox("保存为 pcap 日志（Wireshark 可直接打开）")
        self.log_enabled.setChecked(bool(config.log_enabled))
        self.log_enabled.setToolTip(
            "设了 IP / 端口过滤时只记录命中的报文；\n"
            "不设过滤则记录网卡抓取到的全部报文。"
        )
        self.log_enabled.toggled.connect(self._update_log_hint)
        log_layout.addRow("", self.log_enabled)

        dir_row = QHBoxLayout()
        dir_row.setSpacing(6)
        self.log_dir = QLineEdit(config.log_dir or str(default_log_dir()))
        self.log_dir.setPlaceholderText("留空使用程序目录下的 logs/")
        dir_row.addWidget(self.log_dir, 1)
        browse = QPushButton("浏览…")
        browse.clicked.connect(self._browse_log_dir)
        dir_row.addWidget(browse)
        log_layout.addRow("保存目录", dir_row)

        self.log_hint = QLabel("")
        self.log_hint.setWordWrap(True)
        self.log_hint.setStyleSheet(f"color:{theme.TEXT_SECONDARY}; font-size:11px;")
        log_layout.addRow("", self.log_hint)
        layout.addWidget(log_group)

        self.engine_hint = QLabel("")
        self.engine_hint.setStyleSheet(f"color:{theme.TEXT_SECONDARY}; font-size:11px;")
        layout.addWidget(self.engine_hint)
        layout.addStretch(1)

        self._reload_interfaces(config.interface)
        self._update_bpf_preview()
        return page
    def _reload_interfaces(self, preferred: str = "") -> None:
        wanted = preferred or (self.iface_combo.currentData() if self.iface_combo.count() else "")
        self.iface_combo.clear()
        interfaces = list_interfaces()
        for item in interfaces:
            self.iface_combo.addItem(item.label, item.id)
        self.engine_hint.setText(capture_runtime_info())
        if not interfaces:
            self.iface_combo.addItem("未找到可用网卡", "")
            self.iface_hint.setText("未枚举到网卡，请检查 Npcap 是否安装。")
            return
        index = self.iface_combo.findData(wanted) if wanted else -1
        if index < 0:
            # 默认选第一个有 IPv4 的非 loopback 网卡
            index = 0
            for position, item in enumerate(interfaces):
                if item.ipv4 and not item.is_loopback:
                    index = position
                    break
        self.iface_combo.setCurrentIndex(index)
        self._update_iface_hint()

    def _update_iface_hint(self) -> None:
        current = self.iface_combo.currentData()
        item = next((entry for entry in list_interfaces() if entry.id == current), None)
        if item is None:
            self.iface_hint.setText("")
            return
        tips = [f"描述：{item.description or '—'}"]
        if item.ipv4:
            tips.append(f"IPv4：{', '.join(item.ipv4)}")
        if item.is_loopback:
            tips.append("本机回环网卡：只能抓到本机进程之间的通讯")
        self.iface_hint.setText("   ".join(tips))

    def _update_bpf_preview(self) -> None:
        config = self.pcap_config()
        self.bpf_preview.setText(f"实际过滤表达式：{describe_bpf(config)}")
        self._update_log_hint()

    def _update_log_hint(self) -> None:
        if self.log_enabled.isChecked():
            scope = "过滤命中的报文" if self.pcap_config().has_filter() else "网卡抓取到的全部报文"
            self.log_hint.setText(f"开启后保存{scope}，抓包停止时自动落盘。")
        else:
            self.log_hint.setText("未开启：抓包只显示在界面，不落盘。")

    def _browse_log_dir(self) -> None:
        current = self.log_dir.text().strip() or str(default_log_dir())
        chosen = QFileDialog.getExistingDirectory(self, "选择日志保存目录", current)
        if chosen:
            self.log_dir.setText(chosen)

    # -- 直连设备页 -------------------------------------------------------
    def _build_direct_tab(self, config: CaptureConfig) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 12, 4, 4)
        layout.setSpacing(10)

        mode_group = QGroupBox("连接方式")
        mode_layout = QHBoxLayout(mode_group)
        self.client_radio = QRadioButton("主动连接（客户端）")
        self.server_radio = QRadioButton("监听等待（服务端）")
        (self.client_radio if config.mode == "client" else self.server_radio).setChecked(True)
        mode_layout.addWidget(self.client_radio)
        mode_layout.addWidget(self.server_radio)
        mode_layout.addStretch(1)
        layout.addWidget(mode_group)

        form = QFormLayout()
        form.setSpacing(9)
        self.host = QLineEdit(config.host)
        self.host.setPlaceholderText("127.0.0.1")
        form.addRow("地址", self.host)
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(int(config.port))
        form.addRow("端口", self.port)
        self.direct_protocol = protocol_combo(config.protocol)
        form.addRow("协议", self.direct_protocol)
        self.direct_link_size = QSpinBox()
        self.direct_link_size.setRange(1, 2)
        self.direct_link_size.setValue(int(config.link_address_size))
        form.addRow("IEC101 链路地址长度", self.direct_link_size)
        layout.addLayout(form)

        poll_group = QGroupBox("定时发送（模拟主站轮询）")
        poll_layout = QFormLayout(poll_group)
        poll_layout.setSpacing(9)
        self.poll_enabled = QCheckBox("启用")
        self.poll_enabled.setChecked(bool(config.poll_hex))
        poll_layout.addRow("", self.poll_enabled)
        self.poll_hex = QLineEdit(config.poll_hex)
        self.poll_hex.setPlaceholderText("例如：000100000006010300000009")
        self.poll_hex.setFont(QFont("Consolas"))
        poll_layout.addRow("报文 HEX", self.poll_hex)
        self.poll_interval = QDoubleSpinBox()
        self.poll_interval.setRange(0.1, 3600.0)
        self.poll_interval.setDecimals(1)
        self.poll_interval.setSingleStep(0.5)
        self.poll_interval.setValue(float(config.poll_interval))
        self.poll_interval.setSuffix(" 秒")
        poll_layout.addRow("发送间隔", self.poll_interval)
        layout.addWidget(poll_group)
        layout.addStretch(1)
        return page

    # -- 公共 -------------------------------------------------------------
    def _update_hint(self) -> None:
        if self.mode() == self.MODE_PCAP:
            available, reason = capture_available()
            if not available:
                self.hint.setText(f"⚠ {reason}")
                self.hint.setStyleSheet(f"color:{theme.DANGER}; font-size:11px;")
                return
            self.hint.setText(
                "从网卡被动抓包，可看到链路上所有 TCP/UDP 通讯（含设备与设备之间）。"
                "直接调用 Npcap/libpcap，无需 scapy；IP 过滤同时作用于抓包和列表展示。"
            )
        else:
            self.hint.setText("直连设备：主动连接或监听 TCP 端口，可按周期发送轮询报文。")
        self.hint.setStyleSheet(f"color:{theme.TEXT_SECONDARY}; font-size:11px;")

    def mode(self) -> str:
        return self.MODE_PCAP if self.tabs.currentIndex() == 0 else self.MODE_DIRECT

    def pcap_config(self) -> PcapConfig:
        return PcapConfig(
            interface=str(self.iface_combo.currentData() or ""),
            protocol=str(self.protocol.currentData()),
            link_address_size=int(self.link_size.value()),
            ip_filter=self.ip_filter.text().strip(),
            port_filter=int(self.port_filter.value()),
            master_ip=self.master_ip.text().strip(),
            promisc=self.promisc.isChecked(),
            log_enabled=self.log_enabled.isChecked(),
            log_dir=self.log_dir.text().strip(),
        )

    def direct_config(self) -> CaptureConfig:
        return CaptureConfig(
            mode="client" if self.client_radio.isChecked() else "server",
            host=self.host.text().strip() or "127.0.0.1",
            port=int(self.port.value()),
            protocol=str(self.direct_protocol.currentData()),
            link_address_size=int(self.direct_link_size.value()),
            poll_hex=self.poll_hex.text().strip() if self.poll_enabled.isChecked() else "",
            poll_interval=float(self.poll_interval.value()),
        )

    def _accept(self) -> None:
        if self.mode() == self.MODE_PCAP:
            available, reason = capture_available()
            if not available:
                QMessageBox.warning(self, "无法抓包", reason)
                return
            if not self.iface_combo.currentData():
                QMessageBox.warning(self, "未选择网卡", "请先选择一块网卡。")
                return
            for item in self.ip_filter.text().replace(";", ",").replace(" ", ",").split(","):
                item = item.strip()
                if not item:
                    continue
                try:
                    ipaddress.ip_network(item, strict=False)
                except ValueError:
                    QMessageBox.warning(self, "IP 过滤无效", f"无法识别的 IP 或网段：{item}")
                    return
            self.accept()
            return

        if not self.host.text().strip():
            QMessageBox.warning(self, "地址无效", "请填写监听或连接地址。")
            return
        if self.poll_enabled.isChecked():
            try:
                normalize_hex(self.poll_hex.text())
            except ValueError as exc:
                QMessageBox.warning(self, "发送报文无效", str(exc))
                return
        self.accept()


class SendDialog(QDialog):
    """手动发送一帧报文。"""

    def __init__(self, last: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("发送报文")
        self.setStyleSheet(theme.STYLE)
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        layout.addWidget(QLabel("将以十六进制原样发送到当前连接："))
        self.hex = QLineEdit(last)
        self.hex.setFont(QFont("Consolas"))
        self.hex.setPlaceholderText("例如：000100000006010300000009")
        layout.addWidget(self.hex)
        self.hint = QLabel("")
        self.hint.setStyleSheet(f"color:{theme.DANGER}; font-size:11px;")
        layout.addWidget(self.hint)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        box.button(QDialogButtonBox.StandardButton.Ok).setText("发送")
        box.button(QDialogButtonBox.StandardButton.Ok).setProperty("accent", "primary")
        box.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        box.accepted.connect(self._accept)
        box.rejected.connect(self.reject)
        layout.addWidget(box)

    def _accept(self) -> None:
        try:
            normalize_hex(self.hex.text())
        except ValueError as exc:
            self.hint.setText(str(exc))
            return
        self.accept()

    def payload(self) -> bytes:
        return normalize_hex(self.hex.text())


__all__ = [
    "CaptureDialog",
    "ImportDialog",
    "protocol_combo",
    "role_combo",
    "SendDialog",
    "normalize_hex",
]
