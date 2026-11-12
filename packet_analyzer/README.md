# 电力协议报文解析器（独立 Qt 工具）

从 EMS Simulate 中抽出的报文解析能力，做成**不依赖主项目运行环境**的桌面工具：
同一套字段级解析内核，重写成 Qt 桌面界面，同时补上离线导入与 TCP 实时抓包。

界面默认用 PySide6（Qt 6）；老系统可用 PySide2（Qt 5.15）跑同一份代码，
差异集中在 `ui/qtcompat.py`。

```
packet_analyzer/
├── main.py                # 图形版入口（含 --demo / --selftest / --screenshot）
├── cli.py                 # 命令行版入口（无 Qt，可在无图形环境运行）
├── pa.sh                  # Linux 命令行版启动脚本
├── pa-gui.sh              # Linux 图形版启动（自动优先包内 Qt5）
├── install.sh             # 部署自检
├── scripts/
│   ├── build_linux_bundle.sh   # 生成 Linux 离线部署包
│   └── build_linux_bundle.py   # 打包实现（精确写入权限位）
├── run.bat / run.sh       # 一键启动
├── packet_analyzer.spec   # PyInstaller 打包配置（onedir）
├── build_windows.ps1      # 打包 + 生成 zip 的脚本
├── requirements.txt
├── samples/samples.json   # 8 组内置样例帧
├── core/                  # 解析内核（纯 Python，无 Qt 依赖）
│   ├── registry.py        # 协议注册、自动识别、流式分帧、解析分发
│   ├── store.py           # 报文会话、IP 元信息、请求/响应关联、时延统计
│   ├── wpcap.py           # libpcap/Npcap 的 ctypes 绑定（无第三方依赖）
│   ├── linklayer.py       # 链路层解析：以太网/VLAN/DLT_NULL/IPv4/IPv6 → TCP/UDP
│   ├── ifaces.py          # 本机网卡枚举与抓包能力检测
│   ├── pcap.py            # 网卡抓包：监听 + TCP 重组 + IP 过滤 + GOOSE + 日志
│   ├── pcapfile.py        # 报文日志：标准 pcap 读写（Wireshark 兼容）
│   ├── capture.py         # TCP 直连（客户端/服务端）抓包引擎
│   ├── common.py          # 解析结果通用结构
│   ├── dnp3_objects.py    # DNP3 G52 补充对象组（自包含）
│   └── modbus.py / dlt645.py / iec104.py / iec101.py / dnp3.py / mms.py / goose.py / ft12.py
├── ui/                    # 界面（PySide6 / PySide2 通用）
│   ├── qtcompat.py        # Qt5/Qt6 兼容层：绑定差异只在这里处理
│   ├── main_window.py     # 主窗口：工具栏、列表、详情、菜单
│   ├── detail_view.py     # 详情面板：概要 / 字节 / 字段 / 对象 / 校验
│   ├── widgets.py         # 字节高亮、字段表、对象树、状态标签
│   ├── message_model.py   # 报文列表模型
│   ├── dialogs.py         # 导入、抓包参数、手动发送
│   └── theme.py           # 浅色主题 QSS
└── tests/                 # 回归测试（unittest + 离屏 UI 自检）
```

## 功能

**解析**
- 7 种协议字段级解析：Modbus TCP/RTU、DL/T 645-2007、IEC 60870-5-101/104、DNP3、IEC 61850 MMS、GOOSE
- 自动协议识别，也可手动指定
- 字段级结果：字节偏移、原始 HEX、解析值、说明；数据对象 / 信息体 / 数据集展开
- 校验项：MBAP 长度、CRC16、FT1.2 校验和、APDU 长度、TPKT 长度、DNP3 块 CRC、DL/T 645 校验和
- 请求 / 响应关联：Modbus 事务号 + 从站 + 功能码；DNP3 应用序号

**界面**
- 报文列表：序号、时间、方向、**源 → 目的**、协议地址、长度、原始报文、解析摘要，收发分行着色
- 详情面板：摘要横幅、元信息、**可高亮的原始字节区**、字段表、数据对象树、关联信息、校验、告警
- 点击字段行或对象行，自动高亮其占用的字节区间
- **IP 过滤**：主界面独立的 IP 输入框 + 已出现 IP 下拉，实时筛出指定 IP 的报文（可多选）
- 按摘要 / 原始报文 / 协议地址过滤，自动滚动，实时帧数与平均时延
- 复制当前报文 HEX、导出会话 CSV（UTF-8 BOM，Excel 直接打开）

