# IEC61850 服务端总召唤与主动报告修复

> 版本: 1.0  
> 日期: 2026-06-28  
> 状态: 已实施

## 1. 问题背景

IEC61850 服务端加载厂家 ICD 模型并启动后，主站侧出现以下异常：

| 现象 | 触发场景 | 影响 |
|------|----------|------|
| 总召唤无报告返回 | 主站使能 RCB 后发起 GI | 主站无法获取 DataSet 当前全量值 |
| 测点变化不主动上送 | 服务端更新 `stVal`、`mag.f` 等数据属性 | RCB 已使能但没有变化报告 |
| RCB 数量翻倍 | 通过 ICD 导入并加载服务端模型 | 同一 DataSet/RCB 被注册两次，运行时状态分裂 |
| 部分厂家模型始终不产生变化事件 | ICD 的 DA 未声明 `dchg/qchg/dupd` | ReportControl 声明了变化触发，但底层 DA 没有事件触发位 |

本次修复目标是让服务端在不修改厂家 ICD 文件的前提下，正确响应 GI，并在数据变化后主动生成报告，同时保持“应用启动时不自动加载模型”的现有流程。

## 2. 根因分析

### 2.1 DataAttribute 的触发选项始终为 0

动态模型创建数据属性时，原实现将 `DataAttribute_create` 的 `triggerOptions` 固定传入 `0`：

```python
iec61850.DataAttribute_create(
    name,
    parent,
    iec_type,
    fc,
    0,  # triggerOptions
    0,
    0,
)
```

libIEC61850 依赖 DataAttribute 上的触发位产生变化事件。即使 RCB 的 `TrgOps.dchg` 已开启，只要数据属性没有 `TRG_OPT_DATA_CHANGED`，调用服务端更新接口也不会产生主动报告。

### 2.2 SCL 中的 DA 触发属性在转换过程中丢失

SCL 解析模型已经包含 `dchg`、`qchg`、`dupd`，但原有转换链路只保留了 DA 的路径、FC 和数据类型：

```text
SclDA
  -> TypeResolver
  -> PointData
  -> IEC61850Server.load_model()
  -> IedModelBuilder
```

触发属性没有沿该链路传递到动态模型构建器，因此厂家 ICD 中已明确声明的触发语义也没有生效。

结构化 DA 还存在一层额外问题：最终更新的是 BDA 叶子节点，但触发属性只定义在其所属 DA 上。若不将属性下传到叶子节点，结构化数据变化同样不能触发报告。

### 2.3 部分厂家 ICD 省略 DA 级触发属性

部分厂家文件只在 `ReportControl.TrgOps` 中声明 `dchg/qchg`，具体 DA 上没有对应属性。按照原始文件直接构建时，这些 DA 的触发位仍为 0，导致报告控制块虽可见、可使能，却永远收不到数据变化事件。

### 2.4 RCB 的 GI 能力受厂家 ICD 缺省值限制

部分厂家 ICD 的 `ReportControl/TrgOps` 未声明 `gi="true"`。原实现直接使用解析结果创建运行时 RCB，因此主站写 GI 后没有全量报告产生。

对于仿真服务端，需要面向通用测试主站提供总召唤能力，不能依赖修改厂家原始模型来补充该能力。

### 2.5 DataSet 和 RCB 被重复注册

`IEC61850Server.load_model()` 已经完成 DataSet 和 ReportControlBlock 注册，但 ICD 导入接口随后又执行了一遍注册逻辑：

```text
reload_device_instance()
  -> IEC61850Server.load_model()
     -> 注册 DataSet/RCB
  -> import_points.py 再次注册 DataSet/RCB
```

这会造成 RCB 数量翻倍。例如厂家模型原有 272 个运行时 RCB，重复注册后会变成 544 个，并可能形成同名节点对应不同状态的情况。

## 3. 修复方案

### 3.1 完整传递 SCL 触发属性

扩展 SCL 到动态模型的转换链路，保留并传递以下属性：

| SCL 属性 | libIEC61850 触发位 | 用途 |
|----------|-------------------|------|
| `dchg` | `TRG_OPT_DATA_CHANGED` | 数据值变化 |
| `qchg` | `TRG_OPT_QUALITY_CHANGED` | 品质变化 |
| `dupd` | `TRG_OPT_DATA_UPDATE` | 数据更新 |

`TypeResolver` 解析 DA 时记录三个属性；`PointData` 保存属性；`IEC61850Server.load_model()` 注册测点时将其传给 `IedModelBuilder`；构建器最终生成 libIEC61850 所需的位掩码。

对于结构化 DA，BDA 叶子继承所属 DA 的触发语义，确保实际被更新的叶子属性可以产生事件。

### 3.2 为常用标准叶子提供兼容触发语义

当厂家 ICD 未声明任何 DA 触发属性时，运行时对常用标准叶子进行兼容推断：

| DA 叶子 | 兼容触发语义 |
|---------|--------------|
| `stVal` | `dchg` |
| `mag.f` / `f` | `dchg` |
| `actVal` | `dchg` |
| `q` | `qchg` |
| `t` | 不设置变化触发 |

该兼容只作用于运行时动态模型，不修改厂家 ICD 文件，也不会把时间戳 `t` 误判为数据变化源。

