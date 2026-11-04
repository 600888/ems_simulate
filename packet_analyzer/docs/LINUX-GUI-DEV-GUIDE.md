# Linux 服务器 Python GUI 开发与离线部署指南

面向场景：**目标机不能上网、glibc 较老、系统 Python 版本很低**，但你要在上面开发/部署
Python 图形程序。本文所有结论都在 `192.168.235.144` 上实测过，不是理论推演。

> **路径约定**：下文所有 `scripts/...`、`ui/...` 均相对于 `packet_analyzer/` 目录。
> 模板可直接拷贝到新项目里用（`bundle_gui_app.py` 与项目结构无关）。
> 下载缓存默认落在**当前工作目录的 `cache/`**，可用 `CACHE_DIR=...` 改。

---

## 0. 先看结论

| 问题 | 答案 |
| --- | --- |
| 能装系统的 Python 3.10 吗 | 不能（apt 只有 3.4），但**不需要**——用便携 Python |
| 图形界面能用 Qt 吗 | 能，但只能用 **Qt5（PySide2）**，Qt6 要求 glibc ≥ 2.28 |
| 需要 root 吗 | 部署不需要；只有抓包这类特权操作才要 |
| 需要联网吗 | 部署时不需要。依赖在开发机下好，打进包里 |
| 包多大 | 纯命令行 26MB；带 Qt5 图形界面 59MB（压缩后） |

本机（144）实测基线：

```
系统      Linx GNU/Linux 6.0.80 (jessie)，基于 Debian 8
内核      4.9.0-8-linx-security-amd64
glibc     2.19                    ← 决定 Qt6 不可用
libstdc++ GLIBCXX_3.4.24          ← Qt5.15 需要 3.4.21，够
Python    3.4.2（无 pip、无 dataclasses）
libpcap   1.6.2
图形      Xorg + lightdm，ess 用户在 :0 有桌面会话
locale    zh_CN.GBK               ← 会导致中文乱码，见第 9 节
```

---

## 1. 第一步永远是环境勘察

不要先写代码。先花两分钟把这几个数字拿到，后面所有选型都由它们决定。

```bash
# 一次跑完，把输出存下来
{
  echo "== 系统 ==";  cat /etc/os-release | head -3; uname -r
  echo "== glibc =="; ldd --version | head -1
  echo "== 架构 ==";  uname -m
  echo "== Python =="; for p in python3 python3.8 python3.10 python3.11; do
      command -v $p >/dev/null && echo "  $p -> $($p -V 2>&1)"; done
  echo "== libstdc++ =="; strings /usr/lib/x86_64-linux-gnu/libstdc++.so.6 2>/dev/null \
      | grep -o 'GLIBCXX_3\.4\.[0-9]*' | sort -u -V | tail -1
  echo "== 图形 =="; echo "  DISPLAY=$DISPLAY"; ls /tmp/.X11-unix 2>/dev/null
  echo "== locale =="; echo "  LANG=$LANG"
  echo "== 系统 Qt =="; ls /usr/lib/x86_64-linux-gnu/libQt5Core.so.5* 2>/dev/null || echo "  无"
} 2>&1 | tee env-report.txt
```

### 判读表

| 参数 | 含义 | 影响 |
| --- | --- | --- |
| glibc **≥ 2.28** | 较新的发行版（Debian 10+/Ubuntu 20.04+） | 可用 PySide6（Qt6），最省事 |
| glibc **2.17 ~ 2.27** | Debian 8/9、CentOS 7 | 只能 PySide2（Qt5），本文重点 |
| glibc < 2.17 | 极老系统 | 只能用 Tkinter 或自行编译 Qt4 |
| 系统 Python ≥ 3.10 | — | 可直接用，但仍建议便携版以免污染系统 |
| 系统 Python < 3.10 | 常见 3.4/3.6 | 必须带便携 Python |
| 系统有 `libQt5Core.so.5.3` | Qt5.3 很老 | 必须让包内 Qt 优先，否则符号冲突 |
| `LANG=*.GBK` | 非 UTF-8 locale | 输出会乱码，见第 9 节 |

> ⚠️ `ldconfig -p` 在普通用户下可能没有输出（PATH 里没有 /sbin），
> 判断库是否存在请直接 `ls /usr/lib/x86_64-linux-gnu/libXXX`，别被假阴性误导。

