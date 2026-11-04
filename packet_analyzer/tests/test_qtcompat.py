"""Qt 版本兼容层回归。

这里只验证与绑定无关的契约（模块归属、事件循环入口、枚举可用性），
不依赖具体是 PySide6 还是 PySide2——两边都应该通过。
"""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from packet_analyzer.ui import qtcompat  # noqa: E402


class BindingTests(unittest.TestCase):
    def test_binding_is_known(self):
        self.assertIn(qtcompat.binding_name(), ("PySide6", "PySide2"))
        self.assertIn(qtcompat.QT_MAJOR, (5, 6))

    def test_binding_matches_major_version(self):
        expected = "PySide6" if qtcompat.QT_MAJOR >= 6 else "PySide2"
        self.assertEqual(qtcompat.binding_name(), expected)

    def test_platform_note_mentions_version(self):
        note = qtcompat.platform_note()
        self.assertIn(qtcompat.binding_name(), note)
        self.assertIn(qtcompat.QT_VERSION, note)

    def test_qaction_comes_from_correct_module(self):
        """Qt6 在 QtGui，Qt5 在 QtWidgets —— 这是两版最主要的差异。"""
        module_name = qtcompat.QAction.__module__
        if qtcompat.QT_MAJOR >= 6:
            self.assertTrue(module_name.startswith("PySide6.QtGui"), module_name)
        else:
            self.assertTrue(module_name.startswith("PySide2.QtWidgets"), module_name)

    def test_qshortcut_from_correct_module(self):
        module_name = qtcompat.QShortcut.__module__
        if qtcompat.QT_MAJOR >= 6:
            self.assertTrue(module_name.startswith("PySide6.QtGui"), module_name)
        else:
            self.assertTrue(module_name.startswith("PySide2.QtWidgets"), module_name)


class EventLoopTests(unittest.TestCase):
    def test_run_app_prefers_exec_then_fallback(self):
        class FakeApp:
            def __init__(self, name):
                self.name = name
                self.called = 0

            def exec(self):  # noqa: A003 - 模拟 Qt 的命名
                self.called += 1
                return 7

        class OldQtApp:
            def __init__(self):
                self.called = 0

            def exec_(self):
                self.called += 1
                return 9

        modern = FakeApp("exec")
        self.assertEqual(qtcompat.run_app(modern), 7)
        self.assertEqual(modern.called, 1)

        legacy = OldQtApp()
        self.assertEqual(qtcompat.run_app(legacy), 9)
        self.assertEqual(legacy.called, 1)

    def test_run_app_raises_without_any_entry(self):
        class Broken:
            pass

        with self.assertRaises(RuntimeError):
            qtcompat.run_app(Broken())


class EnumCompatibilityTests(unittest.TestCase):
    """界面代码全程使用全限定枚举，两个版本都必须支持。"""

    def test_fully_qualified_enums_available(self):
        Qt = qtcompat.Qt  # noqa: N806 - 与 Qt 官方命名保持一致
        checks = [
            Qt.AlignmentFlag.AlignCenter,
            Qt.ItemDataRole.UserRole,
            Qt.ItemRole if hasattr(Qt, "ItemRole") else Qt.ItemDataRole.DisplayRole,
            Qt.Orientation.Horizontal,
            Qt.TextElideMode.ElideRight,
            Qt.ItemFlag.ItemIsEditable,
        ]
        self.assertEqual(len(checks), 6)

    def test_widget_enums_available(self):
        checks = [
            qtcompat.QHeaderView.ResizeMode.Interactive,
            qtcompat.QHeaderView.ResizeMode.Stretch,
            qtcompat.QAbstractItemView.SelectionBehavior.SelectRows,
            qtcompat.QAbstractItemView.EditTrigger.NoEditTriggers,
            qtcompat.QSizePolicy.Policy.Expanding,
            qtcompat.QFrame.Shape.NoFrame,
            qtcompat.QDialog.DialogCode.Accepted,
            qtcompat.QStyle.StandardPixmap.SP_MediaPlay,
            qtcompat.QFont.StyleHint.Monospace,
        ]
        self.assertEqual(len(checks), 9)

    def test_core_symbols_exported(self):
        for name in ("QWidget", "QApplication", "QTableWidget", "QAction", "Signal", "Qt"):
            self.assertTrue(hasattr(qtcompat, name), f"缺少 {name}")

    def test_high_dpi_is_noop_on_qt6(self):
        # Qt6 默认开启高 DPI，这里只要求不抛异常
        qtcompat.enable_high_dpi()


class UiModuleImportTests(unittest.TestCase):
    """界面模块必须只通过兼容层拿 Qt 符号，不能再直接 import PySide6。"""

    UI_FILES = ("main_window.py", "dialogs.py", "widgets.py", "message_model.py", "detail_view.py")

    def test_ui_modules_never_import_binding_directly(self):
        offenders = []
        for name in self.UI_FILES:
            text = (ROOT / "ui" / name).read_text(encoding="utf-8")
            if "from PySide6" in text or "from PySide2" in text:
                offenders.append(name)
        self.assertEqual(offenders, [], f"这些文件应改用 qtcompat：{offenders}")

    def test_entry_point_uses_compat(self):
        text = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertNotIn("from PySide6", text)
        self.assertIn("qtcompat", text)

    def test_test_scripts_use_compat(self):
        for name in ("ui_smoke.py", "ui_flows.py"):
            text = (ROOT / "tests" / name).read_text(encoding="utf-8")
            self.assertNotIn("from PySide6", text, f"{name} 还直接引用了 PySide6")


if __name__ == "__main__":
    unittest.main(verbosity=2)
