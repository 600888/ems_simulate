# IEC61850 模型发现与 MMS 类型推断优化

> 版本：1.0  
> 日期：2026-07-12  
> 分类：模型发现 / MMS 类型 / SCL 导入 / 性能优化 / 前端展示 / Bug 修复  
> 状态：已实施

## 1. 问题背景

IEC61850 客户端在线发现大模型以及服务端导入 ICD 模型时，现场出现了两类相互关联的问题：

1. 模型发现偶尔非常慢，尤其是目标 IED 不提供描述属性时；
2. 服务端导入模型后，模型树中的 `mag`、`q`、`t`、`dU` 和部分系统 DO 显示为 `MMS_UNKNOWN`。

典型日志如下：

```text
读取描述失败 (尝试 dU/d, DC/CF 均无): ZCA-110LD/InGGIO63.AnIn6
读取描述失败 (尝试 dU/d, DC/CF 均无): ZCA-110LD/InGGIO63.AnIn7
读取描述失败 (尝试 dU/d, DC/CF 均无): ZCA-110LD/InGGIO63.AnIn8
```

问题并非单一超时参数造成。旧实现对大量已经能够静态确定类型的 DA/BDA 仍逐点发起在线探测，并在描述不存在时重复执行必然失败的兼容读取。服务端模型树的补全分支又没有为虚拟节点写入 MMS 类型，最终同时产生性能和显示问题。

## 2. 影响范围

| 场景 | 旧行为 | 影响 |
|------|--------|------|
| 在线发现标准 DA/BDA | 先查变量规格，失败后读取运行值 | 每个叶子增加 1～2 次 MMS 往返 |
| IED 不包含 `dU/d` | 每个 DO 尝试 `dU/d × DC/CF` | 每个 DO 最多 4 次失败请求 |
| 服务端导入 ICD 后展示模型树 | 根据注册点反推并补充标准节点 | 补充节点类型为空，显示 `MMS_UNKNOWN` |
| 系统 DO 展示 | 无注册主值时无法选择 MMS 类型 | `NamPlt`、`PhyNam`、`Beh`、`Health`、`Mod` 类型不明确 |
| 前端 MMS 类型标签 | 列宽使用默认 100px | 较长类型名称显示拥挤 |

## 3. 根因分析

### 3.1 精确类型探测被无差别应用

在线发现原有优先级为：

```text
变量规格查询 → 运行值读取 → 静态路径推断
```

该策略对厂家自定义字段是必要的，但对 `mag.f`、`q`、`t`、`dU`、`Oper.ctlVal` 等标准路径没有额外价值。这些路径的线级类型已经可以确定，无差别在线探测只会让请求数量随模型叶子数量线性增长。

如果变量规格查询失败，代码还会继续读取运行值。对于一个包含上万 DA/BDA 的模型，即使单次延迟很小，也会形成明显累计耗时；当设备偶发慢响应时，单点请求超时会被进一步放大。

### 3.2 描述读取没有复用 DO 目录

模型发现阶段已经调用 `IedConnection_getDataDirectory()` 获取每个 DO 的 DA 目录，但描述补充阶段没有复用该结果，而是固定尝试：

```text
dU (DC) → d (DC) → dU (CF) → d (CF)
```

当目录已经明确不包含 `dU` 或 `d` 时，上述四次读取全部是可预知失败。完全没有描述的 IED 会对每个普通 DO 重复该过程。

### 3.3 服务端模型树存在独立补全路径

客户端拥有完整的不可变 `IedModel`，可以直接读取 `DARef.mms_type`。服务端导入 ICD 后，页面部分场景会根据已注册测点反推 DO/DA/BDA 树，并自动补充：

- 结构父节点，例如 `mag`；
- 标准元数据节点 `q`、`t`、`dU`；
- 已知结构的缺失 BDA。

旧补全逻辑将这些节点的 `mms_type` 初始化为空字符串。API 返回时空字符串又被统一回退成 `MMS_UNKNOWN`。因此 ICD 模板中的类型解析虽然正确，页面仍然显示未知类型。

### 3.4 CDC 类型与 MMS 类型语义混淆

CDC 描述数据对象的公共数据类，MMS 类型描述线上编码，两者不能直接使用同一名称展示。例如：

| DO | CDC | 主值 | MMS 线级类型 |
|----|-----|------|--------------|
| `Beh` | ENS | `stVal` 枚举 | `MMS_INTEGER` |
| `Health` | ENS | `stVal` 枚举 | `MMS_INTEGER` |
| `Mod` | ENC | `stVal` 枚举 | `MMS_INTEGER` |
| `NamPlt` | LPL | 多个铭牌 DA | `MMS_STRUCTURE`（DO 层） |
| `PhyNam` | LPL/DPL 类铭牌结构 | 多个铭牌 DA | `MMS_STRUCTURE`（DO 层） |

