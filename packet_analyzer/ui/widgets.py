"""详情面板的可复用控件。"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import theme


def _item(text: str, *, mono: bool = False, color: str | None = None, align_center: bool = False):
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    if mono:
        font = QFont("Consolas")
        font.setStyleHint(QFont.StyleHint.Monospace)
        item.setFont(font)
    if color:
        item.setForeground(QColor(color))
    if align_center:
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    return item


class SectionHeader(QWidget):
    """带左侧色条的小节标题。"""

    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        bar = QFrame()
        bar.setFixedSize(3, 13)
        bar.setStyleSheet(f"background:{theme.PRIMARY}; border-radius:1px;")
        label = QLabel(text)
        label.setStyleSheet(f"font-size:13px; font-weight:700; color:{theme.TEXT_PRIMARY};")
        layout.addWidget(bar)
        layout.addWidget(label)
        layout.addStretch(1)


class Pill(QLabel):
    """圆角状态标签。"""

    def __init__(self, text: str = "", tone: str = "info", parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_tone(tone)

    def set_tone(self, tone: str) -> None:
        palette = {
            "success": ("#F0F9EB", theme.SUCCESS, "#E1F3D8"),
            "warning": ("#FDF6EC", theme.WARNING, "#FAECD8"),
            "danger": ("#FEF0F0", theme.DANGER, "#FDE2E2"),
            "primary": ("#ECF5FF", theme.PRIMARY, "#D9ECFF"),
            "info": ("#F4F4F5", theme.TEXT_SECONDARY, "#E9E9EB"),
        }
        bg, fg, border = palette.get(tone, palette["info"])
        self.setStyleSheet(
            f"background:{bg}; color:{fg}; border:1px solid {border};"
            "border-radius:9px; padding:1px 8px; font-size:11px;"
        )


class ByteStrip(QWidget):
    """以带背景色的字节序列展示原始报文，可高亮指定区间。"""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._hex = ""
        self._highlight: tuple[int, int] | None = None
        self._label = QLabel()
        self._label.setTextFormat(Qt.TextFormat.RichText)
        self._label.setWordWrap(True)
        self._label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._label.setStyleSheet(
            "background:#0F172A; border-radius:6px; padding:12px 14px;"
            f"font-family:{theme.MONO_FAMILY}; font-size:13px;"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._label)

    def set_frame(self, hex_text: str, highlight: tuple[int, int] | None = None) -> None:
        self._hex = hex_text
        self._highlight = highlight
        self._render()

    def highlight(self, offset: int, length: int) -> None:
        self._highlight = (offset, length) if length > 0 else None
        self._render()

    def _render(self) -> None:
        parts = self._hex.split()
        selected = self._highlight
        chunks: list[str] = []
        for index, byte in enumerate(parts):
            active = bool(selected and selected[0] <= index < selected[0] + selected[1])
            if active:
                chunks.append(
                    f'<span style="background-color:#F59E0B; color:#111827; font-weight:700;">{byte}</span>'
                )
            else:
                chunks.append(f'<span style="color:#A7F3D0;">{byte}</span>')
        # 用普通空格分隔才能让长报文自动换行，&nbsp; 会把整条报文撑成不可换行的长单词
        self._label.setText(" ".join(chunks) or "<span>（空）</span>")


class InfoGrid(QWidget):
    """标签 / 值 两行式信息栅格。"""

    def __init__(self, columns: int = 3, parent: QWidget | None = None):
        super().__init__(parent)
        self._columns = columns
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(18)
        self._grid.setVerticalSpacing(10)

    def set_items(self, items: list[tuple[str, str]]) -> None:
        while self._grid.count():
            entry = self._grid.takeAt(0)
            widget = entry.widget()
            if widget is not None:
                widget.deleteLater()
        for index, (label, value) in enumerate(items):
            row, column = divmod(index, self._columns)
            cell = QWidget()
            cell_layout = QVBoxLayout(cell)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            cell_layout.setSpacing(1)
            caption = QLabel(label)
            caption.setStyleSheet(f"color:{theme.TEXT_SECONDARY}; font-size:11px;")
            text = QLabel(value if value else "—")
            text.setWordWrap(True)
            text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            text.setStyleSheet(f"color:{theme.TEXT_PRIMARY}; font-size:12px; font-weight:600;")
            cell_layout.addWidget(caption)
            cell_layout.addWidget(text)
            self._grid.addWidget(cell, row, column)
        for column in range(self._columns):
            self._grid.setColumnStretch(column, 1)


class FieldTable(QTableWidget):
    """字段解析表；点击行通过 bytesSelected 通知字节高亮。"""

    bytesSelected = Signal(int, int)

    HEADERS = ("字节", "原始HEX", "字段", "解析值", "说明")

    def __init__(self, parent: QWidget | None = None):
        super().__init__(0, len(self.HEADERS), parent)
        self.setHorizontalHeaderLabels(list(self.HEADERS))
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setHighlightSections(False)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.horizontalHeader().setStretchLastSection(True)
        self.setColumnWidth(0, 68)
        self.setColumnWidth(1, 96)
        self.setColumnWidth(2, 104)
        self.setColumnWidth(3, 144)
        self.itemClicked.connect(self._on_click)
        self.setMinimumHeight(120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def _on_click(self, item: QTableWidgetItem) -> None:
        anchor = self.item(item.row(), 0)
        data = anchor.data(Qt.ItemDataRole.UserRole) if anchor is not None else None
        if data and data[1] > 0:
            self.bytesSelected.emit(int(data[0]), int(data[1]))

    def set_fields(self, fields: list[dict[str, Any]]) -> None:
        self.setRowCount(0)
        self.setRowCount(len(fields))
        for row, field in enumerate(fields):
            offset = int(field.get("offset", 0) or 0)
            length = int(field.get("length", 0) or 0)
            byte_range = f"{offset}" if length <= 1 else f"{offset}-{offset + length - 1}"
            name = str(field.get("name", ""))
            value = str(field.get("display_value", ""))
            description = str(field.get("description", "") or "")
            level = str(field.get("level", "normal"))
            color = theme.DANGER if level == "error" else None
            cells = [
                _item(byte_range, mono=True, align_center=True, color=theme.TEXT_SECONDARY),
                _item(str(field.get("raw_hex", "")), mono=True, color=theme.TEXT_REGULAR),
                _item(name, color=color),
                _item(value, mono=False, color=color),
                _item(description, color=theme.TEXT_SECONDARY),
            ]
            cells[0].setData(Qt.ItemDataRole.UserRole, (offset, length))
            for column, cell in enumerate(cells):
                cell.setToolTip(cell.text())
                self.setItem(row, column, cell)
            self.setRowHeight(row, 26)
        self.setVisible(bool(fields))


class ObjectTree(QTreeWidget):
    """数据对象树：对象为父节点，字段为子节点。"""

    bytesSelected = Signal(int, int)

    HEADERS = ("#", "字节", "数据项", "地址", "原始值", "解析值", "工程值", "时标")

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setColumnCount(len(self.HEADERS))
        self.setHeaderLabels(list(self.HEADERS))
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setAlternatingRowColors(False)
        self.setRootIsDecorated(True)
        self.setIndentation(14)
        self.setUniformRowHeights(True)
        header = self.header()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for index, width in enumerate((30, 62, 98, 58, 96, 96, 78, 84)):
            self.setColumnWidth(index, width)
        self.itemClicked.connect(self._on_click)
        self.setMinimumHeight(140)

    def set_objects(self, objects: list[dict[str, Any]]) -> None:
        self.clear()
        for index, obj in enumerate(objects):
            length = _object_length(obj)
            offset = int(obj.get("offset", 0) or 0)
            top = QTreeWidgetItem(
                [
                    str(index),
                    f"{offset}" if length <= 1 else f"{offset}-{offset + length - 1}",
                    str(obj.get("name") or ""),
                    _text(obj.get("address")),
                    str(obj.get("combined_raw") or obj.get("raw_value") or ""),
                    _value_text(obj.get("decoded_value") if obj.get("decoded_value") is not None else obj.get("value")),
                    _engineering_text(obj),
                    _text(obj.get("timestamp")),
                ]
            )
            top.setData(0, Qt.ItemDataRole.UserRole, (offset, length))
            font = QFont("Consolas")
            font.setStyleHint(QFont.StyleHint.Monospace)
            top.setFont(1, font)
            top.setFont(4, font)
            for column in range(len(self.HEADERS)):
                top.setToolTip(column, top.text(column))
            self.addTopLevelItem(top)
            for field in obj.get("fields") or []:
                child_offset = int(field.get("offset", 0) or 0)
                child_length = int(field.get("length", 0) or 0)
                child = QTreeWidgetItem(
                    [
                        "",
                        f"{child_offset}"
                        if child_length <= 1
                        else f"{child_offset}-{child_offset + child_length - 1}",
                        str(field.get("name", "")),
                        "",
                        str(field.get("raw_hex", "")),
                        str(field.get("display_value", "")),
                        "",
                        "",
                    ]
                )
                child.setData(0, Qt.ItemDataRole.UserRole, (child_offset, child_length))
                child.setForeground(2, QColor(theme.TEXT_SECONDARY))
                child.setFont(4, font)
                for column in range(len(self.HEADERS)):
                    child.setToolTip(column, child.text(column))
                top.addChild(child)
        self.setVisible(bool(objects))

    def _on_click(self, item: QTreeWidgetItem, _column: int) -> None:
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and data[1] > 0:
            self.bytesSelected.emit(int(data[0]), int(data[1]))


class ValidationList(QWidget):
    """完整性校验结果列表。"""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(6)

    def set_items(self, items: list[dict[str, Any]]) -> None:
        while self._layout.count():
            entry = self._layout.takeAt(0)
            widget = entry.widget()
            if widget is not None:
                widget.deleteLater()
        for item in items:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(8)
            passed = bool(item.get("passed"))
            pill = Pill("通过" if passed else "失败", "success" if passed else "danger")
            pill.setFixedWidth(44)
            name = QLabel(str(item.get("name", "")))
            name.setStyleSheet(f"font-weight:600; color:{theme.TEXT_PRIMARY};")
            name.setMinimumWidth(96)
            detail = QLabel(str(item.get("detail", "")))
            detail.setStyleSheet(f"color:{theme.TEXT_SECONDARY};")
            detail.setWordWrap(True)
            row_layout.addWidget(pill)
            row_layout.addWidget(name)
            row_layout.addWidget(detail, 1)
            self._layout.addWidget(row)
        self.setVisible(bool(items))


class NoticeList(QWidget):
    """告警/错误提示列表。"""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(6)

    def set_messages(self, warnings: list[str], errors: list[str]) -> None:
        while self._layout.count():
            entry = self._layout.takeAt(0)
            widget = entry.widget()
            if widget is not None:
                widget.deleteLater()
        for text in warnings:
            self._add(text, "warning")
        for text in errors:
            self._add(text, "danger")
        self.setVisible(bool(warnings or errors))

    def _add(self, text: str, tone: str) -> None:
        tone_map = {
            "warning": ("#FDF6EC", "#B88230", "#FAECD8"),
            "danger": ("#FEF0F0", "#C45656", "#FDE2E2"),
        }
        bg, fg, border = tone_map[tone]
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet(
            f"background:{bg}; color:{fg}; border:1px solid {border};"
            "border-radius:4px; padding:7px 10px;"
        )
        self._layout.addWidget(label)


def _object_length(obj: dict[str, Any]) -> int:
    combined = str(obj.get("combined_raw") or "").split()
    return max(int(obj.get("length", 0) or 0), len(combined))


def _text(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, (dict, list)):
        return str(value)
    return str(value)


def _value_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, (dict, list)):
        return str(value)
    return str(value)


def _engineering_text(obj: dict[str, Any]) -> str:
    if obj.get("engineering_value") is None:
        return ""
    point = obj.get("point") or {}
    prefix = f"{point.get('name')}: " if point.get("name") else ""
    return f"{prefix}{_value_text(obj.get('engineering_value'))}"
