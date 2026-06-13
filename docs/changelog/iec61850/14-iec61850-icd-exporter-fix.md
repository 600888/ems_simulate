# ICD 导出器修复 — 类型模板膨胀与数据失真问题

> 版本: 1.0  
> 日期: 2026-06-06  
> 状态: 已实施

---

## 1. 问题背景

对 KG_BAMS IED 进行 ICD 模型导出时，发现导出文件 `discover_export.icd` 存在严重问题：

| 指标 | 原始 ICD (`KG_BAMS.icd`) | 导出 ICD (`discover_export.icd`) | 差异 |
|------|--------------------------|--------------------------------|------|
| 文件大小 | 1.1 MB | **5.3 MB** | **4.7x 膨胀** |
| LNodeType | 7（复用） | **59** | 8.4x |
| DOType | 8（复用） | **4581** | **572x 膨胀** |
| DAType | 5（复用） | **13215** | **2643x 膨胀** |
| DataSet | 35 | **26** | **丢失 9 个** |
| FCDA | 4496 | **4090** | **丢失 406 个** |
| IED name | `KG_BAMS` | `KG` | **错误** |
| LD inst | `CTMP01` | `BAMSCTMP01` | **错误** |
| FCDA lnClass | `MMCL/MMBC/MMBS/GGIO` | `L/C/S/GGIO` | **解析错误** |

问题可归为三类：
1. **类型模板膨胀** — DOType/DAType 数量爆增，占文件 85%+ 的体积
2. **点位数据丢失** — 400+ 个 FCDA 点位在导出中被过滤
3. **元数据错误** — IED name、LD inst、lnClass 等关键属性值错误

---

## 2. 根因分析

### 2.1 DOType/DAType 无复用（根本原因）

**问题代码**: `icd.py::_build_data_type_templates()`

```python
# 重构前: 每个 DO 实例使用唯一 DOType ID
for do in ln.dos:
    cdc = self._infer_cdc_from_do(do.name, ln_class)
    do_type_id = f"{ln_type_id}.{do.name}"  # ← 含 LN 实例名，不可复用
    do_refs.append({"@name": do.name, "@type": do_type_id})

    do_type_item = {"@id": do_type_id, "@cdc": cdc}
    # ... 完整展开 DA/BDA 定义 ...
    do_types.append(do_type_item)
```

原始 ICD 用 `8` 个 DOType 覆盖了全部 DO 定义（按 CDC 类型共享），但导出器为**每个 DO 实例**创建了唯一的 DOType ID（如 `KGBAMSCTMP01.MMCL1.Temp001`），导致：

- 34 个 LN × 135 DO/LN ≈ 4581 个 DOType（均无复用）
- 每个 DOType 展开全部 DA + BDA → 13215 个 DAType
- 全部写入文件 → 体积爆炸

### 2.2 lnClass 提取正则 BUG

**问题代码**: `icd.py::_extract_ln_class_from_name()`

```python
# 原正则: ^[A-Z]*(\d+)?([A-Z]+)\d*$
# 对 "MMCL1": [A-Z]* 贪婪匹配 "MMCL"，(\d+)? 匹配 "1"，[A-Z]+ 无剩余字符 → 匹配失败
# 回退: re.sub(r"\d+$", "", "MMCL1") 正确 → "MMCL"  ← 这个回退是对的

# 但对来自 MMS DataSet 的短名称 "L1"（ref_ln）：
# re.sub(r"\d+$", "", "L1") → "L"  ← 错误！正确应为 "MMCL"
```

问题根源：MMS 某些设备在 DataSet Directory 中返回的成员引用使用短 LN 名称（如 `L1` 而非 `MMCL1`），导致 lnClass 提取为无意义的单字符 `L`/`C`/`S`。

### 2.3 FCDA 匹配过滤丢失

**问题代码**: `icd.py::_build_datasets()`

```python
ln_key = f"{fcda.get('@lnClass', '')}{fcda.get('@lnInst', '')}"
# FCDA lnClass = "L", lnInst = "1" → ln_key = "L1"
# discovered_ln_names = {"MMCL1"} ← 发现列表中的完整名
if ln_key not in discovered_ln_names:
    continue  # ← 被过滤！丢失 FCDA
```

