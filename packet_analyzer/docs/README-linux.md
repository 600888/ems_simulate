# 命令行版部署说明（Linux 服务器）

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

## 八、图形界面

若必须在这台机器上用图形版，前提是 Qt5 路线（PySide2）。已确认该机具备条件：

- glibc 2.19 ≥ PySide2 wheel 要求的 2.17
- libstdc++ 到 GLIBCXX_3.4.24（Qt5.15 需要 3.4.21）
- X11 相关库齐全，且 `ess` 用户在 `:0` 有桌面会话
- 中文字体（文泉驿）已安装

代价：需要把 UI 代码从 Qt6 降到 Qt5（`QAction` 在 Qt5 属于 `QtWidgets`、部分枚举写法不同），
并额外带约 160MB 的 PySide2 wheel。目前**未实施**——如果确实需要，可以作为下一步。

## 九、已知限制

- 命令行为单条流式输出，没有图形版的详情面板与字节高亮；字段级信息用 `parse --json` 或 `replay --json` 取
- 不做 TCP 应用层会话重放（只做链路帧 → 应用帧的分解）
- GOOSE 只在无 IP 过滤时抓取（二层帧没有 IP 可言）
