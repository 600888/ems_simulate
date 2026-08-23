# GOOSE 按设备全栈重构计划

## 1. 结论

GOOSE 管理应从“全局 Publisher/Receiver 汇总页”重构为“设备上下文内的 GOOSE 工作台”。

- 用户侧归属：设备。
- 后端技术归属：设备的 IEC 61850 `channel_id`。
- 网卡：由后端发现并返回可用网卡，前端只能从有效网卡中选择，不再默认写死 `eth0`。
- 配置：全部持久化；运行状态单独维护，不把内存对象当作配置真相源。
- 发布与订阅：均支持完整编辑，但运行中只允许修改实时值；结构性配置需停止后修改并重建运行对象。
- 抓包：默认跟随当前设备选定的网卡，也允许临时切换网卡；抓包会话按设备隔离。

不建议把 GOOSE 直接挂到数据库 `device_id` 上。当前运行时通过 `channel_id` 定位 IEC 61850 handler/server，而且项目中运行时 device ID 与数据库 device ID 存在混用。第一阶段应统一以 `channel_id` 作为领域归属键，API 响应附带设备名称和数据库 `device_id` 供展示。

## 2. 现状问题

### 2.1 前端

- Publisher/Receiver 的网卡字段是自由文本输入，默认值固定为 `eth0`，没有可用网卡查询和选择器。
- Publisher 创建请求没有传 `channel_id`，导致手工创建的发布配置可能无法归属和持久化。
- Publisher/Receiver 列表接口均查询全局资源，虽然页面接收了 `channelId`，但只用于“发现远端控制块”。
- Publisher 没有完整配置编辑入口；现有更新 API 也仅支持 `go_id/conf_rev/time_allowed_to_live/simulation`。
- 数据集旧条目的名称和类型被禁用，只能改值；订阅只能增删，不能编辑过滤条件和描述。
- Receiver 没有设备归属；同一网卡只允许一个全局 Receiver，多个设备会互相共享订阅。
- 打开设备 GOOSE 页会自动导入发现结果，属于隐式写操作，容易产生错误订阅。
- 页面每 5 秒全量刷新所有资源，配置和运行状态混在一起，扩展后性能和交互都会变差。

### 2.2 后端

- `GooseResourceManager` 是应用级单例，Publisher 以 `go_cb_ref` 为 ID，Receiver 以网卡名为 ID，天然缺少设备隔离。
- `_channel_map` 仅覆盖 Publisher，Receiver、Subscription、Capture 都没有稳定的通道归属。
- 只有 Publisher/Entry 有数据库模型；Receiver/Subscription 没有持久化，重启后会丢失。
- Publisher 更新通过销毁并重建对象实现，但允许更新的字段不完整，且缺少统一的运行态校验和事务回滚。
- API 多数资源操作只传资源 ID，不传 `channel_id`，无法做归属校验，存在跨设备误操作风险。
- 网卡名没有后端校验；Windows/Linux 显示名、接口 ID、MAC、启用状态等信息也没有统一抽象。
- 抓包停止、清空和状态查询偏全局语义，无法可靠对应当前设备或网卡。
- 现有数据库升级主要依赖启动时手写 `ALTER TABLE`，本次多表变更需要显式、可重复、可回滚的迁移脚本。

## 3. 目标领域模型

```text
Device (展示边界)
  └─ IEC61850 Channel (GOOSE 归属边界)
       ├─ GooseProfile
       │    ├─ default_publish_interface
       │    ├─ default_subscribe_interface
       │    └─ default_capture_interface
       ├─ GoosePublisher 1..n
       │    └─ GooseDatasetEntry 0..n
       ├─ GooseReceiver 0..n
       │    └─ GooseSubscription 0..n
       └─ GooseCaptureSession 0..n（仅运行态，默认不持久化）
```

### 3.1 标识与唯一性

- 所有可编辑资源使用数据库生成的整数 ID 或 UUID，不再把 `go_cb_ref`、网卡名作为资源 ID。
- Publisher 唯一约束：`(channel_id, go_cb_ref)`。
- Receiver 唯一约束：`(channel_id, interface_id, name)`；默认每个设备每张网卡一个 Receiver，但模型允许多个。
- Subscription 唯一约束：`(receiver_id, go_cb_ref, app_id)`。
- Entry 使用稳定 ID 和 `sort_order`，更新/删除不再依赖数组下标。

### 3.2 配置态与运行态

数据库是配置真相源，内存 Runtime Registry 只保存已启动实例和实时状态：

