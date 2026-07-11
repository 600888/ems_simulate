# GOOSE 按设备作用域全栈重构

日期：2026-07-11

## 变更摘要

- Publisher、Receiver、Subscription 和抓包会话均按 IEC 61850 `channel_id` 隔离。
- Publisher 和 Receiver 支持选择后端发现的真实网卡；无效、禁用或环回网卡不能启动 GOOSE。
- Publisher 支持完整协议配置编辑，数据集条目支持批量、事务化替换。
- Receiver/Subscription 新增数据库持久化，应用重启后可恢复并支持 `auto_start`。
- Subscription 支持编辑 APPID、MAC、DataSetRef、ConfRev 和描述。
- 发现的 GOOSE 控制块不再自动写入配置，必须选择网卡并显式确认导入。
- SCL/ICD 导入默认不覆盖现有 GOOSE 配置，仅在明确开启自动创建时写入。
- WebSocket 抓包命令和报文广播按通道隔离，避免设备之间串包。

## 数据库升级

启动时会自动创建 `goose_receiver`、`goose_subscription` 表，并为旧版
`goose_publisher` 补齐显示名称、描述和自动启动字段。Publisher 原有数据继续保留。

## 新增接口

- `GET /api/network-interfaces`
- `POST /api/network-interfaces/validate`
- `POST /api/channels/goose/publishers/entries/replace`
- `POST /api/channels/goose/receivers/update`
- `POST /api/channels/goose/receivers/subscriptions/replace`

原有 GOOSE API 继续保留，但列表和资源操作增加 `channel_id`，用于设备归属校验。

## 验证

- Ruff 全量检查通过。
- 前端 Vue/TypeScript 类型检查及生产构建通过。
- GOOSE 设备隔离、完整配置更新、Receiver 持久化和原有抓包测试共 6 项通过。
