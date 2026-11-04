"""探测 PySide2 5.15 的能力边界：哪些 Qt6 写法在 Qt5 上可用。

结论直接决定兼容层怎么写，不靠猜。
"""

import sys

print("Python:", sys.version.split()[0])

try:
    import PySide2
    from PySide2 import QtCore, QtGui, QtWidgets
    from PySide2.QtCore import Qt
except ImportError as exc:
    print("PySide2 不可用:", exc)
    raise SystemExit(1)

print("PySide2:", PySide2.__version__)
print("Qt 运行时:", QtCore.qVersion())
print()

checks = []


def check(label, func):
    try:
        value = func()
        checks.append((True, label, repr(value)[:60]))
    except Exception as exc:  # noqa: BLE001
        checks.append((False, label, f"{type(exc).__name__}: {exc}"))


# --- 1. QAction / QShortcut 在哪个模块 ---
check("from QtGui import QAction", lambda: __import__("PySide2.QtGui", fromlist=["QAction"]).QAction)
check("from QtWidgets import QAction", lambda: QtWidgets.QAction)
check("QtGui.QShortcut", lambda: QtGui.QShortcut)
check("QtWidgets.QShortcut", lambda: QtWidgets.QShortcut)
check("QtGui.QDesktopServices", lambda: QtGui.QDesktopServices)

# --- 2. 完全限定枚举（PySide6 的写法）---
check("Qt.AlignmentFlag.AlignCenter", lambda: Qt.AlignmentFlag.AlignCenter)
check("Qt.AlignmentFlag.AlignVCenter", lambda: Qt.AlignmentFlag.AlignVCenter)
check("Qt.ItemDataRole.UserRole", lambda: Qt.ItemDataRole.UserRole)
check("Qt.ItemDataRole.TextAlignmentRole", lambda: Qt.ItemDataRole.TextAlignmentRole)
check("Qt.ItemFlag.ItemIsEditable", lambda: Qt.ItemFlag.ItemIsEditable)
check("Qt.Orientation.Horizontal", lambda: Qt.Orientation.Horizontal)
check("Qt.TextElideMode.ElideRight", lambda: Qt.TextElideMode.ElideRight)
check("Qt.TextFormat.RichText", lambda: Qt.TextFormat.RichText)
check("Qt.TextInteractionFlag.TextSelectableByMouse", lambda: Qt.TextInteractionFlag.TextSelectableByMouse)
check("Qt.CursorShape.PointingHandCursor", lambda: Qt.CursorShape.PointingHandCursor)
check("Qt.ScrollBarPolicy.ScrollBarAlwaysOff", lambda: Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

# --- 3. 控件的枚举 ---
check("QHeaderView.ResizeMode.Interactive", lambda: QtWidgets.QHeaderView.ResizeMode.Interactive)
check("QAbstractItemView.SelectionBehavior.SelectRows", lambda: QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
check("QAbstractItemView.EditTrigger.NoEditTriggers", lambda: QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
check("QAbstractItemView.SelectionMode.SingleSelection", lambda: QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
check("QSizePolicy.Policy.Expanding", lambda: QtWidgets.QSizePolicy.Policy.Expanding)
check("QFrame.Shape.NoFrame", lambda: QtWidgets.QFrame.Shape.NoFrame)
check("QToolButton.ToolButtonPopupMode.InstantPopup", lambda: QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
check("QDialogButtonBox.StandardButton.Ok", lambda: QtWidgets.QDialogButtonBox.StandardButton.Ok)
check("QMessageBox.StandardButton.Yes", lambda: QtWidgets.QMessageBox.StandardButton.Yes)
check("QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon",
      lambda: QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
check("QStyle.StandardPixmap.SP_MediaPlay", lambda: QtWidgets.QStyle.StandardPixmap.SP_MediaPlay)
check("QFont.StyleHint.Monospace", lambda: QtGui.QFont.StyleHint.Monospace)
check("QDialog.DialogCode.Accepted", lambda: QtWidgets.QDialog.DialogCode.Accepted)

# --- 4. Qt5 的短形式（若全限定不可用，需要退回这些）---
check("Qt.AlignCenter (短形式)", lambda: Qt.AlignCenter)
check("QHeaderView.Interactive (短形式)", lambda: QtWidgets.QHeaderView.Interactive)
check("QFont.Monospace (短形式)", lambda: QtGui.QFont.Monospace)

# --- 5. exec / exec_ ---
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([sys.argv[0], "-platform", "offscreen"])
dlg = QtWidgets.QDialog()
check("QDialog.exec()", lambda: hasattr(dlg, "exec"))
check("QDialog.exec_()", lambda: hasattr(dlg, "exec_"))
check("QApplication.exec()", lambda: hasattr(app, "exec"))
check("QApplication.exec_()", lambda: hasattr(app, "exec_"))

# --- 6. 实际创建控件，验证 setStyleSheet / QAction 挂菜单 ---
def make_widgets():
    w = QtWidgets.QWidget()
    label = QtWidgets.QLabel("中文测试")
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    table = QtWidgets.QTableWidget(1, 2)
    table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
    table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Interactive)
    action = QtWidgets.QAction("测试", w)
    action.setShortcut("Ctrl+L")
    font = QtGui.QFont("monospace")
    font.setStyleHint(QtGui.QFont.StyleHint.Monospace)
    return w.sizeHint()


check("实际创建控件（枚举+样式）", make_widgets)

# --- 7. 风格与字体（main.py 里用到）---
check("app.setStyle('Fusion')", lambda: app.setStyle("Fusion"))
check("QApplication.setFont", lambda: app.setFont(QtGui.QFont("DejaVu Sans", 9)))

print("=" * 78)
ok = sum(1 for passed, _, _ in checks if passed)
for passed, label, detail in checks:
    print(f"[{'OK  ' if passed else 'FAIL'}] {label:<52} {detail}")
print("=" * 78)
print(f"通过 {ok}/{len(checks)}")

# 给出推荐写法
print()
print("结论：", end="")
if all(p for p, lbl, _ in checks if lbl.startswith("Qt.AlignmentFlag")):
    print("PySide2 支持完全限定枚举，代码里的 Qt6 写法可直接复用。")
else:
    print("PySide2 不支持完全限定枚举，需要退回短形式或做映射。")
raise SystemExit(0 if ok == len(checks) else 2)
