# IEC61850 DataSet 批量读取、进度展示与软件 GI 修复

> 版本: 1.0  
> 日期: 2026-07-04  
> 分类: DataSet / 批量读取 / Reports / 前后端 / Bug 修复  
> 状态: 已实施

## 1. 问题背景

IEC61850 客户端原有的 `read_points_batch()` 虽然提供了批量接口，但内部仍按测点逐个调用 MMS 单点读取服务。大规模 IED 包含数千个测点时，会产生大量网络往返，并引出以下问题：

| 问题 | 原有表现 | 影响 |
|------|----------|------|
| 批量读取名不副实 | 按类型分组后逐点 `readObject` | MMS 请求数量随测点数线性增长 |
| 读取进度不可见 | HTTP 请求期间进度停留在 0%，结束后直接跳到 100% | 用户无法判断任务是否正常执行 |
| 软件 GI 逐点退化 | URCB 软件 GI 在 DataSet 读取失败后逐成员补读 | 大 DataSet 触发大量 MMS 请求，GI 响应缓慢 |
| DataSet 成员全部报错 | 日志出现 `values=0, errors=240` 等信息 | 设备已配置 DataSet，但客户端未能正确批读 |
| 模型发现职责混淆 | 尝试用 DataSet 返回值补全或反向构建模型 | 容易遗漏未进入 DataSet 的 DO/DA，并产生错误类型映射 |

本次整改的目标是：保持完整模型发现不缩水，将测点批量读取真正改为 DataSet 优先，并把每个 DataSet 的读取进度反馈到前端；URCB 软件 GI 必须保持一次 DataSet 批读语义，不再静默退化成逐点读取。

## 2. 设计边界

### 2.1 模型发现仍然是模型驱动

DataSet 是完整 IEC61850 模型的引用子集，不包含足以重建模型的全部元数据。因此在线发现固定遵循以下顺序：

1. 通过 MMS 目录服务完整发现 LD、LN、DO、DA/BDA。
2. 在完整模型已经建立后，发现 DataSet、FCDA、RCB 和 GoCB。
3. 将 FCDA 引用映射回模型节点，建立批量读取索引。
4. 未进入任何 DataSet 的测点仍保留在模型中，并允许单点兼容读取。

DataSet 只用于运行时批量读取和报告数据获取，不作为模型定义来源，也不替代完整模型目录遍历。

### 2.2 保持公开接口兼容

以下公开接口的调用方式和返回结构保持不变：

- `IEC61850Client.read_points_batch(addresses, fc_map)`
- `IEC61850Client.read_dataset_values(dataset_ref)`
- `IEC61850ClientHandler.read_points_batch(points)`
- `get_discovered_datasets()`
- `/api/channels/iec61850-read-points`
- `/api/devices/iec61850-connect-progress`

进度回调、读取计划和成员级错误均为内部能力。原连接进度接口扩展为 IEC61850 统一任务进度接口，但路由保持不变。

## 3. DataSet 批量读取整改

### 3.1 分层职责

DataSet 读取拆分为四个职责层：

| 模块 | 职责 |
|------|------|
| `models.py` | DataSet、FCDA 成员、读取计划、成员错误等不可变领域对象 |
| `catalog.py` | 引用规范化、完整模型校验、测点到 DataSet 的反向索引 |
| `transport.py` | 一次 NamedVariableList MMS 请求、资源释放、类型与错误解析 |
| `datasets/__init__.py` | 规划、执行、重连、缺失点回退、进度回调和统计日志 |

客户端门面和 Reader 只负责传递请求，不再维护重复的 DataSet 解析或逐类型伪批量逻辑。

### 3.2 确定性读取计划

`DatasetReadPlanner` 对请求地址去重后，通过反向索引选择覆盖请求测点的 DataSet。多个 DataSet 重叠时使用稳定的贪心规则：

1. 优先选择覆盖未读取测点最多的 DataSet。
2. 覆盖数相同时，优先选择成员更少的 DataSet。
3. 仍相同时，按 DataSet 引用排序。

每个选中的 DataSet 在同一批次中最多读取一次。只有未覆盖、成员访问错误、解码失败或结构校验失败的测点进入单点回退，成功成员不会重复读取。

### 3.3 原生 MMS 批读

每个 DataSet 使用一次 `MmsConnection_readNamedVariableListValues`。调用统一进入 `connection.native_operation()`，避免与断线重连、报告回调等操作并发访问失效句柄。

