# OPC UA 操作指南

## 一、创建设备与配置端点

在设备管理中新增设备，协议选择 **OPC UA**，连接类型选择 **TCP 服务端** 或 **TCP 客户端**。

- 服务端：填写监听 IP 和端口，在 **运行状态** 页配置 Endpoint 路径、命名空间 URI。
- 客户端：在 **运行状态** 页填写完整 Endpoint URL，路径必须与服务端一致。

默认端口为 `4840`。同机联调时，服务端与客户端需要使用同一端点。

> 📷 **截图待补：OPC UA 端点与运行状态** — 展示角色、Endpoint URL、连接状态和功能运行情况。
> 建议文件名：`opcua-runtime.png`

<!-- ![OPC UA 端点与运行状态](/img/opcua-runtime.png) -->

## 二、配置地址空间与点表

服务端进入 **地址空间 → 变量定义与模型**，新增变量并配置 NodeId、BrowseName、数据类型、初始值和可写权限。也可导入模型或 Excel 点表；结构调整应先停止服务端。

> 📷 **截图待补：OPC UA 地址空间与变量定义** — 展示 NodeId、BrowseName、数据类型、初始值及可写权限。
> 建议文件名：`opcua-address-space.png`

<!-- ![OPC UA 地址空间与变量定义](/img/opcua-address-space.png) -->

点表示例见仓库 [OPC UA Excel 模板](https://github.com/600888/ems_simulate/blob/main/data/point_csv/point_sample_opcua.xlsx)。导入时先预检，再应用导入结果。客户端测点用于映射远端 NodeId，服务端测点用于建立本地变量。

启动服务端后，在 **地址空间 → 对象与变量值** 中展开对象树、选择变量，查看属性、引用、当前值及数值波形；可写变量可输入当前值并执行写入。

> 📷 **截图待补：OPC UA 对象与实时变量值** — 展开对象树并选择变量，展示属性、当前值、质量码、时间戳及波形。
> 建议文件名：`opcua-values.png`

<!-- ![OPC UA 对象与实时变量值](/img/opcua-values.png) -->

## 三、设置数据模拟

在 **模拟规则** 中选择变量，设置固定值、随机、正弦波或步进参数，保存后应用。运行中可以修改规则，暂停或恢复模拟。

外部写入策略可以选择暂停对应规则、覆盖写入值或拒绝写入，用于验证控制命令与模拟数据的交互。

> 📷 **截图待补：OPC UA 模拟规则** — 展示固定值、随机、正弦波、步进参数，以及外部写入策略。
> 建议文件名：`opcua-simulation.png`

<!-- ![OPC UA 模拟规则](/img/opcua-simulation.png) -->

## 四、客户端浏览与读写

启动客户端连接后，在 **远端浏览** 中输入起始 NodeId（例如 Objects 节点 `i=85`），浏览子节点、读取变量，或向具有写权限的变量发送值。读取结果包含数据类型、质量码与时间戳。

> 📷 **截图待补：OPC UA 客户端浏览与读写** — 展示远端节点、读取结果、数据类型和可写变量的写入操作。
> 建议文件名：`opcua-client.png`

<!-- ![OPC UA 客户端浏览与读写](/img/opcua-client.png) -->

## 五、实时订阅、历史与事件

进入客户端 **发布订阅 → 实时数据**，从左侧地址空间添加变量，设置发布间隔、采样间隔、队列、死区及监控模式，点击 **开始订阅**。可在表格和趋势间切换，停止单个订阅或配置自动重连。

> 📷 **截图待补：OPC UA 客户端实时订阅** — 展示地址空间树、监控变量、发布与采样间隔，以及实时表格或趋势。
> 建议文件名：`opcua-subscription.png`

<!-- ![OPC UA 客户端实时订阅](/img/opcua-subscription.png) -->

服务端在 **发布订阅 → 历史数据** 添加变量，配置保留天数和容量，启用历史存储。客户端选择具有历史读取权限的变量及时间范围后查询，分页读取结果；聚合模式取决于远端的 ReadProcessed 支持。

> 📷 **截图待补：OPC UA 历史数据查询** — 展示查询节点、时间范围、读取模式、结果与分页操作。
> 建议文件名：`opcua-history.png`

<!-- ![OPC UA 历史数据查询](/img/opcua-history.png) -->

> 📷 **截图待补：OPC UA 事件订阅** — 展示事件源、严重度筛选、事件列表和详情。
> 建议文件名：`opcua-events.png`

<!-- ![OPC UA 事件订阅](/img/opcua-events.png) -->

事件页可添加具备 EventNotifier 能力的对象作为事件源。服务端生成事件，客户端按事件类型、严重度、关键字和返回字段订阅，并可导出 CSV。

服务端实时数据与事件发布使用 MQTT/JSON：先在 **发布器设置** 中配置 Broker、PublisherId 和 WriterGroup，再配置变量或事件数据集、字段和主题，保存草稿并开始发布。详细步骤见 [发布订阅工作区](../../../OPCUA_PUBSUB)。

> 📷 **截图待补：OPC UA MQTT/JSON 发布器设置** — 展示 Broker 地址、PublisherId、WriterGroup、数据集和主题配置。
> 建议文件名：`opcua-pubsub.png`

<!-- ![OPC UA MQTT/JSON 发布器设置](/img/opcua-pubsub.png) -->

## 六、安全与诊断

在 **证书与安全** 页发现端点、生成应用证书、管理对端信任，配置消息安全模式和身份。用户名身份要求 `SignAndEncrypt`；服务端用户支持 `viewer` 与 `operator` 角色。

> 📷 **截图待补：OPC UA 证书与安全** — 展示消息安全模式、应用证书、对端信任及用户角色；隐藏密码和私钥。
> 建议文件名：`opcua-security.png`

<!-- ![OPC UA 证书与安全](/img/opcua-security.png) -->

在 **会话与通信日志** 查看真实服务调用及状态码。详细排查步骤见 [报文与诊断查看](./packet-view)。