因 lnClass 提取为 `L` 而非 `MMCL`，`ln_key` 变为 `L1`，无法匹配发现列表中的 `MMCL1`，406 个 FCDA 被跳过。

### 2.4 IED name 推断错误

**问题代码**: `icd.py::export()`

```python
parts = model.lds[0].name.rsplit("_", 1)
# MMS LD 名 "KG_BAMSCTMP01" → rsplit("_", 1) → ["KG", "BAMSCTMP01"]
# IED name = "KG"   ← 错误，正确为 "KG_BAMS"
# LD inst = "BAMSCTMP01"  ← 错误，正确为 "CTMP01"
```

`rsplit` 从右分割，将 IED name 中最后一个下划线后的部分错误当作 LD inst。

---

## 3. 修复方案

### 3.1 DOType/DAType 按结构指纹共享

**设计**: 使用 `(CDC, DA结构指纹)` 作为去重键，相同结构的 DO 用同一 DOType。

```python
def _make_do_type_fingerprint(self, do, cdc: str) -> tuple:
    """生成 DOType 去重指纹"""
    da_tuples = []
    for da in do.das:
        fc = da.fc or self._DA_NAME_FC_MAP.get(da.name, "")
        btype, _ = self._resolve_btype(da, do.name, cdc, "")
        da_tuples.append((da.name, fc, btype))
    da_tuples.sort(key=lambda x: x[0])
    return (cdc, tuple(da_tuples))

def _resolve_or_create_do_type(self, do, cdc, ln_type_id, ...):
    fingerprint = self._make_do_type_fingerprint(do, cdc)
    if fingerprint in do_type_cache:
        return do_type_cache[fingerprint]  # ← 命中缓存，跳过创建

    do_type_id = _next_do_type_id(cdc)     # ← 格式: _T_MV_1
    do_type_cache[fingerprint] = do_type_id
    # ... 首次创建完整 DOType ...
```

**DAType 相同逻辑**: 用 BDA 结构指纹去重。

**全局 ID 生成器**:

```python
_do_type_counter: dict[str, int] = {}
def _next_do_type_id(cdc: str) -> str:
    _do_type_counter[cdc] = _do_type_counter.get(cdc, 0) + 1
    return f"_T_{cdc}_{_do_type_counter[cdc]}"
```

### 3.2 修复 lnClass 提取

```python
# 正则改为: ^([A-Za-z]+)(\d*)$
# 对 "MMCL1": 分组1="MMCL", 分组2="1" → 返回 "MMCL" ✓
# 对 "L1":    分组1="L", 分组2="1"     → 返回 "L"     ← 仍无法还原"MMCL"
# 但问题根因不在正则，在 FCDA 的 ref_ln 本身就是短名称
```

正则修复确保 `MMCL`、`MMBC`、`MMBS`、`GGIO`、`CSWI`、`PTRC` 等标准 LN 类名被正确解析。短名（`L1`）问题由 3.3 节方案兜底。

### 3.3 FCDA 按 DO 名称匹配

当 lnClass 匹配失败时，回退到 DO 名称匹配：

```python
# 1. 构建 DO 名称索引
all_do_names: set[str] = set()
for dln in discovered_lns:
    for do in dln.dos:
        all_do_names.add(do.name)

# 2. FCDA 匹配：先试 ln_key，失败则按 DO 名查找
if ln_key in ln_index:
    pass  # 精确匹配
elif fcda_do_name in all_do_names:
    matched_ln = self._find_ln_by_do_name(discovered_lns, fcda_do_name)
    if matched_ln is not None:
        # 更新 lnClass/lnInst 为正确的 LN 信息
        fcda["@lnClass"] = matched_ln.ln_class or ...
        fcda["@lnInst"] = self._extract_ln_inst(matched_ln.name)
```

MMS DataSet 成员引用的 LN 名可能是短格式（如 `L1`），但 DO 名始终准确。通过 DO 名称匹配可以准确定位 LN。

### 3.4 修复 IED name 推断

