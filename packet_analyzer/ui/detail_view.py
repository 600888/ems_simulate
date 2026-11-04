"""报文解析详情面板。"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .widgets import ByteStrip, FieldTable, InfoGrid, NoticeList, ObjectTree, Pill, SectionHeader, ValidationList

ROLE_LABELS = {
    "request": "请求",
    "response": "响应",
    "publish": "发布",
    "subscribe": "订阅",
    "unknown": "未知",
}

CORRELATION_LABELS = {
    "request_sequence_id": "请求帧序号",
    "match_method": "匹配方式",
    "start_address": "起始地址",
    "end_address": "结束地址",
    "quantity": "数量",
    "application_sequence": "应用序号",
    "request_function_code": "请求功能码",
    "request_function": "请求功能",
}


class DetailPanel(QScrollArea):
    """展示单帧报文的字段级解析结果。"""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setMinimumWidth(420)
        self._content = QWidget()
        self._content.setStyleSheet("background:#FFFFFF;")
        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(18, 16, 18, 18)
        self._layout.setSpacing(16)
        self.setWidget(self._content)
        self.show_placeholder()

    # -- 对外接口 ---------------------------------------------------------
    def show_placeholder(self) -> None:
        self._clear()
        holder = QWidget()
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(0, 60, 0, 0)
        layout.setSpacing(10)
        title = QLabel("选择左侧报文查看解析详情")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"color:{theme.TEXT_SECONDARY}; font-size:14px;")
        hint = QLabel(
            "通过「导入报文」粘贴或加载十六进制数据，"
            "也可以用「开始抓包」连接设备后实时解析。"
        )
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#B1B3B8; font-size:12px;")
        layout.addWidget(title)
        layout.addWidget(hint)
        self._layout.addWidget(holder)
        self._layout.addStretch(1)

    def set_detail(self, detail: dict[str, Any] | None) -> None:
        if not detail:
            self.show_placeholder()
            return
        self._clear()
        self._last_raw_wrapper: QWidget | None = None
        self.verticalScrollBar().setValue(0)
        self._add(self._banner(detail))
        self._add(self._meta(detail))
        raw_section = self._raw_section(detail)
        self._last_raw_wrapper = raw_section
        self._add(raw_section)
        self._add(self._fields_section(detail))
        if detail.get("objects"):
            self._add(self._objects_section(detail))
        if detail.get("correlation"):
            self._add(self._correlation_section(detail))
        validation = list(detail.get("validation") or [])
        if validation:
            validation_list = ValidationList()
            validation_list.set_items(validation)
            self._add(self._section("完整性校验", validation_list))
        if detail.get("warnings") or detail.get("errors"):
            notices = NoticeList()
            notices.set_messages(list(detail.get("warnings") or []), list(detail.get("errors") or []))
            self._add(self._section("提示与告警", notices))
        self._layout.addStretch(1)

    # -- 构件 -------------------------------------------------------------
    def _clear(self) -> None:
        while self._layout.count():
            entry = self._layout.takeAt(0)
            widget = entry.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _add(self, widget: QWidget) -> None:
        self._layout.addWidget(widget)

    def _banner(self, detail: dict[str, Any]) -> QWidget:
        valid = bool(detail.get("valid"))
        complete = bool(detail.get("complete"))
        if not valid:
            bg, fg, border, tone, text = "#FEF0F0", "#C45656", "#FDE2E2", "danger", "校验失败"
        elif not complete:
            bg, fg, border, tone, text = "#FDF6EC", "#B88230", "#FAECD8", "warning", "部分解析"
        else:
            bg, fg, border, tone, text = "#F0F9EB", "#529B2E", "#E1F3D8", "success", "解析通过"
        frame = QFrame()
        frame.setStyleSheet(f"background:{bg}; border:1px solid {border}; border-radius:6px;")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)
        pill = Pill(text, tone)
        summary = QLabel(str(detail.get("summary") or "（无摘要）"))
        summary.setWordWrap(True)
        summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        summary.setStyleSheet(f"color:{fg}; font-size:13px; font-weight:600; border:none;")
        layout.addWidget(pill, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(summary, 1)
        return frame

    def _meta(self, detail: dict[str, Any]) -> QWidget:
        role = ROLE_LABELS.get(str(detail.get("msg_type", "")).lower(), str(detail.get("msg_type", "")))
        direction = "发送 TX" if detail.get("direction") == "TX" else "接收 RX"
        status = "完整" if detail.get("valid") and detail.get("complete") else (
            "校验失败" if not detail.get("valid") else "部分解析"
        )
        items = [
            ("协议", str(detail.get("protocol_name") or detail.get("protocol") or "—")),
            ("帧类型", str(detail.get("frame_kind") or "—")),
            ("方向", f"{direction} / {role}"),
            ("时间", str(detail.get("formatted_time") or "—")),
            ("长度", f"{detail.get('raw_length', 0)} 字节"),
            ("解析状态", status),
        ]
        grid = InfoGrid(columns=3)
        grid.set_items(items)
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(SectionHeader("概要"))
        layout.addWidget(grid)
        return wrapper

    def _raw_section(self, detail: dict[str, Any]) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.addWidget(SectionHeader("原始报文"))
        head.addStretch(1)
        copy_button = QPushButton("复制 HEX")
        copy_button.setCursor(Qt.CursorShape.PointingHandCursor)
        hex_text = str(detail.get("raw_hex") or "")
        copy_button.clicked.connect(lambda: QApplication.clipboard().setText(hex_text))
        head.addWidget(copy_button)
        layout.addLayout(head)

        strip = ByteStrip()
        strip.set_frame(hex_text)
        layout.addWidget(strip)

        hint = QLabel("提示：点击下方字段行或对象行，可高亮该字段占用的字节。")
        hint.setStyleSheet(f"color:{theme.TEXT_SECONDARY}; font-size:11px;")
        layout.addWidget(hint)
        wrapper._byte_strip = strip  # type: ignore[attr-defined]
        return wrapper

    def _fields_section(self, detail: dict[str, Any]) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(SectionHeader("字段解析"))
        table = FieldTable()
        table.set_fields(list(detail.get("fields") or []))
        strip = getattr(self._last_raw_wrapper, "_byte_strip", None)
        if strip is not None:
            table.bytesSelected.connect(strip.highlight)
        layout.addWidget(table)
        return wrapper

    def _objects_section(self, detail: dict[str, Any]) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(SectionHeader(f"数据对象（{len(detail.get('objects') or [])}）"))
        tree = ObjectTree()
        tree.set_objects(list(detail.get("objects") or []))
        strip = getattr(self._last_raw_wrapper, "_byte_strip", None)
        if strip is not None:
            tree.bytesSelected.connect(strip.highlight)
        layout.addWidget(tree)
        return wrapper

    def _correlation_section(self, detail: dict[str, Any]) -> QWidget:
        correlation = detail.get("correlation") or {}
        items = [
            (CORRELATION_LABELS.get(key, key), str(value))
            for key, value in correlation.items()
            if value is not None
        ]
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(SectionHeader("请求 / 响应关联"))
        grid = InfoGrid(columns=2)
        grid.set_items(items)
        layout.addWidget(grid)
        return wrapper

    def _section(self, title: str, widget: QWidget) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(SectionHeader(title))
        layout.addWidget(widget)
        return wrapper
