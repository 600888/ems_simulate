"""界面配色与全局样式（浅色主题）。"""

from __future__ import annotations

# 主色板：与 Element Plus 的浅色风格保持一致
PRIMARY = "#409EFF"
SUCCESS = "#67C23A"
WARNING = "#E6A23C"
DANGER = "#F56C6C"
TEXT_PRIMARY = "#303133"
TEXT_REGULAR = "#606266"
TEXT_SECONDARY = "#909399"
BORDER = "#DCDFE6"
BORDER_LIGHT = "#EBEEF5"
FILL = "#F5F7FA"

# 报文方向背景
TX_TINT = "#EAF4FF"
RX_TINT = "#EEF9E8"

MONO_FAMILY = "Consolas, 'Cascadia Mono', 'Courier New', monospace"
UI_FAMILY = "'Microsoft YaHei UI', 'Microsoft YaHei', 'Segoe UI', sans-serif"

STYLE = f"""
QWidget {{
    font-family: {UI_FAMILY};
    font-size: 12px;
    color: {TEXT_PRIMARY};
}}
QMainWindow, QDialog {{ background: #FFFFFF; }}

QToolBar {{
    background: #FFFFFF;
    border: none;
    border-bottom: 1px solid {BORDER_LIGHT};
    padding: 7px 10px;
    spacing: 6px;
}}
QToolBar QToolButton {{
    padding: 6px 10px;
    border: 1px solid transparent;
    border-radius: 4px;
    color: {TEXT_REGULAR};
}}
QToolBar QToolButton:hover {{ background: #ECF5FF; color: {PRIMARY}; }}
QToolBar QToolButton:pressed {{ background: #D9ECFF; }}
QToolBar QToolButton:disabled {{ color: #C0C4CC; }}
QToolBar::separator {{ width: 1px; background: {BORDER_LIGHT}; margin: 3px 8px; }}
QToolButton#startCapture {{
    background: {PRIMARY}; color: #FFFFFF; font-weight: 600;
    border-radius: 4px; padding: 6px 12px;
}}
QToolButton#startCapture:hover {{ background: #66B1FF; color: #FFFFFF; }}
QToolButton#startCapture:disabled {{ background: #A0CFFF; color: #FFFFFF; }}
QToolButton#stopCapture {{ color: {DANGER}; }}
QToolButton#stopCapture:hover {{ background: #FEF0F0; color: {DANGER}; }}
QToolButton#stopCapture:disabled {{ color: #C0C4CC; }}

QFrame#filterBar {{ background: #FFFFFF; border-bottom: 1px solid {BORDER_LIGHT}; }}

QPushButton {{
    min-height: 26px;
    padding: 2px 14px;
    border: 1px solid {BORDER};
    border-radius: 4px;
    background: #FFFFFF;
    color: {TEXT_REGULAR};
}}
QPushButton:hover {{ border-color: #C6E2FF; background: #ECF5FF; color: {PRIMARY}; }}
QPushButton:pressed {{ border-color: {PRIMARY}; }}
QPushButton:disabled {{ color: #C0C4CC; background: #F5F7FA; border-color: {BORDER_LIGHT}; }}
QPushButton[accent="primary"] {{
    background: {PRIMARY}; border-color: {PRIMARY}; color: #FFFFFF; font-weight: 600;
}}
QPushButton[accent="primary"]:hover {{ background: #66B1FF; border-color: #66B1FF; color: #FFFFFF; }}
QPushButton[accent="primary"]:disabled {{ background: #A0CFFF; border-color: #A0CFFF; color: #FFFFFF; }}
QPushButton[accent="danger"] {{ color: {DANGER}; border-color: #FBC4C4; }}
QPushButton[accent="danger"]:hover {{ background: #FEF0F0; border-color: {DANGER}; color: {DANGER}; }}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {{
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 4px 8px;
    background: #FFFFFF;
    selection-background-color: {PRIMARY};
    selection-color: #FFFFFF;
}}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QPlainTextEdit:hover {{
    border-color: #C0C4CC;
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QPlainTextEdit:focus {{
    border-color: {PRIMARY};
}}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox QAbstractItemView {{
    border: 1px solid {BORDER_LIGHT};
    background: #FFFFFF;
    selection-background-color: #ECF5FF;
    selection-color: {PRIMARY};
    outline: none;
}}
QCheckBox {{ spacing: 6px; color: {TEXT_REGULAR}; }}
QCheckBox::indicator {{
    width: 14px; height: 14px; border: 1px solid {BORDER};
    border-radius: 3px; background: #FFFFFF;
}}
QCheckBox::indicator:checked {{ background: {PRIMARY}; border-color: {PRIMARY}; }}
QRadioButton {{ spacing: 6px; color: {TEXT_REGULAR}; }}

QTableView, QTableWidget, QTreeWidget {{
    border: 1px solid {BORDER_LIGHT};
    border-radius: 6px;
    background: #FFFFFF;
    alternate-background-color: #FBFCFE;
    gridline-color: #F2F4F8;
    selection-background-color: #ECF5FF;
    selection-color: {TEXT_PRIMARY};
    outline: none;
}}
QTableView::item, QTableWidget::item, QTreeWidget::item {{ padding: 3px 4px; }}
QTreeWidget::item:selected {{ background: #ECF5FF; color: {TEXT_PRIMARY}; }}
QHeaderView::section {{
    background: {FILL};
    border: none;
    border-right: 1px solid #EFF1F5;
    border-bottom: 1px solid {BORDER_LIGHT};
    padding: 6px 8px;
    color: {TEXT_REGULAR};
    font-weight: 600;
}}
QTableCornerButton::section {{ background: {FILL}; border: none; }}

QMenuBar {{ background: #FFFFFF; border-bottom: 1px solid {BORDER_LIGHT}; }}
QMenuBar::item {{ padding: 5px 10px; background: transparent; }}
QMenuBar::item:selected {{ background: #ECF5FF; color: {PRIMARY}; }}
QMenu {{ background: #FFFFFF; border: 1px solid {BORDER_LIGHT}; padding: 4px; }}
QMenu::item {{ padding: 6px 24px 6px 18px; border-radius: 4px; }}
QMenu::item:selected {{ background: #ECF5FF; color: {PRIMARY}; }}
QMenu::separator {{ height: 1px; background: {BORDER_LIGHT}; margin: 4px 8px; }}

QStatusBar {{ background: {FILL}; border-top: 1px solid {BORDER_LIGHT}; color: {TEXT_SECONDARY}; }}
QStatusBar::item {{ border: none; }}

QSplitter::handle {{ background: {FILL}; }}
QSplitter::handle:horizontal {{ width: 6px; }}
QSplitter::handle:hover {{ background: #E4E7ED; }}

QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 9px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #DCDFE6; border-radius: 4px; min-height: 28px; }}
QScrollBar::handle:vertical:hover {{ background: #C0C4CC; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QScrollBar:horizontal {{ background: transparent; height: 9px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #DCDFE6; border-radius: 4px; min-width: 28px; }}
QScrollBar::handle:horizontal:hover {{ background: #C0C4CC; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: transparent; }}

QGroupBox {{
    border: 1px solid {BORDER_LIGHT};
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 10px;
    font-weight: 600;
    color: {TEXT_REGULAR};
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; }}

QToolTip {{
    background: #FFFFFF;
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_LIGHT};
    padding: 4px 8px;
}}
"""
