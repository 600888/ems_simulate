# GOOSE 跨平台收发与自发自收

本文说明 EMS Simulate 在 Linux 和 Windows 上如何发送、捕获和订阅 GOOSE，以及本机发出的报文在旧版 Linux 接收路径中被丢弃的原因。

GOOSE 使用以太网二层组播，协议 EtherType 为 `0x88B8`。发布器、订阅器和抓包器各自选择网卡。这里的**自发自收**指发布器和订阅器在同一台主机、同一块以太网网卡上运行，订阅器读取系统抓包接口提供的本机出站帧副本。选用发布时的实际网卡即可。模型加载后，GOOSE 可以独立于 MMS 连接运行，详见 [IEC 61850 操作指南](./operation)。

## Linux 与 Windows 的实现差异

| 项目 | Linux | Windows |
| --- | --- | --- |
| 发布 | 由 `pyiec61850-ng` 调用 libiec61850，按发布配置构造并发送以太网帧 | 由 Scapy 构造以太网帧和 GOOSE 负载，通过 Npcap 发送 |
| VLAN ID 为 `0` | 发布器仍生成 802.1Q 标签。VID 为 `0`，PCP 携带配置的优先级 | 与 Linux 一致，始终添加 `Dot1Q` 头；VID 为 `0` 时仍保留配置的 PCP |
| VLAN ID 大于 `0` | 发布器生成带 VID 和 PCP 的 802.1Q 帧 | Scapy 添加带 VID 和 PCP 的 `Dot1Q` 头。现场可在对端抓包确认网卡实际发出的标签 |
| 订阅和独立抓包 | `AF_PACKET` 原始套接字绑定指定网卡，使用 `ETH_P_ALL` 接收，并在应用内解析 EtherType | Scapy 在指定的 Npcap 适配器上抓取二层帧，再使用同一套 GOOSE 解析器 |
| 运行条件 | 后端进程在对应网络命名空间中具有 `CAP_NET_RAW`，并能看到目标网卡 | 安装并启用 Npcap。若安装时限制为仅管理员访问，后端需要相应权限 |
| 订阅历史中的 `timestamp` | 毫秒级 GOOSE 事件时标，取自帧内字段 `t` | 毫秒级本机捕获时刻 |

两端都用本机捕获时刻更新订阅的最后接收时间。抓包详情会区分帧内事件时标与捕获时刻。同一状态的周期重发通常保留事件时标，接收计数和 `sqNum` 更适合判断订阅是否持续收到报文。

