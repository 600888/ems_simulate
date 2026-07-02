# IEC61850 MMS 类型识别与标签样式优化

> 版本: 1.0  
> 日期: 2026-07-02  
> 分类: MMS / 前后端 / UI 优化 / Bug 修复  
> 状态: 已实施

## 1. 问题背景

IEC61850 设备测点表格中的 MMS 类型原先使用普通文本展示，例如 `MMS_BOOLEAN`、`MMS_FLOAT`、`MMS_STRUCTURE`。同一表格内的帧类型、IEC104 类型和 FC 已使用标签样式，MMS 类型与现有视觉规范不一致，也不便于快速区分不同数据类别。

在使用部分厂家 IED 在线发现模型时，还发现控制结构与配置结构的子项会错误显示为 `MMS_UNKNOWN`。以 `SY_ES630K.icd` 为例，ICD 已明确声明 `Oper.ctlVal`、`Oper.ctlNum`、`Oper.T`、`Oper.Test` 等 BDA 的 `bType`，但在线发现为避免读取 FC=CO 的控制值，会使用静态兜底类型；原兜底映射未覆盖这些标准字段。`pulseConfig` 也未被识别为 CF 结构体。

本次优化同时修复在线模型 MMS 类型识别，并将 MMS 类型改为 Element Plus `el-tag` 展示，使其与 IEC104 类型列保持一致的视觉风格。

| 项目 | 优化前 | 优化后 |
|------|--------|--------|
| 展示组件 | 普通文本 `span` | Element Plus `el-tag` |
| 标签效果 | 无 | `effect="light"` |
| 类型区分 | 仅依赖类型名称 | 类型名称 + 标签颜色 |
| 表格提示 | 使用文本溢出提示 | 标签完整展示，不启用溢出提示 |
| 控制 BDA 类型 | 多个字段显示 `MMS_UNKNOWN` | 按 IEC61850 标准语义识别 |
| `pulseConfig` | 普通未知 DA | `CF / MMS_STRUCTURE` 并展开 BDA |

## 2. 优化方案

### 2.1 MMS 类型标签渲染

在设备测点表格的动态列渲染中增加 MMS 类型分支。当满足以下条件时，使用标签展示：

- 当前设备为 IEC61850 设备。
- 当前列为“测点类型”。
- 当前行存在 MMS 类型值。

核心渲染逻辑：

```vue
<el-tag
  v-else-if="isIec61850 && header === '测点类型' && scope.row[header]"
  :type="getMmsTagType(scope.row[header])"
  effect="light"
  class="status-tag"
>
  {{ scope.row[header] }}
</el-tag>
```

该分支只影响 IEC61850 的 MMS 类型列，不改变其他协议的测点表格展示。

### 2.2 标签颜色分类

新增 `getMmsTagType()`，按 MMS 数据语义返回 Element Plus 标签类型：

| 分类 | MMS 类型 | 标签类型 | 视觉含义 |
|------|----------|----------|----------|
| 布尔类型 | `MMS_BOOLEAN` | `success` | 状态量，绿色 |
| 数值类型 | `MMS_FLOAT`、`MMS_INTEGER`、`MMS_UNSIGNED`、`MMS_BCD` | `primary` | 数值量，主色 |
| 时间类型 | `MMS_UTC_TIME`、`MMS_BINARY_TIME`、`MMS_GENERALIZED_TIME` | `warning` | 时间量，橙色 |
| 复合及错误类型 | `MMS_ARRAY`、`MMS_STRUCTURE`、`MMS_DATA_ACCESS_ERROR` | `danger` | 复合结构或访问错误，红色 |
| 其他类型 | 字符串、位串、八位组及未知类型等 | `info` | 通用类型，灰色 |

未知或后续新增的 MMS 类型统一回退为 `info`，避免出现无样式标签。

### 2.3 表格溢出提示调整

“测点类型”列加入标签列排除列表，不再启用普通文本的 `show-overflow-tooltip`。标签文本由 `el-tag` 自身展示，避免鼠标悬停时出现不必要的重复提示。

### 2.4 通用在线类型发现

在线发现优先调用 libIEC61850 的 `IedConnection_getVariableSpecification()` 获取变量类型规格，再通过 `MmsVariableSpecification_getType()` 转换为原生 MMS 类型。该流程只读取模型元数据，不读取变量值，因此同样适用于 FC=CO 控制字段。

这条链路不依赖 ICD 文件名、厂家 Type ID 或 DA/BDA 字段名：

- 已知 FC 的字段直接查询变量类型规格。
- FC 未知的厂家自定义字段按候选 FC 查询，并使用服务器实际返回的 FC 和 MMS 类型。
- 类型规格显示为结构体时，继续从服务端目录发现子项；厂家自定义结构无需加入名称白名单。
- 当前 pyiec61850 绑定或目标设备不支持类型规格时，才回退到运行时读值探测与标准字段静态映射。

标准控制 BDA 的兼容回退如下：