简单地址模式创建的模拟量 `f`、状态量 `stVal` 和标准品质 `q` 同步设置相应触发位，保证手工创建模型与 ICD 模型行为一致。

### 3.3 运行时统一开放 GI 能力

注册 RCB 时创建一份 `effective_trg_ops`：

```python
effective_trg_ops = dict(trg_ops or default_trg_ops)
effective_trg_ops["gi"] = True
```

该配置同时用于原生 ReportControlBlock 创建和运行时 RCB 元数据，确保主站发现的能力与服务端实际行为一致。

此处仅增强仿真服务端的运行时能力，厂家 ICD 内容保持不变。

### 3.4 DataSet/RCB 只注册一次

ICD 导入流程不再二次创建 DataSet 和 RCB，而是复用 `IEC61850Server.load_model()` 的注册结果：

```python
registered_dataset_count = len(server.browse_datasets())
rc_registered = len(server.reports.rcb_list)
```

导入接口后续只负责统计、持久化和按原流程处理 GOOSE，避免模型节点重复创建。

## 4. 边界与约束

### 4.1 不修改厂家模型文件

本次修复没有修改任何 ICD、CID 或 SCD 文件。GI 兼容和 DA 触发推断均发生在内存中的运行时模型上，厂家文件继续作为原始数据源保留。

### 4.2 应用启动时不加载模型

本次没有增加应用启动阶段的模型加载，也没有改变设备启动与模型加载的职责边界。模型仍在用户执行明确的导入或加载操作后进入内存，应用启动本身不解析厂家 ICD。

### 4.3 保留厂家显式配置

当 DA 已明确声明 `dchg/qchg/dupd` 时，优先使用厂家配置；兼容推断只在三个触发属性均未设置时生效。

## 5. 关键文件

| 文件 | 变更 |
|------|------|
| `src/proto/iec61850/plugins/scl/parser/type_resolver.py` | 保留 DA 的 `dchg/qchg/dupd`，修正结构化 DA/BDA 路径并下传触发语义 |
| `src/proto/iec61850/plugins/scl/transformer/point_transformer.py` | `PointData` 增加触发属性并使用 DA 的实际 FC |
| `src/proto/iec61850/iec61850_server.py` | 加载模型时将触发属性传入动态模型构建器 |
| `src/proto/iec61850/plugins/datamodels/builder.py` | 构建 trigger bit mask，并为标准值、品质叶子提供兼容推断 |
| `src/proto/iec61850/plugins/reports/manager.py` | 使用运行时有效 TrgOps 创建 RCB 并统一开放 GI |
| `src/web/api/channel/import_points.py` | 删除 DataSet/RCB 二次注册，复用 `load_model()` 结果 |
| `src/tests/iec61850/test_report_trigger_configuration.py` | 增加 SCL 触发属性、GI 能力和兼容推断回归测试 |

## 6. 修复后的行为

### 主动报告

- RCB 使能后，更新 `stVal`、`mag.f`、`actVal` 可产生 `dchg` 报告。
- 更新品质 `q` 可产生 `qchg` 报告。
- 厂家显式 DA 触发属性可以完整进入动态模型。
- 厂家省略 DA 触发属性时，常用标准叶子仍可按兼容规则产生报告。

### 总召唤

- 运行时 RCB 对主站公开 GI 能力。
- 主站使能 RCB 后触发 GI，可收到对应 DataSet 的全量当前值报告。
- 不需要编辑厂家 ICD 中的 `TrgOps`。

### 模型注册

- DataSet 和 RCB 在 `load_model()` 中唯一注册。
- 导入流程不会再次创建相同模型节点。
- 厂家模型中的运行时 RCB 数量不再因导入流程翻倍。

## 7. 验证结果

### 7.1 自动化测试

```text
ruff check: passed
pytest src/tests/iec61850 -q:
75 passed, 25 skipped, 1 warning
```

其中新增测试覆盖：

- SCL 中 `stVal.dchg`、`q.qchg`、`mag.f.dchg` 的解析和传递。
- 厂家 TrgOps 未声明 GI 时，运行时 RCB 仍公开 GI 能力。
- `stVal`、`mag.f`、`q` 和 `t` 的兼容触发推断。

### 7.2 端到端验证

| 模型 | 验证项 | 结果 |
|------|--------|------|
| `SY_ES630K.icd` | 使能 RCB 后更新测点 | 收到主动变化报告 |
| `SY_ES630K.icd` | 主站触发 GI | 收到 GI 全量报告 |
| `KG_BAMS.icd` | 运行时 RCB 数量 | 保持 272，未重复为 544 |
| `KG_BAMS.icd` | DA 未显式声明触发属性 | 生成单点变化报告 |
| `KG_BAMS.icd` | 主站触发 GI | 返回完整 DataSet 报告 |

## 8. 总结

本次修复打通了服务端报告生成所需的完整配置链路：

```text
SCL DA 触发属性
  -> PointData
  -> IEC61850Server
  -> IedModelBuilder triggerOptions
  -> libIEC61850 变化事件
  -> RCB 主动报告
```

同时在运行时统一开放 GI，并消除 DataSet/RCB 重复注册。修复后服务端可以接受总召唤，也可以在测点变化时主动上送报告；整个过程不修改厂家模型文件，也不在应用启动时自动加载模型。
