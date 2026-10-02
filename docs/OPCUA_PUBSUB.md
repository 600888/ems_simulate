# OPC UA 发布订阅工作区

设备页的“发布订阅”包含实时数据、历史数据、事件三个子页。左侧树按层级浏览当前设备的地址空间，搜索筛选已加载节点。节点支持多选拖拽，也可以点击“添加所选节点”。拖入仅修改草稿，保存或点击开始后应用到设备。切换子页保留各自配置。

## 客户端

- 启动设备连接后，在实时数据页添加 Variable 节点，配置发布间隔和监控项的采样、队列、死区、监控模式，然后开始订阅。页面展示实际质量码、源时间戳和服务器修订参数，表格与趋势可以切换。每个订阅可以独立停止，自动重连会恢复已启用的订阅。
- 历史数据页仅接受有 HistoryRead 权限的变量。选择时间范围、原始值/聚合模式、每页上限、时间戳和边界值选项后查询。多节点分别保存 continuation，下一页继续原查询；新查询、移除节点、设备停止和页面卸载会释放 continuation。聚合通过远端原生 ReadProcessed 完成，要求远端支持相应函数；本应用内置 asyncua 服务端目前提供原始历史读取。边界值是否返回也由远端 HistoryRead 实现决定。
- 事件页接受具有 EventNotifier 订阅能力的 Object，支持多事件源、事件类型、最低严重度、消息关键字及返回字段。点击事件行显示详情，结果可以导出 CSV。

客户端历史查询节点按设备保存在浏览器本地；订阅、事件及服务端配置保存在应用数据库中。

## 服务端

1. 在地址空间配置变量并启动服务端。
2. 在实时数据页选择变量 DataSetWriter，拖入变量。字段别名对应 JSON Payload 的字段名。
3. 点击“发布器设置”，填写 PublisherId、MQTT 地址、WriterGroup 和发布间隔；数据集页可增删变量/事件 DataSetWriter，配置 ID、主题、元数据主题和 KeyFrameCount。设置先应用到草稿，返回工作区保存或开始发布。
4. 事件页拖入 Object 作为事件源，选择事件数据集并开始发布。此操作同时启用 UA 事件生成；可以选择事件源、消息和严重度触发测试事件。停止此事件数据集不会停止其他已启用的数据集。
5. 历史数据页选择需要记录的变量，设置保留天数和每节点容量后启用存储。历史数据写入设备独立的 SQLite 文件，客户端经 OPC UA 查询；历史数据不通过 MQTT 推送。

## 当前 MQTT/JSON 范围

- MQTT 传输通过 `aiomqtt==2.5.1` 实现，底层 `paho-mqtt==2.1.0` 由 `uv.lock` 锁定。连接上下文、心跳、报文和 TLS 交给库；发布插件负责重连、元数据重发和完整帧恢复。生产代码不再自行编解码 MQTT 报文。
- Windows 启动入口明确选择支持 `add_reader` 的 Selector 循环，适配 Uvicorn 0.40 自行创建事件循环的行为。直接通过 Uvicorn CLI 启动时需使用 `--loop asyncio:SelectorEventLoop`。
- MQTT 3.1.1，`mqtt://host:port` 或 `mqtts://host:port`，匿名 Broker、QoS 0。TLS 使用系统默认信任验证；不支持用户名密码、WebSocket、UADP 或 MQTT DataSetReader。
- 使用 OPC UA 1.04 可逆 JSON 字段编码，变量发送 `ua-data`，事件发送 `ua-event` DataSetMessage；首次连接和重连保留发布 `ua-metadata`。KeyFrameCount 控制完整帧与变化字段帧。消息/字段内容掩码控制可选标识、质量和时间戳。
- “已发送”表示消息已写入 MQTT 连接，QoS 0 没有订阅端送达确认。连接以成功 CONNACK 为准；失败显示原因，并按 1–30 秒退避重连。Broker 故障不会停止 UA 服务。
- 实时/事件缓存最多 2,000 条，历史查询最多缓存 10,000 条。慢消费者或连接中断造成缺口时显示提示；趋势在断线、缺口或坏质量处中断。

客户端实时订阅仍走原生 OPC UA Subscription；服务端发布走 MQTT/JSON。这两条链路共用工作区，但不互相替代。

## 开发验证

执行 `uv sync --frozen --extra dev` 安装锁定依赖，运行 `pytest tests/protocols/opcua -q`。真实 Broker 测试自动启动本机 Mosquitto；也可设置 `EMS_TEST_MQTT_BROKER_URL=mqtt://127.0.0.1:1883` 指向独立测试 Broker。测试使用随机主题前缀，不要连接生产 Broker。CI 安装 Mosquitto 后执行此测试。
