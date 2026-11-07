# OPC UA

OPC UA 模块支持 **服务端（Server）** 与 **客户端（Client）**，用于能源设备的地址空间建模、数据模拟、读写验证和实时订阅。协议实现基于 `asyncua 2.0.1`。

## 连接与角色

| 属性 | 说明 |
|------|------|
| 传输与端口 | UA TCP，默认端口 `4840`，Endpoint URL 示例：`opc.tcp://127.0.0.1:4840/ems/` |
| 服务端 | 配置监听地址、端口、Endpoint 路径及命名空间 URI，维护变量并响应客户端请求 |
| 客户端 | 使用完整 Endpoint URL 连接，浏览远端地址空间，读取、写入和订阅变量 |
| 节点标识 | 使用 NodeId 定位节点，例如 `ns=2;s=ActivePower`；命名空间 URI 用于识别模型命名空间 |
| 数据质量 | 查看 StatusCode、源时间戳及服务器时间戳 |

## 功能模块

| 模块 | 功能 |
|------|------|
| 测点与地址空间 | Excel 点表预检、导入与导出；变量定义、类型、初始值、可写权限；模型导入与导出 |
| 对象与变量值 | 树形浏览、属性与引用查看、实时值、写入与数值波形 |
| 数据模拟 | 固定值、随机、正弦波、步进；按变量配置参数及外部写入策略，运行时保存生效 |
| 客户端采集 | 单点读写、实时订阅、监控项采样间隔、队列、死区和自动重连 |
| 历史数据 | 服务端 SQLite 历史存储，客户端 HistoryRead 查询、分页和时间范围筛选 |
| 事件 | 服务端生成测试事件；客户端订阅事件源、筛选和 CSV 导出 |
| MQTT/JSON 发布 | 服务端变量与事件 DataSetWriter、WriterGroup、主题、元数据和完整帧配置 |
| 安全配置 | Endpoint 发现、应用证书、对端证书信任、消息安全模式和用户角色 |
| 运行与诊断 | 服务运行状态、会话、真实服务调用摘要、耗时与状态码 |

> 📷 **截图待补：OPC UA 地址空间与变量定义** — 展示 NodeId、BrowseName、数据类型、初始值及可写权限。
> 建议文件名：`opcua-address-space.png`

<!-- ![OPC UA 地址空间与变量定义](/img/opcua-address-space.png) -->

## 发布订阅范围

客户端实时订阅使用原生 OPC UA Subscription；服务端 MQTT/JSON 发布需要额外连接 MQTT Broker。支持 MQTT 3.1.1、匿名 Broker、QoS 0 和 `mqtt://` / `mqtts://`，当前不提供 UADP 或 MQTT DataSetReader。历史数据通过 OPC UA 查询。

内置服务端提供原始历史读取；客户端聚合查询需要远端支持 ReadProcessed。配置与限制详见 [发布订阅工作区](../../../OPCUA_PUBSUB)。

## 截图补充方式

截图占位提供了建议文件名与已注释的图片语法。将图片放到 `resources/img/`（仓库 README）和 `docs/public/img/`（在线文档），然后取消对应图片语法的 HTML 注释并删除占位说明。同一张图在两个目录使用相同文件名。

| 建议文件名 | 截图页面 |
|------------|----------|
| `opcua-runtime.png` | 端点与运行状态 |
| `opcua-address-space.png` | 地址空间与变量定义 |
| `opcua-values.png` | 对象与实时变量值 |
| `opcua-simulation.png` | 模拟规则 |
| `opcua-client.png` | 客户端浏览与读写 |
| `opcua-subscription.png` | 客户端实时订阅 |
| `opcua-history.png` | 历史数据查询 |
| `opcua-events.png` | 事件订阅 |
| `opcua-pubsub.png` | MQTT/JSON 发布器设置 |
| `opcua-security.png` | 证书与安全 |
| `opcua-diagnostics.png` | 会话与通信日志 |

## 界面预览

> 📷 **截图待补：OPC UA 对象与实时变量值** — 展开对象树并选择变量，展示属性、当前值、质量码、时间戳及波形。
> 建议文件名：`opcua-values.png`

<!-- ![OPC UA 对象与实时变量值](/img/opcua-values.png) -->

> 📷 **截图待补：OPC UA 客户端实时订阅** — 展示地址空间树、监控变量、发布与采样间隔，以及实时表格或趋势。
> 建议文件名：`opcua-subscription.png`

<!-- ![OPC UA 客户端实时订阅](/img/opcua-subscription.png) -->

详细步骤见 [操作指南](./operation)，通信排查见 [报文与诊断查看](./packet-view)。
