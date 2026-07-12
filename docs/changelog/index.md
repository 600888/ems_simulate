# 更新日志

> 记录项目各模块的详细变更记录、重构计划和设计方案。
> 文档按时间倒序排列，序号反映实际开发时间线。

## 功能模块变更

| 文档 | 说明 |
|------|------|
| [IEC104 协议全 ASDU 类型支持](./01-iec104-asdu-type-support) | IEC104 全 ASDU 类型支持 — 日期：2026-04-29 |
| [Web API 层重构](./02-api-refactoring) | 前后端代码架构重构，去除硬编码 — 日期：2026-05-01 |
| [Ruff 代码质量工具引入计划](./03-ruff-introduction-plan) | Ruff 代码质量工具引入 — 版本：1.1，日期：2026-06-01，状态：第 1~2 阶段已完成 |

## IEC 61850

### 核心架构

| 文档 | 说明 |
|------|------|
| [模块化重构计划](./iec61850/02-iec61850-refactoring-plan) | IEC61850 代码架构重整，插件模式 — 版本：1.0，日期：2026-05-30 |
| [统一模型架构重构](./iec61850/09-iec61850-unified-model-refactoring) | 模型发现重构 + SCL 模块 + 全局单次发现 — 版本：3.0，日期：2026-06-02 |
| [数据存储架构与协议流程整改计划](./iec61850/18-iec61850-data-storage-optimization-plan) | ICD 文件权威存储 + 流程解耦 + 数据清理 — 版本：1.0，日期：2026-06-27 |

### GOOSE

| 文档 | 说明 |
|------|------|
| [GOOSE 专题总览](./iec61850/goose/) | GOOSE 当前能力地图、核心约束、阅读路线和快速排障 |
| [GOOSE 接收、DataSet 历史与抓包链路重构](./iec61850/goose/04-receive-history-capture-refactoring) | Windows Npcap 接收、BER 解码、DataSet 映射、历史环形队列、WebSocket 与前端性能优化 — 日期：2026-07-12 |
| [GOOSE 按设备作用域全栈重构](./iec61850/25-goose-device-scoped-refactoring) | 网卡选择、设备隔离、完整编辑与订阅持久化 — 日期：2026-07-11 |
| [GOOSE 模块插件化重构](./iec61850/06-goose-plugin-refactoring) | GOOSE 插件化重构 — 版本：1.0，日期：2026-05-31 |
| [GOOSE 功能支持](./iec61850/01-goose-support) | IEC61850 增加 GOOSE 支持 + 前端管理界面 — 日期：2026-05-04 |

### Reports

| 文档 | 说明 |
|------|------|
| [Reports 报告功能](./iec61850/03-iec61850-reports-support) | 61850 报告插件 + dataset 发现修复 — 版本：1.0，日期：2026-05-30 |
| [Reports 树形数据展示重构](./iec61850/17-iec61850-report-tree-ui-refactoring) | Reports 报告树形数据展示 + 前后端重构 + UI 优化 — 版本：1.0，日期：2026-06-24 |
| [报告回调崩溃与禁用逻辑修复](./iec61850/15-iec61850-report-callback-crash-fix) | RCB 回调注销崩溃 + URCB 禁用逻辑修复 — 日期：2026-06-19 |
| [报告 GI 与 DataSet 读取修复](./iec61850/16-iec61850-report-gi-dataset-read-fix) | 多报告 GI 路由修复 + URCB 软件 GI + MMS DataSet 批量读取 — 日期：2026-06-22 |
| [服务端总召唤与主动报告修复](./iec61850/19-iec61850-server-gi-spontaneous-report-fix) | DA 触发语义恢复 + 运行时 GI 能力 + DataSet/RCB 去重 — 日期：2026-06-28 |
| [DataSet 批量读取、进度展示与软件 GI 修复](./iec61850/22-iec61850-dataset-batch-read-progress-gi-fix) | DataSet 优先批读 + 实时进度 + URCB 软件 GI 严格批读 — 日期：2026-07-04 |
| [报告上送与 DataModel 并发读取崩溃修复](./iec61850/23-iec61850-report-datamodel-concurrency-crash-fix) | 双 MMS 连接隔离 + GIL-safe 原生调用 + 报告回调安全排空 — 日期：2026-07-04 |

### 模型与发现

| 文档 | 说明 |
|------|------|
| [SCL 文件模块](./iec61850/04-iec61850-scl-file-module) | IEC61850 文件服务 — 日期：2026-05-31（已废弃，合并至 09） |
| [SCL 模块重构实施](./iec61850/07-iec61850-scl-refactoring-implementation) | 文件列表加载 + 下载 Bug 修复 — 日期：2026-05-31（已废弃，合并至 09） |
| [模型导出优化方案](./iec61850/08-iec61850-model-export-optimization) | IEC61850 客户端导出模型优化 — 日期：2026-06-02（已废弃，合并至 09） |
| [测点注册表精简优化](./iec61850/11-iec61850-point-registry-optimization) | 模型发现慢问题修复 — 日期：2026-06-03 |
| [元数据按需读取服务](./iec61850/12-iec61850-metadata-reader) | 品质描述读取 — 日期：2026-06-03 |
| [模型发现性能优化](./iec61850/13-iec61850-discovery-performance-optimization) | 发现性能优化 — 版本：1.0，日期：2026-06-06 |
| [文件下载服务模块](./iec61850/05-iec61850-file-download-module) | 文件下载服务 — 日期：2026-05-31 |
| [ICD 导出器修复](./iec61850/14-iec61850-icd-exporter-fix) | 导出模型类型模板膨胀与数据失真修复 — 日期：2026-06-06 |
| [MMS 类型识别与标签样式优化](./iec61850/21-iec61850-mms-type-tag-ui) | 在线模型 MMS 类型补全 + 测点表格标签化与分类配色 — 日期：2026-07-02 |

### 性能与稳定性

| 文档 | 说明 |
|------|------|
| [客户端模型发现进度条修复](./iec61850/20-iec61850-client-discovery-progress-fix) | 发现模型进度展示稳定性修复 + 后端进度快照 + 秒数同步 — 日期：2026-06-29 |
| [超大模型性能、超时与服务状态治理](./iec61850/24-iec61850-large-model-performance-timeout-fix) | 大模型发现与服务状态稳定性治理 — 日期：2026-07-06 |

### 界面与交互

| 文档 | 说明 |
|------|------|
| [前端 UI 设计](./iec61850/10-iec61850-frontend-ui-design) | 模型发现 Bug 修复 + UI 设计 — 日期：2026-06-02 |

## Optimization

| 文档 | 说明 |
|------|------|
| [MSIX 打包后端进程启动修复](./optimization/msix-backend-startup-fix) | MSIX 后端启动修复 + 代码拆分重构 — 日期：2026-06-17 |
| [消除应用启动黑框闪现](./optimization/startup-black-screen-elimination) | Tauri + PyInstaller 启动控制台黑框彻底消除 — 日期：2026-06-13 |