---

## 2. 选型：Qt 版本与 Python 版本

### 2.1 Qt 版本由 glibc 决定

| 方案 | 要求 | 适用 | 代价 |
| --- | --- | --- | --- |
| **PySide6（Qt6）** | glibc ≥ 2.28 | 新机器 | 无 |
| **PySide2（Qt5.15）** | glibc ≥ 2.17，libstdc++ ≥ 3.4.21 | 老机器 | 包多 33MB；Qt6 的少数新 API 不可用 |
| Tkinter | 便携 Python 自带 | 界面简单时 | 控件少、样式朴素 |

**关键约束：PySide2 的 abi3 wheel 只到 cp310。**
Python 3.11 / 3.12 **没有** Qt5 绑定。所以"老系统 + 图形界面"这条路锁定 Python 3.10。

### 2.2 Python 版本：最低 3.10

不是偏好问题，是硬性依赖。`dataclasses` 的 `slots=True` 参数是 **3.10** 才加的，
3.9 上会直接报：

```
TypeError: dataclass() got an unexpected keyword argument 'slots'
```

其他常见下限：

| 特性 | 最低版本 |
| --- | --- |
| `dataclass(slots=True)` | 3.10 |
| 结构化模式匹配 `match` | 3.10 |
| 内置泛型 `list[int]` 注解 | 3.9 |
| `except*` / `tomllib` / `StrEnum` | 3.11 |

**推荐 3.10**：既能用 Qt5 图形，又不需要 3.11 的新语法。

### 2.3 让代码同时兼容两个 Qt 版本

不要维护两套 UI 代码。实测 PySide2 5.15 **完全支持全限定枚举**
（`Qt.AlignmentFlag.AlignCenter`、`QStyle.StandardPixmap.SP_MediaPlay` 等），
Qt5/Qt6 的真实差异只有两处：

| 差异 | Qt6 | Qt5 |
| --- | --- | --- |
| `QAction` / `QShortcut` | `QtGui` | `QtWidgets` |
| `QApplication.exec()` | 有 | 只有 `exec_()` |

所以只需要一个 30 行的兼容模块。可直接拷 `packet_analyzer/ui/qtcompat.py`，核心逻辑：

```python
# compat.py
try:                                    # 优先 Qt6
    from PySide6 import QtCore, QtGui, QtWidgets
    from PySide6.QtCore import *
    from PySide6.QtGui import *
    from PySide6.QtWidgets import *
    QT_MAJOR = 6
except ImportError:                     # 退回 Qt5
    from PySide2 import QtCore, QtGui, QtWidgets
    from PySide2.QtCore import *
    from PySide2.QtGui import *
    from PySide2.QtWidgets import *
    QT_MAJOR = 5

if QT_MAJOR >= 6:
    from PySide6.QtGui import QAction, QShortcut
else:
    from PySide2.QtWidgets import QAction, QShortcut


def run_app(app):
    """Qt6 有 exec()，Qt5 只有 exec_()。"""
    return int((getattr(app, "exec", None) or app.exec_)())


def enable_high_dpi():
    """Qt5 需显式开启高 DPI；Qt6 默认已开，这里是空操作。"""
    if QT_MAJOR >= 6:
        return
    for name in ("AA_EnableHighDpiScaling", "AA_UseHighDpiPixmaps"):
        attr = getattr(QtCore.Qt, name, None)
        if attr is not None:
            QtWidgets.QApplication.setAttribute(attr, True)
```

**两条铁律**（违反就会在某个版本上炸）：

1. 界面代码**只从 compat 导入**，绝不出现 `from PySide6 import ...`
2. `run_app(app)` 替代 `app.exec()`；`QAction` 从 compat 拿

可以加一条测试守住第 1 条：

```python
def test_no_direct_binding_import():
    for py in Path("myapp").rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        assert "from PySide6" not in text, f"{py} 应改用 compat"
```

---

## 3. 便携 Python：为什么不装系统的

| | 系统 Python | 便携 Python |
| --- | --- | --- |
| 版本 | 3.4（改不了） | 3.10 / 3.11 / 3.12 任选 |
| 装法 | apt，需要 root | 解压，不需要 root |
| 影响系统 | 会（升级可能坏依赖） | 无，全在目录内 |
| 离线 | 需要配 apt 源 | 一个 tar.gz 带走 |