因此不能把所有系统 DO 统一标记为结构体，也不能直接在 MMS 类型列显示 `ENS/ENC`。

## 4. 优化方案

### 4.1 标准类型静态优先，未知类型在线探测

新增统一叶子类型解析入口，调整为：

```text
确定性标准路径 → 本地静态类型
未知/厂家自定义路径 → 变量规格查询 → 安全运行值回退
```

处理原则：

- 静态推断结果不是 `MMS_UNKNOWN` 时，直接缓存并返回；
- 不发送变量规格请求，也不读取运行值；
- 厂家自定义字段和未知路径仍保留在线精确探测；
- FC 为 `CO` 的控制安全边界保持不变，不通过运行值读取探测控制值；
- 类型探测缓存继续以 `(ref, fc)` 为键，避免同一任务内重复解析。

该策略兼顾了标准模型的性能和厂家扩展的准确性。

### 4.2 复用 DO 目录跳过不存在的描述

模型发现服务缓存每个成功读取的 DO 目录中实际出现的描述 DA：

```python
do_ref -> ("dU", "d") 的实际子集
```

缓存采用三态语义：

| 缓存结果 | 含义 | 描述阶段行为 |
|----------|------|--------------|
| `None` | 目录读取失败或没有目录信息 | 保留旧兼容读取 |
| `()` | 目录成功，明确没有 `dU/d` | 跳过全部描述读取 |
| `("dU",)` 等 | 存在描述候选 | 执行兼容读取 |

这一区分非常重要：目录不可用不能等同于字段不存在，否则会破坏部分兼容性较差 IED 的描述读取。

缓存会在模型失效和重新发现前清空，不会跨设备或跨发现任务污染。

### 4.3 服务端补全节点写入确定性 MMS 类型

服务端树形数据的反推分支现在为所有补充节点写入类型：

| 节点 | MMS 类型 |
|------|----------|
| `mag` 父节点 | `MMS_STRUCTURE` |
| `mag.f` | `MMS_FLOAT` |
| `q` | `MMS_BIT_STRING` |
| `t` | `MMS_UTC_TIME` |
| `dU` | `MMS_VISIBLE_STRING` |
| 其他结构父节点 | `MMS_STRUCTURE` |
| 已知 BDA | 按完整路径推断 |

类型来源优先级为：

```text
服务端点类型映射 → 客户端注册表类型 → 标准路径推断 → MMS_UNKNOWN
```

实际 ICD/运行时类型始终优先，静态推断只填补缺失信息。

### 4.4 系统 DO 默认类型补全

集中式 MMS 推断增加系统 DO 规则：

```text
NamPlt / PhyNam     → MMS_STRUCTURE
Beh / Health / Mod  → MMS_INTEGER
```

模型树在无法从已注册主值获得类型时使用该规则。普通信号 DO 仍优先展示实际主值的 MMS 类型，不会因为本次修改全部变成 `MMS_STRUCTURE`。

### 4.5 前端类型列宽调整

“测点类型”列由默认 `100px` 调整为 `180px`，以完整展示：

- `MMS_VISIBLE_STRING`；
- `MMS_GENERALIZED_TIME`；
- `MMS_DATA_ACCESS_ERROR`；
- 其他较长 MMS 类型标签。

调整只作用于该列，不改变其他协议列宽和表格交互。

## 5. 主要代码修改

以下代码保留了本次修复的关键判断，省略了日志、异常处理和与主题无关的上下文。实际实现以对应源码文件为准。

### 5.1 标准叶子类型优先使用静态推断

文件：`src/proto/iec61850/model/discovery.py`

```python
def _resolve_leaf_mms_type(
    self,
    conn,
    ref: str,
    fc: str,
    fallback: MmsType,
) -> MmsType:
    key = (ref, fc)
    cached = self._type_probe_cache.get(key)
    if cached is not None:
        return cached

    if fallback is not MmsType.UNKNOWN:
        self._type_probe_stats["total"] += 1
        self._type_probe_stats["static"] += 1
        self._type_probe_cache[key] = fallback
        return fallback

    return self._probe_mms_type(conn, ref, fc, fallback)
```

调用方先通过标准 DA/BDA 路径获得 `fallback`。只有结果仍为 `MMS_UNKNOWN` 时，才进入变量规格查询和安全运行值探测。

```python
fallback_mms_type = infer_mms_type_from_path(
    effective_da_path,
    effective_iec_type,
)
mms_type = specified_type or self._resolve_leaf_mms_type(
    conn,
    f"{do_ref}.{effective_da_path}",
    da_fc,
    fallback_mms_type,
)
```