原先的 libiec61850 Windows 接收路径曾出现接口启动后未收到回调的情况。当前二层收发使用 Scapy/Npcap。安装要求和迁移背景可参阅以下资料。 [Npcap 用户指南](https://npcap.com/guide/npcap-users-guide.html) · [GOOSE 接收、DataSet 历史与抓包链路重构](../../../changelog/iec61850/goose/04-receive-history-capture-refactoring)

## Linux 旧接收路径为何漏掉本机帧

两种帧的差别出现在源 MAC 之后。下表中的偏移从以太网帧首字节开始计算。

| 帧格式 | 偏移 12–13 | 偏移 14–15 | 偏移 16–17 | APPID 起始偏移 |
| --- | --- | --- | --- | --- |
| 无标签 GOOSE | `0x88B8` | APPID | GOOSE 长度 | 14 |
| 单层 802.1Q GOOSE | `0x8100` | VLAN TCI，含 PCP、DEI 和 VID | `0x88B8` | 18 |

例如 VID 为 `0`、PCP 为 `4`、DEI 为 `0` 时，带标签的帧从偏移 12 开始可见 `81 00 80 00 88 B8`。旧过滤器读到的是前两个字节 `81 00`。

1. Linux 发布端调用 `GoosePublisher_create()`。libiec61850 v1.6.1 通过该入口启用 VLAN 标签，因此默认 VID 为 `0` 时，帧仍以 `0x8100` 作为外层 EtherType。 [libiec61850 v1.6.1 发布端源码](https://github.com/mz-automation/libiec61850/blob/v1.6.1/src/goose/goose_publisher.c)
2. Linux 可将本机发送的帧以 `PACKET_OUTGOING` 类型交给同一接口上的其他抓包套接字。本机可以通过这份副本观察发布流量，无需等待交换机把帧送回。 [Linux packet(7)](https://man7.org/linux/man-pages/man7/packet.7.html)
3. 旧订阅路径使用 libiec61850 的 Linux GOOSE 接收器。其内核过滤器只比较偏移 12–13 的值与 `0x88B8`。当出站副本保留 802.1Q 头时，该位置是 `0x8100`，帧在到达 GOOSE 解析和订阅匹配之前就被丢弃。这解释了同一网卡上独立抓包有数据、订阅计数却为零的现象。 [libiec61850 v1.6.1 Linux 接收过滤器源码](https://github.com/mz-automation/libiec61850/blob/v1.6.1/hal/ethernet/linux/ethernet_linux.c)

旧版 Windows 在 VID 为 `0` 时构造无标签帧。现在发布行为已统一为 Linux 的方式：始终携带单层 802.1Q 头，包括 VID 为 `0` 的优先级标签。两端均保留配置的 VID 和 PCP，外层 EtherType 为 `0x8100`，内层 GOOSE EtherType 为 `0x88B8`。接收与独立抓包仍兼容外部设备发来的无标签帧。

## 修复后的 Linux 接收流程

```text
GOOSE Publisher → 指定以太网网卡 → 本机出站帧副本
                                          ↓
外部 GOOSE 组播 → 同一网卡 ───────→ AF_PACKET / ETH_P_ALL
                                          ↓
                              识别无标签或单层 802.1Q
                                          ↓
                                 解析 GOOSE 头和 PDU
                                          ↓
                           匹配启用的订阅 → 更新数据和历史
```

- 接收套接字按网卡绑定，并使用套接字级的 `PACKET_MR_ALLMULTI` 接收该网卡上的外部二层组播。套接字关闭时，内核清理这项成员资格。 [Linux packet(7)](https://man7.org/linux/man-pages/man7/packet.7.html)
- 应用识别帧头是否含单层 `0x8100` 标签，再从正确位置读取 `0x88B8` 和 APPID。Linux 发布端继续使用 libiec61850，现有的 VID 和优先级配置仍可使用。
- 订阅器仅处理已启用、`goCbRef` 完全一致的订阅。配置了 APPID 或目的 MAC 时，对应字段也必须相同。独立抓包有数据只说明捕获到了帧，订阅还需通过这些条件。
- `confRev` 用于提示配置版本是否一致。若报文已匹配但数据成员含义不符，核对 DataSet 引用、成员顺序和配置版本。

## 本机自发自收验证

### 配置发布与订阅

1. 在测试网段中打开已加载模型的 IEC 61850 设备，选择一条已配置 DataSet 的 GOOSE 发布项。
2. 发布和订阅选同一块已启用的以太网网卡。Linux 可用 `ip -br link` 查网卡名称。Windows 可用 `Get-NetAdapter` 查适配器名称和状态。容器或虚拟机内的后端需要使用其自身可见的网卡。
3. 从发布配置复制实际的 GoCBRef、APPID 和目的组播 MAC。例如 GoCBRef 可以是 `IED1LD0/LLN0$GO$gcb1`。填写订阅后先启用本地接收，再启动发布。
4. 查看订阅的最新数据和接收历史。周期重发时，接收计数应递增，`stNum` 通常保持稳定，`sqNum` 递增。变更一个发布成员值后，检查订阅值和 `stNum` 是否更新。
5. 两个系统都先用 VID `0` 验证默认的优先级标签，再在允许该 VLAN 的测试网段验证非零 VID。相同 VID 和 PCP 配置下，两端的 802.1Q 头应一致；默认 VID `0`、PCP `4` 时，从偏移 12 开始应为 `81 00 80 00 88 B8`。

### Linux 抓包

将 `eth0` 替换为后端所用的网卡名。使用 `-Q out` 查看本机出站帧，省略该选项可同时观察入站和出站流量。 [tcpdump 手册源码](https://github.com/the-tcpdump-group/tcpdump/blob/master/tcpdump.1.in)

```bash
sudo tcpdump -ni eth0 -Q out -e -vv +  'ether proto 0x88b8 or (vlan and ether proto 0x88b8)'
```

预期能看到与发布配置一致的目的 MAC。带标签的帧通常会显示 `802.1Q`、VLAN ID 和优先级，内层协议为 `0x88b8`。该命令以提升后的权限运行，应用后端进程的套接字权限需要单独核对。若只看到本机出站帧，可在另一台测试主机或交换机镜像口确认线上是否收到。

### Windows 抓包

在 Wireshark 中选择与 EMS Simulate 相同的以太网适配器，开始抓包后使用显示过滤器 `goose`。要缩小范围，可用 `goose.appid == 0x0001` 并替换为实际 APPID。展开以太网、802.1Q 和 GOOSE 层，核对目的 MAC、标签和 GoCBRef。 [Wireshark GOOSE 显示过滤器参考](https://www.wireshark.org/docs/dfref/g/goose.html)

如果后端无法打开适配器，先检查 Npcap 驱动和安装时的访问设置，再重新启动后端。 [Npcap 用户指南](https://npcap.com/guide/npcap-users-guide.html)

驱动或网卡可能移除 VLAN 标签，导致本机抓包看不到标签。需要确认线上的标签时，可使用能保留 VLAN 标签的对端抓包接口，或使用保留标签的交换机镜像口。 [Wireshark VLAN 抓包说明](https://wiki.wireshark.org/CaptureSetup/VLAN)

## 按现象定位

| 现场现象 | 核对顺序 |
| --- | --- |
| 启动接收时提示原始套接字权限不足 | Linux 核对实际后端进程的 `CAP_NET_RAW` 及其网络命名空间。Windows 核对 Npcap 驱动、访问权限和所选适配器 |
| 指定网卡抓不到本机发布帧 | 确认发布已启用、选中的网卡处于可用状态、抓包绑定同一网卡，再检查发布日志。发布状态和抓到实际帧是两项独立证据 |
| 旧版 Linux 能抓到带标签的出站帧，订阅计数为零 | 确认是否仍在使用 libiec61850 接收路径。更新含本修复的后端后，启动日志应显示 `GOOSE Receiver 已启动 (AF_PACKET)` |
| 更新后能抓到帧，订阅计数仍为零 | 核对本地订阅已启用，订阅网卡一致，`goCbRef` 完全相同，APPID 和目的 MAC 与帧一致 |
| 订阅有接收记录，成员值或版本不符 | 比对帧中的 `datSet`、`confRev`、成员个数及顺序，检查订阅使用的 SCL 模型 |
| 本机自收正常，对端仍收不到 | 在对端或交换机镜像口抓包，核对端口 VLAN、标签处理和二层组播转发。自收只验证本机发布与订阅链路 |

## 自动化验证范围

回归测试模拟 Linux 原始套接字，分别注入无标签帧、VID `0` 优先级标签帧和 VID `100` 帧。测试检查绑定的网卡、订阅匹配、数据集历史和事件时标，并验证短帧以及 APPID 或目的 MAC 不匹配的帧不会更新订阅。

Windows 发布回归测试拦截 Npcap 发送调用，检查 VID 为 `0` 和非零 VID 时实际构造的帧字节、PCP、内层 EtherType 和 GOOSE 长度，再把同一帧交给公共抓包与订阅处理链路，验证订阅计数和数据值更新。

```bash
python -m pytest tests/protocols/iec61850/goose/test_capture_subscriber.py tests/protocols/iec61850/goose/test_publisher_transport.py -q
```

该测试覆盖应用的收包和解析流程。网卡驱动是否提供出站帧副本，以及跨主机的 VLAN 标签和转发行为，需要按上面的实机步骤验证。
