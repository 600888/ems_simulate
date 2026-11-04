"""Qt 版本兼容层：同一份界面代码同时跑 PySide6(Qt6) 与 PySide2(Qt5)。

为什么需要它：老 Linux 服务器（glibc 2.19）装不了 Qt6，只能退回 Qt5。
实测 PySide2 5.15.2 与 PySide6 的差异只有两处（已用 scripts/probe_pyside2.py 证实）：

1. ``QAction`` / ``QShortcut`` 在 Qt6 属于 ``QtGui``，在 Qt5 属于 ``QtWidgets``
2. ``QApplication.exec()`` 是 Qt6 才有的名字，Qt5 只有 ``exec_()``

其余**完全一致**，包括 ``Qt.AlignmentFlag.AlignCenter`` 这类全限定枚举、
``QFont.StyleHint.Monospace``、``QStyle.StandardPixmap.SP_MediaPlay``，
所以界面代码里的枚举写法不用改。

界面模块统一从这里导入，不再直接 ``from PySide6...``。
"""

from __future__ import annotations

from contextlib import suppress
import sys

try:  # 优先 Qt6
    from PySide6 import QtCore, QtGui, QtWidgets
    from PySide6.QtCore import *  # noqa: F403
    from PySide6.QtGui import *  # noqa: F403
    from PySide6.QtWidgets import *  # noqa: F403

    QT_MAJOR = 6
    QT_VERSION = QtCore.qVersion()
    _BINDING = "PySide6"
except ImportError:  # 退回 Qt5
    try:
        from PySide2 import QtCore, QtGui, QtWidgets  # noqa: F401
        from PySide2.QtCore import *  # noqa: F403
        from PySide2.QtGui import *  # noqa: F403
        from PySide2.QtWidgets import *  # noqa: F403

        QT_MAJOR = 5
        QT_VERSION = QtCore.qVersion()
        _BINDING = "PySide2"
    except ImportError as exc:  # pragma: no cover - 环境缺失时给出可操作提示
        raise ImportError(
            "未找到 Qt 绑定。请安装 PySide6（Qt6，需 glibc ≥ 2.28）"
            "或 PySide2（Qt5，兼容 glibc 2.17+）：\n"
            "    pip install PySide6\n"
            "    pip install PySide2==5.15.2.1   # 老系统\n"
        ) from exc

# QAction / QShortcut 的归属模块随 Qt 大版本变化，这里统一暴露
if QT_MAJOR >= 6:
    from PySide6.QtGui import QAction, QShortcut  # noqa: F401
else:
    from PySide2.QtWidgets import QAction, QShortcut  # noqa: F401


def binding_name() -> str:
    """当前使用的绑定名，用于「关于」对话框与自检输出。"""
    return _BINDING


def run_app(app: QtWidgets.QApplication) -> int:
    """进入事件循环。Qt6 用 exec()，Qt5 只有 exec_()。"""
    runner = getattr(app, "exec", None) or getattr(app, "exec_", None)
    if runner is None:  # pragma: no cover - 理论上不会发生
        raise RuntimeError("当前 Qt 绑定既没有 exec() 也没有 exec_()")
    return int(runner())


def enable_high_dpi() -> None:
    """Qt5 需要显式开启高 DPI 缩放；Qt6 默认已开启，无需处理。"""
    if QT_MAJOR >= 6:
        return
    for attribute_name in ("AA_EnableHighDpiScaling", "AA_UseHighDpiPixmaps"):
        attribute = getattr(QtCore.Qt, attribute_name, None)
        if attribute is not None:
            with suppress(AttributeError, RuntimeError):
                QtWidgets.QApplication.setAttribute(attribute, True)


def platform_note() -> str:
    """一行环境说明，写进自检输出便于排查。"""
    return f"{_BINDING} (Qt {QT_VERSION}) on {sys.platform}"