便携版来自 **python-build-standalone**（astral-sh 维护），面向 **glibc 2.17+** 构建，
在 Debian 8 上实测可用。文件名格式：

```
cpython-3.10.14+20240726-x86_64-unknown-linux-gnu-install_only.tar.gz
        └版本┘ └发布标签┘                    └变体┘
```

- `install_only` 变体 = 解压即用的完整 CPython（含 `bin/python3`、标准库、`tkinter`）
- 下载地址：`https://github.com/astral-sh/python-build-standalone/releases`

### 3.1 下载

```bash
# 方式一：一条命令备齐所有依赖（推荐）
bash scripts/templates/fetch_offline_deps.sh
#   → cache/python310.tar.gz
#   → cache/wheels/PySide2-*.whl, shiboken2-*.whl
#   → cache/libdbus-1.so.3

# 方式二：只下 Python（纯命令行程序够用）
bash scripts/templates/fetch_offline_deps.sh --no-qt
```

GitHub 直连慢的话：

```bash
HTTPS_PROXY=http://127.0.0.1:7890 bash scripts/templates/fetch_offline_deps.sh
```

实在下不动就用浏览器手动下载上面的 URL，改名后放进 `cache/` 目录。

### 3.2 传到服务器（三种方式）

```bash
# A. scp（最常规）
scp cache/python310.tar.gz ess@192.168.235.144:~/

# B. 管道直传（目标机没装 ssh 服务端工具、或只开了受限 shell 时）
cat cache/python310.tar.gz | ssh ess@192.168.235.144 'cat > ~/python310.tar.gz'

# C. U 盘中转（完全隔离的机器）
#    拷到 U 盘挂载后 cp，适合涉密环境
```

B 方式在 Git Bash 下很好用，注意**不要**加 `-t`/`-T` 之外的伪终端参数，否则二进制会被破坏。

### 3.3 验证是否能在目标机跑

```bash
mkdir -p ~/pyruntime && tar xzf python310.tar.gz -C ~/pyruntime --strip-components=1
~/pyruntime/bin/python3 -V
~/pyruntime/bin/python3 -c "import platform,sys; print(platform.libc_ver(), sys.version)"
```

能打印版本号就说明便携 Python 可用。若报 `GLIBC_2.xx not found`，说明构建版本太新，
换更早的发布标签（如 `PBS_TAG=20230726`）。

---

## 4. 备齐图形依赖（只有做 GUI 才需要）

### 4.1 PySide2 与 shiboken2

```bash
# 用镜像下（比官方快很多，且文件一致）
MIRROR=https://pypi.tuna.tsinghua.edu.cn/packages
# 具体路径让脚本从 PyPI 元数据解析，见 fetch_offline_deps.sh
```

两个包都要：`shiboken2` 是绑定层，`PySide2` 是 Qt 的 Python 接口。

### 4.2 libdbus：最容易漏的一个

Qt 5.15 的 `libQt5DBus.so.5` 需要 `LIBDBUS_1_3` 版本标记（dbus ≥ 1.10）。
Debian 8 自带 **1.8.14**，直接启动 xcb 会失败：

```
relocation error: libQt5DBus.so.5: symbol dbus_message_get_allow_interactive_authorization,
version LIBDBUS_1_3 not defined in file libdbus-1.so.3
```

解决：把较新的 `libdbus-1.so.3` 放进包内 Qt 库目录（**仅 335KB**）。
实测 Debian 11 的 1.12.28 可用。

```bash
# fetch_offline_deps.sh 已自动处理；手动方式：
curl -O http://deb.debian.org/debian/pool/main/d/dbus/libdbus-1-3_1.12.28-0+deb11u1_amd64.deb
ar x libdbus-1-3_1.12.28-0+deb11u1_amd64.deb && tar xf data.tar.*
cp lib/x86_64-linux-gnu/libdbus-1.so.3.19.17 cache/libdbus-1.so.3
```

替换系统库是**错误做法**（会连带影响整个桌面），务必只放进包内目录。

---

## 5. 打包成离线包

### 5.1 用通用打包器