**报文日志**
- 工具栏「报文日志」开关（`Ctrl+Shift+L`），抓包前设置或**运行中随时开关**
- 存成标准 **pcap** 文件：Wireshark / tshark 可直接打开，现场分析不用额外工具
- 日志内容是**完整链路帧**（含 IP/TCP 头），所以 Wireshark 能一路解到 Modbus 应用层
- 范围按抓包过滤走：设了 IP / 端口过滤就只记命中的报文，不设过滤则记录网卡抓到的全部报文
- 文件名带网卡名与时间戳（如 `以太网_20261027_193800.pcap`），默认存到程序目录的 `logs/`
- 状态栏实时显示已写帧数与文件大小，抓包停止时自动落盘
- 「打开日志」(`Ctrl+Shift+O`) 可把日志读回来重新解析，也能打开 Wireshark 抓的包回放

**输入**
- 粘贴十六进制（支持空格、换行、逗号、`0x` 前缀）
- 导入文本 / HEX / LOG / BIN 文件；支持「每行一帧」或「整段一帧」
- 方向支持请求、响应、按行交替（便于成对粘贴请求与响应）
- 内置 8 组样例，菜单一键载入

**网卡抓包（主要方式）**
- 先选网卡再抓包：直接读 Npcap 设备表，显示连接名 + IPv4 + 硬件型号，可随时刷新
- 被动监听，可看到链路上**所有** TCP/UDP 通讯，包括设备与设备之间
- IP 过滤（支持网段）、端口过滤、主站 IP 指定，并实时展示实际生效的 BPF 表达式
- 混杂模式可开关：关掉只收本机流量，做旁路分析时打开
- 抓包调优：内核缓冲区可调（默认 32MB，突发场景防丢包）；低延迟模式可选
  （默认按约 20ms 批量交付，CPU 约省 5 倍；开启后延迟约 0.3ms 但 CPU 高 5 倍）
- **丢包可见**：状态栏实时显示内核丢包数（红标），停止时明确告知漏了多少；
  此前这类丢包完全无声——界面正常但报文已缺失，最容易导致误判
- TCP 按流重组后自动分帧；UDP 按数据报分帧；Modbus RTU over TCP 按段边界断帧
- **GOOSE 二层抓包**：识别 EtherType 0x88B8 的以太网帧，整帧交给 GOOSE 解析器
- 请求/响应角色判定：主站 IP > TCP SYN 学到的客户端 > 常见服务端口 > 端口启发式
- 自行解析以太网 / VLAN（含 QinQ）/ IPv4 / IPv6 / TCP / UDP，支持回环的 DLT_NULL 与 Linux 的 SLL

**直连抓包（辅助方式）**
- TCP 客户端（主动连接设备）与 TCP 服务端（监听端口等设备连入）两种模式
- 可设定时发送（模拟主站轮询，如总召唤、读寄存器），也可手动发送单帧
- 适合需要主动发报文、或网卡抓包不可用的场景

## 运行

要求 Python 3.11+。必需依赖只有 PySide6（LGPLv3，可闭源商用）。
网卡抓包通过 ctypes 直接调用 libpcap/Npcap，**不需要 scapy 等第三方抓包库**。

**Windows 需安装 Npcap**：<https://npcap.com/>。未安装时离线解析与直连模式仍可用，
点"开始抓包"会给出明确提示而不是静默失败。
Linux 需 `libpcap`（如 `apt install libpcap0.8`）；macOS 自带。

可选：装 `psutil` 后网卡列表能显示"以太网"这类系统连接名（不装则显示硬件型号）。

### 老 Linux 服务器（glibc 2.19 这类老系统）

图形版默认用 PySide6（Qt 6，要求 **glibc ≥ 2.28**）。更老的系统（Debian 8 / glibc 2.19）
可以走 **PySide2（Qt 5.15）**：界面代码通过 `ui/qtcompat.py` 同时兼容两版，不用维护两套。

