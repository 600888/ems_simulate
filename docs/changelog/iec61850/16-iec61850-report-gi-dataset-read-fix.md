# IEC61850 报告 GI 与 DataSet 读取修复

> 版本: 1.0  
> 日期: 2026-06-22  
> 状态: 已实施

## 1. 问题背景

在 IEC61850 Reports 功能联调中，LLN0 下多个 BRCB/URCB 报告控制块启用后，先后暴露出以下问题：

| 现象 | 触发场景 | 影响 |
|------|----------|------|
| BRCB 触发 GI 后回调路由到第一个报告 | 对 `brcbDin03` 触发总召唤，日志仍显示 `brcbDin01` | 前端请求不到目标报告的数据 |
| 多报告启用后重复订阅异常 | 同一 LLN0 下多个报告模块启用 | `subscriber is already registered`，严重时进程崩溃 |
| GI 回调持续触发 | 总召唤后回调被反复分发 | 缓存与前端数据刷新异常 |
| URCB 触发 GI 后进程卡死 | 对 URCB 写 `GI=True` 或调用同步 `setRCBValues` | 后端进程阻塞 |
| URCB 软件 GI 初始读取 DataSet 为空 | 通过 DataSet 读取当前值写入缓存 | GI 接口返回 500 |
| 逐点读取 fallback 可用但效率低 | DataSet 批量读取不可用后逐个 `readObject` | 大 DataSet 总召唤耗时明显增加 |

本次修复的目标是让 BRCB/URCB 在多报告场景下稳定启用、准确路由 GI 数据，并让 URCB 在不能安全写 `GI=True` 时仍可通过 DataSet 批量读取完成软件总召唤。

## 2. 根因分析

### 2.1 RptId 与 RCB 引用不是一一对应

同一 LLN0 下多个报告控制块可能共享基础 RptId，例如：

```text
PCS001LD0/LLN0.brcbDin01 -> LD0/LLN0$BR$brcbDin
PCS001LD0/LLN0.brcbDin02 -> LD0/LLN0$BR$brcbDin
PCS001LD0/LLN0.brcbDin03 -> LD0/LLN0$BR$brcbDin
```

`01/02/03` 后缀用于区分多个 RCB 实例，但报告回调中的 RptId 可能不携带该实例后缀。只按 RptId 建立回调映射时，GI 数据容易落到第一个注册的报告缓存中。

### 2.2 URCB GI 写入路径存在阻塞风险

BRCB 触发 GI 可通过 RCB 对象写回完成；但 URCB 在当前 `pyiec61850` 绑定与部分设备实现下，直接写 `GI` 属性或同步 `setRCBValues` 存在阻塞/卡死风险。为避免进程挂死，URCB 总召唤需要避开危险写路径。

### 2.3 `IedConnection_readDataSetValues` 的 Python 绑定不可直接使用

排查发现当前 `pyiec61850` 中：

```python
IedConnection_readDataSetValues(_self, dataSetReference, dataSet)
```

第三个参数要求传入非空 `ClientDataSet`，但 Python 包没有暴露可用的 `ClientDataSet_create`。传 `None` 会报：

```text
ClientDataSet is NULL
```

因此不能依赖 `IedConnection_readDataSetValues` 作为 URCB 软件 GI 的主要读取路径。

### 2.4 DataSet directory 为空时值被误丢弃

旧逻辑按下面方式遍历 DataSet 值：

```python
for i in range(min(array_size, len(members))):
    ...
```

如果设备返回了 DataSet 值数组，但 `browse_dataset_directory()` 暂时未拿到成员目录，`len(members)=0` 会导致循环 0 次，最终误判为 DataSet 为空。

## 3. 修复方案

### 3.1 GI 路由增加 pending target

在触发 GI 前记录目标 RCB：

```text
target = PCS001LD0/LLN0.brcbDin03
rpt_id = LD0/LLN0$BR$brcbDin
```

