"""主窗口：报文列表 + 解析详情。"""

from __future__ import annotations

import csv
from datetime import datetime
import json
from pathlib import Path
import sys

from PySide6.QtCore import QObject, QSettings, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QStyle,
    QTableView,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, APP_VERSION
from ..core import registry
from ..core.capture import CaptureConfig, CaptureEngine
from ..core.ifaces import local_addresses
from ..core.linklayer import parse_link_frame
from ..core.pcap import FrameMeta, PcapCaptureEngine, PcapConfig, _flow_key, infer_role
from ..core.pcapfile import PcapFileError, default_log_dir, default_log_name, read_pcap
from ..core.store import MessageStore
from . import theme
from .detail_view import DetailPanel
from .dialogs import CaptureDialog, ImportDialog, SendDialog
from .message_model import MessageTableModel

SETTINGS_ORG = "EMS"
SETTINGS_APP = "PacketAnalyzer"


def samples_path() -> Path:
    """开发态从源码目录读取，PyInstaller 打包后从临时解包目录读取。"""
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        return Path(bundled) / "samples" / "samples.json"
    return Path(__file__).resolve().parents[1] / "samples" / "samples.json"


class CaptureBridge(QObject):
    """把后台抓包线程的回调转成 Qt 信号，保证 UI 线程安全。"""

    frame = Signal(bytes, str, object)
    status = Signal(str)
    error = Signal(str)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.store = MessageStore(max_size=5000)
        self.model = MessageTableModel(self.store, self)
        self.settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        self.engine: PcapCaptureEngine | CaptureEngine | None = None
        self._pcap_config, self._direct_config = self._load_capture_configs()
        self._capture_mode = CaptureDialog.MODE_PCAP
        self._last_sent = ""
        self._bridge = CaptureBridge()
        self._bridge.frame.connect(self._on_frame)
        self._bridge.status.connect(self._on_capture_status)
        self._bridge.error.connect(self._on_capture_error)
        self._samples = self._load_samples()

        self.setWindowTitle(f"{APP_NAME}  v{APP_VERSION}")
        self.resize(1440, 880)
        self.setStyleSheet(theme.STYLE)
        self._build_toolbar()
        self._build_body()
        self._build_statusbar()
        self._build_menus()
        self._restore_settings()
        self._update_actions()

        # 日志按链路帧计数，只靠 _on_frame 刷新会滞后（纯 ACK 不产生应用层帧），
        # 用轻量定时器保证状态栏数字始终是实时的。
        self._log_timer = QTimer(self)
        self._log_timer.setInterval(1000)
        self._log_timer.timeout.connect(self._refresh_log_label)
        self._log_timer.start()

    # -- 界面 -------------------------------------------------------------
    def _icon(self, pixmap: QStyle.StandardPixmap) -> QIcon:
        return self.style().standardIcon(pixmap)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("主工具栏")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(16, 16))
        self.addToolBar(toolbar)
        self.toolbar = toolbar

        self.act_start = QAction(self._icon(QStyle.StandardPixmap.SP_MediaPlay), "开始抓包", self)
        self.act_start.setShortcut("F5")
        self.act_start.triggered.connect(self.start_capture)
        toolbar.addAction(self.act_start)
        start_button = toolbar.widgetForAction(self.act_start)
        if isinstance(start_button, QToolButton):
            start_button.setObjectName("startCapture")

        self.act_stop = QAction(self._icon(QStyle.StandardPixmap.SP_MediaStop), "停止", self)
        self.act_stop.setShortcut("Shift+F5")
        self.act_stop.triggered.connect(self.stop_capture)
        toolbar.addAction(self.act_stop)
        stop_button = toolbar.widgetForAction(self.act_stop)
        if isinstance(stop_button, QToolButton):
            stop_button.setObjectName("stopCapture")

        toolbar.addSeparator()

        self.act_import = QAction(self._icon(QStyle.StandardPixmap.SP_DialogOpenButton), "导入报文", self)
        self.act_import.setShortcut("Ctrl+O")
        self.act_import.triggered.connect(self.import_messages)
        toolbar.addAction(self.act_import)

        self.act_open_pcap = QAction(self._icon(QStyle.StandardPixmap.SP_FileDialogContentsView), "打开日志", self)
        self.act_open_pcap.setShortcut("Ctrl+Shift+O")
        self.act_open_pcap.setToolTip("打开 pcap 报文日志并重新解析（也可打开 Wireshark 抓的包）")
        self.act_open_pcap.triggered.connect(self.open_pcap)
        toolbar.addAction(self.act_open_pcap)

        sample_button = QToolButton()
        sample_button.setText("样例")
        sample_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        sample_button.setMenu(self._build_sample_menu(sample_button))
        toolbar.addWidget(sample_button)

        toolbar.addSeparator()

        self.act_log = QAction(self._icon(QStyle.StandardPixmap.SP_DialogSaveButton), "报文日志", self)
        self.act_log.setCheckable(True)
        self.act_log.setShortcut("Ctrl+Shift+L")
        self.act_log.setToolTip("保存抓到的报文为 pcap 日志（Wireshark 可直接打开）")
        self.act_log.toggled.connect(self.toggle_log)
        toolbar.addAction(self.act_log)

        self.act_clear = QAction(self._icon(QStyle.StandardPixmap.SP_TrashIcon), "清空", self)
        self.act_clear.setShortcut("Ctrl+L")
        self.act_clear.triggered.connect(self.clear_messages)
        toolbar.addAction(self.act_clear)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        filter_bar = QFrame()
        filter_bar.setObjectName("filterBar")
        filter_layout = QHBoxLayout(filter_bar)
        filter_layout.setContentsMargins(12, 8, 14, 8)
        filter_layout.setSpacing(8)

        label = QLabel("搜索")
        label.setStyleSheet(f"color:{theme.TEXT_SECONDARY};")
        filter_layout.addWidget(label)

        self.search_mode = QComboBox()
        for key, text in MessageTableModel.MODES.items():
            self.search_mode.addItem(text, key)
        self.search_mode.setFixedWidth(110)
        self.search_mode.currentIndexChanged.connect(self._apply_filter)
        filter_layout.addWidget(self.search_mode)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("输入关键字过滤报文…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setFixedWidth(260)
        self.search_edit.textChanged.connect(self._apply_filter)
        filter_layout.addWidget(self.search_edit)

        ip_label = QLabel("IP 过滤")
        ip_label.setStyleSheet(f"color:{theme.TEXT_SECONDARY};")
        filter_layout.addWidget(ip_label)

        self.ip_filter_edit = QLineEdit()
        self.ip_filter_edit.setPlaceholderText("按 IP 过滤，多个用逗号分隔")
        self.ip_filter_edit.setClearButtonEnabled(True)
        self.ip_filter_edit.setFixedWidth(200)
        self.ip_filter_edit.setToolTip("只显示源或目的 IP 命中该关键字的报文；留空显示全部")
        self.ip_filter_edit.textChanged.connect(self._apply_filter)
        filter_layout.addWidget(self.ip_filter_edit)

        self.ip_combo = QComboBox()
        self.ip_combo.setFixedWidth(150)
        self.ip_combo.setToolTip("从已抓到的报文中挑选 IP")
        self.ip_combo.addItem("选择已出现的 IP", "")
        self.ip_combo.activated.connect(self._pick_ip)
        filter_layout.addWidget(self.ip_combo)

        filter_layout.addStretch(1)

        self.auto_scroll = QCheckBox("自动滚动")
        self.auto_scroll.setChecked(True)
        filter_layout.addWidget(self.auto_scroll)

        self.summary_label = QLabel("共 0 帧")
        self.summary_label.setStyleSheet(f"color:{theme.TEXT_SECONDARY};")
        filter_layout.addWidget(self.summary_label)

        self.latency_label = QLabel("")
        self.latency_label.setStyleSheet(
            f"color:{theme.WARNING}; background:#FDF6EC; border:1px solid #FAECD8;"
            "border-radius:9px; padding:1px 8px; font-size:11px;"
        )
        self.latency_label.setVisible(False)
        filter_layout.addWidget(self.latency_label)

        self._filter_bar = filter_bar

    def _build_body(self) -> None:
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(False)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(30)
        header = self.table.horizontalHeader()
        header.setHighlightSections(False)
        header.setStretchLastSection(False)
        widths = (
            (MessageTableModel.COL_SEQ, 44),
            (MessageTableModel.COL_TIME, 86),
            (MessageTableModel.COL_DIRECTION, 48),
            (MessageTableModel.COL_ENDPOINT, 164),
            (MessageTableModel.COL_ADDRESS, 62),
            (MessageTableModel.COL_LENGTH, 46),
            (MessageTableModel.COL_HEX, 176),
        )
        for column, width in widths:
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
            self.table.setColumnWidth(column, width)
        header.setSectionResizeMode(MessageTableModel.COL_SUMMARY, QHeaderView.ResizeMode.Stretch)
        self.table.selectionModel().currentRowChanged.connect(self._on_row_changed)

        self.detail = DetailPanel()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.table)
        splitter.addWidget(self.detail)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([780, 660])
        self.splitter = splitter

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._filter_bar)
        layout.addWidget(splitter, 1)
        self.setCentralWidget(central)

    def _build_statusbar(self) -> None:
        status = QStatusBar()
        self.setStatusBar(status)
        self.status_label = QLabel("就绪")
        status.addWidget(self.status_label, 1)
        self.count_label = QLabel("接收 0 / 发送 0")
        self.protocol_label = QLabel("协议：自动识别")
        self.interface_label = QLabel("网卡：未开始抓包")
        self.log_label = QLabel("")
        self.log_label.setStyleSheet(
            f"color:{theme.SUCCESS}; background:#EEF9F1; border:1px solid #CFE9D8;"
            "border-radius:9px; padding:1px 8px; font-size:11px;"
        )
        self.log_label.setVisible(False)
        status.addPermanentWidget(self.log_label)
        for widget in (self.interface_label, self.count_label, self.protocol_label):
            widget.setStyleSheet(f"color:{theme.TEXT_SECONDARY}; padding-right:12px;")
            status.addPermanentWidget(widget)

    def _build_menus(self) -> None:
        bar = self.menuBar()

        file_menu = bar.addMenu("文件")
        file_menu.addAction(self.act_import)
        file_menu.addAction(self.act_open_pcap)
        export_action = QAction("导出会话 CSV…", self)
        export_action.setShortcut("Ctrl+S")
        export_action.triggered.connect(self.export_csv)
        file_menu.addAction(export_action)
        file_menu.addSeparator()
        quit_action = QAction("退出", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        edit_menu = bar.addMenu("编辑")
        edit_menu.addAction(self.act_clear)
        copy_action = QAction("复制当前报文 HEX", self)
        copy_action.setShortcut("Ctrl+Shift+C")
        copy_action.triggered.connect(self.copy_current_hex)
        edit_menu.addAction(copy_action)

        capture_menu = bar.addMenu("抓包")
        capture_menu.addAction(self.act_start)
        capture_menu.addAction(self.act_stop)
        capture_menu.addAction(self.act_log)
        capture_menu.addSeparator()
        open_log_action = QAction("打开日志目录", self)
        open_log_action.triggered.connect(self.open_log_dir)
        capture_menu.addAction(open_log_action)
        capture_menu.addSeparator()
        send_action = QAction("发送报文…", self)
        send_action.setShortcut("F6")
        send_action.triggered.connect(self.send_manual)
        capture_menu.addAction(send_action)

        help_menu = bar.addMenu("帮助")
        help_menu.addMenu(self._build_sample_menu(help_menu))
        help_menu.addSeparator()
        about_action = QAction("关于", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _build_sample_menu(self, parent: QWidget) -> QMenu:
        menu = QMenu(parent)
        for key, item in self._samples.items():
            name = item.get("name") or key
            submenu = menu.addMenu(name)
            for label, field, role in (
                ("请求帧", "request", registry.ROLE_REQUEST),
                ("响应帧", "response", registry.ROLE_RESPONSE),
            ):
                text = item.get(field) or ""
                if not text:
                    continue
                action = QAction(label, submenu)
                action.triggered.connect(
                    lambda _checked=False, k=key, f=field, r=role: self.load_sample(k, f, r)
                )
                submenu.addAction(action)
        return menu

    # -- 报文操作 ---------------------------------------------------------
    def import_messages(self) -> None:
        dialog = ImportDialog(self)
        if dialog.exec() != int(dialog.DialogCode.Accepted):
            return
        protocol = dialog.protocol_key()
        role = dialog.role_value()
        frames = dialog.frames()
        for index, raw in enumerate(frames):
            frame_role = role
            if role == "__alternate__":
                frame_role = registry.ROLE_REQUEST if index % 2 == 0 else registry.ROLE_RESPONSE
            direction = (
                "TX"
                if frame_role in (registry.ROLE_REQUEST, "Publish")
                else "RX"
            )
            self.store.append(direction, raw, protocol, role=frame_role, source="导入")
        self.store.invalidate()
        self.model.reload()
        self._refresh_summary()
        if len(self.store):
            self.table.selectRow(self.model.rowCount() - 1)
        self.status_label.setText(f"已导入 {len(frames)} 帧报文")

    def open_pcap(self) -> None:
        """导入 pcap 日志并重新解析，便于回看现场抓到的报文。"""
        directory = self._log_dir()
        start = str(directory) if directory.exists() else ""
        path, _filter = QFileDialog.getOpenFileName(
            self, "打开 pcap 日志", start, "pcap 日志 (*.pcap *.cap);;所有文件 (*)"
        )
        if not path:
            return
        try:
            linktype, records = read_pcap(path)
        except PcapFileError as exc:
            QMessageBox.warning(self, "打开失败", str(exc))
            return
        if not records:
            QMessageBox.information(self, "没有报文", "该文件里没有可解析的报文。")
            return

        protocol = self._pcap_config.protocol
        master_ip = self._pcap_config.master_ip
        local_ips = local_addresses()

        # 先扫一遍 SYN，学到每条连接的客户端，回放时角色判定才准确
        clients: dict[tuple[tuple[str, int], tuple[str, int]], tuple[str, int]] = {}
        parsed: list[tuple[bytes, str, FrameMeta]] = []
        for record in records:
            segment = parse_link_frame(record.data, linktype)
            if segment is None:
                continue
            if segment.is_goose:
                parsed.append((segment.goose_frame, "RX", FrameMeta(transport="ETH", role="Publish")))
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
                master_ip=master_ip,
                client_endpoint=clients.get(
                    _flow_key(segment.src_ip, segment.src_port, segment.dst_ip, segment.dst_port)
                ),
            )
            # 回放时本机地址表未必可达（日志可能来自别的机器），方向按角色推断
            direction = "TX" if role == registry.ROLE_REQUEST else "RX"
            if segment.src_ip in local_ips and segment.dst_ip not in local_ips:
                direction = "TX"
            elif segment.dst_ip in local_ips and segment.src_ip not in local_ips:
                direction = "RX"
            parsed.append(
                (
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

        added = 0
        for payload, direction, meta in parsed:
            if not payload:
                continue
            self.store.append(
                direction,
                payload,
                protocol,
                role=meta.role,
                source=f"日志 {Path(path).name}",
                src_ip=meta.src_ip,
                src_port=meta.src_port,
                dst_ip=meta.dst_ip,
                dst_port=meta.dst_port,
                transport=meta.transport,
            )
            added += 1
        self.store.invalidate()
        self.model.reload()
        self._refresh_summary()
        if added:
            self.table.selectRow(self.model.rowCount() - 1)
        self.status_label.setText(
            f"已从 {Path(path).name} 载入 {added} 帧（文件共 {len(records)} 帧）"
        )

    def load_sample(self, key: str, field: str = "request", role: str = registry.ROLE_REQUEST) -> None:
        item = self._samples.get(key) or {}
        text = item.get(field) or ""
        if not text:
            return
        raw = bytes.fromhex(text.replace(" ", ""))
        direction = "TX" if role == registry.ROLE_REQUEST else "RX"
        record = self.store.append(direction, raw, key, role=role, source=f"样例 · {item.get('name', key)}")
        self.model.append(record)
        self._refresh_summary()
        if self.auto_scroll.isChecked():
            self.table.scrollToBottom()
        row = self.model.row_of(record.sequence)
        if row >= 0:
            self.table.selectRow(row)
        self.status_label.setText(f"已载入样例：{item.get('name', key)}")

    def copy_current_hex(self) -> None:
        record = self._current_record()
        if record is None:
            self.status_label.setText("请先选择一条报文")
            return
        QApplication.clipboard().setText(record.hex_data)
        self.status_label.setText(f"已复制 #{record.sequence} 的原始报文")

    def clear_messages(self) -> None:
        if not len(self.store):
            return
        answer = QMessageBox.question(
            self,
            "清空报文",
            f"确定清空当前 {len(self.store)} 条报文记录吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.store.clear()
        self.model.reload()
        self.detail.show_placeholder()
        self._refresh_summary()

    def export_csv(self) -> None:
        if not len(self.store):
            QMessageBox.information(self, "导出会话", "当前没有可导出的报文。")
            return
        default = f"报文会话_{datetime.now():%Y%m%d_%H%M%S}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "导出会话", default, "CSV 文件 (*.csv)")
        if not path:
            return
        try:
            with Path(path).open("w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.writer(handle)
                writer.writerow(["序号", "时间", "方向", "协议", "地址", "长度", "原始报文", "解析摘要"])
                for record in self.store.records:
                    detail = self.store.detail(record.sequence)
                    writer.writerow(
                        [
                            record.sequence,
                            record.formatted_time,
                            record.direction,
                            detail.get("protocol_name", ""),
                            detail.get("address", ""),
                            len(record.raw),
                            record.hex_data,
                            self.store.summary(record.sequence),
                        ]
                    )
        except OSError as exc:
            QMessageBox.warning(self, "导出失败", f"写入文件失败：{exc}")
            return
        self.status_label.setText(f"已导出 {len(self.store)} 条报文到 {path}")

    # -- 抓包 -------------------------------------------------------------
    def start_capture(self) -> None:
        if self.engine and self.engine.running:
            return
        dialog = CaptureDialog(self._pcap_config, self._direct_config, self)
        if dialog.exec() != int(dialog.DialogCode.Accepted):
            return
        self._capture_mode = dialog.mode()
        if self._capture_mode == CaptureDialog.MODE_PCAP:
            self._pcap_config = dialog.pcap_config()
            self._save_pcap_config()
            self._start_pcap_capture()
            return

        self._direct_config = dialog.direct_config()
        self.settings.setValue("direct", json.dumps(self._direct_config.to_dict(), ensure_ascii=False))
        self._start_direct_capture()

    def _start_pcap_capture(self) -> bool:
        config = self._pcap_config
        log_path = self._next_log_path() if config.log_enabled else ""
        self.engine = PcapCaptureEngine(
            config,
            on_frame=lambda raw, direction, meta: self._bridge.frame.emit(raw, direction, meta),
            on_status=lambda text: self._bridge.status.emit(text),
            on_error=lambda text: self._bridge.error.emit(text),
            log_path=log_path,
        )
        if not self.engine.start():
            self.engine = None
            self._update_actions()
            return False
        # 抓包时再过滤一次，避免无关流量进入列表
        if config.ip_filter and not self.ip_filter_edit.text().strip():
            self.ip_filter_edit.setText(config.ip_filter)
        self._update_actions()
        self.status_label.setText(f"正在从网卡抓包：{config.interface or '默认网卡'}")
        self.protocol_label.setText(
            "协议：" + (
                registry.PROTOCOLS[config.protocol].name if registry.is_known(config.protocol) else "自动识别"
            )
        )
        self.interface_label.setText(f"网卡：{config.interface or '默认'}")
        # 同步勾选状态时不能触发 toggle_log，否则会与抓包线程抢着建日志文件
        self.act_log.blockSignals(True)
        self.act_log.setChecked(bool(config.log_enabled and log_path))
        self.act_log.blockSignals(False)
        return True

    # -- 报文日志 ---------------------------------------------------------
    def _next_log_path(self) -> str:
        """按配置算出本次日志的完整路径。"""
        directory = self._log_dir()
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError:
            directory = default_log_dir()
            directory.mkdir(parents=True, exist_ok=True)
        return str(directory / default_log_name(self._pcap_config.interface))

    def toggle_log(self, enabled: bool) -> None:
        """运行中或空闲时切换报文日志。"""
        engine = self.engine
        if isinstance(engine, PcapCaptureEngine) and engine.running:
            if enabled:
                path = self._next_log_path()
                if engine.set_log(path):
                    self.status_label.setText(
                        f"报文日志已开启：{path}"
                        + ("（仅记录过滤命中的报文）" if self._pcap_config.has_filter() else "（记录全部抓取报文）")
                    )
                else:
                    self.act_log.setChecked(False)
            else:
                count = engine.log_count
                path = engine.log_path
                engine.close_log()
                self.status_label.setText(f"报文日志已停止，共记录 {count} 帧：{path}")
            self._refresh_log_label()
            return

        # 空闲状态：只记下开关，下次开始抓包时生效
        self._pcap_config.log_enabled = bool(enabled)
        self._save_pcap_config()
        self._refresh_log_label()
        if enabled:
            self.status_label.setText(f"报文日志已启用，开始抓包后写入 {self._log_dir()}")
        else:
            self.status_label.setText("报文日志已关闭")

    def _log_dir(self) -> Path:
        return Path(self._pcap_config.log_dir or default_log_dir())

    def _refresh_log_label(self) -> None:
        engine = self.engine
        if not (isinstance(engine, PcapCaptureEngine) and engine.log_count):
            self.log_label.setVisible(False)
            return
        path = Path(engine.log_path)
        size_kb = max(1, round(path.stat().st_size / 1024)) if path.exists() else 0
        self.log_label.setText(f"日志 {engine.log_count} 帧 · {size_kb} KB")
        self.log_label.setToolTip(str(path))
        self.log_label.setVisible(True)

    def _save_pcap_config(self) -> None:
        self.settings.setValue("pcap", json.dumps(self._pcap_config.to_dict(), ensure_ascii=False))

    def open_log_dir(self) -> None:
        """在文件管理器里打开日志目录。"""
        directory = self._log_dir()
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, "打开目录失败", str(exc))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))
        self.status_label.setText(f"日志目录：{directory}")

    def _start_direct_capture(self) -> None:
        config = self._direct_config
        self.engine = CaptureEngine(
            config,
            on_frame=lambda raw, direction, meta: self._bridge.frame.emit(raw, direction, meta),
            on_status=lambda text: self._bridge.status.emit(text),
            on_error=lambda text: self._bridge.error.emit(text),
        )
        self.engine.start()
        self._update_actions()
        self.status_label.setText(
            f"正在{'连接' if config.mode == 'client' else '监听'} {config.host}:{config.port}"
        )
        self.protocol_label.setText(
            "协议：" + (
                registry.PROTOCOLS[config.protocol].name if registry.is_known(config.protocol) else "自动识别"
            )
        )
        self.interface_label.setText(f"直连：{config.host}:{config.port}")

    def stop_capture(self) -> None:
        engine = self.engine
        log_info = ""
        if isinstance(engine, PcapCaptureEngine) and engine.log_count:
            log_info = f"，报文日志 {engine.log_count} 帧 → {engine.log_path}"
        if engine:
            engine.stop()
        self._update_actions()
        self._refresh_log_label()
        self.status_label.setText("抓包已停止" + log_info)

    def send_manual(self) -> None:
        if not isinstance(self.engine, CaptureEngine) or not self.engine.running:
            QMessageBox.information(
                self,
                "发送报文",
                "发送报文需要直连模式并已建立连接。\n网卡抓包是被动监听，不能发送。",
            )
            return
        dialog = SendDialog(self._last_sent, self)
        if dialog.exec() != int(dialog.DialogCode.Accepted):
            return
        self._last_sent = dialog.hex.text()
        if not self.engine.send_hex(self._last_sent):
            QMessageBox.warning(self, "发送失败", "当前连接不可用，请检查是否已建立连接。")
            return
        self.status_label.setText("已发送 1 帧报文")

    # -- 抓包回调（UI 线程） ----------------------------------------------
    def _on_frame(self, raw: bytes, direction: str, meta: FrameMeta | None) -> None:
        meta = meta or FrameMeta()
        pcap_mode = self._capture_mode == CaptureDialog.MODE_PCAP
        protocol = self._pcap_config.protocol if pcap_mode else self._direct_config.protocol
        record = self.store.append(
            direction,
            raw,
            protocol,
            role=meta.role,
            source="网卡抓包" if pcap_mode else "直连抓包",
            src_ip=meta.src_ip,
            src_port=meta.src_port,
            dst_ip=meta.dst_ip,
            dst_port=meta.dst_port,
            transport=meta.transport,
        )
        self.model.append(record)
        if self.auto_scroll.isChecked():
            self.table.scrollToBottom()
        self._refresh_summary()

    def _on_capture_status(self, text: str) -> None:
        self.status_label.setText(text)
        self._update_actions()

    def _on_capture_error(self, text: str) -> None:
        self.status_label.setText(f"抓包失败：{text}")
        self._update_actions()
        QMessageBox.critical(self, "抓包失败", text)

    # -- 状态刷新 ---------------------------------------------------------
    def _current_record(self):
        index = self.table.currentIndex()
        if not index.isValid():
            return None
        return self.model.record_at(index.row())

    def _on_row_changed(self, current, _previous) -> None:
        if not current.isValid():
            self.detail.show_placeholder()
            return
        record = self.model.record_at(current.row())
        if record is None:
            self.detail.show_placeholder()
            return
        self.detail.set_detail(self.store.detail(record.sequence))

    def _apply_filter(self) -> None:
        self.model.set_ip_filter(self.ip_filter_edit.text())
        self.model.set_filter(self.search_edit.text(), str(self.search_mode.currentData()))
        self._refresh_ip_combo()
        self._refresh_summary()
        if self.table.currentIndex().isValid():
            return
        if self.model.rowCount():
            self.table.selectRow(0)
        else:
            self.detail.show_placeholder()

    def _pick_ip(self, index: int) -> None:
        value = str(self.ip_combo.itemData(index) or "")
        if value:
            self.ip_filter_edit.setText(value)

    def _refresh_ip_combo(self) -> None:
        """把会话中出现过的 IP 填进下拉框，供一键过滤。"""
        existing = {self.ip_combo.itemData(i) for i in range(1, self.ip_combo.count())}
        for address in self.model.available_ips():
            if address and address not in existing:
                self.ip_combo.addItem(address, address)

    def _refresh_summary(self) -> None:
        total = len(self.store)
        shown = self.model.rowCount()
        if shown == total:
            self.summary_label.setText(f"共 {total} 帧")
        else:
            self.summary_label.setText(f"显示 {shown} / {total} 帧")
        stats = self.store.stats()
        if stats["pair_count"]:
            self.latency_label.setText(
                f"平均时延 {stats['avg_latency_ms']} ms · {stats['pair_count']} 组"
            )
            self.latency_label.setVisible(True)
        else:
            self.latency_label.setVisible(False)
        self.count_label.setText(f"接收 {stats['rx_count']} / 发送 {stats['tx_count']}")
        self._refresh_ip_combo()
        self._refresh_log_label()
        self._update_actions()

    def _update_actions(self) -> None:
        running = bool(self.engine and self.engine.running)
        self.act_start.setEnabled(not running)
        self.act_stop.setEnabled(running)
        self.act_import.setEnabled(True)
        self.act_clear.setEnabled(len(self.store) > 0)
        # 日志只对网卡抓包有效，直连模式没有原始链路帧
        is_pcap = isinstance(self.engine, PcapCaptureEngine)
        self.act_log.setEnabled(not running or is_pcap)

    # -- 配置 -------------------------------------------------------------
    def _load_capture_configs(self) -> tuple[PcapConfig, CaptureConfig]:
        settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        pcap = PcapConfig()
        raw_pcap = settings.value("pcap", "")
        if raw_pcap:
            try:
                pcap = PcapConfig.from_dict(json.loads(str(raw_pcap)))
            except (ValueError, TypeError):
                pcap = PcapConfig()
        direct = CaptureConfig()
        raw_direct = settings.value("direct", "") or settings.value("capture", "")
        if raw_direct:
            try:
                direct = CaptureConfig.from_dict(json.loads(str(raw_direct)))
            except (ValueError, TypeError):
                direct = CaptureConfig()
        return pcap, direct

    def _load_samples(self) -> dict:
        try:
            return json.loads(samples_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _restore_settings(self) -> None:
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        sizes = self.settings.value("splitter")
        if sizes:
            self.splitter.setSizes([int(value) for value in sizes])
        mode = self.settings.value("search_mode")
        if mode:
            index = self.search_mode.findData(str(mode))
            if index >= 0:
                self.search_mode.setCurrentIndex(index)

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "关于",
            f"<b>{APP_NAME}</b> v{APP_VERSION}<br><br>"
            "支持 Modbus TCP/RTU、DL/T 645、IEC 101/104、DNP3、"
            "IEC 61850 MMS 与 GOOSE 的字段级报文解析。<br><br>"
            "独立桌面版，复用 EMS Simulate 的协议解析内核。",
        )

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.engine:
            self.engine.stop()
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("splitter", self.splitter.sizes())
        self.settings.setValue("search_mode", self.search_mode.currentData())
        super().closeEvent(event)