现场设备验证发现，NamedVariableList 请求的 `specWithResult=False` 会返回 MMS 错误 55：`object-constraint-conflict`。本次改为 `specWithResult=True`，要求响应携带访问规格，目标 IED 可以正常返回完整数组。

Transport 会校验：

- 返回数组长度与 DataSet 成员数是否一致。
- 成员顺序与目录顺序是否一致。
- 每个成员的运行时 MMS 类型。
- 是否存在 `DATA_ACCESS_ERROR`。
- 结构体和数组的叶子投影数量是否与模型一致。

成员失败会保留具体索引、引用和原因，批次日志按错误原因汇总，不再只输出空字典。

### 3.4 结构值安全投影

DO 或结构级 FCDA 需要展开到实际叶子测点。投影严格依据完整 `IedModel`、FC、模型顺序和运行时 MMS 类型：

- 只有真实 `MMS_STRUCTURE` 或 `MMS_ARRAY` 才递归展开。
- `q` 等 `MMS_BIT_STRING` 在线上仍是一个标量，不能按 UI 展示节点拆成多个值。
- 结构数量或类型无法验证时禁止猜测映射，仅回退受影响测点。

这项修复解决了 DataSet 返回数量正常、但客户端错误展开品质位后导致整组成员映射失败的问题。

## 4. 批量读取进度展示

### 4.1 协议层进度事件

DataSet 批读增加内部进度回调，按下列阶段上报：

| 阶段 | 含义 | Handler 进度范围 |
|------|------|------------------|
| `planning` | 建立 DataSet 读取计划 | 1%～5% |
| `dataset` | 每完成一个 DataSet 上报一次 | 5%～90% |
| `retry` | 重连后重新规划并读取未完成部分 | 保持单调递增，最高 90% |
| `fallback` | 单点读取未覆盖或失败测点 | 90%～99% |
| `done` | Handler 映射、系数换算完成 | 100% |

重连后 DataSet 计数可能重新开始，Handler 使用当前最大百分比保证进度条不会倒退。

### 4.2 后端并发响应进度查询

原生 MMS 调用是同步阻塞操作。批读 API 使用 `asyncio.to_thread()` 将 Handler 批读放到工作线程执行，使 FastAPI 事件循环在读取期间仍能响应进度查询。

统一进度快照新增：

- `phase="reading"`
- `operation="read"`
- 当前百分比和 DataSet 阶段消息
- 活动状态、操作 ID 和耗时

连接、发现和读取继续复用原进度接口，避免新增前端 API 和破坏兼容性。

### 4.3 前端轮询

IEC61850 批读发起后，前端每 100ms 查询一次进度快照：

- 只接受 `operation="read"` 的进度。
- 使用 `Math.max()` 过滤乱序响应，保证显示值单调递增。
- 实时展示“已读取 DataSet X/Y”及当前 DataSet 名称。
- HTTP 批读完成并刷新表格后，将进度置为 100%。
- 无论成功或异常，均停止轮询定时器，避免后台泄漏。

整改后不再出现长时间 0% 后直接跳到 100% 的情况。

## 5. URCB 软件 GI 严格批读

URCB 软件 GI 现在通过以下调用读取完整 DataSet：

```python
datasets.read_dataset_values(
    data_set_ref,
    allow_member_fallback=False,
)
```

严格模式具有以下语义：

- DataSet 完整读取成功：生成一条 GI 报告缓存，所有成员的原因码为 `gi`。
- 任一成员访问或解码失败：本次软件 GI 失败，不逐成员补读。
- DataSet 目录或原生 Transport 不可用：直接失败，不进入单点兼容路径。

普通 DataSet 查询接口仍保留原有兼容回退能力；只有软件 GI 强制严格批量语义。

## 6. 修复后的读取流程

```text
请求测点
  ↓
地址去重与 DataSet 规划
  ↓
按 DataSet 逐组执行 NamedVariableList 批读
  ↓ 每完成一组上报进度
运行时类型校验与模型叶子投影
  ↓
保留所有成功结果
  ↓
仅对未覆盖或失败测点单点回退
  ↓
point.code 映射与遥测系数换算
  ↓
进度 100%，返回兼容结果
```

在 DataSet 100% 覆盖且读取成功时，请求数由测点数量 `N` 次降为 DataSet 数量 `D` 次，单点请求为 0 次。

## 7. 修改文件清单