`scripts/templates/bundle_gui_app.py` 与项目结构无关，任何 Python 包都能打：

```bash
python scripts/templates/bundle_gui_app.py \
    --app-dir ./myapp \
    --package myapp \
    --python-cache cache/python310.tar.gz \
    --qt5-wheels cache/wheels/shiboken2-*.whl cache/wheels/PySide2-*.whl \
    --libdbus cache/libdbus-1.so.3 \
    --title "我的工具" \
    --output dist/myapp-linux-x86_64.tar.gz
```

产物结构（解压即用，不需要目标机装任何东西）：

```
myapp-linux-x86_64/
├── myapp/                    # 你的源码（自动排除 __pycache__/tests/build）
├── python/                   # 便携 CPython 3.10（含标准库 + tkinter）
├── python/lib/python3.10/site-packages/PySide2/   # 裁剪后的 Qt5
├── run-gui.sh                # 图形版启动（自动生成）
└── run-cli.sh                # 命令行启动（指定 --cli-module 时生成）
```

参数速查：

| 参数 | 作用 |
| --- | --- |
| `--app-dir` | 源码目录，整体打包（自动跳过缓存/构建产物） |
| `--package` | 包名，启动时执行 `python -m <package>` |
| `--python-cache` | 便携 Python 的 tar.gz |
| `--qt5-wheels` | 提供则打图形包；不给就是纯命令行包 |
| `--libdbus` | 老系统必带，否则 xcb 起不来 |
| `--vendor` | 额外的纯 Python 依赖目录（如 `pydnp3_pure`） |
| `--cli-module` | 额外生成 `run-cli.sh` |
| `--extra` | 附带 README、配置样例等 |

### 5.2 为什么必须用 Python 的 tarfile 打包

这不是洁癖。**Windows 上 `chmod` 对 NTFS 常常静默失效**，用 shell + tar 打出来的包，
`python/bin/python3` 会丢掉可执行位，到 Linux 上就是：

```
错误：未找到 python/bin/python3
```

更隐蔽的是：`ls -l` 在 Windows 上看着"像"有权限（Git Bash 模拟），但 tar 记录的是 644。
用 `tarfile` 直接写 mode 才能保证跨平台一致。

同理，便携 Python 要**流式并入归档**（直接读原 tar 的成员再写出去），
不能"解压到磁盘再打包"——中间那一步就把权限丢了。

### 5.3 Qt5 裁剪：446MB → 167MB

完整 PySide2 装完 446MB，其中 362MB 是 Qt 库。你的程序通常只用到
`QtCore`/`QtGui`/`QtWidgets`，其余（QtWebEngine、Qt3D、QtQuick…）都是死重。

打包器的白名单：

```python
PYSIDE2_KEEP_SO = {"QtCore.abi3.so", "QtGui.abi3.so", "QtWidgets.abi3.so"}
QT_LIB_KEEP_PREFIXES = (
    "libQt5Core.so", "libQt5Gui.so", "libQt5Widgets.so",
    "libQt5XcbQpa.so", "libQt5DBus.so", "libQt5PrintSupport.so", "libQt5Svg.so",
    "libQt5Qml.so",      # ← Qt5Core 依赖它，删了就 ImportError
    "libQt5Network.so",  # ← 系统常是 Qt5.3，混用会符号不匹配
    "libicudata.so", "libicuuc.so", "libicui18n.so",
)
```

**两个必须保留的"看起来没用"的库**，都是踩过坑才知道的：

1. **`libQt5Qml.so`** — 明明没用 QML，但 Qt5Core 链式依赖它。删掉后连
   `import QtCore` 都失败：`ImportError: libQt5Qml.so.5: cannot open shared object file`
2. **`libQt5Network.so`** — 系统自带的是 Qt 5.3 版本，与包内 5.15 的 QtCore 混用会报
   `undefined symbol: _ZN15QIPAddressUtils8toStringER7QStringPh`

平台插件只留 `libqxcb.so`（真实显示）和 `libqoffscreen.so`（无显示环境自检）。

### 5.4 额外的 pip 依赖怎么带

除了 Qt，你的程序大概率还要 `requests`、`pandas`、`numpy` 之类。两条路：

**A. 纯 Python 包 → 用 `--vendor`**（简单，推荐）