```text
Repository -> GooseApplicationService -> RuntimeRegistry -> pyiec61850 adapter
```

- 配置 CRUD 总是先校验并写数据库，再刷新对应运行对象。
- 启停只改变运行态；是否开机自动启动使用单独的 `auto_start` 配置字段。
- 结构性字段变更时要求资源已停止：网卡、GoCBRef、DataSetRef、APPID、目标 MAC、VLAN、条目结构、订阅过滤条件。
- Publisher 运行时允许修改数据集值；成功后递增 `stNum` 并立即发布。
- 所有失败返回稳定错误码，例如 `GOOSE_INTERFACE_NOT_FOUND`、`GOOSE_RESOURCE_RUNNING`、`GOOSE_CONFIG_CONFLICT`。

## 4. 数据库设计

### 4.1 新增/调整表

`goose_profile`

- `channel_id`，唯一外键。
- `publish_interface_id`、`subscribe_interface_id`、`capture_interface_id`。
- `auto_start_publishers`、`auto_start_receivers`。
- `created_at`、`updated_at`。

`goose_publisher`

- 保留现有业务字段。
- `channel_id` 改为非空。
- 增加 `name`、`description`、`auto_start`、`enabled`、`created_at`、`updated_at`。
- `interface` 迁移为 `interface_id`；必要时保留一版兼容读字段。
- 增加 `(channel_id, go_cb_ref)` 唯一约束。

`goose_entry`

- 保留稳定主键。
- 增加 `data_ref`/`fcda_ref`（名称用于展示，引用用于绑定模型）。
- 类型和名称允许编辑，但必须在 Publisher 停止时进行。
- 排序使用 `sort_order`，提供批量重排接口。

`goose_receiver`

- `id`、`channel_id`、`name`、`description`、`interface_id`、`enabled`、`auto_start`、时间戳。

`goose_subscription`

- `id`、`receiver_id`、`go_cb_ref`、`app_id`、`dst_mac`、`description`。
- 增加期望的 `data_set_ref`、`conf_rev` 和可选源 MAC，用于一致性检查。
- 实时 `state/st_num/sq_num/last_update/data_values` 不持久化。

### 4.2 迁移策略

1. 备份数据库并建立 schema 版本表。
2. 新建 Receiver/Subscription/Profile 表及新列，暂不删除旧字段。
3. 将已有 Publisher 按 `channel_id` 迁移；`channel_id IS NULL` 的记录进入迁移报告，不自动猜归属。
4. 将现有 `interface` 文本解析成 `interface_id`；匹配失败则保留原值并标记 `needs_review`。
5. 应用双读单写一版：优先新字段，兼容旧数据。
6. 验证后删除兼容代码和旧字段。

迁移脚本必须支持 dry-run、重复执行、迁移统计和失败回滚。

## 5. 网卡资源服务

新增与协议无关的 `NetworkInterfaceService`：

- API 返回 `id/name/display_name/mac/ipv4/ipv6/is_up/is_loopback/supports_raw_ethernet`。
- Linux 使用稳定接口名；Windows 将系统接口 GUID/适配器名称映射为 pyiec61850/pcap 实际可接受的标识。
- 创建或更新配置时后端重新校验接口存在、已启用且支持二层原始报文。
- 前端展示“友好名称 + IP + MAC”，提交稳定 `interface_id`。
- 网卡消失时配置仍保留，但状态显示“网卡不可用”，禁止启动，不静默回退到第一张网卡。

建议接口：

- `GET /api/network-interfaces?capability=goose`
- `POST /api/network-interfaces/validate`

## 6. 后端重构

### 6.1 分层

- `domain/`：Publisher、Receiver、Subscription、Entry 配置和值对象及校验规则。
- `application/goose_service.py`：按 `channel_id` 编排 CRUD、启停、发布、导入和权限/归属校验。
- `infrastructure/repositories/`：SQLAlchemy Repository。
- `runtime/registry.py`：键为 `(channel_id, resource_id)` 的运行对象注册表。
- `runtime/publisher_runtime.py`、`receiver_runtime.py`、`capture_runtime.py`：封装 pyiec61850 生命周期。
- Web 路由只做 schema 转换，不再访问 manager 私有字段或直接查运行时设备。

### 6.2 API v2

所有业务接口显式带 `channel_id`，并先验证其为 IEC 61850 通道：

