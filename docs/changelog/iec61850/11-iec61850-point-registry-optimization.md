# IEC 61850 测点注册表精简优化

> 版本: 1.0  
> 日期: 2026-06-03  
> 状态: 规划中


## 1. 问题

### 1.1 现象

统一模型发现完成后，`point_refs` 生成了 **41,098 个测点**，其中绝大多数是 `q`（品质）和 `t`（时标）的子属性：

```
统一模型发现完成, 耗时 0.50s, {
  totalLDs: 25, totalLNs: 59,
  totalDOs: 4566,           ← 4,566 个数据对象
  totalDAs: 18268,           ← 含 q/t/dU 的 DA 总计
  totalDataSets: 34, totalRCBs: 272, totalGoCBs: 0
}

从 IedModel 派生完成, 填充了 41098 个测点   ← 4,566 × ~9 = 41K!
```

### 1.2 根因：q/t 子属性被展开为测点

上一轮修复中，为了解决「读取 `.t` 和 `.q` 失败」的 DEBUG 日志，将 `q`/`t` 的结构子属性展开了：

| 父结构 | 子属性 | 类型 | 每 DO 增加 |
|--------|--------|------|-----------|
| `q` | `validity`, `detailQuality`, `source`, `operatorBlocked`, `test` | 5 个子 DA | +5 |
| `t` | `seconds`, `fraction`, `TimeAccuracy` | 3 个子 DA | +3 |
| **合计** | | | **+8/DO** |

```
4,566 DOs × 8 个 q/t 子测点 = 36,528 个额外测点
4,566 DOs × 1~2 个主值测点  = ~5,000 个主值测点
────────────────────────────────
总计                          = 41,098 个测点  (8倍膨胀)
```

### 1.3 影响

| 方面 | 影响 |
|------|------|
| `point_refs` 生成 | 额外遍历 36K 个子 DA，O(n) 扩展 |
| `PointRegistry` 内存 | 36K 额外字典条目 + 地址/ref/fc/iec_type 映射 |
| `build_registry_from_model` | 36K 次 `set_ref` + `set_fc` + `set_iec_type` 调用 |
| `_fill_du_names` | 对每个主值 DO 的额外遍历（影响较小） |
| 实际使用 | 99% 的 q/t 子测点永远不会被前端读取 |


## 2. 优化方案

### 2.1 核心原则

- **`IedModel` 保留完整的模型结构**（含 q/t 子 DA），供导出/结构浏览使用
- **`PointRegistry` 只保留主值测点**（mag.f、stVal、ctlVal 等），不包含 q/t 元数据
- **q/t 读取走独立路径**：需要时通过 `do_ref.q.validity` 等完整引用直接 MMS 读取，不从 PointRegistry 查找

### 2.2 代码变更

#### 2.2.1 `ied_model.py` — `_extract_do_points` 回退

**变更前**（当前代码）:
```python
# q/t 已展开为子 DA, 父结构不作为独立测点;
NON_POINT_DA_NAMES = SKIP_DA_NAMES  # q, t 在 SKIP_DA_NAMES 中

for da in do.das:
    skip_parent = da.name in NON_POINT_DA_NAMES  # q/t 被 skip_parent
    if not skip_parent:
        # ... 创建主值测点 ...
    else:
        frame_type = ...  # 为子 DA 准备 frame_type

    # 展开 BDA (包括 q/t 的子 DA)
    for bda in da.sub_das:
        # ... 创建 q.validity, t.seconds 等测点 ...  ← 36K 条
```

**变更后**:
```python
# q/t 子属性不作为测点（元数据结构不可直接读或很少读取），
# 其他元数据 DA (dU/subQ/subID 等) 同样跳过
NON_POINT_DA_NAMES = SKIP_DA_NAMES | {"q", "t"}

for da in do.das:
    if da.name in NON_POINT_DA_NAMES:
        continue   # q/t/dU/subQ 全部跳过，不展开子 DA

    # ... 创建主值测点 ...

    # 展开 BDA (仅限于 origin.orCat / origin.orIdent)
    for bda in da.sub_das:
        # ... origin 子测点（数量极少，保留）...
```

> **注意**：`SKIP_DA_NAMES` 是 `frozenset` 不可修改，可以用 `NON_POINT_DA_NAMES = SKIP_DA_NAMES` 并配合 `skip_parent = da.name in NON_POINT_DA_NAMES and not da.sub_das` 逻辑，或直接扩写条件。

#### 2.2.2 保留内容

以下内容**不需回退**，它们服务于 IedModel 结构（导出/浏览），不影响 PointRegistry 大小：

| 文件 | 内容 | 作用 |
|------|------|------|
| `da_patterns.py` | `STRUCT_DA_EXPAND_ONLINE` 含 `"q"`, `"t"` | 模型发现时展开子结构（供导出用） |
| `da_patterns.py` | `KNOWN_BDA_FALLBACK_ONLINE` 含 q/t 子 BDA | 在线发现失败时的回退数据 |
| `discovery.py` | `_DEFAULT_META_DAS` 展开 q/t 子 DA | 构建完整 IedModel.DARef.sub_das |

#### 2.2.3 不需要变更

| 文件 | 原因 |
|------|------|
| `discovery.py:_discover_data_attributes` | q/t 子 DA 已正确硬编码创建 |
| `registry_bridge.py:build_registry_from_model` | 只遍历 `model.point_refs`，点数减少后自然变快 |
| `iec61850_client.py:_fill_du_names` | 仅遍历主值测点 DO，q/t 跳过不影响 |


## 3. 效果预估

| 指标 | 优化前 | 优化后 | 改善 |
|------|--------|--------|------|
| 测点总数 | 41,098 | ~5,000 | **8x 减少** |
| `point_refs` 生成时间 | ~50ms (估计) | ~6ms | ~8x |
| `PointRegistry` 条目 | 41K | 5K | 36K 节省 |
| `build_registry_from_model` 耗时 | ~200ms (估计) | ~30ms | ~6x |
| 模型结构完整性 | 完整 ✅ | 完整 ✅ | 不变 |
| 导出功能 | 正常 ✅ | 正常 ✅ | 不变 |
| 主值读取 | 正常 ✅ | 正常 ✅ | 不变 |
| q/t 读取 | 部分可用 ⚠️ | 需走独立路径 | 降级为按需 |


## 4. q/t 独立读取方案（可选后续）

如果后续需要在前端展示品质/时标信息，可通过以下方式按需读取：

### 4.1 API 层新增 `read_metadata`

```python
def read_metadata(connection, do_ref: str) -> dict:
    """读取 DO 的元数据（品质 + 时标），仅在需要时调用"""
    result = {}
    # 读取 q.validity (整数)
    result["quality_validity"] = connection.read_integer(f"{do_ref}.q.validity")
    # 读取 t.seconds (整数)
    result["timestamp_seconds"] = connection.read_integer(f"{do_ref}.t.seconds")
    return result
```

### 4.2 前端调用

仅当用户点击「查看品质/时标」按钮时才调用 `read_metadata`，不纳入常规轮询或批量读取。


## 5. 实施步骤

1. 修改 `ied_model.py:_extract_do_points`：q/t 父结构跳过，不再展开子 DA 为测点
2. 验证：重启后端，确认日志中 `填充了 ~5000 个测点`（而非 41098）
3. 验证：导出功能不受影响（`IedModel.to_dict()` 仍含完整 q/t 子结构）
4. 验证：主值读写功能正常