```bash
# 在开发机上装到某个目录
pip install --target ./vendor requests

# 打进包（可给多个）
python scripts/templates/bundle_gui_app.py ... --vendor ./vendor/requests ./vendor/urllib3
```

**B. 带二进制扩展的包 → 用 pip 直接装进便携 Python**

便携 Python **自带 pip**（实测 3.10.14 内置 pip 24.1.2），所以可以离线装 wheel：

```bash
# 开发机上：下好 manylinux wheel
pip download --only-binary=:all: --platform manylinux2014_x86_64 \
    --python-version 310 --implementation cp --abi cp310 -d wheels/ numpy

# 目标机上：装进包内解释器
cd ~/apps/myapp
./python/bin/python3 -m pip install --no-index --find-links ~/wheels numpy
```

注意 wheel 的 tag 要匹配：`cp310` + `manylinux*_x86_64`。
`manylinux2014` 要求 glibc ≥ 2.17，本类机器可以用；
`manylinux_2_28` 就装不上（要 glibc 2.28）。

体积大的包（numpy/pandas 动辄几十 MB）建议先确认真的需要，
否则包会从 59MB 涨到 200MB 以上。

### 5.5 验证裁剪没剪坏

打完包一定在目标机跑一次离屏渲染，比自己肉眼检查靠谱：

```bash
QT_QPA_PLATFORM=offscreen ./run-gui.sh --screenshot /tmp/check.png
ls -l /tmp/check.png     # 有文件且 > 10KB 基本就是渲染成功
```

---

## 6. 部署到服务器

```bash
# 上传
scp dist/myapp-linux-x86_64.tar.gz ess@192.168.235.144:~/

# 解压（不需要 root）
ssh ess@192.168.235.144
mkdir -p ~/apps && tar xzf myapp-linux-x86_64.tar.gz -C ~/apps
cd ~/apps/myapp-linux-x86_64

# 验证
./run-cli.sh --selftest        # 如果你实现了自检（强烈建议）
./run-gui.sh --demo            # 图形界面
```

**建议每个工具都实现 `--selftest`**：无界面环境下跑一遍核心逻辑并返回非零退出码。
离线部署最怕"看起来装好了但某个功能静默降级"，自检是唯一能自动发现它的手段。

自检至少覆盖：

1. 每个功能模块各跑一次真实用例
2. **可选依赖是否真的存在**（缺了要让自检失败，而不是默默降级）
3. 运行环境打印（Python 版本、glibc、Qt 版本），出问题好排查

---

## 7. 启动脚本要点

打包器会自动生成 `run-gui.sh`，其核心是这几行：

```sh
DIR=$(cd "$(dirname "$0")" && pwd)
SP="$DIR/python/lib/python3.10/site-packages"
QT_LIB="$SP/PySide2/Qt/lib"

# 1) 包内 Qt 必须在最前！否则撞上系统 Qt5.3
LD_LIBRARY_PATH="$QT_LIB${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export LD_LIBRARY_PATH

# 2) 让 python -m 找得到你的包
PYTHONPATH="$SP:$DIR${PYTHONPATH:+:$PYTHONPATH}"

# 3) 没有 DISPLAY 时给人话提示，而不是抛 xcb 报错
if [ -z "$DISPLAY" ] && [ -z "$WAYLAND_DISPLAY" ] && [ -z "$QT_QPA_PLATFORM" ]; then
    echo "提示：当前没有 DISPLAY，无法弹出窗口。" >&2
    echo "  · 在服务器桌面上运行，或 ssh -X 转发显示" >&2
    exit 1
fi

exec "$DIR/python/bin/python3" -m myapp "$@"
```

三个细节：

- `$(dirname "$0")` 而不是相对路径 → 从任何目录都能启动
- 用 `${VAR:+:$VAR}` 拼接 → 用户已有 `LD_LIBRARY_PATH` 时不会被覆盖
- `exec` → 信号（Ctrl-C）能直达 Python 进程

### 7.1 桌面快捷方式

在服务器桌面上建图标（`~/.local/share/applications/myapp.desktop`）：

```ini
[Desktop Entry]
Type=Application
Name=我的工具
Comment=协议报文分析
Exec=/home/ess/apps/myapp-linux-x86_64/run-gui.sh
Icon=utilities-terminal
Terminal=false
Categories=Development;
```

