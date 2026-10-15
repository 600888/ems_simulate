# IEC 61850 通用枚举支持整改计划

日期：2026-10-15；实施更新：2026-10-16。状态：第一批核心链路已实现，后续功能继续按本文分阶段推进。

## 1. 目标与原则

实现一套由元数据驱动的枚举能力，贯通 SCL 建模、导入、运行模型、缓存、界面显示、设值校验和导出。支持标准枚举、厂商枚举、用户建模定义的枚举，以及缺少 SCL 时显式绑定的本地显示字典。

最终体验：用户选择 `3 · direct-with-enhanced-security · 直接控制／增强安全`，程序保存、仿真和协议写入使用整数 `3`；厂商增加新的 EnumType 后，无须修改前端代码即可显示对应下拉框。

实施原则：

1. 通过 DA/BDA 的 `bType="Enum"` 和 `type` 引用解析真实定义，不依赖类型 ID 或属性名称猜测。
2. 枚举的语义类型与底层 MMS 类型分开保存；普通 Enum 通常以 MMS_INTEGER 传输，不为增加下拉框而改变协议编码。
3. 有枚举选项不代表设备允许远程修改；界面选项、SCL 工程配置、本地仿真和远端写入分别判断。
4. 自定义标准允许扩展的数据模型时使用适当命名空间并做模型校验；不能随意重新解释标准 `ctlModel` 等字段的固定语义。
5. 保留原始整数、原始 literal 和来源。中文说明属于显示层，不覆盖 SCL 原文。

## 2. 当前代码的实际断点

以下结论来自当前工作区源码检查，不表示所有入口均已运行验证。

| 环节 | 当前实现与问题 | 整改位置 |
| --- | --- | --- |
| SCL 解析 | 已有 `SclEnumType`、`SclEnumVal(ord, value, desc)`；非法 ord 被静默改为 0，EnumType 的 desc 未建模 | `src/proto/iec61850/plugins/scl/model/scl_document.py`、`parser/scl_parser.py` |
| 类型展开 | `TypeResolver` 返回 bType/iecType/mmsType，但没有传递 EnumType 引用及选项；嵌套 Struct BDA 被跳过 | `src/proto/iec61850/plugins/scl/parser/type_resolver.py` |
| 服务端运行模型 | `_build_da` 将 Enum 映射为 integer；BDA 未携带枚举语义，深层 Struct 不展开 | `src/proto/iec61850/plugins/scl/transformer/server_model_builder.py` |
| 统一模型 | `DARef` 只有 IEC/MMS 类型等字段，没有 bType/typeId/enumRef；字典序列化随之丢失信息 | `src/proto/iec61850/model/ied_model.py` |
| 注册与缓存 | PointRegistry、registry bridge、模型 JSON 缓存需要随统一模型传递枚举元数据 | `src/proto/iec61850/core/registry.py`、`model/registry_bridge.py`、`model/cache.py` |
| API | 树数据主要返回数值与 MMS 类型；写值请求使用 `float \| str`，没有枚举契约 | `src/web/api/channel/iec61850.py` |
| 写值界面 | `Iec61850WriteDialog.vue` 统一使用文本框，依靠 Number 转换输入 | `front/src/components/device/Iec61850WriteDialog.vue`、`front/src/api/channelApi.ts` |
| 工程建模 | 已支持 ENUM_TYPE / ENUM_VALUE 节点与 EnumType 引用，不应另起一套类型管理；需要补易用的条目编辑与实例值选项 | `src/modeling/catalog.py`、`reference_options.py`、`effective_instance.py`、`front/src/views/modeling/ModelWorkspaceView.vue` |
| 导出 | 运行模型 ICD 导出器存在固定枚举表及 `0=unknown` 占位逻辑；建模序列化器输出 EnumVal 时未显式输出 desc | `src/proto/iec61850/plugins/model_exporter/exporters/icd.py`、`src/modeling/scl_serializer.py` |

关键链路：

```text
SCL EnumType 定义已存在
  → 类型展开／运行模型丢失 typeId 和条目
  → 注册表、缓存和 API 无法提供选项
  → 前端只看到 integer，使用文本框
```

2026-10-15 对 `data/` 和 `tests/fixtures/iec61850/` 中 ICD/CID/SCD/IID/SED 的只读扫描：43 个文件，443 个 EnumType，72 种不同条目组合，无 XML 解析失败。组合按原始条目顺序、ord 文本和 literal 文本比较，不代表 72 个标准枚举类型；样本包含副本及非标准定义。

