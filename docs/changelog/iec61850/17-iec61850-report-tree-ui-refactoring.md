# IEC61850 Reports 树形数据展示重构

> 版本: 1.0  
> 日期: 2026-06-24  
> 分类: Reports / 前后端重构 / UI 优化  
> 状态: 已实施


## 1. 问题背景

IEC61850 Reports 功能已经支持 RCB 发现、报告使能、GI 触发和报告缓存查询，但前端展示仍停留在扁平表格阶段。报告中的数据引用通常是 IEC61850 层级路径，例如：

```text
LD0/GGIO1.Ind1.stVal
LD0/GGIO1.Ind1.q
LD0/GGIO1.Ind1.t
```

旧界面直接把 `data_values` 展示成 key/value 列表，无法体现 `LD → LN → DO → DA/BDA` 的模型结构，也不便查看 Quality、Timestamp 这类复合含义数据。

本次重构目标是参考 IEDScout 的报告数据展示方式，在保留原有 RCB 控制能力的基础上，将“最近一次报告数据”和“报告数据页面”改造为树形表格。

| 模块 | 重构前 | 重构后 |
|------|--------|--------|
| 最近报告 | 描述表 + 扁平数据项 | IEDScout 风格树形表格 |
| 报告历史 | 扁平报告列表 | 历史列表 + 选中报告树形详情 |
| 报告值解析 | `data_values` 原样展示 | `LD/LN/DO/DA` 层级归并 |
| Quality | 原始值展示 | 展开 Validity、Quality Details、Source、Test、OperatorBlocked |
| Timestamp | 原始毫秒值展示 | 展开时间、秒、UnixMs、Fraction |


## 2. 设计目标

### 2.1 保持原有控制能力

以下能力保持兼容，不改变原有业务流程：

- RCB 列表发现。
- RCB 属性展示。
- `RptEna` 使能/禁用。
- `TrgOps` 与 `OptFields` 配置。
- GI 触发。
- 报告数据轮询。

### 2.2 新增报告数据树形结构

新增后端树形转换层，将报告缓存中的扁平结构：

```json
{
  "data_values": {
    "LD0/GGIO1.Ind1.stVal": true,
    "LD0/GGIO1.Ind1.q": 0,
    "LD0/GGIO1.Ind1.t": 1000
  },
  "reason_codes": {
    "LD0/GGIO1.Ind1.stVal": "gi"
  }
}
```

转换为前端可直接渲染的树形节点：

```text
LD0
└── GGIO1
    └── Ind1
        ├── stVal = true
        ├── q = good
        │   ├── Validity = good
        │   ├── Quality Details
        │   ├── Source = process
        │   ├── Test = false
        │   └── OperatorBlocked = false
        └── t = 1970-01-01 08:00:01.000
```

### 2.3 继续使用 REST 轮询

本次没有引入 WebSocket。原因：

1. 现有 Reports 数据缓存已经通过 REST 查询。
2. 轮询模式更容易兼容 Tauri 桌面场景。
3. WebSocket 需要额外处理连接生命周期、断线重连、订阅清理等逻辑，超出本次 UI 重构范围。


## 3. 后端重构

### 3.1 新增 ReportTreeBuilder

新增纯转换模块：

```text
src/proto/iec61850/plugins/reports/report_tree.py
```

该模块不依赖 FastAPI、pyiec61850 和设备连接，只负责把单条报告缓存转换为树节点，便于单元测试和后续复用。

支持的引用格式：

| 输入格式 | 示例 | 解析结果 |
|----------|------|----------|
| 点号格式 | `LD0/GGIO1.Ind1.stVal` | `LD0 → GGIO1 → Ind1 → stVal` |
| 带 FC 点号格式 | `LD0/GGIO1.ST.Ind1.stVal` | 识别 `ST` 为 FC |
| `$` MMS 格式 | `LD0/GGIO1$ST$Ind1$q` | 识别 `ST` 为 FC，展开 q |
| fallback | `data[0]` | 归入 `Unmapped Data` |

### 3.2 树节点模型

后端返回统一的 `ReportTreeNode`：

```python
class ReportTreeNode(BaseModel):
    id: str
    label: str
    node_type: str
    fc: str | None
    reason: str | None
    value: Any
    raw_ref: str | None
    children: list[ReportTreeNode]
```

字段说明：