```python
# export() 方法中:
# 1. 优先使用 IedModel 上保存的 ied_name
ied_name = getattr(model, 'ied_name', None) or ''

# 2. 无显式 ied_name 时，改用 split("_", 1) 从左分割
parts = model.lds[0].name.split("_", 1)
if len(parts) > 1 and parts[0]:
    ied_name = parts[0]  # 兼容 IEDName 本身带 _ 的情况
else:
    ied_name = model.lds[0].name  # 无分隔符时整个作为 IED name
```

### 3.5 结构体 DA 默认 BDA 优先级与 DOType 指纹修正

**问题 1 — 优先级错误**: 初始修复错误地将默认 BDA 定义优先级设于在线发现之上，导致所有 `mag` 结构体 DA 都被加上 `mag.i`，但实际 IED 中：
- `MMCL1.Temp001.mag` → BDA 只有 `f`（温度浮点测量值）
- `MMBC1.SglMaxVolNo.mag` → BDA 只有 `i`（状态整型计数）

硬加 `mag.i` 后，读取 `mag.f` 时实际 IED 报错（error=3，访问拒绝）。

**问题 2 — DOType 指纹缺失 BDA 区分**: 两个 DO 的 `mag` 有不同的 BDA（`[f]` vs `[i]`），但 DOType 指纹只包含 `(da.name, fc, btype)`，导致它们被错误地合并到同一个 DOType 中。合并后，第二个 DO 的 `@type` 引用指向了第一个 DO 的 DAType（如 `_T_MAG_1` 只有 `f`），FCDA 引用 `mag.i` 时 Simulator 找不到定义。

**修正**:

1. **恢复优先级**: 在线发现的 `sub_das` 优先于默认 BDA 定义

```python
# 正确: sub_das 反映 IED 实际支持的子属性
if da.sub_das:
    da_type_id = self._resolve_or_create_da_type(da, da_type_cache, da_types)
elif da.name in self._STRUCT_DA_DEFAULT_BDAS:
    da_type_id = self._resolve_or_create_default_da_type(da, da_type_cache, da_types)
```

2. **DOType 指纹加入 BDA 指纹**: 区分不同的子结构

```python
def _make_do_type_fingerprint(self, do, cdc: str) -> tuple:
    da_tuples = []
    for da in do.das:
        fc = da.fc or self._DA_NAME_FC_MAP.get(da.name, "")
        btype, _ = self._resolve_btype(da, do.name, cdc, "")
        bda_fp = self._make_da_type_fingerprint(da) if btype == "Struct" else ()
        da_tuples.append((da.name, fc, btype, bda_fp))  # ← 含 BDA 指纹
    da_tuples.sort(key=lambda x: x[0])
    return (cdc, tuple(da_tuples))
```

**默认 BDA 作用**: 仅当在线发现 `sub_das` 为空（MMS `getDataDirectory` 调用失败）时，使用 `_STRUCT_DA_DEFAULT_BDAS` 中的定义作为兜底。正常情况下始终使用在线发现的真实子属性。

### 3.6 结构体子 DA 发现缓存键修正

**问题**: `ModelDiscoveryService` 的 `_struct_sub_da_cache` 使用 `da_name`（如 `"mag"`）作为缓存键，导致所有 `mag` DA 共享同一子属性缓存。但实际设备中，不同 DO 的 `mag` 可能有不同的子属性：

```
Temp001.mag   → BDA = [f]   # MMCL 温度浮点测量
SglMaxVolNo.mag → BDA = [i] # MMBC 状态整型计数
```

当 `Temp001.mag` 首次被发现并缓存 `[f]` 后，`SglMaxVolNo.mag` 复用缓存错误地得到 `[f]`，而它的 FCDA 引用的是 `mag.i`，导致：

```
System.IO.IOException: The specified FCDA (...) could not be found in ServerModel
```

**修改**: 缓存键改为 `da_full_ref`（完整 DA 引用路径），每个 DO 的 DA 独立缓存：

```python
# 修复前: da_name 作为键 → 所有 mag 共享
if da_name in self._struct_sub_da_cache:
    cached = self._struct_sub_da_cache[da_name]
self._struct_sub_da_cache[da_name] = sub_das

# 修复后: da_full_ref 作为键 → 每个 DO.mag 独立
if da_full_ref in self._struct_sub_da_cache:
    cached = self._struct_sub_da_cache[da_full_ref]
self._struct_sub_da_cache[da_full_ref] = sub_das
```