### 5.2 复用 DO 目录判断描述是否存在

文件：`src/proto/iec61850/model/discovery.py`

```python
da_names = get_list_from_linked_list(da_list) if da_list is not None else []
if da_list is not None:
    self._description_da_cache[do_ref] = tuple(
        name for name in ("dU", "d") if name in da_names
    )
```

缓存查询保留 `None` 和空元组的区别：

```python
def description_da_names(self, do_ref: str) -> tuple[str, ...] | None:
    return self._description_da_cache.get(do_ref)
```

文件：`src/proto/iec61850/iec61850_client.py`

```python
for index, do_ref in enumerate(do_refs, start=1):
    description_das = self._discovery.description_da_names(do_ref)
    du_desc = (
        ""
        if description_das == ()
        else self._read_du_description(do_ref)
    )

    if du_desc:
        for point in do_point_index.get(do_ref, []):
            point["name"] = du_desc
            self._registry.set_name(point["address"], du_desc)
```

目录明确返回空元组时不再发起描述读请求；目录未知时仍调用原有兼容读取，避免影响特殊设备。

### 5.3 服务端反推模型树补充 MMS 类型

文件：`src/web/api/channel/iec61850.py`

```python
def _infer_tree_mms_type(path: str, *, is_struct: bool = False) -> str:
    if is_struct:
        return MmsType.STRUCTURE.value
    return infer_mms_type_from_path(path).value
```

结构父节点不再使用空字符串：

```python
do_info["da_map"][top_da] = {
    "da_name": top_da,
    "da_path": top_da,
    "fc": parent_fc,
    "is_struct": True,
    "mms_type": _infer_tree_mms_type(top_da, is_struct=True),
    "children": [],
}
```

补充的标准元数据 DA 同样写入确定性类型：

```python
da_map[da_name] = {
    "da_name": da_name,
    "da_path": da_name,
    "fc": fc,
    "is_struct": is_struct,
    "mms_type": _infer_tree_mms_type(
        da_name,
        is_struct=is_struct,
    ),
    "children": [],
}
```

已有服务端点类型或客户端注册表类型仍然优先：

```python
def _resolve_mms_type(
    address: str,
    fallback: str = "MMS_UNKNOWN",
) -> str:
    mms_type = _point_mms_type_map.get(address, "")
    if not mms_type and _client_mms_getter is not None:
        mms_type = _client_mms_getter(address) or ""
    return mms_type or fallback
```

### 5.4 系统 DO 的 CDC 语义映射到 MMS 类型

文件：`src/proto/iec61850/defs/mms_types.py`

```python
def infer_mms_type_from_path(
    path: str,
    iec_type: str | IecType = IecType.UNKNOWN,
) -> MmsType:
    leaf = str(path or "").split(".")[-1]

    if leaf in ("NamPlt", "PhyNam"):
        return MmsType.STRUCTURE

    # Beh/Health 为 ENS，Mod 为 ENC；其 stVal 在线上编码为整数。
    if leaf in ("Beh", "Health", "Mod"):
        return MmsType.INTEGER

    if leaf == "f":
        return MmsType.FLOAT
    if leaf in ("q", "subQ", "Check"):
        return MmsType.BIT_STRING
    if leaf in ("t", "T"):
        return MmsType.UTC_TIME
    if leaf in ("dU", "du", "d"):
        return MmsType.VISIBLE_STRING

    return mms_type_from_iec_type(iec_type)
```

模型树 DO 层仅在无法从已注册主值获得类型时采用默认推断。`NamPlt/PhyNam` 保持结构语义，`Beh/Health/Mod` 则展示其枚举主值对应的 `MMS_INTEGER`。

### 5.5 前端测点类型列宽

文件：`front/src/constants/table.ts`

```typescript
export const COLUMN_WIDTH_MAP: Record<string, number> = {
  '测点编码': 150,
  '测点名称': 200,
  'IEC104类型': 160,
  '测点类型': 180,
  '状态': 80,
  'default': 100,
};
```

## 6. 修改文件

| 文件 | 变更 |
|------|------|
| `src/proto/iec61850/model/discovery.py` | 静态类型优先、描述目录缓存、发现状态清理 |
| `src/proto/iec61850/iec61850_client.py` | 描述补充阶段跳过明确不存在的 `dU/d` |
| `src/proto/iec61850/defs/mms_types.py` | 铭牌 DO、ENS/ENC 系统 DO 默认 MMS 推断 |
| `src/web/api/channel/iec61850.py` | 服务端反推模型树的 DA/BDA/DO 类型补全 |
| `front/src/constants/table.ts` | “测点类型”列宽调整为 180px |
| `src/tests/iec61850/test_mms_types.py` | 标准、厂家自定义和系统 DO 类型回归测试 |
| `src/tests/iec61850/test_remote_discovery_refresh.py` | 无描述目录时零读取回归测试 |
| `src/tests/iec61850/test_model_tree_coverage.py` | 服务端模型树类型补全回归测试 |