| 字段 | 说明 |
|------|------|
| `id` | 前端 tree table 的稳定 row-key |
| `label` | 节点显示名 |
| `node_type` | `ld/ln/do/da/bda/group/value` |
| `fc` | 功能约束，如 `ST/MX` |
| `reason` | 报告包含原因，如 `gi/data-change` |
| `value` | 节点值 |
| `raw_ref` | 原始报告引用 |
| `children` | 子节点 |

### 3.3 新增 data-tree 接口

新增接口：

```text
POST /api/channels/iec61850/reports/data-tree
```

请求体：

```json
{
  "channel_id": 12,
  "rcb_ref": "LD0/LLN0.brcb01",
  "entry_key": null,
  "latest": true
}
```

响应体：

```json
{
  "rcb_ref": "LD0/LLN0.brcb01",
  "entry": {
    "entry_key": "2026-06-24 10:00:00.000|1|0",
    "index": 0,
    "seq_num": 1,
    "received_at": "2026-06-24 10:00:00.000",
    "value_count": 3
  },
  "tree_items": []
}
```

原有接口保持不变：

```text
POST /api/channels/iec61850/reports/data
```

前端仍用该接口获取历史列表，再用 `data-tree` 获取某一条报告的树形详情。

### 3.4 Quality 解码

`q` 支持按 IEC61850 Quality packed bits 解码：

| 子字段 | 含义 |
|--------|------|
| `Validity` | `good/invalid/questionable/reserved` |
| `Quality Details` | Overflow、OutOfRange、BadReference、Oscillatory、Failure、OldData、Inconsistent、Inaccurate |
| `Source` | `process/substituted` |
| `Test` | 测试位 |
| `OperatorBlocked` | 操作员闭锁 |

若 `q` 无法解析为 packed bits，则作为普通值展示，不丢弃原始数据。

### 3.5 Timestamp 解码

`t` 按 Unix 毫秒解析，展开：

| 子字段 | 说明 |
|--------|------|
| `Datetime` | 格式化时间 |
| `Seconds` | 秒 |
| `UnixMs` | Unix 毫秒 |
| `Fraction` | IEC61850 fraction 近似值 |


## 4. 前端重构

### 4.1 组件拆分

原 `ReportsManager.vue` 体积较大，同时承担 RCB 树、配置表单、报告历史和报告值展示。本次拆分为：

| 组件 | 职责 |
|------|------|
| `ReportsManager.vue` | 页面状态编排、轮询、接口调用 |
| `RcbTreePanel.vue` | 左侧 RCB 树、搜索、选中 |
| `ReportControlPanel.vue` | RCB 属性、RptEna、TrgOps、OptFields、GI 操作 |
| `ReportDataTreeTable.vue` | IEDScout 风格树形报告数据表 |
| `ReportHistoryPanel.vue` | 报告历史列表与 entry 选择 |

拆分后，`ReportsManager.vue` 不再包含大量表格模板和 checkbox 表单逻辑，页面职责更清晰。

### 4.2 树形报告表格

`ReportDataTreeTable.vue` 使用 Element Plus tree table：

| 列 | 说明 |
|----|------|
| `Name` | LD/LN/DO/DA/BDA 名称 |
| `FC` | 功能约束 |
| `Reason` | 报告原因 |
| `Value` | 当前值 |

视觉参考 IEDScout：

- 浅灰色表格底色。
- DO/DA 使用蓝色短标签。
- 行高保持紧凑。
- 值列使用单行省略，避免长引用撑开表格。

### 4.3 最近报告与历史报告

页面现在有两个数据展示入口：

1. **最近报告信息**
   - 默认展示最新一条报告的树形数据。
   - 自动刷新时更新 latest tree。

2. **报告数据**
   - 左侧展示历史报告列表。
   - 点击某条历史报告后，右侧加载对应 entry 的树形详情。
   - `entry_key` 用 `received_at + seq_num + index` 生成，避免报告没有独立 ID 时无法选中。

### 4.4 配置项显示优化

`TrgOps` 和 `OptFields` 的选项显示改为中文 + IEC 字段名：

```text
数据变化 (dchg)
品质变化 (qchg)
数据更新 (dupd)
周期 (period)
总召唤 (gi)

序号 (seqNum)
时标 (timeStamp)
数据集引用 (dataSet)
变化原因 (reasonCode)
数据引用 (dataRef)
入口 ID (entryID)
配置引用 (configRef)
缓冲溢出 (bufOvfl)
```

报告已使能时，恢复提示：