| 文件 | 改动 | 说明 |
|------|------|------|
| `src/proto/iec61850/plugins/datasets/models.py` | 新增 | 不可变 DataSet 领域模型和详细读取结果 |
| `src/proto/iec61850/plugins/datasets/catalog.py` | 新增/修改 | 引用规范化、反向索引、读取规划和安全结构投影 |
| `src/proto/iec61850/plugins/datasets/directory.py` | 新增 | 统一 DataSet 目录与 FCDA 解析 |
| `src/proto/iec61850/plugins/datasets/transport.py` | 新增/修改 | NamedVariableList 原生批读、错误解析和资源释放 |
| `src/proto/iec61850/plugins/datasets/__init__.py` | 重构 | DataSet 规划执行、进度、重连和精确回退 |
| `src/proto/iec61850/core/reader.py` | 修改 | 固定执行 DataSet 优先批读链并透传进度 |
| `src/proto/iec61850/iec61850_client.py` | 修改 | 客户端门面透传批读进度 |
| `src/proto/iec61850/model/discovery.py` | 修改 | 恢复模型优先发现边界，DataSet 不再反向补模型 |
| `src/device/protocol/iec61850_handler.py` | 修改 | 读取进度快照、结果映射和遥测系数换算 |
| `src/web/api/channel/iec61850.py` | 修改 | 在线程中执行阻塞批读，保持进度接口可响应 |
| `src/device/core/device.py` | 修改 | 统一连接、发现和读取任务进度说明 |
| `src/web/api/device/router.py` | 修改 | 扩展原连接进度接口说明 |
| `front/src/api/deviceApi.ts` | 修改 | 增加 `reading/read` 进度类型 |
| `front/src/composables/useAutoRead.ts` | 修改 | 批读期间轮询 DataSet 进度并更新进度条 |
| `src/proto/iec61850/plugins/reports/__init__.py` | 修改 | URCB 软件 GI 改为严格 DataSet 批读 |
| `src/tests/iec61850/test_dataset_batch_reader.py` | 修改 | 覆盖规划、投影、回退、进度及严格模式 |
| `src/tests/iec61850/test_report_trigger_configuration.py` | 修改 | 覆盖软件 GI 严格批读行为 |

本次新增及修改的核心函数均补充了中文注释，说明模型边界、原生资源生命周期、进度映射和回退条件。

## 8. 验证结果

### 8.1 现场 IED 验证

在支持持久 DataSet 的目标 IED 上验证：

| 指标 | 结果 |
|------|------|
| DataSet 数量 | 34 |
| DataSet 覆盖测点 | 4496 |
| 成功返回测点 | 4496 |
| 失败测点 | 0 |
| 单点回退 | 0 |
| 批读耗时 | 约 428 ms |

原先 `values=0, errors=240` 的电芯温度、电芯电压等 DataSet 均可以完整返回。

### 8.2 后端测试

```text
python -m pytest <本次相关 IEC61850 测试>
86 passed

python -m pytest \
  src/tests/iec61850/test_dataset_batch_reader.py \
  src/tests/iec61850/test_report_trigger_configuration.py
18 passed
```

新增测试覆盖：

- DataSet 选择稳定性、重复地址和重叠覆盖。
- 标量、结构和数组 FCDA 投影。
- 数组长度、类型和成员访问错误。
- 仅失败或未覆盖测点进入单点回退。
- 每个 DataSet 完成后的进度事件。
- Handler 进度单调递增并以 100% 收尾。
- 软件 GI 严格模式禁止逐成员回退。
- `point.code` 映射和遥测系数换算保持兼容。

### 8.3 前端和代码质量

```text
ruff check ...
passed

npm run type-check
passed

npm run build:fast
✓ built successfully
```

前端构建仅保留项目原有的 `channelApi.ts` 动态导入与静态导入并存提示，不影响本次功能。

## 9. 兼容性与限制

1. 完整模型发现仍需要浏览 LD/LN/DO/DA；只有运行时读值可以在 DataSet 完全覆盖时实现零单点请求。
2. 本次只读取 IED 已配置的持久 DataSet，不创建或删除动态 DataSet。
3. 未进入 DataSet 的测点仍保留并按需单点读取。
4. 写入、报告订阅、GOOSE、ICD 导入和数据库结构不变。
5. 软件 GI 要求完整 DataSet 批读成功；部分成功不会生成不完整的 GI 报告。
6. 公开 API、前端 DataSet 字典结构和 Handler 返回结构保持兼容。

