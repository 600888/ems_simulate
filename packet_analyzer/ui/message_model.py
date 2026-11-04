"""报文列表的数据模型。"""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor, QFont

from ..core import registry
from ..core.store import FrameRecord, MessageStore
from . import theme


class MessageTableModel(QAbstractTableModel):
    """把 MessageStore 中的记录映射成表格行。

    过滤支持两种维度，可叠加：

    * ``set_filter(text, mode)`` —— 按摘要、原始报文、协议地址过滤
    * ``set_ip_filter(text)`` —— 按源/目的 IP 过滤，多个关键字用逗号分隔
    """

    HEADERS = ("#", "时间", "方向", "源 → 目的", "地址", "长度", "原始报文", "解析摘要")
    MODES = {"summary": "解析摘要", "hex": "原始报文", "address": "协议地址"}

    COL_SEQ = 0
    COL_TIME = 1
    COL_DIRECTION = 2
    COL_ENDPOINT = 3
    COL_ADDRESS = 4
    COL_LENGTH = 5
    COL_HEX = 6
    COL_SUMMARY = 7

    def __init__(self, store: MessageStore, parent=None):
        super().__init__(parent)
        self._store = store
        self._rows: list[FrameRecord] = []
        self._filter_text = ""
        self._filter_mode = "summary"
        self._ip_terms: list[str] = []
        self._mono = QFont("Consolas")
        self._mono.setStyleHint(QFont.StyleHint.Monospace)

    # -- Qt 接口 ----------------------------------------------------------
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if role != Qt.ItemDataRole.DisplayRole or orientation != Qt.Orientation.Horizontal:
            return None
        return self.HEADERS[section]

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        record = self._rows[index.row()]
        column = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            if column == self.COL_SEQ:
                return str(record.sequence)
            if column == self.COL_TIME:
                return record.formatted_time
            if column == self.COL_DIRECTION:
                return record.direction
            if column == self.COL_ENDPOINT:
                return record.endpoint_text or "—"
            if column == self.COL_ADDRESS:
                address = registry.frame_address(record.raw, record.protocol)
                return "—" if address is None else str(address)
            if column == self.COL_LENGTH:
                return str(len(record.raw))
            if column == self.COL_HEX:
                return record.hex_data
            return self._store.summary(record.sequence)
        if role == Qt.ItemDataRole.ToolTipRole:
            if column == self.COL_HEX:
                return record.hex_data
            if column == self.COL_SUMMARY:
                return self._store.summary(record.sequence)
            if column == self.COL_ENDPOINT and record.src_ip:
                return f"{record.transport}  {record.endpoint_text}"
            if column == self.COL_SEQ:
                return f"来源：{record.source}" if record.source else None
            return None
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if column in (self.COL_SEQ, self.COL_DIRECTION, self.COL_ADDRESS, self.COL_LENGTH):
                return int(Qt.AlignmentFlag.AlignCenter)
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.BackgroundRole:
            return QColor(theme.TX_TINT if record.direction == "TX" else theme.RX_TINT)
        if role == Qt.ItemDataRole.ForegroundRole:
            if column == self.COL_DIRECTION:
                return QColor(theme.PRIMARY if record.direction == "TX" else theme.SUCCESS)
            if column in (self.COL_ADDRESS, self.COL_LENGTH):
                return QColor(theme.TEXT_SECONDARY)
            if column == self.COL_ENDPOINT:
                return QColor(theme.TEXT_REGULAR)
            return None
        if role == Qt.ItemDataRole.FontRole and column in (self.COL_HEX, self.COL_ENDPOINT):
            return self._mono
        if role == Qt.ItemDataRole.UserRole:
            return record.sequence
        return None

    # -- 数据更新 ---------------------------------------------------------
    def record_at(self, row: int) -> FrameRecord | None:
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None

    def row_of(self, sequence: int) -> int:
        for row, record in enumerate(self._rows):
            if record.sequence == sequence:
                return row
        return -1

    def reload(self) -> None:
        self.beginResetModel()
        self._rows = [record for record in self._store.records if self._matches(record)]
        self.endResetModel()

    def append(self, record: FrameRecord) -> bool:
        if not self._matches(record):
            return False
        row = len(self._rows)
        self.beginInsertRows(QModelIndex(), row, row)
        self._rows.append(record)
        self.endInsertRows()
        return True

    def set_filter(self, text: str, mode: str) -> None:
        text = (text or "").strip().lower()
        if text == self._filter_text and mode == self._filter_mode:
            return
        self._filter_text = text
        self._filter_mode = mode
        self.reload()

    def set_ip_filter(self, text: str) -> None:
        """按 IP 过滤；支持逗号分隔多个 IP，命中原/目的任一即可。"""
        terms = [item.strip() for item in (text or "").replace(";", ",").replace(" ", ",").split(",")]
        terms = [item for item in terms if item]
        if terms == self._ip_terms:
            return
        self._ip_terms = terms
        self.reload()

    def ip_terms(self) -> list[str]:
        return list(self._ip_terms)

    def available_ips(self) -> list[str]:
        """会话中出现过的 IP，供界面下拉提示。"""
        seen: set[str] = set()
        for record in self._store.records:
            if record.src_ip:
                seen.add(record.src_ip)
            if record.dst_ip:
                seen.add(record.dst_ip)
        return sorted(seen)

    # -- 内部 -------------------------------------------------------------
    def _matches(self, record: FrameRecord) -> bool:
        if self._ip_terms and not any(record.matches_ip(term) for term in self._ip_terms):
            return False
        if not self._filter_text:
            return True
        if self._filter_mode == "hex":
            # 忽略空格，允许用户直接输入连续十六进制片段
            needle = self._filter_text.replace(" ", "")
            return needle in record.hex_data.replace(" ", "").lower()
        if self._filter_mode == "address":
            address = registry.frame_address(record.raw, record.protocol)
            return self._filter_text in str(address).lower()
        return self._filter_text in self._store.summary(record.sequence).lower()