- `GET /api/channels/{channel_id}/goose/overview`
- `GET/POST /api/channels/{channel_id}/goose/publishers`
- `GET/PATCH/DELETE /api/channels/{channel_id}/goose/publishers/{publisher_id}`
- `POST /api/channels/{channel_id}/goose/publishers/{publisher_id}:start|stop|publish`
- `PUT /api/channels/{channel_id}/goose/publishers/{publisher_id}/entries`（批量、事务化）
- `PATCH /api/channels/{channel_id}/goose/publishers/{publisher_id}/entries/{entry_id}/value`
- `GET/POST /api/channels/{channel_id}/goose/receivers`
- `GET/PATCH/DELETE /api/channels/{channel_id}/goose/receivers/{receiver_id}`
- `POST /api/channels/{channel_id}/goose/receivers/{receiver_id}:start|stop`
- `PUT /api/channels/{channel_id}/goose/receivers/{receiver_id}/subscriptions`
- `GET /api/channels/{channel_id}/goose/discovered`
- `POST /api/channels/{channel_id}/goose/discovered:import`（显示预览并由用户确认）
- `POST/GET/DELETE /api/channels/{channel_id}/goose/captures...`

列表响应统一包含 `config`、`runtime`、`validation_issues`，避免用一个扁平对象混合三种语义。配置更新使用 `revision` 或 `updated_at` 做乐观锁。

### 6.3 兼容与清理

- 旧 `/goose/*` API 保留一个版本，内部转发到新服务并输出弃用日志。
- 禁止新代码访问 `manager._channel_map` 等私有字段。
- 修复 `get_device_by_id(channel_id)` / `get_device_by_channel_id(channel_id)` 的混用，统一通过一个 `Iec61850ChannelContextResolver` 获取 handler/server。
- 应用启动时按 `auto_start` 从数据库恢复；失败只标记该资源错误，不影响其他设备启动。

## 7. 前端重构

### 7.1 信息架构

保留侧边栏设备下的 GOOSE 节点，路由改为：

`/devices/:deviceId/channels/:channelId/goose`

页面顶部固定显示设备、通道、协议角色、默认发布/订阅网卡和总体状态。主体分为：

- 概览：发布数、订阅健康度、网卡状态、最近错误。
- 发布：当前设备的 Publisher 卡片/表格。
- 订阅：Receiver 与其 Subscription 的主从视图。
- 发现：只读发现结果，勾选后显式导入。
- 抓包：当前设备的会话和报文。

不再提供默认的全局编辑页。如需运维总览，另建只读“GOOSE 总览”，点击后进入具体设备。

### 7.2 组件拆分

- `GooseWorkspace.vue`：设备上下文与页签。
- `GooseOverview.vue`。
- `PublisherList.vue`、`PublisherEditorDrawer.vue`、`DatasetEntryEditor.vue`。
- `ReceiverList.vue`、`ReceiverEditorDrawer.vue`、`SubscriptionEditor.vue`。
- `DiscoveredGooseImport.vue`。
- `NetworkInterfaceSelect.vue`：发布、订阅、抓包共用。
- `GooseCapturePanel.vue`。
- Pinia `useGooseStore(channelId)`：缓存配置；实时状态单独轮询或 WebSocket 更新。

### 7.3 编辑体验

Publisher 编辑器至少覆盖：

- 名称/描述、网卡、GoCBRef、GoID、DataSetRef。
- APPID（十进制和十六进制联动）、目标 MAC（自动建议 `01-0C-CD-01-xx-xx`）。
- ConfRev、TAL/最小与最大重发时间、VLAN ID/优先级、Simulation、Auto Start。
- 数据集条目的引用、名称、类型、初始值、顺序和批量导入。

Receiver/Subscription 编辑器至少覆盖：

- Receiver 名称、网卡、描述、Auto Start。
- GoCBRef、APPID、目标/源 MAC、期望 DataSetRef、ConfRev、描述。
- 运行状态、最后报文时间、丢失原因、stNum/sqNum 和数据值。

运行中打开编辑器时，结构字段只读并明确提示“停止后可编辑”；值字段仍可实时写入。保存采用一次批量请求，不循环逐条调用 API。

## 8. SCL/ICD 导入整合

- 导入结果必须绑定目标 `channel_id` 和用户选择的网卡。
- 先展示 Publisher/Subscription 差异预览：新增、更新、冲突、删除候选。
- 冲突策略由用户选择：跳过、覆盖、复制为新配置。
- 导入使用数据库事务；任何结构注册失败时回滚配置，并返回逐项错误。
- 删除当前“进入页面即自动导入订阅”的行为。
- SCL 地址信息中的 APPID/MAC/VLAN 优先于默认值，网卡属于本机部署信息，不从 SCL 猜测。