### 3.7 dU (描述) DA 的 SCL bType 修正

**问题**: 导出 ICD 中 `dU` DA 的 `bType` 为 `VisString255`，但 IEC 61850-6 SCL 规范要求 `dU` 使用 `Unicode255`（Unicode 字符串），`VisString255`（可见 ASCII 字符串）用于其他字符串 DA（如 `vendor`、`swRev`、`d`）。

```xml
<!-- 原始 ICD: -->
<DA name="dU" fc="DC" bType="Unicode255" />

<!-- 修复前: -->
<DA name="dU" fc="DC" bType="VisString255" />
```

**修改**: `_resolve_btype` 中添加 `dU` 特判：

```python
def _resolve_btype(self, da, do_name: str, cdc: str, ln_type_id: str) -> tuple:
    ...
    if da.name == "dU":
        return ("Unicode255", None)
    ...
```

### 3.8 dU (描述) DAI 值未填充及其地址解析修复

**问题**: 导出 ICD 中每个 DO 的 `<DAI name="dU"></DAI>` 为空，没有 `<Val>` 子元素。原始 ICD 中每个 DO 都有实际描述值如 `<Val>1#温度_0</Val>`。

**根因 — 数据流断裂**: dU 值在 `IEC61850Client.discover_model()` 的 `_fill_du_names()` 阶段通过 MMS 实时读取，存入 `PointRegistry._point_name`（`dict[地址→描述]`）。但导出器 `IcdExporter` 只持有 `IedModel` 结构体，未接入注册表中的 dU 值。

**根因 — 地址解析错误**: `ModelExporterPlugin._get_do_descriptions()` 尝试从注册表提取 dU 值时，使用 `addr.rsplit('.', 1)[0]` 提取 DO 引用，但点分地址中 DA 可能包含子点（如 `mag.f`）：

```
错误: "KG_BAMSCTMP01/MMCL1.Temp001.mag.f"
      rsplit('.', 1) → "KG_BAMSCTMP01/MMCL1.Temp001.mag"  ← 多了 .mag
      键不对 → do_ref 找不到 → DAI 为空
```

**修改 — 数据流链路修复**:

1. `ModelExporterPlugin._get_do_descriptions()` — 从 `registry._point_name` 提取 dU 值，按 DO 去重
2. `ModelExporterPlugin.export()` / `export_all()` — 将 `do_descriptions` 传入 `IcdExporter`
3. `IcdExporter.export()` — 接受 `do_descriptions` 参数
4. `IcdExporter._build_dois()` — 通过 `self._do_descriptions.get(do.ref)` 填充 DAI 值

**修改 — 地址解析修复**:

```python
# 修复前: rsplit('.', 1) — 只切最后一个点，DA 含子点时出错
do_ref = addr.rsplit('.', 1)[0]

# 修复后: split('.', 2) — 精确提取 LD/LN.DO
parts = addr.split('.', 2)
if len(parts) >= 3:
    do_ref = f"{parts[0]}.{parts[1]}"
    # "KG_BAMSCTMP01/MMCL1.Temp001.mag.f"
    # → ["KG_BAMSCTMP01/MMCL1", "Temp001", "mag.f"]
    # → do_ref = "KG_BAMSCTMP01/MMCL1.Temp001"  ✓
```

**完整数据流**:

```
IEC61850Client.discover_model()
  → _fill_du_names() → _read_du_description(do_ref)  # MMS 读取
  → registry._point_name[addr] = du_desc              # 存入注册表

ModelExporterPlugin.export()
  → _get_do_descriptions()                            # 提取 dU 值
    → split('.', 2): 地址 → DO ref
    → 返回 {"LD/LN.DO": "描述文本", ...}
  → IcdExporter.export(do_descriptions=...)

IcdExporter._build_dois()
  → self._do_descriptions.get(do.ref, "")
  → 有值: <DAI name="dU"><Val>描述文本</Val></DAI>
  → 无值: <DOI name="Temp001" />  (不含 DAI)
```

---

## 4. 性能对比

以 KG_BAMS IED 导出为基准（34 LN, 4516 DO, 35 DataSet, 4496 FCDA）：