回调分发时，如果报告 RptId 与 pending GI 记录匹配，则优先写入触发 GI 的目标 RCB 缓存，而不是默认落到第一个同 RptId 的报告模块。

### 3.2 保留实例后缀作为缓存归属

`urcbAin01`、`brcbDin03` 这样的实例后缀应保留在 RCB 引用中，用于：

- 区分同一 LLN0 下多个报告实例。
- 作为前端请求报告数据的缓存 key。
- 保证 GI 结果写入用户实际触发的报告模块。

读取当前值时不通过该 RCB ref 读取，而是通过 RCB 绑定的 `data_set_ref` 读取。

### 3.3 URCB 改为软件 GI

URCB 不再强依赖写 `GI=True`，而是执行软件总召唤：

1. 根据 RCB 明细取出 `data_set_ref`。
2. 读取 DataSet 当前值。
3. 构造 `ReportDataEntry`。
4. 直接追加到对应 RCB 的报告缓存。
5. 前端继续通过原有 `/reports/data` 接口读取缓存。

这样避免了 URCB 写 GI 或同步 `setRCBValues` 导致的进程卡死。

### 3.4 DataSet 优先使用 MMS NamedVariableList 批量读取

为解决逐点读取效率问题，新增 MMS 层批量读取路径：

```python
mms_conn = iec61850.IedConnection_getMmsConnection(conn)
mms_error = iec61850.MmsError_create()
values = iec61850.MmsConnection_readNamedVariableListValues(
    mms_conn,
    mms_error,
    domain_id,
    item_id,
    False,
)
```

DataSet 引用转换规则：

| 输入 | domain_id | item_id |
|------|-----------|---------|
| `PCS001MEAS/LLN0$dsAin` | `PCS001MEAS` | `LLN0$dsAin` |
| `PCS001MEAS/LLN0.dsAin` | `PCS001MEAS` | `LLN0$dsAin` |

MMS 批量读取成功后，只需一次请求即可取回整个 DataSet 值数组，再按 DataSet 成员顺序映射成 `{fcda_ref: value}`。

### 3.5 保留逐点读取 fallback

当 MMS 批量读取不可用或设备返回错误时，保留逐成员 `IedConnection_readObject` fallback：

```text
MMS DataSet read failed
  -> IedConnection_readDataSetValues 兼容尝试
  -> DataSet directory + readObject 逐点读取
```

这样既保证常规场景性能，也保证异常设备或绑定差异下功能可用。

### 3.6 DataSet 成员目录缓存

DataSet 成员目录用于把数组下标映射回 FCDA 引用。为减少重复 GI 时的额外 MMS 请求，读取时增加成员缓存：

- 首次读取时调用 `browse_dataset_directory()`。
- 成功获取成员后按完整 DataSet ref 缓存。
- 后续 GI 复用成员列表，只读取 DataSet 值数组。
- 断开或关闭插件时清理缓存。

## 4. 关键文件

| 文件 | 变更 |
|------|------|
| `src/proto/iec61850/plugins/reports/callback.py` | 增加 GI pending 路由、RptId 别名匹配、缓存追加接口 |
| `src/proto/iec61850/plugins/reports/__init__.py` | URCB 触发 GI 改为软件 GI，按 DataSet 读取后写入报告缓存 |
| `src/proto/iec61850/plugins/reports/brcb.py` | BRCB GI 触发前记录 pending 路由，避免同 RptId 多实例串线 |
| `src/proto/iec61850/plugins/reports/urcb.py` | 避免 URCB 同步写 GI 导致进程卡死，保留必要兼容逻辑 |
| `src/proto/iec61850/plugins/datasets/__init__.py` | 新增 MMS NamedVariableList 批量读取、成员缓存、逐点 fallback |

## 5. 修复后的行为

### BRCB

- 多个 BRCB 可同时启用。
- 对 `brcbDin03` 触发 GI 后，数据写入 `brcbDin03` 缓存。
- 前端按目标 `rcb_ref` 请求可拿到对应数据。