```bash
# 1. 打包（在开发机上）
bash packet_analyzer/scripts/build_linux_bundle.sh          # 命令行版，约 26MB
bash packet_analyzer/scripts/build_linux_bundle.sh --gui     # 图形版，约 59MB

# 2. 传到服务器并解压（不需要 root，不动系统 Python）
scp build/linux/packet-analyzer-linux-x86_64-gui.tar.gz ess@<服务器>:~/
ssh ess@<服务器>
tar xzf packet-analyzer-linux-x86_64-gui.tar.gz && cd packet-analyzer
./install.sh          # 自检 + 权限检查

# 3. 使用
./pa-gui.sh                                       # 图形界面
./pa.sh ifaces                                    # 命令行
sudo ./pa.sh capture --iface eth0 --ip 192.168.1.10 --duration 60 --log run.pcap
./pa.sh replay run.pcap --protocol modbus_tcp
./pa.sh parse 000100000006010300000009
```

Qt5 与 Qt6 的差异（`QAction` 归属模块、`QApplication.exec_()`）只在 `ui/qtcompat.py` 里处理一次，
界面代码仍用 Qt6 风格的全限定枚举。

便携 Python 来自 python-build-standalone（面向 glibc 2.17+ 构建），解压即用。
详见 [docs/README-linux.md](docs/README-linux.md)。

**要在同一台服务器上开发其它 Python GUI 程序**，看
[docs/LINUX-GUI-DEV-GUIDE.md](docs/LINUX-GUI-DEV-GUIDE.md) —— 通用的环境勘察、
选型依据、离线依赖准备、打包器与启动脚本模板，可直接复用到新项目。

```bat
:: Windows
cd packet_analyzer
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

```bash
# Linux / macOS
cd packet_analyzer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

也可以直接双击 `run.bat`（Windows）或执行 `./run.sh`。启动脚本会依次尝试：本目录 `.venv` → 上级目录 `.venv` → 系统 `python`。

命令行参数：

| 参数 | 说明 |
| --- | --- |
| `--demo` | 启动后自动载入全部内置样例，便于快速查看界面 |
| `--selftest` | 不启动界面，逐帧解析内置样例并检查可选依赖，退出码 0/1 |
| `--screenshot PATH` | 渲染主窗口截图后退出（供自动化自检使用） |

`--selftest` 也可以对打包后的 exe 使用，用来确认分发包是否完整：

```bat
PacketAnalyzer.exe --selftest
```

## 协议识别与分帧

| 协议 | 起始特征 | 分帧依据 | 列表地址字段 |
| --- | --- | --- | --- |
| Modbus TCP | MBAP 协议标识为 0 + 合法功能码 | `6 + 长度字段` | 单元标识 Unit ID |
| Modbus RTU | CRC16 校验通过 | 链路空闲间隔（默认 50 ms） | 从站地址 |
| DL/T 645 | `68 ... 68` | `12 + 数据域长度` | 表地址（6 字节 BCD） |
| IEC 104 | `68` + APDU 长度 | `2 + 长度字节` | 公共地址 |
| IEC 101 | `10` / `68` / `E5` | FT1.2 固定帧长或 `长度 + 6` | 链路地址 |
| DNP3 | `05 64` | 长度字段 + 每 16 字节追加的 CRC 块 | 源地址 |
| MMS | `03 00` (TPKT) | TPKT 长度字段 | — |
| GOOSE | EtherType `88B8`（含 VLAN 时 `8100`） | 仅离线，按整帧解析 | APPID |

说明：

- 自动识别会按上述特征打分，置信度不足时请手动指定协议。
- **Modbus RTU over TCP 建议显式选择协议**：无长度字段，分帧依赖链路空闲；自动模式只对完整到达的 RTU 帧做 CRC 识别。
- GOOSE 是二层以太网帧，无法通过 TCP 抓取。除离线粘贴 / 导入整帧外，**网卡抓包现已支持 GOOSE**：
  选一块接入 GOOSE 网的网卡，EtherType 为 `0x88B8` 的帧会被识别并整帧交给 GOOSE 解析器。

## 常见用法

1. **查一条报文**：`导入报文` → 粘贴 HEX → 选择协议（或自动识别）→ 解析 → 在列表点选 → 右侧看字段与字节高亮。
2. **看一对请求响应**：导入时选择「按行交替（请求、响应）」，第二帧的详情会出现「请求 / 响应关联」。
3. **抓网卡上的报文**：`开始抓包` → 网卡抓包页 → 选网卡（如"以太网 192.168.3.5"）→ 需要时填 IP 过滤
   （如 `192.168.3.10`，只关心这台设备）→ 开始。列表里的「源 → 目的」列会显示每条通讯的双方地址。