```bash
chmod +x ~/.local/share/applications/myapp.desktop
update-desktop-database ~/.local/share/applications 2>/dev/null || true
```

### 7.2 远程使用

```bash
# X11 转发（慢但能用，适合偶尔看界面）
ssh -X ess@192.168.235.144
~/apps/myapp/run-gui.sh

# 更好：VNC（先装 tigervnc，桌面更流畅）
```

---

## 8. 排查手册

按症状查，都是实测遇到过的。

| 症状 | 原因 | 处理 |
| --- | --- | --- |
| `未找到 python/bin/python3` | 打包时丢了可执行位 | 用 `tarfile` 打包，别用 shell+tar（见 5.2） |
| `bad interpreter: /bin/sh^M` | shell 脚本被转成 CRLF | `.gitattributes` 加 `*.sh text eol=lf`，或 `sed -i 's/\r$//'` |
| `ImportError: libQt5Qml.so.5` | 裁剪时删多了 | 把 `libQt5Qml` 加回白名单 |
| `undefined symbol: ...QIPAddressUtils...` | 混用了系统 Qt5.3 | `LD_LIBRARY_PATH` 把包内 Qt 放最前 |
| `LIBDBUS_1_3 not defined` | 系统 dbus < 1.10 | 包内带 `libdbus-1.so.3`（见 4.2） |
| `could not connect to display` | 没有 `DISPLAY` | 在服务器桌面跑，或 `ssh -X` |
| `xcb plugin not found` | 缺平台插件 | 保留 `plugins/platforms/libqxcb.so` |
| 中文全是方块 | 缺中文字体 | `sudo apt install fonts-wqy-microhei` |
| 输出乱码 | locale 是 GBK | 见 9.1 |
| `UnicodeEncodeError: surrogates not allowed` | `python -c` 里带了中文 | 见 9.2 |
| `No module named xxx` | 依赖没打进包 | `--vendor` 加入，或检查 selftest 的可选依赖检查 |
| 包体积异常大 | 忘了裁剪 Qt | 见 5.3 |

---

## 9. 两个 locale 坑（GBK 系统必看）

老的中文发行版 `LANG` 常是 `zh_CN.GBK`，会引出两个很迷惑的问题。

### 9.1 输出到文件是乱码

GBK locale 下 Python 的 `sys.stdout.encoding` 是 `gbk`，重定向到文件后，
别的工具（Excel、编辑器）按 UTF-8 解就读成乱码。

程序启动时统一处理：

```python
import sys

_ASCII_LIKE = {"", "ascii", "ansi_x3.4-1968", "us-ascii", "646"}

def prepare_stdio() -> None:
    """重定向到文件/管道时强制 UTF-8；本地 GBK 终端保持原样。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            enc = (getattr(stream, "encoding", "") or "").lower()
            if not stream.isatty() or enc in _ASCII_LIKE:
                stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass
```

规则：**非终端 → UTF-8**（方便管道和文件）；**终端且能表示中文（GBK）→ 不动**
（这样你在服务器终端直接跑时中文仍然正常）。

### 9.2 脚本里 `python -c` 不能带中文

```bash
# 报错：UnicodeEncodeError: 'utf-8' codec can't encode character '\udcaf' ...
./python/bin/python3 -c "import platform; print('glibc:', platform.libc_ver())"
```

原因：命令行参数按 GBK 解码后再被重新编码，中文字节成了孤立的代理字符。

**规矩：写进脚本的 `python -c` 只用 ASCII。** 需要中文就：

```bash
# 方案 A：unicode 转义
./python/bin/python3 -c "print('\u4e2d\u6587')"

# 方案 B：写临时 .py 文件（推荐，可读性好）
cat > /tmp/probe.py <<'PY'
print("中文可以随便写")
PY
./python/bin/python3 /tmp/probe.py
```

---

## 10. 完整工作流（照着做）

