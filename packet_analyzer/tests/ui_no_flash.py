"""防止「切换报文时满屏/瞬时弹窗闪烁」这个 bug 回退。（Qt5 / Linux 分支）

有两类成因，本测试都要守住：

1. **滞留型**：清理详情面板时对可见控件调用 ``setParent(None)``，Qt 会立刻把它
   变成顶级窗口；``deleteLater()`` 要等回到事件循环才销毁，中间的帧里这些控件
   作为无边框独立窗口留在屏幕上。60 多个控件同时如此 → 满屏闪烁。

2. **瞬时型**（更难发现）：控件刚构造、还没 addWidget 时没有父级，此时
   ``setVisible(True)`` 会直接让它成为一个可见的顶级窗口。随后它被重新认父，
   屏幕上一闪而过——只在"稳定时刻"采样 topLevelWidgets() 根本抓不到。

因此本测试做两层断言：
  · 采样顶级可见窗口数量（防滞留型），正常恒为 1（只有主窗口）
  · 监听 Show/Polish 事件（防瞬时型），只要事件发生时 isWindow() 为真就失败
"""

import ast
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from packet_analyzer.main import DEMO_FRAMES  # noqa: E402
from packet_analyzer.ui.main_window import MainWindow  # noqa: E402
from packet_analyzer.ui.qtcompat import QApplication, QEvent, QObject, QWidget  # noqa: E402

MAX_TOP_LEVEL = 1  # 只允许主窗口


class TransientWindowWatcher(QObject):
    """捕获任何一瞬间变成"窗口"的控件。

    只看某一时刻的 topLevelWidgets() 是不够的：控件可能在同一个事件循环迭代里
    先变成可见的顶级窗口、随后又被 addWidget 重新认父，采样根本抓不到，但屏幕上
    确实闪了一下。这里监听 Show/Polish 事件，只要事件发生时 isWindow() 为真就记账。
    """

    def __init__(self) -> None:
        super().__init__()
        self.hits: list[tuple[str, str]] = []

    def reset(self) -> None:
        self.hits.clear()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - Qt 命名
        is_window_event = event.type() in (QEvent.Type.Show, QEvent.Type.Polish)
        if (
            is_window_event
            and isinstance(obj, QWidget)
            and obj.isWindow()
            and type(obj).__name__ != "MainWindow"  # 主窗口本身当然会显示
        ):
            self.hits.append((type(obj).__name__, obj.windowTitle()))
        return False


def visible_top_level() -> list[QWidget]:
    return [w for w in QApplication.topLevelWidgets() if w.isVisible()]


def main() -> int:
    app = QApplication([sys.argv[0], "-platform", "offscreen"])
    watcher = TransientWindowWatcher()
    app.installEventFilter(watcher)

    window = MainWindow()
    window.resize(1440, 880)
    window.show()
    app.processEvents()

    failures: list[str] = []

    def check(ok: bool, message: str) -> None:
        print(("PASS " if ok else "FAIL ") + message)
        if not ok:
            failures.append(message)

    def assert_no_extra_window(tag: str) -> None:
        tops = visible_top_level()
        names = [type(w).__name__ for w in tops if type(w).__name__ != "MainWindow"]
        check(
            len(tops) <= MAX_TOP_LEVEL,
            f"{tag}：顶级可见窗口 {len(tops)} 个（应在 {MAX_TOP_LEVEL} 以内）"
            + (f"，多出：{names[:5]}" if names else ""),
        )

    assert_no_extra_window("初始")

    for key, field, role in DEMO_FRAMES:
        window.load_sample(key, field, role)
    app.processEvents()
    assert_no_extra_window("载入 10 条样例后")

    model = window.model
    check(model.rowCount() == len(DEMO_FRAMES), f"表格行数 = {model.rowCount()}")

    # 逐行切换（等价于用户连续点击报文）
    # 这里同时检查"瞬时闪现"：只看采样点会漏掉一闪而过的顶层窗口
    watcher.reset()
    for row in range(model.rowCount()):
        window.table.selectRow(row)
        app.processEvents()
    assert_no_extra_window("逐行切换一遍后")
    check(
        not watcher.hits,
        f"逐行切换期间没有控件短暂变成窗口（捕获 {len(watcher.hits)} 次）"
        + (f"，如：{watcher.hits[:5]}" if watcher.hits else ""),
    )

    # 反复切换，确认没有控件泄漏
    widget_count_after_first = len(window.findChildren(QWidget))
    watcher.reset()
    for _ in range(3):
        for row in range(model.rowCount()):
            window.table.selectRow(row)
            app.processEvents()
    assert_no_extra_window("反复切换 3 轮后")
    check(
        not watcher.hits,
        f"反复切换期间没有控件短暂变成窗口（捕获 {len(watcher.hits)} 次）",
    )

    widget_count = len(window.findChildren(QWidget))
    check(
        abs(widget_count - widget_count_after_first) <= 5,
        f"控件数量稳定（{widget_count_after_first} → {widget_count}），无泄漏",
    )

    # 清空 -> 占位提示，也不能留下窗口
    window.table.clearSelection()
    window.detail.show_placeholder()
    app.processEvents()
    assert_no_extra_window("清空选择后")

    # 直接检查实现：setParent(None) 一旦回来，这个 bug 就会复发。
    # 用 AST 而不是字符串匹配——注释与文档里说明"不要用 setParent(None)"不算违规。
    def set_parent_calls(path: Path) -> list[int]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        return [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "setParent"
        ]

    # 用已加载模块的 __file__ 定位源码，不靠相对路径推导：
    # 测试被复制到别处运行时（如部署包里 tests/ 与 packet_analyzer/ 同级），
    # 相对路径会指向错误的目录，导致检查静默失效。
    import packet_analyzer.ui.detail_view as detail_module
    import packet_analyzer.ui.widgets as widgets_module

    detail_path = Path(detail_module.__file__)
    widgets_path = Path(widgets_module.__file__)
    detail_lines = set_parent_calls(detail_path)
    widgets_lines = set_parent_calls(widgets_path)
    check(not detail_lines, f"detail_view 不再调用 setParent（发现于行 {detail_lines}）")
    check(not widgets_lines, f"widgets.py 不再调用 setParent（发现于行 {widgets_lines}）")

    detail_source = detail_path.read_text(encoding="utf-8")
    check("widget.hide()" in detail_source, "detail_view._clear 会先 hide()")
    check(
        "sendPostedEvents" in detail_source,
        "销毁后主动派发 DeferredDelete，避免待删控件堆积",
    )

    print()
    if failures:
        print(f"失败项：{len(failures)}")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("失败项：0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