## 7. 行为对比

### 7.1 类型发现

| 情况 | 优化前 | 优化后 |
|------|--------|--------|
| 标准 `mag.f` | 规格查询，失败后可能读值 | 本地直接返回 `MMS_FLOAT` |
| 标准 `q/t/dU` | 逐点在线探测 | 本地确定性映射 |
| 未知厂家字段 | 在线探测 | 仍在线探测 |
| 厂家控制字段 | 安全规格查询，不读控制值 | 行为不变 |

### 7.2 描述读取

假设模型包含 `N` 个普通 DO，且 IED 完全不提供 `dU/d`：

| 指标 | 优化前 | 优化后 |
|------|--------|--------|
| 每个 DO 描述读请求 | 最多 4 次 | 0 次 |
| 描述阶段额外请求 | 最多 `4N` | 0 |
| 失败 DEBUG 日志 | 每个 DO 一条 | 无 |

目录查询本身不是新增请求，它已经是模型发现过程的一部分。

### 7.3 服务端模型展示

优化前：

```text
mag     MMS_UNKNOWN
q       MMS_UNKNOWN
t       MMS_UNKNOWN
dU      MMS_UNKNOWN
Beh     MMS_UNKNOWN
Mod     MMS_UNKNOWN
```

优化后：

```text
mag     MMS_STRUCTURE
q       MMS_BIT_STRING
t       MMS_UTC_TIME
dU      MMS_VISIBLE_STRING
Beh     MMS_INTEGER
Health  MMS_INTEGER
Mod     MMS_INTEGER
```

## 8. 兼容性与安全边界

1. API 请求和响应结构不变，仅修正 `mms_type` 值。
2. ICD/SCL 的 `bType` 解析仍是离线导入类型的权威来源。
3. 厂家自定义、静态无法确定的类型继续在线探测，不强行套用标准类型。
4. 目录读取失败时不启用描述跳过，保留旧设备兼容路径。
5. `CO` 控制值不会因类型推断而被额外读取或写入。
6. 模型缓存格式不变，旧缓存仍可加载。
7. CDC 与 MMS 类型保持分层：CDC 用于模型语义，MMS 类型用于当前“测点类型”列和精确读写。

## 9. 验证结果

本次修复执行了以下验证：

| 验证项 | 结果 |
|--------|------|
| 标准类型不触发在线探测 | 通过 |
| 未知厂家字段继续变量规格探测 | 通过 |
| 无 `dU/d` 目录时不读取描述 | 通过 |
| `mag/q/t/dU` 服务端树类型 | 通过 |
| `NamPlt/PhyNam` 默认类型 | 通过 |
| `Beh/Health/Mod` 默认类型 | 通过 |
| IEC61850 定向回归测试 | 通过 |
| Ruff 静态检查 | 通过 |
| 前端 Vue/TypeScript 类型检查 | 通过 |
| Git 差异空白检查 | 通过 |

仓库当前另有一个可独立复现的控制状态点重定向测试失败，与本次模型发现、描述读取和 MMS 类型修复无关，未纳入本次变更范围。

## 10. 现场验收建议

建议使用“包含描述”和“不包含描述”的两类 IED 分别验收：

1. 强制重新发现模型，记录总耗时和 MMS 类型统计；
2. 确认无描述 IED 不再连续输出 `读取描述失败` 日志；
3. 检查 `mag/q/t/dU` 的 MMS 类型是否符合预期；
4. 检查 `Beh/Health/Mod` 是否显示 `MMS_INTEGER`；
5. 检查 `NamPlt/PhyNam` DO 层是否显示 `MMS_STRUCTURE`，展开后的 DA 是否保持自身类型；
6. 抽查厂家自定义字段，确认仍能通过在线规格查询获得实际类型；
7. 对比优化前后发现耗时，重点关注高延迟网络和数千 DO 的大模型。

## 11. 后续建议

- 在发现完成日志中进一步输出“跳过的静态类型探测数”和“跳过的描述读取数”，便于现场量化收益；
- 如果后续需要在同一列同时展示 CDC 与 MMS，建议拆分为“CDC 类型”和“MMS 类型”两列，避免 `ENS/ENC` 与 `MMS_INTEGER` 的语义混淆；
- 对超大模型建立固定设备基准，持续跟踪 MMS 请求总数、发现耗时和失败请求比例，而不只比较单次总耗时。