4. **只看某台设备**：抓包后在主界面 `IP 过滤` 输入框填 `192.168.3.10`，或用右侧下拉从已出现的 IP 里挑；
   多个 IP 用逗号分隔（如 `192.168.3.10, 192.168.3.11`），留空显示全部。
5. **模拟主站轮询**：切到「直连设备」页，填设备地址端口，启用「定时发送」并填入轮询报文与间隔
   （如 Modbus 读保持寄存器 `000100000006010300000009`，1 秒）。
6. **留存报文日志**：勾选工具栏「报文日志」（或抓包设置里的"报文日志"分组）→ 抓包 → 停止时自动落盘到
   `logs/`。事后用 Wireshark 打开，或用本工具 `打开日志`(`Ctrl+Shift+O`) 重新解析。
7. **导出留档**：`文件 → 导出会话 CSV`。

### 日志记了什么

按 pcap 的语义，日志记录的是**链路层帧**，所以帧数会比界面行数多——一次 Modbus 往返在界面上是 2 行，
在日志里还包含 TCP 三次握手与 ACK，通常是 8～12 帧。这不是重复，是完整的报文留档，正因如此
Wireshark 才能逐层展开 IP / TCP / Modbus。

两个工具的产物不要混用：

| 功能 | 内容 | 用途 |
| --- | --- | --- |
| **报文日志**（pcap） | 完整链路帧，可含非目标协议流量 | Wireshark 深度分析、事后追溯 |
| **导出会话 CSV** | 已解析的界面行（含摘要） | Excel 汇总、给别人看结论 |

### 抓包时的角色判定

列表里的「请求 / 响应」不靠猜端口，优先级如下：

1. 抓包设置里填了**主站 IP** → 该 IP 发出的即请求
2. **TCP SYN** 学到的客户端端点 → 客户端发出的即请求（回环抓包两端 IP 相同时也有效）
3. 命中常见服务端口（502 / 2404 / 102 / 20000 …）的一方为服务端
4. 兜底：目标端口更小的一侧视为请求

协议解析依赖这个角色区分请求与响应，若发现方向判反，最直接的办法是在抓包设置里指定主站 IP。

## 测试

```bash
# 解析内核 + 抓包引擎（14 项）
python -m unittest discover -s packet_analyzer/tests -p "test_*.py" -v

# 界面结构与布局自检（离屏渲染 + 像素抽样）
QT_QPA_PLATFORM=offscreen python packet_analyzer/tests/ui_smoke.py

# 交互流程自检（导入 / 过滤 / 导出 / 复制 / 清空 / 抓包回调 / 对话框）
QT_QPA_PLATFORM=offscreen python packet_analyzer/tests/ui_flows.py
```

Windows 下如需在 Git Bash 中设置环境变量，可直接写 `QT_QPA_PLATFORM=offscreen python ...`。

## 与主项目的关系

- `core/` 下的协议解析器复制自主项目 `src/device/core/message/parsers/`，`ft12.py` 复制自 `src/proto/iec101/ft12.py`，仅把 `from src.proto...` 改为包内相对导入，**解析逻辑未改动**。
- `core/dnp3_objects.py` 复制自 `src/proto/dnp3/objects.py`（G52 补充对象组）。原解析器里曾直接
  `import src.proto.dnp3.objects`，等于隐式依赖主项目；现已改为导入本工具内的副本，
  真正自包含。`tests/test_core.py` 有专门用例阻止该依赖回潮。
- 主项目解析器升级后，重新复制这些文件即可同步；`common.py` 的导入关系保持不变。
- 新增的 `registry.py`（识别/分帧/分发）、`store.py`（会话与关联）、`capture.py`（TCP 抓包）和整个 `ui/` 是本工具独有的。
- 未包含：IEC 61850 模型（ICD/SCD）加载与远程发现、测点导入与工程值换算、设备模拟功能。

## 打包为 exe（onedir）

用仓库内自带的 spec 与脚本，一条命令完成打包并生成分发包：

```powershell
# 依赖（打包机需要，运行 exe 的机器不需要）
uv pip install PySide6 pyinstaller

cd packet_analyzer
.\build_windows.ps1
```

产物：