### URCB

- 启用报告仍安装正常报告回调。
- 触发 GI 时优先执行软件 GI，不再阻塞进程。
- DataSet 值优先通过 MMS NamedVariableList 一次性读取。
- 读取成功后写入同一个报告缓存通道，前端无须区分真实回调或软件 GI。

### DataSet 读取

- 首选路径：`MmsConnection_readNamedVariableListValues` 一次读完整 DataSet。
- 兼容路径：尝试 `IedConnection_readDataSetValues` 多种签名。
- 兜底路径：DataSet directory + `IedConnection_readObject` 逐点读。
- 当成员目录为空但值数组存在时，使用 `data[0]`、`data[1]` 兜底 key，避免误判整包为空。

## 6. 验证要点

### 6.1 BRCB 多实例 GI 路由

请求：

```json
{
  "channel_id": 12,
  "rcb_ref": "PCS001LD0/LLN0.brcbDin03"
}
```

期望日志：

```text
GI 待路由已记录: target=PCS001LD0/LLN0.brcbDin03
```

前端请求 `brcbDin03` 的报告数据，应能读取到本次 GI 写入的缓存。

### 6.2 URCB 软件 GI

请求：

```json
{
  "channel_id": 12,
  "rcb_ref": "PCS001MEAS/LLN0.urcbAin01"
}
```

期望日志：

```text
MMS DataSet read succeeded: ref=PCS001MEAS/LLN0$dsAin, values=...
URCB 软件 GI 已写入缓存: ref=PCS001MEAS/LLN0.urcbAin01
```

### 6.3 fallback 验证

当 MMS 批量读取失败时，日志应进入 fallback：

```text
MMS DataSet read failed: ...
Read DataSet values fallback succeeded: ref=..., values=...
```

如果 fallback 仍失败，应根据日志继续定位：

| 日志 | 含义 |
|------|------|
| `fallback failed: no members` | DataSet directory 读取失败或设备未暴露成员目录 |
| `fallback got no values` | 成员可见，但逐点 `readObject` 全部失败 |
| `MMS DataSet read failed ... error=...` | MMS NamedVariableList 读取被设备拒绝或引用格式不匹配 |

## 7. 风险与注意事项

1. **软件 GI 与真实设备 GI 语义不同**  
   软件 GI 是读取当前 DataSet 值后写入本地缓存，不会要求设备主动发送一帧 GI 报告。对前端展示和数据刷新足够，但不等同于设备侧真实 GI 流程。

2. **DataSet 成员顺序必须稳定**  
   MMS 返回值数组按 DataSet 成员顺序排列。成员缓存假设同一连接生命周期内 DataSet 结构不变。如果设备动态修改 DataSet，应断开重连或重新发现。

3. **同 RptId 多实例仍依赖 pending GI 路由**  
   普通周期/变化报告若设备只给共享 RptId，仍可能无法仅凭 RptId 区分实例；本次修复主要保证主动触发 GI 的数据归属准确。

4. **`MmsErrror_destroy` 拼写保持兼容**  
   当前 pyiec61850 暴露的析构函数名为 `MmsErrror_destroy`，代码优先使用该拼写，并兼容未来可能存在的 `MmsError_destroy`。

## 8. 总结

本次修复把 IEC61850 报告总召唤从“依赖设备回调和不稳定 SWIG 绑定”调整为“明确路由 + 安全软件 GI + MMS 批量读取”的组合：

- 多报告实例通过 pending GI 准确写入目标缓存。
- URCB 避免写 GI 和同步 `setRCBValues` 引发进程卡死。
- DataSet 读取优先走 MMS NamedVariableList，一次请求取回完整值数组。
- 保留逐点读取 fallback，保证设备兼容性。

修复后，BRCB 和 URCB 在多报告场景下都可以稳定完成总召唤，前端按目标 RCB 请求数据时能够获取正确缓存。