```bash
# ── 开发机（Windows / Linux 都行）─────────────────────────
# 1. 备依赖（只需一次，之后缓存复用）
bash scripts/templates/fetch_offline_deps.sh

# 2. 写代码：界面只从 compat 导入
#    myapp/__init__.py, myapp/__main__.py, myapp/compat.py

# 3. 本地先跑通（装 PySide6 开发最舒服）
python -m myapp

# 4. 打包
python scripts/templates/bundle_gui_app.py \
    --app-dir ./myapp --package myapp \
    --python-cache cache/python310.tar.gz \
    --qt5-wheels cache/wheels/shiboken2-*.whl cache/wheels/PySide2-*.whl \
    --libdbus cache/libdbus-1.so.3 \
    --title "我的工具" --output dist/myapp.tar.gz

# ── 目标机 ────────────────────────────────────────────────
# 5. 上传解压
scp dist/myapp.tar.gz ess@192.168.235.144:~/
ssh ess@192.168.235.144
mkdir -p ~/apps && tar xzf myapp.tar.gz -C ~/apps && cd ~/apps/myapp

# 6. 验证（先离屏，再真实显示）
QT_QPA_PLATFORM=offscreen ./run-gui.sh --screenshot /tmp/check.png && ls -l /tmp/check.png
DISPLAY=:0 ./run-gui.sh --demo

# 7. 日常使用
./run-gui.sh
```

更新代码时**不用重传 Python 和 Qt**，只传源码目录即可：

```bash
scp -r myapp ess@192.168.235.144:~/apps/myapp/
```

---

## 附录 A：模板文件清单

| 文件 | 用途 |
| --- | --- |
| `scripts/templates/fetch_offline_deps.sh` | 一键下载 便携 Python + PySide2 wheel + libdbus |
| `scripts/templates/bundle_gui_app.py` | 通用打包器（跨平台，精确写权限位） |
| `ui/qtcompat.py` | Qt5/Qt6 兼容层（可直接拷贝） |
| `scripts/probe_pyside2.py` | 环境探测：一次性验证某台机器上哪些 Qt 用法可用 |

探测脚本的用法（换新机器时先跑它，避免靠猜）：

```bash
./python/bin/python3 scripts/probe_pyside2.py
# 输出每项用法的 OK / FAIL，最后给结论
```

## 附录 B：本机（192.168.235.144）实测记录

| 项目 | 结果 |
| --- | --- |
| 便携 CPython 3.10.14 | ✅ glibc 2.19 上正常运行 |
| 便携 CPython 3.9.19 | ❌ `dataclass(slots=True)` 不支持 |
| PySide2 5.15.2.1 导入 | ✅ 支持全限定枚举，界面代码零改动 |
| `QApplication.exec()` | ❌ 不存在，必须用 `exec_()` |
| 真实 X 显示（`:0`） | ✅ 成功开窗并截图 |
| tkinter（Tk 8.6） | ✅ 窗口可创建；⚠️ `tkfont.families()` 枚举不到中文字体族，中文显示需显式指定字号字体并验证 |
| 裁剪后 Qt5 | 446MB → 167MB（压缩后 59MB） |
| 图形包总大小 | 59MB（压缩）/ 186MB（解压） |
| 命令行包 | 26MB（压缩）/ 93MB（解压） |

## 附录 C：可选依赖必须显式检查

离线部署最容易出的事故不是"跑不起来"，而是**跑起来了但某个功能静默降级**。
例如缺 `pydnp3_pure` 时，DNP3 报文仍然"解析成功"，只是对象列表为空——
不报错、不崩溃，只是数据不对。

自检里要把这类依赖单独检查，并按严重程度分级：

```python
# (模块名, 用途, 缺失是否算失败)
OPTIONAL_DEPENDENCIES = (
    ("pydnp3_pure", "DNP3 对象解析", True),    # 缺了功能就废了 → 失败
    ("dlt645",      "DL/T645 数据项中文名", False),  # 只是没中文名 → 警告
)

for module, purpose, required in OPTIONAL_DEPENDENCIES:
    present = importlib.util.find_spec(module) is not None
    if present:
        print(f"[OK  ] {module:<12} {purpose}")
    elif required:
        print(f"[FAIL] {module:<12} 缺失 → {purpose}不可用")
    else:
        print(f"[WARN] {module:<12} 缺失 → {purpose}")
```

同时注意：**不要把"数据质量警告"当成失败**。样例数据里故意截断的帧会触发
"数据不完整"警告，那是正常的，判失败会让自检永远红着，最终没人看。
只判「解析不出来」。
