# 命令行版部署说明（Linux 服务器）

> 想在这台服务器上**开发其它** Python GUI 程序？看
> [LINUX-GUI-DEV-GUIDE.md](LINUX-GUI-DEV-GUIDE.md)：环境勘察、选型依据、
> 便携 Python 与 Qt5 的准备、通用打包器与启动脚本模板。

图形版需要 PySide6（Qt 6 要求 **glibc ≥ 2.28**）。老服务器（如 Debian 8 / glibc 2.19）装不上，
因此单独提供这套**命令行版**：核心解析代码与图形版完全一致，只是没有界面。

## 一、这包能做什么

| 命令 | 作用 |
| --- | --- |
| `pa.sh ifaces` | 列出本机网卡、IP 与抓包能力 |
| `pa.sh capture` | 从网卡实时抓包，按协议解析并打印，同时存 pcap |
| `pa.sh replay` | 回放 pcap 日志，重新解析（也能读 Wireshark 抓的包） |
| `pa.sh parse` | 解析一帧十六进制报文 |
| `pa.sh selftest` | 验证 16 组样例帧的解析是否正常 |

支持的协议与图形版一致：Modbus TCP/RTU、DL/T 645、IEC 101/104、DNP3、MMS、GOOSE，并支持自动识别。

## 二、为什么自带 Python

目标机常见情况：

- 发行版 Debian 8（Linx 凝思 / 中标麒麟等国产化系统多基于此），**glibc 2.19**
- 系统自带 `python3` 是 **3.4.2**，连 `dataclasses` 都没有（3.7 才有），本工具需要 **3.10+**

所以包里内置一份**便携 CPython 3.10**（来自 python-build-standalone，面向 glibc 2.17+ 构建），
解压即用，不写系统目录、不碰 `apt`、不升级 glibc。

> 为什么不用 PySide2 做图形版：PySide2/Qt5 的 wheel 在 glibc 2.19 上确实能加载，
> 但那是把整个 GUI 降级重写一遍，代码要维护 Qt5 / Qt6 两套分支。若确实需要图形界面，
> 见文末「图形界面」一节。

## 三、部署步骤

```bash
# 1. 上传并解压（在能连到服务器的机器上执行）
scp packet-analyzer-linux-x86_64.tar.gz ess@192.168.235.144:~/
ssh ess@192.168.235.144
tar xzf packet-analyzer-linux-x86_64.tar.gz
cd packet-analyzer

# 2. 自检 + 权限检查
./install.sh

# 3. 开始用
./pa.sh ifaces
sudo ./pa.sh capture --iface eth0 --duration 30
```

`install.sh` 只做检查与提示，不修改系统。

## 四、抓包需要权限

抓包走 libpcap 的原始套接字，需要 **root** 或 `CAP_NET_RAW` 能力：

```bash
# 方式一：直接 sudo（最简单）
sudo ./pa.sh capture --iface eth0

# 方式二：给解释器加能力，之后普通用户也能抓
sudo setcap cap_net_raw,cap_net_admin=eip ./python/bin/python3
./pa.sh capture --iface eth0
```

系统需要 `libpcap`：`ls /usr/lib/x86_64-linux-gnu/libpcap.so*` 有文件即可。
Debian 系缺失时：`sudo apt install libpcap0.8`。

## 五、常用命令

```bash
# 列出网卡
./pa.sh ifaces

# 抓 60 秒，只看某台设备，存日志
sudo ./pa.sh capture --iface eth0 --ip 192.168.235.10 --duration 60 --log run.pcap

# 只看 Modbus，端口 502，同时导出 CSV
sudo ./pa.sh capture --iface eth0 --port 502 --protocol modbus_tcp \
                     --duration 120 --log mb.pcap --csv mb.csv

# 只收本机流量（关混杂模式，普通用户也可能够用）
./pa.sh capture --iface eth0 --no-promisc --duration 30

# 回放日志，按摘要关键字过滤
./pa.sh replay run.pcap --protocol modbus_tcp --search 总召唤

# 解析一帧
./pa.sh parse "000100000006010300000009" --protocol modbus_tcp
./pa.sh parse "680E000000006401060001000000 14"        # 自动识别
```

`capture` 会实时打印每帧的方向、源/目的、长度与解析摘要，Ctrl-C 停止并落盘。