## 9. 实施阶段

### Phase 0：契约冻结与测试基线（1 天）

- 为现有 API、Publisher 持久化、启停和 SCL 导入补回归测试。
- 采集一份 Linux 和 Windows 的网卡/发布/订阅实机样本。
- 冻结 v1 行为，明确迁移数据统计。

### Phase 1：网卡服务与设备上下文（1～2 天）

- 实现网卡发现/校验 API 和前端通用选择器。
- 实现统一的 IEC 61850 channel context resolver。
- Publisher、Receiver、Capture 创建时禁止无效网卡。

### Phase 2：数据库与 Repository（2～3 天）

- 新增 Profile、Receiver、Subscription 表并调整 Publisher/Entry。
- 编写 dry-run 迁移、回滚和异常数据报告。
- Repository 单元测试覆盖唯一约束、级联删除和事务。

### Phase 3：领域服务与运行时注册表（3～4 天）

- 用 `(channel_id, resource_id)` 隔离运行对象。
- 完成完整 CRUD、运行态约束、错误码、自动启动和故障隔离。
- 支持批量 Entry/Subscription 更新和回滚。

### Phase 4：API v2 与兼容层（2 天）

- 上线按通道作用域的 REST API。
- v1 转发并记录弃用；OpenAPI 和前端类型从同一契约生成或校验。
- 增加跨设备资源 ID 访问测试，必须返回 404/冲突而不是误操作。

### Phase 5：前端工作台（3～5 天）

- 新路由、概览、发布、订阅、发现、抓包页签。
- 完整编辑器、网卡选择、运行态锁定、校验和错误展示。
- 配置查询与实时状态刷新拆分，移除全局 5 秒全量刷新。

### Phase 6：SCL/ICD 导入与联调（2～3 天）

- 增加差异预览、网卡映射和显式确认。
- 验证同一网卡上多个设备的逻辑隔离，以及多个网卡并行发布/订阅。

### Phase 7：清理与发布（1～2 天）

- 数据迁移演练、性能/稳定性测试、文档和升级说明。
- 移除旧页面的全局写入口；下一版本再删除 v1 API 和兼容字段。

预计总工作量：15～21 个工程日；若需要 Windows/Linux 双平台二层报文实机验收，另预留 2～3 天。

## 10. 测试矩阵

- 单元测试：领域校验、MAC/APPID/VLAN、网卡映射、状态机、Repository。
- API 测试：按通道过滤、完整编辑、运行中禁止结构修改、乐观锁、跨设备隔离。
- 迁移测试：空库、旧库、空 `channel_id`、重复 GoCBRef、失效网卡、重复执行和回滚。
- 前端测试：设备切换不串数据、表单校验、十六进制 APPID、运行态字段锁定、导入确认。
- 集成测试：双设备同网卡、单设备双网卡、Publisher 到 Receiver 回环、VLAN 报文、超时 LOST 恢复。
- 稳定性测试：连续启停 100 次、运行 24 小时、设备删除/重载、网卡断开再恢复、应用重启自动恢复。

## 11. 验收标准

- 从任一 IEC 61850 设备进入 GOOSE，只能看到和操作该设备的资源。
- 发布、订阅和抓包都能从后端返回的真实网卡列表中选择网卡。
- Publisher 所有协议配置和数据集结构均可编辑；Subscription 所有过滤与描述字段均可编辑。
- Receiver/Subscription 重启应用后配置不丢失。
- 运行中不能误改结构配置，停止后修改可正确重建并再次启动。
- SCL/ICD 导入不会静默创建订阅，用户可预览差异并选择网卡。
- 两个设备使用相同 GoCBRef 或相同网卡时不会互相覆盖或串状态。
- 旧 Publisher 数据可迁移；无法确定归属的数据会被报告且不会被错误绑定。
- Windows 和 Linux 至少各完成一次真实 GOOSE 发布、订阅和抓包验收。

## 12. 推荐的首个交付切片

先完成 Phase 0～2，并交付一个可独立验收的纵向切片：

1. 当前设备的 Publisher 列表按 `channel_id` 过滤。
2. 手工创建 Publisher 必须携带 `channel_id` 并持久化。
3. 发布网卡改为真实网卡选择器并由后端校验。
4. Publisher 完整编辑在停止状态可用。
5. 不改 Receiver 运行机制，但先隐藏全局串数据风险并建立新表迁移。

这个切片能最快解决用户当前最明显的问题，同时为 Receiver/Subscription 的彻底重构建立正确的数据基础。
