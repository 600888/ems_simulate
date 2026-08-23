# EMS-Simulate 设计与实施文档

`plan` 目录按“架构、功能、协议、对外材料”分类。新增文档应放入对应主题目录，不再直接堆放在根目录。

## 目录说明

| 目录 | 内容 |
| --- | --- |
| [`architecture/`](architecture/) | 跨模块架构、数据模型和技术评估 |
| [`features/`](features/) | 按产品功能归档的设计与实施计划 |
| [`DNP3/`](DNP3/) | DNP3 协议设计 |
| [`IEC104/`](IEC104/) | IEC104 专题文章、图片和实现方案 |
| [`IEC61850/`](IEC61850/) | IEC61850 专题文章、建模、GOOSE、报告与实现方案 |
| [`submissions/`](submissions/) | 项目申报等对外材料及其配图 |
| [`assets/`](assets/) | 无法归属单篇文档的共享资源 |

## 重点文档

### 架构

- [数据库 V4 测点表复用设计](architecture/database-v4-point-table-reuse-design.md)
- [多进程架构必要性评估](architecture/multiprocessing-architecture-assessment.md)

### 功能

- [服务端客户端连接监控后端实施计划](features/server-connection-monitoring/backend-implementation-plan.md)
- [自动读取后端任务重构计划](features/auto-read/auto-read-backend-task-refactor-plan.md)
- [设备表单协议与安全设计](features/device-configuration/device-form-tabs-protocol-security-design.md)
- [测点级仿真配置设计](features/simulation/point-level-simulation-config-design.md)

### 协议

- [DNP3 实现设计](DNP3/dnp3-implementation-design.md)
- [IEC104 TLS 实施计划](IEC104/implementation/iec104-tls-implementation-plan.md)
- [IEC61850 GOOSE 设备级全栈重构](IEC61850/implementation/goose-device-scoped-fullstack-refactor.md)
- [IEC61850 通用建模工具设计](IEC61850/modeling/iec61850-general-modeling-tool-design.md)

## 维护约定

- 新功能使用 `features/<feature-name>/`，同一功能的前端、后端和测试方案放在同一主题目录。
- 协议专属内容放入协议目录；实现方案放 `implementation/`，建模专题放 `modeling/`。
- 单篇文档专用图片优先与文档同层或放其下级 `image/`；只有跨文档复用的资源才放 `assets/`。
- 文档内部使用相对 Markdown 链接；移动文档时同步修正引用和图片路径。
- 新增重要设计文档后更新本索引。