## 六、日志与导出

- `--log x.pcap` 存标准 pcap，**Wireshark 可直接打开**；不写 `--log` 时默认存到 `logs/`
- `--csv x.csv` 导出已解析的帧（UTF-8 BOM，Excel 直接打开）
- `--json x.json` 导出结构化结果，便于对接其它系统

日志记录的是**完整链路帧**，所以帧数比打印出的应用层报文多（含 TCP 握手与 ACK），属正常。

## 七、内网离线机器怎么更新代码

代码更新后，只需重新传 `packet_analyzer/` 目录，不必重传 Python：

```bash
scp -r packet_analyzer ess@192.168.235.144:~/packet-analyzer/
```

## 八、图形界面（Qt5 / PySide2）

Qt6（PySide6）要求 glibc ≥ 2.28，本类机器只有 2.19，因此图形版走 **PySide2 / Qt 5.15** 路线。
同一份界面代码通过 `ui/qtcompat.py` 同时兼容 Qt5 与 Qt6，不需要两套代码。

### 8.1 打包（在开发机上）

```bash
# 1) 准备 PySide2 与 shiboken2 的 manylinux wheel（约 158MB）
mkdir -p build/cache/wheels
pip download --only-binary=:all: --platform manylinux1_x86_64 \
    --python-version 310 --implementation cp --abi abi3 \
    -d build/cache/wheels "PySide2==5.15.2.1" "shiboken2==5.15.2.1"

# 2) libdbus：目标机自带 1.8，Qt5.15 需要 >= 1.10，单独取一份较新的
#    （Debian 包里的 .so 即可，放进 build/cache/libdbus-1.so.3）

# 3) 出图形包（产物约 59MB，内含便携 Python + 裁剪后的 Qt5）
bash packet_analyzer/scripts/build_linux_bundle.sh --gui
#   → build/linux/packet-analyzer-linux-x86_64-gui.tar.gz
```

### 8.2 部署与运行

```bash
tar xzf packet-analyzer-linux-x86_64-gui.tar.gz && cd packet-analyzer
./pa-gui.sh                      # 打开图形界面
./pa-gui.sh --demo               # 带样例报文，便于快速确认渲染是否正常
```

`pa-gui.sh` 会自动：

- 把**包内** Qt5 加入 `LD_LIBRARY_PATH`（必须优先于系统 Qt，否则符号不匹配）
- 补好 `PYTHONPATH`
- 检测无 DISPLAY 时给出提示而不是抛 xcb 错误

命令行功能仍在 `./pa.sh`，两者共用同一套解析代码。

### 8.3 为什么带 59MB 而不是 400MB+

原始 PySide2 安装后 446MB，其中 362MB 是 Qt 库。工具只用 QtCore/QtGui/QtWidgets，
打包器按白名单裁剪（见 `scripts/build_linux_bundle.py` 的 `QT_LIB_KEEP_PREFIXES`），
保留必要的 `libQt5Qml`（Qt5Core 依赖）、`libQt5Network`（系统自带的是 5.3，必须用包内 5.15）、
xcb/offscreen 平台插件与图像插件，最终约 167MB，压缩后 59MB。

### 8.4 现场验证结果（192.168.235.144）

| 项目 | 结果 |
| --- | --- |
| 绑定识别 | `PySide2 (Qt 5.15.2) on linux` |
| `--selftest` | 通过（16 组样例帧 + 抓包能力） |
| 离屏渲染自检 | 0 失败（含对象树、字节高亮、像素抽样） |
| 交互流程自检 | 0 失败（导入、过滤、抓包参数、日志、回放） |
| 真实 X 显示 | 在 `:0` 成功开窗并截图（1440×823） |
| 已知依赖 | 系统 libdbus 1.8 太旧 → 包内自带 1.12.28 |

## 九、已知限制

- 图形版**没有**隐藏的系统依赖，但要求目标机有 X11（本地桌面或 `ssh -X`）；纯字符界面下请用 `pa.sh`
- 命令行为单条流式输出，没有图形版的详情面板与字节高亮；字段级信息用 `parse --json` 或 `replay --json` 取
- 不做 TCP 应用层会话重放（只做链路帧 → 应用帧的分解）
- GOOSE 只在无 IP 过滤时抓取（二层帧没有 IP 可言）