实际已有 `CtlModels/ctlModel/CN_ctlModel`、`OrCat/OrCategory/orCategory/CN_orCategory` 等多种 ID；还有 SIUnit、方向、开关能力、风机控制、运行状态等定义。不能维护一份全局 `id → 标准表` 来覆盖它们。

## 3. 常见枚举与适用场景

这是首批覆盖清单，不是 IEC 61850 全部枚举，也不表示所有字段都能在线设置。常见条目以用户提供的 XML、本项目样本及文末资料核对；具体工程始终以绑定的 SCL、所用标准版本和设备实现为准。

| 字段／类型族 | 常见 ord → literal | 界面用途与限制 |
| --- | --- | --- |
| `ctlModel` / CtlModels | 0=status-only；1=direct-with-normal-security；2=sbo-with-normal-security；3=direct-with-enhanced-security；4=sbo-with-enhanced-security | 工程控制模型配置与状态展示；远端支持修改与否需独立判断 |
| `origin.orCat` / OrCategory | 0=not-supported；1=bay-control；2=station-control；3=remote-control；4=automatic-bay；5=automatic-station；6=automatic-remote；7=maintenance；8=process | 控制命令来源参数或状态记录；不能把来源字段一概当成独立可写点 |
| `sboClass` / SboClasses | 0=operate-once；1=operate-many | SBO 选择后单次／多次操作配置；实际能力依设备 |
| `Mod`、`Beh` 类型族 | 常见 1=on；2=blocked；3=test；4=test/blocked；5=off | Mod 是模式控制，Beh 是行为状态；界面可共用选项，访问与操作规则不同 |
| `Health` 类型族 | 常见 1=OK；2=Warning；3=Alarm；样本大小写不同 | 健康状态显示与本地仿真；通常不是远端命令 |
| `units.SIUnit`、`units.multiplier` | 来自对应模型的单位和倍率字典 | 大选项列表需搜索；倍率包含负编码的情况不能被无符号校验拦截 |
| 方向、相别、角度参考、开关能力等 | 逐项读取真实 EnumType，不按短名称套表 | 先完整解析、显示；是否加入标准模板库另行核对版本 |
| 厂商／项目自定义 EnumType | 例如 0=idle，10=charging，20=discharging，99=fault | 支持非连续 ord、任意合法 ID、Unicode 文本和嵌套 BDA |

另有两类离散选项需要复用控件，但保持独立语义：