| 路径 | 说明 |
| --- | --- |
| `dist\PacketAnalyzer\PacketAnalyzer.exe` | 可执行文件 |
| `dist\PacketAnalyzer\_internal\` | Qt 运行库与样例数据，必须随 exe 一起分发 |
| `build\windows\PacketAnalyzer_windows.zip` | 分发包（单层 `PacketAnalyzer` 目录，解压即用） |

打包完建议用自检验证：

```powershell
.\dist\PacketAnalyzer\PacketAnalyzer.exe --selftest
```

手工调用 PyInstaller 也可以：

```bat
python -m PyInstaller --noconfirm --workpath build/work --distpath dist packet_analyzer.spec
```

### 打包要点

- **只用 onedir**：PySide6 为 LGPLv3，保留独立 Qt 动态库便于用户替换，符合"可替换"要求；
  压缩成 `--onefile` 单文件会削弱这一点，商业交付前建议与法务确认。
- **剔除无用 Qt 模块**：完整 PySide6 约 655MB（含 WebEngine/Quick/3D）。spec 里已排除这些
  模块，并过滤掉 `Qt6Qml*`、`Qt6Quick*`、`opengl32sw.dll`，最终目录约 **83MB**、压缩包约 **35MB**。
- **`dlt645` 是可选依赖**：装了才会显示 DL/T 645 的 DI 中文名称（如"正向有功总电能"）。
  spec 里用 `hiddenimports` 显式声明，缺失时程序仍可正常运行，只是 DI 只显示十六进制。
- **不分发 wpcap.dll**：Npcap 由用户自行安装，程序只按名字加载系统里的 `wpcap.dll`，
  既避免再分发驱动，也顺带满足 Npcap 的许可要求。
- 分发包**必须整个目录一起拷**，只拷 exe 会因缺少 `_internal` 而无法启动。

## 为什么不用 scapy

最初用 scapy 做网卡抓包，后来改为 ctypes 直调 libpcap，原因按重要性排序：

1. **许可证**：scapy 是 **GPL-2.0-only**。本工具特意从 PyQt6(GPL) 迁到 PySide6(LGPL) 就是为了
   能闭源交付；把 scapy 打进分发包等于又把 GPL 带回来，整个"可闭源"的前提就不成立了。
   libpcap/Npcap 用 `ctypes` 在运行时调用，不随程序分发，不产生衍生作品问题。
2. **体积**：scapy 让分发包从 84MB 涨到 98MB。
3. **启动速度**：`import scapy.all` 约 **2 秒**，而自写的 `wpcap` + `linklayer` 合计约 **0.12 秒**。
4. **可控性**：本工具只要 L2–L4 头部，自己解析反而更透明——也顺带支持了 GOOSE 二层抓包。

代价是需要自己处理平台差异，已在代码里固定并有测试守着：

- `pcap_pkthdr` 结构体：Windows 的 `long` 是 32 位（`timeval` 8 字节、结构体 16 字节），
  Linux/macOS 是 64 位（16 / 24 字节）。弄错会让 `caplen` 读出垃圾值。
- 链路层类型：回环设备是 `DLT_NULL`（4 字节地址族，不是以太网头），
  以太网是 `DLT_EN10MB`，Linux 还有 `DLT_LINUX_SLL`，各自分别处理。

## 关于 GUI 绑定

本工具原先用 PyQt6（GPLv3）实现，现已迁移到 **PySide6（LGPLv3）**，以便闭源交付。
两者底层都是同一个 Qt 6，界面与性能一致。迁移涉及的实际改动：

| 项目 | 原（PyQt6） | 现（PySide6） |
| --- | --- | --- |
| 导入 | `from PyQt6.QtWidgets import ...` | `from PySide6.QtWidgets import ...` |
| 信号 | `pyqtSignal(bytes, str)` | `Signal(bytes, str)` |
| 槽 / 属性 | `@pyqtSlot` / `pyqtProperty` | `@Slot` / `Property` |
| 设计器转换 | `pyuic6` / `pyrcc6` | `pyside6-uic` / `pyside6-rcc` |

代码中所有枚举均使用完整作用域写法（如 `Qt.ItemDataRole.DisplayRole`），两套绑定通用，
因此无需改动。`Signal(bytes, str)` 在 PySide6 中收发仍是 Python `bytes`，解析内核直接可用。
