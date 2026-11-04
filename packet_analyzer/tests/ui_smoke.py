"""界面结构与布局自检（离屏运行，不依赖显示器）。

用法：
    QT_QPA_PLATFORM=offscreen python packet_analyzer/tests/ui_smoke.py
"""

from __future__ import annotations

import os
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QLabel, QTableWidget, QTreeWidget  # noqa: E402

from packet_analyzer.main import DEMO_FRAMES, build_application  # noqa: E402
from packet_analyzer.ui.detail_view import DetailPanel  # noqa: E402
from packet_analyzer.ui.main_window import MainWindow  # noqa: E402

failures: list[str] = []
QSettings("EMS", "PacketAnalyzer").clear()


def check(condition: bool, message: str) -> None:
    print(("PASS " if condition else "FAIL ") + message)
    if not condition:
        failures.append(message)


def section_titles(panel: DetailPanel) -> list[str]:
    return [label.text() for label in panel._content.findChildren(QLabel) if label.text()]


app, _args = build_application([])
window = MainWindow()
# 离屏平台屏幕尺寸很小，restoreGeometry 会把窗口压缩；显式指定尺寸后再校验布局
window.resize(1440, 880)
window.show()
for key, field, role in DEMO_FRAMES:
    window.load_sample(key, field, role)
app.processEvents()
window.resize(1440, 880)
app.processEvents()

check(window.model.rowCount() == len(DEMO_FRAMES), f"表格行数 = {window.model.rowCount()}（期望 {len(DEMO_FRAMES)}）")
check(window.model.columnCount() == 8, f"表格列数 = {window.model.columnCount()}")
check(window.table.horizontalScrollBar().maximum() == 0, "报文列表无横向滚动条")

titles = " | ".join(section_titles(window.detail))
for expected in ("概要", "原始报文", "字段解析", "数据对象"):
    check(expected in titles, f"详情包含「{expected}」小节")

# 当前选中的是 DNP3 响应帧，应有 4 个数据对象与一条请求关联
detail = window.store.detail(window.store.records[-1].sequence)
check(detail.get("protocol_key") == "dnp3", f"当前详情协议 = {detail.get('protocol_key')}")
check(len(detail.get("objects") or []) == 4, f"数据对象数 = {len(detail.get('objects') or [])}")
check(detail.get("correlation") is not None, "DNP3 响应已关联到请求帧")

field_tables = window.detail._content.findChildren(QTableWidget)
check(bool(field_tables), f"找到字段表格 {len(field_tables)} 个")
for table in field_tables:
    check(table.horizontalScrollBar().maximum() == 0, f"字段表格无横向滚动条（列宽 {table.width()}）")

trees = window.detail._content.findChildren(QTreeWidget)
check(bool(trees), "找到数据对象树")
for tree in trees:
    check(tree.horizontalScrollBar().maximum() == 0, f"对象树无横向滚动条（宽度 {tree.width()}）")
    check(tree.topLevelItemCount() == 4, f"对象树顶层节点 = {tree.topLevelItemCount()}")

content = window.detail.widget()
check(content.width() <= window.detail.viewport().width() + 2, "详情内容宽度适配视口")
check(content.height() > 600, f"详情内容高度 = {content.height()}")

# 字节高亮联动：点击字段行后高亮区间应生效
table = field_tables[0]
if table.rowCount():
    table.itemClicked.emit(table.item(0, 0))
    app.processEvents()
    strip = getattr(window.detail._last_raw_wrapper, "_byte_strip", None)
    check(strip is not None and strip._highlight is not None, "字段行点击后字节高亮生效")

path = ROOT / "_ui_smoke.png"
window.grab().save(str(path))
size = window.size()
check(size.width() == 1440 and size.height() == 880, f"窗口尺寸 = {size.width()}x{size.height()}")

# 像素抽样：确认主色按钮、深色报文区和成功横幅都真正绘制出来
image = window.grab().toImage()
counts = {"dark": 0, "primary": 0, "banner": 0}
for y in range(0, image.height(), 4):
    for x in range(0, image.width(), 4):
        color = image.pixelColor(x, y)
        red, green, blue = color.red(), color.green(), color.blue()
        if red + green + blue < 150:
            counts["dark"] += 1
        if abs(red - 64) < 26 and abs(green - 158) < 26 and abs(blue - 255) < 26:
            counts["primary"] += 1
        if abs(red - 240) < 6 and abs(green - 249) < 6 and abs(blue - 235) < 6:
            counts["banner"] += 1
check(counts["dark"] > 1500, f"深色报文区已绘制（dark={counts['dark']}）")
check(counts["primary"] > 90, f"主色按钮已绘制（primary={counts['primary']}）")
check(counts["banner"] > 80, f"解析通过横幅已绘制（banner={counts['banner']}）")
print(f"截图：{path}")

# 切换到其它协议验证渲染不崩溃
for key, field, role in DEMO_FRAMES:
    window.load_sample(key, field, role)
    app.processEvents()
check(window.model.rowCount() == len(DEMO_FRAMES) * 2, "重复载入样例后行数正确")

window.close()
QSettings("EMS", "PacketAnalyzer").clear()
print()
print(f"失败项：{len(failures)}")
for item in failures:
    print(f"  - {item}")
raise SystemExit(1 if failures else 0)