| 路径 | ICD `bType` | 修复后的 MMS 类型 |
|------|-------------|--------------------|
| `Oper.ctlVal` | `BOOLEAN` | `MMS_BOOLEAN` |
| `Oper.origin` | `Struct` | `MMS_STRUCTURE` |
| `Oper.ctlNum` | `INT8U` | `MMS_UNSIGNED` |
| `Oper.T` | `Timestamp` | `MMS_UTC_TIME` |
| `Oper.Test` | `BOOLEAN` | `MMS_BOOLEAN` |
| `Oper.Check` | `Check` | `MMS_BIT_STRING` |

同时将 `pulseConfig` 纳入在线结构展开范围：

| 路径 | 修复后的 FC | 修复后的 MMS 类型 |
|------|-------------|--------------------|
| `pulseConfig` | `CF` | `MMS_STRUCTURE` |
| `pulseConfig.cmdQual` | `CF` | `MMS_INTEGER` |
| `pulseConfig.onDur` | `CF` | `MMS_UNSIGNED` |
| `pulseConfig.offDur` | `CF` | `MMS_UNSIGNED` |
| `pulseConfig.numPls` | `CF` | `MMS_UNSIGNED` |

当类型规格或在线目录不可用时，使用同一组标准 BDA 作为兼容回退，避免结构节点再次退化为 `MMS_UNKNOWN`。

## 3. 实现说明

MMS 标签复用 IEC104 类型已有的以下视觉约定：

- 使用 Element Plus `el-tag`。
- 使用浅色 `light` 效果。
- 复用 `status-tag` 类名。
- 根据类型返回 `primary/success/info/warning/danger` 语义色。

颜色映射函数放在表格常量模块中，与 `getIec104TagType()` 相邻，便于后续统一维护协议类型标签规则。

后端类型推断优先级为“变量类型规格 → 安全的运行时读值探测 → 标准静态映射”。变量类型规格查询不会读取或写入控制值，既能识别厂家自定义名称，也保持现有控制安全边界。

## 4. 修改文件清单

| 文件 | 改动 | 说明 |
|------|------|------|
| `front/src/components/device/Table.vue` | 小 | 增加 MMS 类型 `el-tag` 渲染分支，并关闭该列普通文本溢出提示 |
| `front/src/constants/table.ts` | 小 | 新增 `getMmsTagType()` 及 MMS 类型颜色分类规则 |
| `src/proto/iec61850/defs/mms_types.py` | 小 | 补充控制 BDA、时间字段和脉冲配置的静态 MMS 类型推断 |
| `src/proto/iec61850/defs/da_patterns.py` | 小 | 补充 `pulseConfig` 的 FC、结构展开规则及标准 BDA 类型 |
| `src/proto/iec61850/model/discovery.py` | 中 | 增加通用变量类型规格查询、未知 FC 探测、自定义结构展开及 BDA 回退逻辑 |
| `src/tests/iec61850/test_mms_types.py` | 小 | 增加厂家自定义类型、控制结构和 `pulseConfig` 在线发现回归测试 |

本次修改不改变 IEC61850 API 结构、测点值或控制流程，只修正模型节点的 MMS 类型与 FC 元数据并优化前端展示。

## 5. 优化后的行为

- IEC61850 DO、DA、BDA 行的 MMS 类型均以标签形式展示。
- 同类 MMS 类型使用一致颜色，便于浏览大规模模型时快速识别。
- `MMS_UNKNOWN` 和未纳入显式映射的新类型仍能以 `info` 标签正常显示。
- `Oper` 标准控制 BDA 不再大面积显示 `MMS_UNKNOWN`。
- `pulseConfig` 显示为 `CF / MMS_STRUCTURE`，并展示标准配置子项。
- IEC104 类型、帧类型、FC 标签及其他协议表格行为保持不变。

## 6. 验证结果

### 6.1 TypeScript/Vue 类型检查

```text
npm run type-check
passed
```

### 6.2 前端生产构建

```text
npm run build:fast
✓ 1856 modules transformed
✓ built successfully
```

构建过程中仅保留现有的 `channelApi.ts` 动态导入与静态导入并存提示，不影响本次功能和构建结果。

### 6.3 IEC61850 后端测试

```text
python -m pytest -q src/tests/iec61850
146 passed, 25 skipped, 1 warning

ruff check ...
passed

ruff format --check ...
passed
```

新增测试覆盖任意厂家自定义字段的变量规格识别、未知 FC 解析、自定义结构展开、`Oper` 六个标准 BDA、`pulseConfig` 结构展开及静态兼容回退。

## 7. 兼容性说明

1. MMS 类型原始文本不做翻译或格式转换，仍直接展示后端返回值。
2. 标签颜色只影响视觉表现，不参与筛选、排序或业务判断。
3. 未识别类型使用 `info` 作为默认样式，兼容后端后续扩展新的 MMS 类型。
4. 非 IEC61850 设备不会进入 MMS 标签渲染分支。
5. FC=CO 类型推断只读取模型目录，不读取或写入控制值，不改变现有控制安全边界。