```text
报告已使能，无法修改属性。请先取消"报告使能"并点击"应用配置"禁用后，再设置属性。
```

复选框尺寸保持旧版交互规格：

- checkbox 输入框：18px。
- label 字体：15px。
- 行高：32px。


## 5. 修改文件清单

### 5.1 后端

| 文件 | 说明 |
|------|------|
| `src/proto/iec61850/plugins/reports/report_tree.py` | 新增报告树形转换器、引用解析、q/t 解码、entry 选择 |
| `src/web/api/channel/report.py` | 新增 `/iec61850/reports/data-tree` 接口 |
| `src/web/api/schemas/report.py` | 新增 ReportTree 请求/响应 schema |
| `src/web/api/schemas/__init__.py` | 导出新增 schema |
| `src/tests/iec61850/test_report_tree.py` | 新增报告树形转换单元测试 |

### 5.2 前端

| 文件 | 说明 |
|------|------|
| `front/src/api/reportApi.ts` | 新增 `ReportTreeNode`、`ReportDataTreeResponse`、`getReportDataTree()` |
| `front/src/constants/api.ts` | 新增 `REPORT_API.DATA_TREE` |
| `front/src/components/reports/ReportsManager.vue` | 重构为页面状态编排层 |
| `front/src/components/reports/RcbTreePanel.vue` | 新增 RCB 树组件 |
| `front/src/components/reports/ReportControlPanel.vue` | 新增 RCB 配置与操作组件 |
| `front/src/components/reports/ReportDataTreeTable.vue` | 新增报告树表组件 |
| `front/src/components/reports/ReportHistoryPanel.vue` | 新增历史报告列表组件 |
| `front/src/i18n/locales/zh-CN.ts` | 新增报告历史、树表名称文案 |
| `front/src/i18n/locales/en-US.ts` | 新增对应英文文案 |


## 6. 验证结果

### 6.1 后端单元测试

新增测试覆盖：

| 测试项 | 结果 |
|--------|------|
| dot ref 解析 | 通过 |
| dollar ref + FC 解析 | 通过 |
| `data[i]` fallback | 通过 |
| Quality packed bits 解码 | 通过 |
| Timestamp UnixMs 解码 | 通过 |
| 同一 DO 下 `stVal/q/t` 合并 | 通过 |
| latest entry 选择 | 通过 |
| entry_key 不存在 | 通过 |
| 空缓存 | 通过 |

执行结果：

```text
python -m unittest src.tests.iec61850.test_report_tree

Ran 9 tests in 0.000s
OK
```

### 6.2 前端类型检查

```text
npm.cmd run type-check
```

结果：

```text
vue-tsc --build
通过
```

### 6.3 前端构建

```text
npm.cmd run build:fast
```

结果：

```text
vite build
✓ built
```


## 7. 风险与注意事项

### 7.1 设备返回引用不完整

部分报告可能只返回 `data[0]`、`data[1]`，没有 DataRef。此时后端无法还原真实 DO/DA 层级，会归入 `Unmapped Data`，保证数据仍可见。

### 7.2 q/t 解码依赖值类型

`q` 优先解析 packed integer 或 quality-like dict。若设备返回不可解析字符串，则不展开子字段，只显示原值。

`t` 按 Unix 毫秒解析。若设备返回格式化字符串，则作为普通值展示。

### 7.3 entry_key 是缓存级标识

报告缓存目前没有后端持久 ID，`entry_key` 由 `received_at + seq_num + index` 生成。缓存滚动淘汰后，旧 `entry_key` 可能失效，此时接口返回“报告条目不存在或已被缓存淘汰”。

### 7.4 服务端模式

服务端模式仍保留 RCB 列表与属性展示；报告数据树主要面向 IEC61850 客户端订阅收到的报告缓存。


## 8. 总结

本次重构把 Reports 页面从“控制块配置 + 扁平数据列表”升级为“控制块配置 + 报告树形数据浏览”：

- 后端新增纯转换层，统一解析报告引用并生成树节点。
- 前端拆分组件，降低 `ReportsManager.vue` 复杂度。
- 最近报告和历史报告都支持 IEDScout 风格树形表格。
- Quality 和 Timestamp 可以按 IEC61850 语义展开。
- 保留 REST 轮询和原有报告控制接口，兼容现有业务流程。

重构后，用户可以更直观地按 `LD/LN/DO/DA` 层级查看报告内容，尤其适合分析 `stVal/q/t`、品质明细和总召唤结果。