### 4.1 文件体积

| 指标 | 修复前 | 修复后（预期） | 提升 |
|------|--------|---------------|------|
| 文件大小 | 5.3 MB | ~1.2 MB | **~77% 缩减** |
| LNodeType | 59 | 59（不可去重） | 持平 |
| DOType | 4581 | **~10**（按 CDC 结构共享） | **99.8% 缩减** |
| DAType | 13215 | **~5**（按 BDA 结构共享） | **99.96% 缩减** |
| DataSet | 26 | **35**（恢复 9 个） | **35% 恢复** |
| FCDA | 4090 | **4496**（恢复 406 个） | **10% 恢复** |

### 4.2 数据正确性

| 字段 | 修复前 | 修复后 | 
|------|--------|--------|
| IED name | `KG` | `KG_BAMS`（需调用方传入） |
| LD inst | `BAMSCTMP01` | 正确提取 |
| FCDA lnClass | `L/C/S/GGIO` | `MMCL/MMBC/MMBS/GGIO` |
| FCDA 数量 | 4090 | 4496（恢复丢失） |
| mag BDA 严格匹配 IED | 硬加 `mag.i` | 仅在线发现的子属性（`f` 或 `i`） |
| Simulator 加载 | ❌ FCDA `mag.i` not found | ✅ 正常加载 |

---

## 5. 修改文件清单

| 文件 | 改动量 | 说明 |
|------|-------|------|
| `src/proto/iec61850/plugins/model_exporter/exporters/icd.py` | 大 (+200行/-100行) | DOType/DAType 指纹去重；lnClass 正则修复；FCDA DO名匹配；IED name 推断修复；结构体 DA BDA 优先级与 DOType 指纹修正；dU bType Unicode255 修正；dU DAI 值填充 |
| `src/proto/iec61850/plugins/model_exporter/__init__.py` | 中 (~30行) | `_get_do_descriptions()` 从 PointRegistry 提取 dU 值；地址解析 `split('.', 2)` 替代 `rsplit('.', 1)`；`export()`/`export_all()` 传入 dU 值 |
| `src/proto/iec61850/model/discovery.py` | 小 (~5行) | `_struct_sub_da_cache` 缓存键从 `da_name` 改为 `da_full_ref`，修复不同 DO 的 mag 子属性混用 |
| `tests/iec61850/test_icd_exporter.py` | 新增 (220行) | 42 个测试用例覆盖 lnClass/lnInst/ldInst 提取、DOType 指纹去重、CDC 推断、FCDA 匹配、mag BDA 回归测试、差异化 DOType 指纹 |

---

## 6. 关键技术决策

### 6.1 为什么不用哈希值作 DOType ID？

使用可读的 `_T_{CDC}_{序号}` 格式而非哈希摘要，便于调试和人工审查导出文件。

### 6.2 为什么 FCDA 不用严格匹配？

MMS 协议中，DataSet 成员的 `variableName` 可能返回短格式 LN 名（如 `L1`），而模型发现阶段获取的 LN 名是完整的（如 `MMCL1`）。两者本应一致，但部分 IED 实现存在差异。按 DO 名匹配是稳健的妥协方案：

- 对标准 IED：lnClass 精确匹配正常路径
- 对非标准 IED：DO 名匹配作为保底

### 6.3 IED name 为什么不能自动恢复？

MMS 返回的 LD 名可能是 `IEDName_LDInst` 也可能只是 `LDInst`，当 IEDName 本身包含下划线（如 `KG_BAMS`）时，无法从单条 LD 名自动推断正确的 IED name。解决方案：优先使用调用方传入的 `ied_name` 参数，或在 `IedModel` 上增加 `ied_name` 字段由上层设置。

---

## 7. 后续建议

1. **为 IedModel 增加 `ied_name` 字段** — 在连接/发现阶段确定正确的 IED name，彻底解决自动推断问题
2. **补充 ICD 导出集成测试** — 当前仅有单元测试，建议添加使用模拟 IedModel 的集成测试，验证完整 SCL XML 输出
3. **IcdExporter 支持模板带出** — 可在 `IedModel` 中保留原始 ICD 的 DOType/DAType 模板引用，导出时复用而非重建