| 类型 | 常见选择 | 处理要求 |
| --- | --- | --- |
| `Dbpos` | 0=中间态，1=分位，2=合位，3=异常态 | 属于 CODED ENUM；标准映射使用位串，不能套用普通 Enum 的整数编码。见 [libiec61850 Dbpos 文档](https://support.mz-automation.de/doc/libiec61850/c/latest/group__DBPOS.html) |
| `Tcmd` | 常见 0=stop，1=lower，2=higher，3=reserved | 独立编码枚举适配器；reserved 不作为普通操作选项。绑定 SCL 如显式声明为 Enum，则按该声明处理并给出兼容性诊断 |

`Quality`、`Check`、`OptFlds`、`TrgOps` 是标志或位域，应使用位域编辑器；即使某个厂商将类似名称用于 EnumType，也要根据实际 bType 选择编码，不能仅看名字。DPC 的 `stVal` 可能是 Dbpos，而 `Oper.ctlVal` 为 BOOLEAN，写值必须使用目标属性自身的类型域。ABB 的 [DPC 类说明](https://help.plc.abb.com/iec_61850_server_introduction.html)也展示了这一差别。

## 4. 自定义的三种模式

### 4.1 从 SCL 导入厂商枚举

```xml
<DOType id="VendorBattery" cdc="ENS">
  <DA name="stVal" bType="Enum" type="VendorChargeState" fc="ST"/>
</DOType>
<EnumType id="VendorChargeState">
  <EnumVal ord="0">idle</EnumVal>
  <EnumVal ord="10">charging</EnumVal>
  <EnumVal ord="20">discharging</EnumVal>
  <EnumVal ord="99">fault</EnumVal>
</EnumType>
```

上述为片段示意，完整模型仍需 q/t、LN/DO 引用及适用的命名空间等定义。无需为 VendorChargeState 编写专用前后端逻辑；导入后自动绑定选项，ST 的远端可写性仍按状态属性规则处理。

### 4.2 建模工具创建自定义枚举

复用已有 ENUM_TYPE / ENUM_VALUE 节点，提供表格编辑 ord、literal、desc；从 DA/BDA 的类型引用选择或创建枚举。编辑 EnumType 时展示引用它的属性，修改 ord、删除条目或删除类型前给出具体受影响值和引用位置。未解决的引用或初值冲突阻止发布模型。

标准模板通过复制生成工程类型，保留模板来源与版本；用户显示别名与标准 literal 分开。不能因为软件允许编辑表格，就认为修改标准语义后仍符合标准。

### 4.3 没有 SCL 时绑定本地字典

纯在线 MMS 发现一般只能获得传输类型及结构，不能据此保证拿到 EnumType 文本。因此允许用户在指定设备、完整引用路径及 FC 上绑定本地整数选项字典。

此模式标记 `source=user-mapping`，保存作用范围和版本；它为整数增加显示与输入约束，不自动改写远端类型，也不自动生成合规的 Enum DA。后续绑定 SCL 时进行冲突比较，由工程编辑流程解决，不能静默覆盖设备模型。

## 5. 通用元数据设计

### 5.1 类型字典与属性绑定

在统一模型中增加共享枚举字典，DARef/BDA 保存引用，避免在每个测点重复存储完整选项。建议值对象仍采用 frozen dataclass / tuple，与现有模型风格一致。

```text
EnumItem: ord: int, literal: str, desc: str
EnumDefinition:
  key, typeId, desc, source, sourceRevision, items, contentHash
DARef 增量字段:
  bType, typeId, valueKind, enumRef
IedModel 增量字段:
  schemaVersion, enumDefinitions
```

`valueKind` 区分 enum、coded-enum、bitfield、primitive；显式本地字典通过独立 binding 标识，不能把原始 `bType=INT32` 伪装成 `bType=Enum`。已有 `iec_type`、`mms_type` 保留原用途。

枚举唯一键必须包含文档／模型作用域和修订，至少做到 `(modelScope, modelRevision, typeId)`；禁止仅用 `typeId` 做跨设备全局缓存键。相同 ID 在两个文件内完全可以表示不同条目。

类型内容指纹用于缓存和冲突比较，不能代替作用域；导出保留原始 ID，合并文档遇到同名异构时重命名并更新引用。

### 5.2 解析及来源优先级

1. 解析完整路径：LN.lnType → LNodeType → DO/SDO → DOType → DA → 任意层 Struct/DAType/BDA → EnumType。
2. FC 由所属 DA 继承，地址保留数组索引等实例信息；加入循环检测、最大深度和未解析引用诊断。
3. 有实际 SCL 定义时，以定义为准；语义不符可报告，不能用内置模板替换。
4. 缺少 SCL 时，使用用户明确绑定到该模型和路径的本地字典。
5. 标准模板回退仅在命名空间、标准版本、LN/DO/DA 语义、bType 等证据足够时启用，标明 inferred；只凭 `CtlModels`、`stVal` 或 INT32 无法自动绑定。
6. 没有可靠定义时显示原始整数与“枚举定义未提供”；保留受协议类型约束的原有输入能力。明确损坏的绑定则显示配置错误，不伪造选项。

### 5.3 值的表示与校验

- ord 不是数组下标：保留 0、负数、非连续值；按实际类型检查范围。禁止使用 `value || default` 导致 0 丢失。
- ord 必须是合法整数；重复 ord 报错。禁止非法 ord 自动变成 0、浮点静默取整、bool 自动当作 0/1。
- literal 原样保留，中文翻译、短标签另存；重复 literal 做诊断，并依据所用 SCL schema/工程规则决定严重级别，存在歧义时拒绝从 literal 反查 ord。
- 未定义的运行值显示 `未知枚举值（17）` 并保留原始值，不自动改成第一个选项，也不自动加入字典。
- 对有可靠定义的常规设值执行成员校验；对标准推断定义不能因候选表不完整而丢弃读值。确需异常值注入的测试场景以后单独提供显式模式。
- SCL `<Val>` 是 XML 文本表示，不可直接假定等同于协议整数。按所用 SCL 版本/schema 校验 literal；历史数字形式只做明确的兼容解析与诊断。运行时内部统一 ord，并保留原文以支持往返。

## 6. API 与写值路径

保持现有树和写值接口兼容，增加可选字段；已有请求调用方无需同时升级。

树／详情响应增加示例：

```json
{
  "point_code": "IEDLD/LLN0.Mod.stVal",
  "fc": "ST",
  "b_type": "Enum",
  "mms_type": "MMS_INTEGER",
  "value_kind": "enum",
  "enum_ref": "model-a:r7:BehKind",
  "model_revision": "r7"
}
```

树响应可在顶层附本页涉及的 `enum_definitions`；属性只带 enum_ref。详情接口按引用补取选项，字典按模型修订缓存；实时值更新继续传原始值，不反复推送大字典。

写值前需返回或解析**实际写入目标**及其类型域：

```text
请求选中 DO/DA
  → 区分本地仿真设值、远端普通写、远端控制
  → 解析目标地址、FC、类型与枚举定义
  → 使用目标域校验值
  → 执行对应服务
```

当前客户端入口会调用 `_resolve_control_write_code`，服务端则直接更新所选属性。应将“准备写入目标”的结果供弹窗使用，避免 UI 使用 stVal 的选项、后端却重定向至不同类型的 Oper.ctlVal。普通 CF/SP 写入是否已有完整入口需在实施时逐项验证并纳入适配，不宣称改一个下拉框就已支持。

后端按最终目标检查整数、成员、范围、模型版本和操作能力。请求增加可选 model_revision，弹窗期间模型改变时返回冲突并刷新选项。客户端提交的 label、enumRef 不能充当后端校验依据。

`ctlModel` 的选项仅定义候选值；在线修改可能不被设备支持。修改模型还会影响已缓存的控制对象，需要在支持该操作的路径中重新建立或失效缓存。控制服务仍按 direct/SBO、normal/enhanced 流程执行。参见 [libiec61850 控制服务文档](https://support.mz-automation.de/doc/libiec61850/c/latest/group__IEC61850__CLIENT__CONTROL.html)。

## 7. 前端统一交互

建议增加 `Iec61850ValueEditor.vue` 和共享格式化工具，由元数据选择控件；所有相关入口复用，不在每个页面写 ctlModel 特判。

| 元数据 | 控件／展示 |
| --- | --- |
| 已解析 enum | 可搜索单选下拉；选项显示 `ord · literal · 中文说明`，提交 number |
| 未提供定义的整数 | 原有数值输入，提示定义未提供 |
| 损坏引用／冲突定义 | 展示具体模型诊断；阻止基于错误字典的正常提交 |
| coded-enum | 复用下拉外观，由 Dbpos/Tcmd 等适配器校验和编码 |
| bitfield | 位域编辑器 |
| 普通 bool/number/string | 相应基础控件 |

覆盖入口包括 IEC 61850 树表、测点详情、写值弹窗、本地仿真、工程默认值／DAI 值、适用的定值编辑。报告／数据集／GOOSE 成员在有精确叶子绑定时复用文本显示，传输仍使用原值。未完成适配的入口不得宣称已全面覆盖。

下拉框支持按数值、literal、中文说明搜索；未知当前值仅作状态展示，不自动变成合法备选项。0 和空输入严格区分。整数 0、负数、切换测点、异步选项到达和提交失败后的重试均需正确处理。

## 8. 持久化、导出与旧数据

1. 模型缓存升级 schemaVersion；旧缓存可读取为“无枚举元数据”，有原始 SCL 的通过重建恢复，无原件的保留现状并提示绑定。
2. 来源文件发生变化、重新发现、替换模型、复制设备或修改字典时刷新修订和缓存，禁止沿用旧设备选项。
3. 本地自定义字典及路径绑定独立持久化，不能仅放临时模型缓存，否则清缓存或重启会丢失。优先使用专门的 IEC 61850 元数据存储；数据库迁移结构在 P1 定稿。
4. 导出优先使用绑定的真实 EnumType，保留 ord、literal、desc 及有效引用；不能继续用 `0=unknown` 占位冒充真实枚举。
5. 在线发现没有枚举表时，允许导出其已知信息并附诊断；需要完整 EnumType 的 SCL 导出必须先补齐定义或明确报告无法完成，不能将整数随意改成 Enum。
6. 显示字典默认不写入 SCL。用户明确将其转为工程类型时，生成 EnumType、更新 DA/BDA 类型引用并重新校验。
7. 工程模型、运行模型、JSON 缓存和设备复制走同一套枚举序列化定义；数据集／GOOSE 路径的类型绑定复用解析服务，避免各自猜测。

## 9. 分阶段实施工作包

以下为单人开发粗估，实际排期取决于现有接口和联调设备；不是固定交付承诺。P1 与 P2 完成后才能交付可靠的动态下拉。

| 阶段 | 工作内容 | 主要交付／验收 | 粗估 |
| --- | --- | --- | --- |
| P0：基线与契约 | 固化当前样本清单；选择标准／厂商／嵌套／缺定义样本；确定源优先级、字段命名、写目标协议、持久化方案 | 可重复的样本盘点与接口样例；区分 enum/coded-enum/bitfield | 0.5–1 人日 |
| P1：后端元数据贯通 | 新增共享值对象；修正解析诊断；递归解析 DA/BDA；扩展 DARef、IedModel、registry、缓存及复制；将建模模型适配到同一语义定义 | 导入、重启、模型替换、跨设备同名枚举均不丢失或串用 | 2–3 人日 |
| P2：运行时显示与设值 | API 增量契约；准备实际写目标；后端严格校验；统一值编辑器和格式化；接入树表、详情、写值、本地仿真 | 标准及自定义枚举自动下拉；显示 label、提交 ord；DPC 状态与命令域不混用 | 2–3 人日 |
| P3：自定义与导出闭环 | 完善已有 EnumType 编辑；缺 SCL 的本地字典绑定；修改影响分析；导出真实枚举；初始化值及模型发布校验 | 自建枚举→绑定→设值→导出→再导入保持一致 | 2–3 人日 |
| P4：其余入口与回归 | 定值、报告／数据集／GOOSE 显示适配；旧数据迁移演练；大模型和用户操作验收；补使用文档 | 所有已声明入口一致；协议线编码和原有发现性能无回退 | 1–2 人日 |

合计初估 7.5–12 人日。建议首批发布 P0–P2（4.5–7 人日），P3 提供完整可编辑闭环，P4 完成扩展入口。首批须保留原始定义并使缓存可恢复，避免 UI 上线后再次重做模型层。

拟新增文件：`src/proto/iec61850/model/enum_types.py`、共享解析／值校验模块、前端 `Iec61850ValueEditor.vue` 与格式化工具；具体命名在 P0 与现有目录规范对齐。标准模板库复用已有 standard_packages，不新增散落在前后端的平行字典。

## 10. 必须通过的验收场景

| 场景 | 预期结果 |
| --- | --- |
| ctlModel、orCat、sboClass，含 ord=0 | 自动显示完整选项，选择后按整数提交，0 不丢失 |
| 厂商枚举 0/10/20/99 | 不修改业务代码，导入即可使用；99 不被当作第 100 项 |
| 同名 EnumType 来自两个设备且内容不同 | 各自显示自己的定义；复制和刷新后仍正确 |
| Struct 内多层 BDA 和 SDO 内枚举 | 按真实完整路径解析，FC 继承正确，循环引用有明确错误 |
| 合法负 ord、大选项列表、Unicode、相同说明文本 | 不错误拒绝合法值；按 ord 唯一选择，搜索可用 |
| ord 非整数、重复 ord、空类型、缺失引用 | 报告具体文件／类型／路径；不静默修复为 0 |
| 当前收到 17，但字典中没有 17 | 显示未知枚举值（17），读值、报告和原始日志不丢失 |
| 绕过前端提交未知成员、1.5、bool、过期修订 | 后端拒绝且给出原因，不截断、不信任前端选项 |
| 只有 MMS 在线发现且无 SCL | 不编造枚举选项；允许明确绑定本地字典并持久化 |
| DPC 的 Dbpos stVal 与 BOOLEAN Oper.ctlVal | 状态显示四态；控制弹窗使用命令目标的布尔域 |
| 远端 Beh/Health 等只读状态与本地服务端仿真 | 按操作能力分别控制；本地仿真不被重定向成控制命令 |
| 模型替换发生于弹窗打开期间 | 提交检测修订冲突，刷新选项而非写入过期编码 |
| 枚举导出再导入、重启缓存、复制设备 | 条目、引用、初值和作用域一致，显示别名不污染 SCL literal |
| 大模型分页与报告更新 | 选项按模型共享，实时更新不重复附整个字典；与现有基线比较负载 |

测试重点为真实解析与往返、API 非法值拦截、写目标类型差异、缓存作用域和前端选择行为。优先扩展 `tests/protocols/iec61850/model/`、`tests/web/api/test_iec61850_write_point.py` 和 `front/src/tests/`。本次规划不新增实现测试，不运行与文档改动无关的完整测试套件。

## 11. 参考依据与待核对项

- 用户提供的 CtlModels / OrCategory XML，以及本项目 43 份 SCL 样本：用于确认当前工程的条目与类型 ID 差异。
- [IEC 61850-7-3 Ed.2.1 官方目录](https://webstore.iec.ch/en/publication/66526)：CDC 和属性类型所属标准及版本依据；公开目录不提供完整枚举表，不能据此宣称已校验所有 literal。
- [ABB 的 IEC 61850 模型说明](https://help.plc.abb.com/iec_61850_server_introduction.html)：DPC 的状态、控制、配置属性及类型差异。
- [libiec61850 Dbpos API](https://support.mz-automation.de/doc/libiec61850/c/latest/group__DBPOS.html)：四态编码与 MMS 位串转换。
- [libiec61850 控制服务 API](https://support.mz-automation.de/doc/libiec61850/c/latest/group__IEC61850__CLIENT__CONTROL.html)：控制流程、来源设置、控制模型修改的设备限制。

P0 需按项目采用的标准包／schema 核对：SCL Val 的版本规则、ord 范围和重复 literal 规则、标准枚举模板的 namespace/version，以及运行库对 Dbpos/Tcmd 的实际编码支持。通用元数据链路不依赖事先列全所有标准枚举。

## 12. 第一批实现记录（2026-10-16）

本批交付范围：已有 SCL EnumType 的通用解析、运行时显示和设值，涵盖标准及厂商自定义类型。这里的“自定义支持”指 SCL 内定义的任意枚举，尚不包含无 SCL 的本地字典管理界面。

已实现：

- 共享 EnumDefinition / EnumItem，DA/BDA 保存原始 bType 和 typeId；枚举定义随 IedModel JSON 缓存保存，旧缓存可以读取。
- 多层 Struct/BDA 和 SDO 的枚举引用解析；循环和深度保护；非法 ord、重复 ord、重复 EnumType ID 不再静默接受。
- 树数据按本页引用返回共享字典，保留原始值；前端显示 ord、literal、desc，未知值显式显示。
- 写值准备接口按最终目标返回值域；统一可搜索下拉编辑器，选择后提交整数，编码 0、负数及非连续编码均不作为数组下标处理。
- 后端拒绝枚举浮点、布尔、字符串和未定义成员；显式损坏引用禁止写入；未提供 type 引用的历史 Enum 保留整数输入兼容。
- 修正 Yx/Yk 仅接受 0/1 及客户端统一转 bool 的链路；枚举值绕过二态限制与模拟量倍率换算，保持原始整数。
- 未注册为业务测点的枚举 CF/SP 等属性按模型直接写入，不额外加入轮询点表；远端 CO 请求参数禁止独立写入。
- 本地 ctlModel 使用 IedServer_updateCtlModel 并核对读回；远端 ctlModel 写入成功后清除缓存控制对象，后续操作重新读取控制模型。
- 弹窗提交携带模型修订，模型更新后要求刷新选项；字典与属性索引按模型实例隔离。

验证记录：相关后端回归 217 项通过，前端枚举／树操作／写后同步测试 18 项通过，TypeScript 检查和隔离输出的 Vite 生产构建通过。对当前工作区 44 份 SCL 样本完成构模扫描：445 个枚举定义、112,211 处枚举属性绑定，无解析或构模异常（含副本，不代表独立模型数）。

浏览器自动化验收页连续两次连接超时，未完成真实点击下拉框的交互检查；自动测试不替代真实 IED 联调。

待续工作：工程枚举表格编辑和影响分析、SCL literal 初值完整兼容、运行模型导出真实 EnumType 的闭环、无 SCL 本地字典持久化、Dbpos/Tcmd 专用适配、定值／报告／GOOSE 等其余入口，以及数组下标完整覆盖。此批不宣称 P0–P4 全部完成。

使用提示：旧缓存中没有保存的枚举选项无法凭整数恢复，需要重新导入对应 SCL；纯在线发现没有可靠字典时保持数字输入。新增前端组件需要与本批后端一起构建启动。
