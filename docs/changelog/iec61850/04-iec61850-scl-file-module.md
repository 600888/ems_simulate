# IEC 61850 SCL 文件模块开发计划

> ⚠️ **本文档已废弃**，已合并至 [iec61850-unified-model-refactoring.md](./09-iec61850-unified-model-refactoring.md) v3.0  
> 合并原因: SCL 离线解析与在线模型发现、导出优化存在强关联，统一文档避免信息分裂  
> 废弃日期: 2026-06-02

> 版本: 1.0  
> 日期: 2026-05-31  
> 状态: 已废弃  
> 关联文档: [iec61850-unified-model-refactoring.md](./09-iec61850-unified-model-refactoring.md)

---

## 1. 概述

IEC 61850 SCL (Substation Configuration Language) 文件是变电站自动化系统的配置核心，定义了 IED 的数据模型、通信参数、GOOSE/Report 控制块等全部工程配置。SCL 文件包括三种类型：

| 文件类型 | 扩展名 | 说明 |
|----------|--------|------|
| **ICD** | `.icd` | IED 能力描述文件，由设备厂商提供，描述单个 IED 的完整能力 |
| **SCD** | `.scd` | 变电站配置描述文件，由系统集成商将多个 ICD 合并生成 |
| **CID** | `.cid` | IED 实例配置文件，由 SCD 裁剪生成，下装到具体 IED |

### 1.1 当前状态

**已实现的功能：**

- ✅ `IcdPointImporter` (`src/tools/icd_point_importer.py`) — 从 ICD 文件解析测点（遥测/遥信/遥控/遥调）并导入数据库
- ✅ `IcdGooseImporter` (`src/tools/icd_goose_importer.py`) — 从 ICD 文件提取 GOOSE 控制块、数据集、通信地址
- ✅ `IEC61850ModelExporter` (`src/proto/iec61850/plugins/model_exporter/`) — 将服务端模型导出为 ICD/XML/JSON/CSV/Text 格式
- ✅ `FilesPlugin` 骨架 (`src/proto/iec61850/plugins/files/`) — 远程 IED 文件服务操作
- ✅ Web API: `/api/channels/import-icd` — ICD 文件上传与点表导入
- ✅ 前端 IEC61850 树形结构展示（含 DataSets、DataModels、GOOSE 等分类）
- ✅ SCL 命名空间检测与处理（有命名空间/无命名空间两种 XML 兼容）
- ✅ 插件重复注册修复（`plugins/__init__.py` 全局 registry 不再自动注册，`IEC61850Client` 使用 `auto_register=False` + 手动注册）

**存在的问题：**

| 问题 | 严重度 | 说明 |
|------|--------|------|
| **解析逻辑分散** | 🔴 高 | ICD 解析逻辑散落在 `icd_point_importer.py`、`icd_goose_importer.py`、`IcdGooseImporter._parse_report_control()` 中，三处独立解析 SCL XML，无共享模型 |
| **无统一 SCL 对象模型** | 🔴 高 | 缺少 SCL 元素（IED、LDevice、LN、DOType、DAType、DataSet 等）的 Python 数据类表示，所有解析结果直接以字典返回 |
| **不支持 SCD/CID** | 🟡 中 | 当前仅支持 ICD 格式，SCD 和 CID 文件无法解析和处理 |
| **无 SCL 校验** | 🟡 中 | 上传 ICD 文件后不做任何结构和语义校验，格式错误时静默跳过或抛出难以理解的异常 |
| **无文件管理能力** | 🟡 中 | 无法查看已上传的 ICD 文件列表、无法对比两个 ICD 版本差异、无法浏览 ICD 文件原始内容 |
| **ReportControl 解析位置不合理** | 🟡 中 | ReportControl 解析在 `icd_goose_importer.py` 中，与 GOOSE 解析耦合 |
| **数据类型缓存不通用** | 🟢 低 | `IcdPointImporter` 内部维护 `_ln_types`、`_do_types`、`_da_types` 缓存，每次导入都重新构建 |
| **导入策略不可配置** | 🟢 低 | 测点导入策略（CDC 映射、DA 路径推断、元数据导入等）硬编码在代码中，无法按需调整 |
| **插件重复注册** | 🟡 中 | `plugins/__init__.py` 模块级代码创建全局 `registry` 并注册插件，`PluginRegistry(auto_register=True)` 又在构造时注册一遍，导致启动日志中出现两遍注册记录 |

### 1.2 目标

构建一个统一的 IEC 61850 SCL 文件管理模块，提供：

1. **统一 SCL 对象模型** — 将 ICD/SCD/CID 解析结果表示为类型安全的 Python dataclass 层次结构
2. **统一 SCL 解析引擎** — 一次解析、多处消费，消除分散的重复解析逻辑
3. **SCL 文件校验** — 结构校验（XML Schema）+ 语义校验（引用完整性、FC 一致性等）
4. **文件管理** — 上传/下载/列表/预览/对比/删除 ICD/SCD/CID 文件
5. **智能导入** — 从 SCL 模型一键生成测点、GOOSE 配置、Report 配置、服务端模型
6. **前端 UI** — SCL 文件浏览器，支持树形结构可视化、原始 XML 查看、导入向导

---

## 2. 总体架构

### 2.1 架构图

```
┌───────────────────────────────────────────────────────────────────────────┐
│                        Frontend (Vue 3 + TypeScript)                       │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │  SclFileManager.vue [新增]                                           │  │
│  │  ┌──────────────┐  ┌──────────────────┐  ┌──────────────────────┐ │  │
│  │  │ 文件列表      │  │ SCL 树形浏览器    │  │ 导入向导              │ │  │
│  │  │ (上传/删除)   │  │ (LD/LN/DO/DA)   │  │ (测点/GOOSE/Report)  │ │  │
│  │  └──────────────┘  └──────────────────┘  └──────────────────────┘ │  │
│  │  ┌──────────────┐  ┌──────────────────┐                            │  │
│  │  │ XML 原始查看  │  │ 文件对比 (Diff)   │                            │  │
│  │  └──────────────┘  └──────────────────┘                            │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │  sclApi.ts (API 层) [新增]                                          │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────┬──────────────────────────────────────────┘
                                 │ HTTP JSON / WebSocket
┌────────────────────────────────▼──────────────────────────────────────────┐
│                         Backend (FastAPI)                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │  src/web/api/scl/ [新增]                                            │  │
│  │  ├── router.py          文件管理路由 (CRUD / 上传 / 下载)            │  │
│  │  ├── preview.py         SCL 预览与浏览路由                           │  │
│  │  ├── import_wizard.py   导入向导路由                                 │  │
│  │  └── diff.py            文件对比路由                                 │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │  src/web/api/schemas/scl.py [新增]                                  │  │
│  │  Pydantic 请求/响应模型                                              │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────┬──────────────────────────────────────────┘
                                 │
┌────────────────────────────────▼──────────────────────────────────────────┐
│              SCL 文件插件核心 (src/proto/iec61850/plugins/scl/) [新增]           │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │  model/                        SCL 对象模型                          │  │
│  │  ├── __init__.py                                                   │  │
│  │  ├── scl_base.py              基础数据类 (SclElement)               │  │
│  │  ├── ied.py                   IED / AccessPoint / Server             │  │
│  │  ├── logical_device.py        LDevice / LN0 / LN                    │  │
│  │  ├── data_object.py           DOI / DAI / SDI                       │  │
│  │  ├── data_type.py             LNodeType / DOType / DAType / EnumType │  │
│  │  ├── dataset.py               DataSet / FCDA                        │  │
│  │  ├── control_block.py         GSEControl / ReportControl / SVControl │  │
│  │  ├── communication.py         Communication / SubNetwork / ConnectedAP│  │
│  │  └── scl_document.py          SCL 文档 (顶层容器)                   │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │  parser/                       SCL 解析引擎                         │  │
│  │  ├── __init__.py                                                   │  │
│  │  ├── scl_parser.py            统一 SCL 解析器 (ICD/SCD/CID)         │  │
│  │  ├── type_resolver.py         数据类型引用解析器                     │  │
│  │  └── namespace.py             XML 命名空间处理                       │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │  validator/                    SCL 校验引擎                         │  │
│  │  ├── __init__.py                                                   │  │
│  │  ├── schema_validator.py      XML Schema (XSD) 结构校验             │  │
│  │  └── semantic_validator.py    语义校验 (引用完整性/FC一致性/必选元素) │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │  transformer/                  SCL 模型转换器                       │  │
│  │  ├── __init__.py                                                   │  │
│  │  ├── point_transformer.py     SCL → 测点数据 (替代 IcdPointImporter) │  │
│  │  ├── goose_transformer.py     SCL → GOOSE 配置 (替代 IcdGooseImporter)│  │
│  │  ├── report_transformer.py    SCL → Report 配置                     │  │
│  │  └── server_model_builder.py  SCL → 服务端 IedModel                 │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │  service/                      业务服务层                            │  │
│  │  ├── __init__.py                                                   │  │
│  │  ├── file_manager.py          文件管理 (上传/存储/列表/删除)         │  │
│  │  ├── import_service.py        导入服务 (编排解析→校验→转换→持久化)    │  │
│  │  └── diff_service.py          文件对比服务                          │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 数据流

```
用户上传 ICD/SCD/CID 文件
         │
         ▼
┌──────────────────┐
│ 1. 文件存储       │  file_manager.py → data/61850icd/ 目录
│    (.icd/.scd/.cid)│
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ 2. SCL 解析       │  scl_parser.py → SclDocument (内存对象模型)
│    (XML → Model)  │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ 3. SCL 校验       │  schema_validator.py + semantic_validator.py
│    (结构 + 语义)  │  → 校验报告 (errors / warnings)
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ 4. 模型转换       │  transformer/ (按用户选择)
│    (按需转换)      │  ├── point_transformer  → 测点数据库
│                   │  ├── goose_transformer  → GOOSE 配置
│                   │  ├── report_transformer → Report 配置
│                   │  └── server_model_builder → IedModel
└──────────────────┘
```

---

## 3. 详细设计

### 3.1 SCL 对象模型 (`src/proto/iec61850/plugins/scl/model/`)

#### 3.1.1 基础数据类 (`scl_base.py`)

```python
"""SCL 基础数据类"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SclElement:
    """SCL 元素基类"""
    # 通用属性
    desc: str = ""
    # 原始 XML 行号 (用于校验报告定位)
    _source_line: Optional[int] = field(default=None, repr=False)
```

#### 3.1.2 SCL 文档 (`scl_document.py`)

```python
"""SCL 文档 - 顶层容器"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from .scl_base import SclElement
from .ied import SclIED
from .data_type import SclLNodeType, SclDOType, SclDAType, SclEnumType
from .communication import SclCommunication


@dataclass
class SclDocument:
    """SCL 文档对象模型
    
    对应 SCL XML 根元素 <SCL>，包含 IED 配置、数据类型模板、通信配置。
    支持 ICD/SCD/CID 三种文件类型。
    """
    # 文件元信息
    file_path: str = ""
    file_type: str = ""          # "ICD" / "SCD" / "CID"
    scl_revision: str = ""       # SCL 版本 (如 "B" / "2007B4")
    
    # 顶级节
    ieds: List[SclIED] = field(default_factory=list)
    data_type_templates: SclDataTypeTemplates = field(default_factory=lambda: SclDataTypeTemplates())
    communication: Optional[SclCommunication] = None
    
    # 解析辅助缓存 (不序列化)
    _ln_type_index: Dict[str, SclLNodeType] = field(default_factory=dict, repr=False)
    _do_type_index: Dict[str, SclDOType] = field(default_factory=dict, repr=False)
    _da_type_index: Dict[str, SclDAType] = field(default_factory=dict, repr=False)
    _enum_type_index: Dict[str, SclEnumType] = field(default_factory=dict, repr=False)
    
    def build_type_index(self) -> None:
        """构建数据类型索引 (解析后调用)"""
        for t in self.data_type_templates.ln_types:
            self._ln_type_index[t.id] = t
        for t in self.data_type_templates.do_types:
            self._do_type_index[t.id] = t
        for t in self.data_type_templates.da_types:
            self._da_type_index[t.id] = t
        for t in self.data_type_templates.enum_types:
            self._enum_type_index[t.id] = t
    
    def get_ln_type(self, type_id: str) -> Optional[SclLNodeType]:
        return self._ln_type_index.get(type_id)
    
    def get_do_type(self, type_id: str) -> Optional[SclDOType]:
        return self._do_type_index.get(type_id)
    
    def get_da_type(self, type_id: str) -> Optional[SclDAType]:
        return self._da_type_index.get(type_id)
    
    def get_enum_type(self, type_id: str) -> Optional[SclEnumType]:
        return self._enum_type_index.get(type_id)


@dataclass
class SclDataTypeTemplates:
    """DataTypeTemplates 节"""
    ln_types: List[SclLNodeType] = field(default_factory=list)
    do_types: List[SclDOType] = field(default_factory=list)
    da_types: List[SclDAType] = field(default_factory=list)
    enum_types: List[SclEnumType] = field(default_factory=list)
```

#### 3.1.3 IED 模型 (`ied.py`)

```python
"""IED 相关模型"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from .scl_base import SclElement


@dataclass
class SclIED(SclElement):
    """IED 元素"""
    name: str = ""
    manufacturer: str = ""
    type: str = ""
    config_revision: str = ""
    original_scl_revision: str = ""
    
    access_points: List[SclAccessPoint] = field(default_factory=list)


@dataclass
class SclAccessPoint(SclElement):
    """AccessPoint 元素"""
    name: str = ""
    server: Optional[SclServer] = None


@dataclass
class SclServer(SclElement):
    """Server 元素"""
    timeout: str = ""
    logical_devices: List[SclLogicalDevice] = field(default_factory=list)
```

#### 3.1.4 逻辑设备与逻辑节点 (`logical_device.py`)

```python
"""逻辑设备与逻辑节点模型"""
from dataclasses import dataclass, field
from typing import List, Optional
from .scl_base import SclElement


@dataclass
class SclLogicalDevice(SclElement):
    """LDevice 元素"""
    inst: str = ""                  # 逻辑设备实例名 (如 "LD0")
    ld_name: str = ""               # 逻辑设备名 (如 "KG_BAMSCTMP01")
    
    ln0: Optional[SclLN0] = None
    logical_nodes: List[SclLN] = field(default_factory=list)


@dataclass
class SclLN0(SclElement):
    """LN0 元素 (逻辑节点零)"""
    ln_class: str = "LLN0"
    ln_type: str = ""               # 引用 LNodeType id
    inst: str = ""
    prefix: str = ""
    
    # LN0 下的子元素
    data_sets: List[SclDataSet] = field(default_factory=list)
    gse_controls: List[SclGSEControl] = field(default_factory=list)
    report_controls: List[SclReportControl] = field(default_factory=list)
    sv_controls: List[SclSVControl] = field(default_factory=list)
    doi_list: List[SclDOI] = field(default_factory=list)


@dataclass
class SclLN(SclElement):
    """LN 元素"""
    ln_class: str = ""              # 逻辑节点类 (如 "MMXU", "GGIO")
    ln_type: str = ""               # 引用 LNodeType id
    inst: str = ""                  # 实例号
    prefix: str = ""                # 前缀
    
    doi_list: List[SclDOI] = field(default_factory=list)
    
    @property
    def ln_name(self) -> str:
        """构造 LN 名称: prefix + lnClass + inst"""
        if self.ln_class == "LLN0":
            return "LLN0"
        return f"{self.prefix}{self.ln_class}{self.inst}"
```

#### 3.1.5 数据对象与数据属性 (`data_object.py`)

```python
"""DOI / DAI / SDI 模型"""
from dataclasses import dataclass, field
from typing import List, Optional
from .scl_base import SclElement


@dataclass
class SclDOI(SclElement):
    """DOI (数据对象实例) 元素"""
    name: str = ""                  # DO 名称 (如 "AnIn1", "Ind1")
    dai_list: List[SclDAI] = field(default_factory=list)
    sdi_list: List[SclSDI] = field(default_factory=list)


@dataclass
class SclDAI(SclElement):
    """DAI (数据属性实例) 元素"""
    name: str = ""                  # DA 名称 (如 "du", "setVal")
    value: Optional[str] = None     # <Val> 内容
    val_imported: bool = False      # valImported 属性


@dataclass
class SclSDI(SclElement):
    """SDI (结构数据实例) 元素"""
    name: str = ""
    dai_list: List[SclDAI] = field(default_factory=list)
    sdi_list: List[SclSDI] = field(default_factory=list)
```

#### 3.1.6 数据类型模板 (`data_type.py`)

```python
"""DataTypeTemplates 中的类型定义模型"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from .scl_base import SclElement


@dataclass
class SclLNodeType(SclElement):
    """LNodeType (逻辑节点类型)"""
    id: str = ""                    # 类型 ID (如 "MMXU1_Type")
    ln_class: str = ""              # 逻辑节点类
    
    do_list: List[SclDO] = field(default_factory=list)


@dataclass
class SclDO(SclElement):
    """DO (数据对象) 类型引用"""
    name: str = ""                  # DO 名称
    type: str = ""                  # 引用 DOType id
    access_control: str = ""        # 访问控制
    transient: bool = False         # 瞬态标记


@dataclass
class SclDOType(SclElement):
    """DOType (数据对象类型)"""
    id: str = ""
    cdc: str = ""                   # 公共数据类 (如 "MV", "SPS", "SPC")
    
    da_list: List[SclDA] = field(default_factory=list)
    sdo_list: List[SclSDO] = field(default_factory=list)


@dataclass
class SclDA(SclElement):
    """DA (数据属性)"""
    name: str = ""
    fc: str = ""                    # 功能约束 (如 "MX", "ST", "CO")
    b_type: str = ""                # 基本类型 (如 "Float32", "Boolean", "Struct")
    type: str = ""                  # 引用 DAType/EnumType id (仅 Struct/Enum)
    val: Optional[str] = None       # 默认值
    dchg: bool = False              # 数据变化触发
    qchg: bool = False              # 品质变化触发
    dupd: bool = False              # 数据更新触发
    count: int = 0                  # 数组元素数


@dataclass
class SclSDO(SclElement):
    """SDO (子数据对象)"""
    name: str = ""
    type: str = ""                  # 引用 DOType id


@dataclass
class SclDAType(SclElement):
    """DAType (数据属性类型)"""
    id: str = ""
    
    bda_list: List[SclBDA] = field(default_factory=list)


@dataclass
class SclBDA(SclElement):
    """BDA (约束数据属性)"""
    name: str = ""
    b_type: str = ""
    type: str = ""                  # 引用 DAType/EnumType id
    val: Optional[str] = None
    count: int = 0


@dataclass
class SclEnumType(SclElement):
    """EnumType (枚举类型)"""
    id: str = ""
    
    enum_values: Dict[int, str] = field(default_factory=dict)   # ord → desc
```

#### 3.1.7 数据集 (`dataset.py`)

```python
"""DataSet / FCDA 模型"""
from dataclasses import dataclass, field
from typing import List
from .scl_base import SclElement


@dataclass
class SclDataSet(SclElement):
    """DataSet (数据集) 元素"""
    name: str = ""                  # 数据集名称 (如 "dsGOOSE1", "dsReport1")
    
    fcdas: List[SclFCDA] = field(default_factory=list)


@dataclass
class SclFCDA(SclElement):
    """FCDA (功能约束数据属性) 元素"""
    ld_inst: str = ""               # 逻辑设备实例名
    prefix: str = ""                # LN 前缀
    ln_class: str = ""              # 逻辑节点类
    ln_inst: str = ""               # 逻辑节点实例号
    do_name: str = ""               # 数据对象名
    da_name: str = ""               # 数据属性名 (可选)
    fc: str = ""                    # 功能约束
    
    @property
    def fcda_ref(self) -> str:
        """构建完整 FCDA 引用路径
        
        格式: ldInst/prefix+lnClass+lnInst.doName.daName
        """
        ln_name = "LLN0" if self.ln_class == "LLN0" else f"{self.prefix}{self.ln_class}{self.ln_inst}"
        parts = [self.ld_inst or "LD0", ln_name]
        if self.do_name:
            parts.append(self.do_name)
        ref = "/".join(parts[:2]) + "." + ".".join(parts[2:])
        if self.da_name:
            ref += f".{self.da_name}"
        return ref
```

#### 3.1.8 控制块 (`control_block.py`)

```python
"""GSEControl / ReportControl / SVControl 模型"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from .scl_base import SclElement


@dataclass
class SclGSEControl(SclElement):
    """GSEControl (GOOSE 控制块) 元素"""
    name: str = ""                  # 控制块名 (如 "gcb1")
    app_id: str = ""                # APPID
    dat_set: str = ""               # 引用 DataSet 名称
    conf_rev: int = 1               # 配置修订号
    type: str = "GOOSE"             # 控制块类型
    
    @property
    def go_cb_ref(self) -> str:
        """MMS 格式 GOOSE 控制块引用 (需配合 LD/LN 信息构建)"""
        # 实际构建在 transformer 中完成，此处仅定义接口
        return ""


@dataclass
class SclTrgOps:
    """触发选项"""
    dchg: bool = False
    qchg: bool = False
    dupd: bool = False
    period: bool = False
    gi: bool = False


@dataclass
class SclOptFields:
    """可选字段"""
    seq_num: bool = False
    time_stamp: bool = False
    data_set: bool = False
    reason_code: bool = False
    data_ref: bool = False
    entry_id: bool = False
    config_ref: bool = False
    buf_ovfl: bool = False


@dataclass
class SclReportControl(SclElement):
    """ReportControl (报告控制块) 元素"""
    name: str = ""
    rpt_id: str = ""
    dat_set: str = ""               # 引用 DataSet 名称
    buffered: bool = False          # true=BRCB, false=URCB
    conf_rev: int = 1
    buf_time: int = 0               # 缓冲时间 (ms)
    intg_pd: int = 0                # 完整性周期 (ms)
    
    trg_ops: Optional[SclTrgOps] = None
    opt_fields: Optional[SclOptFields] = None
    
    @property
    def rcb_type(self) -> str:
        return "BRCB" if self.buffered else "URCB"


@dataclass
class SclSVControl(SclElement):
    """SVControl (采样值控制块) 元素"""
    name: str = ""
    dat_set: str = ""
    conf_rev: int = 1
    smv_id: str = ""
    smp_mod: str = ""               # 采样模式 (SmpPerSec/SmpPerPeriod)
    smp_rate: int = 0               # 采样率
    nof_asdu: int = 0               # 每个 ASDU 数量
```

#### 3.1.9 通信配置 (`communication.py`)

```python
"""Communication 配置模型"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from .scl_base import SclElement


@dataclass
class SclCommunication:
    """Communication 节"""
    sub_networks: List[SclSubNetwork] = field(default_factory=list)


@dataclass
class SclSubNetwork(SclElement):
    """SubNetwork 元素"""
    name: str = ""
    type: str = ""                  # 如 "8-MMS"
    
    connected_aps: List[SclConnectedAP] = field(default_factory=list)


@dataclass
class SclConnectedAP:
    """ConnectedAP 元素"""
    ied_name: str = ""
    ap_name: str = ""
    
    gse_list: List[SclGSE] = field(default_factory=list)
    smv_list: List[SclSMV] = field(default_factory=list)
    address: Optional[SclAddress] = None


@dataclass
class SclGSE:
    """GSE (GOOSE 通信地址) 元素"""
    ld_inst: str = ""
    ln_class: str = "LLN0"
    ln_inst: str = ""
    cb_name: str = ""
    
    address: Optional[SclAddress] = None
    min_time: int = 10              # ms
    max_time: int = 1000            # ms


@dataclass
class SclSMV:
    """SMV (SV 通信地址) 元素"""
    ld_inst: str = ""
    ln_class: str = "LLN0"
    ln_inst: str = ""
    cb_name: str = ""
    
    address: Optional[SclAddress] = None


@dataclass
class SclAddress:
    """Address 元素 (P 类型-值对列表)"""
    params: Dict[str, str] = field(default_factory=dict)   # type → value
    
    @property
    def app_id(self) -> str:
        return self.params.get("APPID", "")
    
    @property
    def mac_address(self) -> str:
        return self.params.get("Multicast", "")
    
    @property
    def vlan_id(self) -> int:
        try:
            return int(self.params.get("VLAN-ID", "0"), 16)
        except ValueError:
            return 0
    
    @property
    def vlan_priority(self) -> int:
        try:
            return int(self.params.get("VLAN-PRIORITY", "4"))
        except ValueError:
            return 4
    
    @property
    def ip(self) -> str:
        return self.params.get("IP", "")
    
    @property
    def port(self) -> int:
        try:
            return int(self.params.get("UDP-PORT", "102"))
        except ValueError:
            return 102
```

### 3.2 SCL 解析引擎 (`src/proto/iec61850/plugins/scl/parser/`)

#### 3.2.1 统一解析器 (`scl_parser.py`)

```python
"""统一 SCL 解析器

解析 ICD/SCD/CID 文件，构建 SclDocument 内存对象模型。
替代 IcdPointImporter 和 IcdGooseImporter 中分散的 XML 解析逻辑。
"""
import xml.etree.ElementTree as ET
from typing import Optional
from ..model.scl_document import SclDocument, SclDataTypeTemplates
from ..model.ied import SclIED, SclAccessPoint, SclServer
from ..model.logical_device import SclLogicalDevice, SclLN0, SclLN
from ..model.data_object import SclDOI, SclDAI, SclSDI
from ..model.data_type import SclLNodeType, SclDOType, SclDAType, SclDO, SclDA, SclSDO, SclBDA, SclEnumType
from ..model.dataset import SclDataSet, SclFCDA
from ..model.control_block import SclGSEControl, SclReportControl, SclSVControl, SclTrgOps, SclOptFields
from ..model.communication import SclCommunication, SclSubNetwork, SclConnectedAP, SclGSE, SclSMV, SclAddress
from .namespace import NamespaceHelper


class SclParser:
    """SCL 文件解析器
    
    用法:
        parser = SclParser()
        doc = parser.parse_file("path/to/file.icd")
        # 或
        doc = parser.parse_string(scl_xml_string)
    """
    
    def __init__(self):
        self._ns = NamespaceHelper()
    
    def parse_file(self, file_path: str) -> SclDocument:
        """解析 SCL 文件
        
        Args:
            file_path: ICD/SCD/CID 文件路径
            
        Returns:
            SclDocument 对象模型
            
        Raises:
            FileNotFoundError: 文件不存在
            SclParseError: XML 解析错误
        """
        tree = ET.parse(file_path)
        root = tree.getroot()
        return self._parse_root(root, file_path=file_path)
    
    def parse_string(self, xml_string: str) -> SclDocument:
        """解析 SCL XML 字符串"""
        root = ET.fromstring(xml_string)
        return self._parse_root(root)
    
    def _parse_root(self, root: ET.Element, file_path: str = "") -> SclDocument:
        """解析 <SCL> 根元素"""
        self._ns.detect(root)
        
        doc = SclDocument()
        doc.file_path = file_path
        doc.scl_revision = root.get("revision", "")
        
        # 推断文件类型
        doc.file_type = self._infer_file_type(root)
        
        # 解析 IED 节
        for ied_elem in root.findall(self._ns.tag("IED")):
            doc.ieds.append(self._parse_ied(ied_elem))
        
        # 解析 DataTypeTemplates 节
        dtt = root.find(self._ns.tag("DataTypeTemplates"))
        if dtt is not None:
            doc.data_type_templates = self._parse_data_type_templates(dtt)
            doc.build_type_index()
        
        # 解析 Communication 节
        comm = root.find(self._ns.tag("Communication"))
        if comm is not None:
            doc.communication = self._parse_communication(comm)
        
        return doc
    
    def _infer_file_type(self, root: ET.Element) -> str:
        """推断 SCL 文件类型"""
        ieds = root.findall(self._ns.tag("IED"))
        if len(ieds) > 1:
            return "SCD"
        if len(ieds) == 1:
            # ICD: 单 IED，通常有 DataTypeTemplates
            # CID: 单 IED，通常有 Communication + 无 DataTypeTemplates (某些实现)
            if root.find(self._ns.tag("DataTypeTemplates")) is not None:
                return "ICD"
            return "CID"
        return "ICD"
    
    def _parse_ied(self, elem: ET.Element) -> SclIED: ...
    def _parse_access_point(self, elem: ET.Element) -> SclAccessPoint: ...
    def _parse_server(self, elem: ET.Element) -> SclServer: ...
    def _parse_logical_device(self, elem: ET.Element) -> SclLogicalDevice: ...
    def _parse_ln0(self, elem: ET.Element) -> SclLN0: ...
    def _parse_ln(self, elem: ET.Element) -> SclLN: ...
    def _parse_doi(self, elem: ET.Element) -> SclDOI: ...
    def _parse_dai(self, elem: ET.Element) -> SclDAI: ...
    def _parse_data_type_templates(self, elem: ET.Element) -> SclDataTypeTemplates: ...
    def _parse_ln_type(self, elem: ET.Element) -> SclLNodeType: ...
    def _parse_do_type(self, elem: ET.Element) -> SclDOType: ...
    def _parse_da_type(self, elem: ET.Element) -> SclDAType: ...
    def _parse_enum_type(self, elem: ET.Element) -> SclEnumType: ...
    def _parse_dataset(self, elem: ET.Element) -> SclDataSet: ...
    def _parse_fcda(self, elem: ET.Element) -> SclFCDA: ...
    def _parse_gse_control(self, elem: ET.Element) -> SclGSEControl: ...
    def _parse_report_control(self, elem: ET.Element) -> SclReportControl: ...
    def _parse_sv_control(self, elem: ET.Element) -> SclSVControl: ...
    def _parse_communication(self, elem: ET.Element) -> SclCommunication: ...
    def _parse_connected_ap(self, elem: ET.Element) -> SclConnectedAP: ...
    def _parse_gse_address(self, elem: ET.Element) -> SclGSE: ...
    def _parse_address(self, elem: ET.Element) -> SclAddress: ...
```

#### 3.2.2 命名空间处理 (`namespace.py`)

```python
"""XML 命名空间处理

SCL 文件可能使用或不使用 XML 命名空间:
  - 有命名空间: <SCL xmlns="http://www.iec.ch/61850/2003/SCL">
  - 无命名空间: <SCL>
  
兼容两种格式，统一处理。
"""
import xml.etree.ElementTree as ET

SCL_NS = "http://www.iec.ch/61850/2003/SCL"


class NamespaceHelper:
    """SCL 命名空间辅助工具"""
    
    def __init__(self):
        self._ns_prefix: str = ""
    
    def detect(self, root: ET.Element) -> None:
        """检测根元素的命名空间"""
        if root.tag.startswith("{"):
            self._ns_prefix = root.tag.split("}")[0] + "}"
        else:
            self._ns_prefix = ""
    
    def tag(self, name: str) -> str:
        """构造带命名空间的标签名"""
        return f"{self._ns_prefix}{name}" if self._ns_prefix else name
    
    @property
    def has_namespace(self) -> bool:
        return bool(self._ns_prefix)
```

### 3.3 SCL 校验引擎 (`src/proto/iec61850/plugins/scl/validator/`)

#### 3.3.1 结构校验 (`schema_validator.py`)

```python
"""SCL XML Schema 结构校验

使用 IEC 61850-6 定义的 SCL XSD Schema 校验文件结构。
"""
from dataclasses import dataclass, field
from typing import List
from enum import Enum


class ValidationSeverity(Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ValidationIssue:
    """校验问题"""
    severity: ValidationSeverity
    message: str
    xpath: str = ""                # 问题所在 XML 路径
    line: int = 0                  # 行号 (如果可获取)
    element_name: str = ""         # 相关元素名


@dataclass
class ValidationResult:
    """校验结果"""
    is_valid: bool = True
    issues: List[ValidationIssue] = field(default_factory=list)
    
    @property
    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == ValidationSeverity.ERROR]
    
    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == ValidationSeverity.WARNING]


class SclSchemaValidator:
    """SCL Schema 校验器"""
    
    def validate(self, doc: 'SclDocument') -> ValidationResult:
        """校验 SclDocument 结构
        
        校验规则:
        1. 至少包含一个 IED
        2. DataTypeTemplates 必须存在且非空
        3. 每个 LNodeType 必须引用存在的 DOType
        4. 每个 DOType 必须引用存在的 DAType/EnumType
        5. GSEControl 的 datSet 必须引用存在的 DataSet
        6. ReportControl 的 datSet 必须引用存在的 DataSet
        7. FCDA 的 lnClass 必须在 LDevice 中存在
        """
        result = ValidationResult()
        
        # 规则 1: 至少一个 IED
        if not doc.ieds:
            result.issues.append(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                message="SCL 文件中未找到 IED 元素",
                xpath="/SCL/IED"
            ))
        
        # 规则 2: DataTypeTemplates
        if not doc.data_type_templates.ln_types:
            result.issues.append(ValidationIssue(
                severity=ValidationSeverity.WARNING,
                message="DataTypeTemplates 中无 LNodeType 定义",
                xpath="/SCL/DataTypeTemplates"
            ))
        
        # 规则 3-7: 引用完整性 (委托给 semantic_validator)
        
        result.is_valid = len(result.errors) == 0
        return result
```

#### 3.3.2 语义校验 (`semantic_validator.py`)

```python
"""SCL 语义校验

校验 SCL 文件的语义正确性，包括引用完整性、FC 一致性、
必选元素存在性等。
"""
from .schema_validator import ValidationResult, ValidationIssue, ValidationSeverity


class SclSemanticValidator:
    """SCL 语义校验器"""
    
    def validate(self, doc: 'SclDocument') -> ValidationResult:
        """校验 SclDocument 语义"""
        result = ValidationResult()
        
        for ied in doc.ieds:
            for ap in ied.access_points:
                if ap.server is None:
                    continue
                for ld in ap.server.logical_devices:
                    self._validate_logical_device(doc, ld, ied.name, result)
        
        # 校验 GSE 地址与 GSEControl 的匹配
        self._validate_gse_addresses(doc, result)
        
        result.is_valid = len(result.errors) == 0
        return result
    
    def _validate_logical_device(self, doc, ld, ied_name, result): ...
    
    def _validate_gse_addresses(self, doc, result): ...
```

### 3.4 SCL 模型转换器 (`src/proto/iec61850/plugins/scl/transformer/`)

#### 3.4.1 测点转换器 (`point_transformer.py`)

```python
"""SCL → 测点数据转换器

替代原 IcdPointImporter 的核心解析逻辑，
从 SclDocument 对象模型生成测点数据。
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from ..model.scl_document import SclDocument
from ..model.data_type import SclDOType, SclDA
from ..model.logical_device import SclLN0, SclLN


# CDC → 测点类型映射 (与 IcdPointImporter 保持一致)
CDC_YC = {"MV", "CMV", "SAV", "WYE", "DEL", "SEQ", "HMV"}
CDC_YX = {"SPS", "DPS", "INS", "ENS", "ENC", "ACT", "ACD", "SEC", "BCR"}
CDC_YK = {"SPC", "DPC"}
CDC_YT = {"APC", "INC", "ASG", "ING", "SPG", "BAC"}


@dataclass
class PointData:
    """转换后的测点数据"""
    code: str = ""
    name: str = ""
    reg_addr: str = ""           # 完整引用路径
    cdc: str = ""
    da_name: str = ""            # DA 路径
    fc: str = ""
    frame_type: int = 0          # 0=遥测 1=遥信 2=遥控 3=遥调


class SclPointTransformer:
    """SCL 测点转换器
    
    从 SclDocument 提取测点信息，替代原 IcdPointImporter 的解析逻辑。
    优势: 解析与转换解耦，同一 SclDocument 可用于多种转换。
    """
    
    def transform(self, doc: SclDocument, 
                  include_metadata: bool = True,
                  cdc_filter: Optional[set] = None) -> Dict[str, List[PointData]]:
        """从 SclDocument 提取测点
        
        Args:
            doc: SCL 文档对象模型
            include_metadata: 是否包含元数据 DA (q, t, du 等)
            cdc_filter: CDC 过滤集 (None 表示全部)
            
        Returns:
            {"yc": [...], "yx": [...], "yk": [...], "yt": [...]}
        """
        yc_points, yx_points, yk_points, yt_points = [], [], [], []
        
        for ied in doc.ieds:
            for ap in ied.access_points:
                if ap.server is None:
                    continue
                for ld in ap.server.logical_devices:
                    ld_inst = ld.inst
                    
                    # LN0
                    if ld.ln0:
                        self._transform_ln(doc, ld_inst, "LLN0", ld.ln0, 
                                          yc_points, yx_points, yk_points, yt_points,
                                          include_metadata, cdc_filter)
                    
                    # LN
                    for ln in ld.logical_nodes:
                        self._transform_ln(doc, ld_inst, ln.ln_name, ln,
                                          yc_points, yx_points, yk_points, yt_points,
                                          include_metadata, cdc_filter)
        
        return {"yc": yc_points, "yx": yx_points, "yk": yk_points, "yt": yt_points}
    
    def _transform_ln(self, doc, ld_inst, ln_name, ln_elem, 
                      yc, yx, yk, yt, include_metadata, cdc_filter): ...
```

#### 3.4.2 GOOSE 转换器 (`goose_transformer.py`)

```python
"""SCL → GOOSE 配置转换器

替代原 IcdGooseImporter 的核心解析逻辑，
从 SclDocument 对象模型生成 GOOSE Publisher/Subscriber 配置。
"""
from typing import List, Dict, Any
from ..model.scl_document import SclDocument


class SclGooseTransformer:
    """SCL GOOSE 配置转换器"""
    
    def transform(self, doc: SclDocument, 
                  interface: str = "eth0") -> Dict[str, Any]:
        """从 SclDocument 提取 GOOSE 配置
        
        Returns:
            {
                "publishers": [...],       # 可创建的 Publisher 配置
                "subscriptions": [...],    # 可创建的 Subscription 配置
                "pure_datasets": [...],    # 未被 GSEControl 引用的 DataSet
            }
        """
        ...
```

#### 3.4.3 Report 转换器 (`report_transformer.py`)

```python
"""SCL → Report 配置转换器

从 SclDocument 对象模型生成 ReportControlBlock 配置，
供 ReportsPlugin 使用。
"""
from typing import List, Dict, Any
from ..model.scl_document import SclDocument


class SclReportTransformer:
    """SCL Report 配置转换器"""
    
    def transform(self, doc: SclDocument) -> List[Dict[str, Any]]:
        """从 SclDocument 提取 ReportControl 配置"""
        ...
```

### 3.5 文件管理服务 (`src/proto/iec61850/plugins/scl/service/`)

#### 3.5.1 文件管理器 (`file_manager.py`)

```python
"""SCL 文件管理器

管理 ICD/SCD/CID 文件的上传、存储、列表、删除。
文件存储在 data/61850icd/ 目录下。
"""
import os
import shutil
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class SclFileInfo:
    """SCL 文件信息"""
    file_name: str
    file_path: str
    file_type: str                # "ICD" / "SCD" / "CID"
    file_size: int                # bytes
    upload_time: str              # ISO 格式
    ied_name: str = ""            # 文件中的 IED 名称 (解析后填充)
    ied_count: int = 0
    ld_count: int = 0
    point_count: Dict[str, int] = None  # {"yc": N, "yx": N, "yk": N, "yt": N}


class SclFileManager:
    """SCL 文件管理器"""
    
    STORAGE_DIR = "data/61850icd"
    
    def __init__(self, base_dir: str = ""):
        self._base_dir = base_dir or self.STORAGE_DIR
        os.makedirs(self._base_dir, exist_ok=True)
    
    def upload(self, file_name: str, file_content: bytes) -> SclFileInfo:
        """上传 SCL 文件"""
        ...
    
    def list_files(self) -> List[SclFileInfo]:
        """列出所有已上传的 SCL 文件"""
        ...
    
    def get_file(self, file_name: str) -> Optional[bytes]:
        """获取文件内容"""
        ...
    
    def delete(self, file_name: str) -> bool:
        """删除文件"""
        ...
    
    def get_file_info(self, file_name: str) -> Optional[SclFileInfo]:
        """获取文件信息 (含解析后的摘要)"""
        ...
```

#### 3.5.2 导入服务 (`import_service.py`)

```python
"""SCL 导入服务

编排完整的导入流程: 解析 → 校验 → 转换 → 持久化
"""
from typing import Dict, List, Any, Optional
from ..parser.scl_parser import SclParser
from ..validator.schema_validator import SclSchemaValidator, ValidationResult
from ..validator.semantic_validator import SclSemanticValidator
from ..transformer.point_transformer import SclPointTransformer
from ..transformer.goose_transformer import SclGooseTransformer
from ..transformer.report_transformer import SclReportTransformer


@dataclass
class ImportOptions:
    """导入选项"""
    # 测点导入
    import_points: bool = True
    include_metadata_da: bool = True       # 是否包含 q/t/du 等元数据 DA
    clear_existing: bool = True            # 是否清除已有测点
    
    # GOOSE 导入
    import_goose: bool = False
    goose_interface: str = "eth0"
    
    # Report 导入
    import_reports: bool = False
    
    # 校验选项
    validate_before_import: bool = True
    fail_on_validation_error: bool = False  # 校验失败时是否中止


@dataclass
class ImportResult:
    """导入结果"""
    success: bool = True
    validation: Optional[ValidationResult] = None
    point_counts: Dict[str, int] = None    # {"yc": N, "yx": N, "yk": N, "yt": N}
    goose_count: int = 0
    report_count: int = 0
    errors: List[str] = None


class SclImportService:
    """SCL 导入服务"""
    
    def __init__(self):
        self._parser = SclParser()
        self._schema_validator = SclSchemaValidator()
        self._semantic_validator = SclSemanticValidator()
        self._point_transformer = SclPointTransformer()
        self._goose_transformer = SclGooseTransformer()
        self._report_transformer = SclReportTransformer()
    
    def import_file(self, file_path: str, channel_id: int,
                    options: ImportOptions = None) -> ImportResult:
        """完整导入流程"""
        options = options or ImportOptions()
        result = ImportResult()
        
        # 1. 解析
        doc = self._parser.parse_file(file_path)
        
        # 2. 校验
        if options.validate_before_import:
            result.validation = self._schema_validator.validate(doc)
            if result.validation and not result.validation.is_valid:
                if options.fail_on_validation_error:
                    result.success = False
                    return result
        
        # 3. 转换 + 持久化
        if options.import_points:
            points = self._point_transformer.transform(doc, include_metadata=options.include_metadata_da)
            result.point_counts = self._save_points(channel_id, points, options.clear_existing)
        
        if options.import_goose:
            goose_config = self._goose_transformer.transform(doc, interface=options.goose_interface)
            result.goose_count = len(goose_config.get("publishers", []))
        
        if options.import_reports:
            report_config = self._report_transformer.transform(doc)
            result.report_count = len(report_config)
        
        return result
    
    def preview(self, file_path: str) -> Dict[str, Any]:
        """预览导入内容 (不执行持久化)"""
        ...
    
    def _save_points(self, channel_id, points, clear_existing): ...
```

### 3.6 后端 Web API

**新增路由文件：** `src/web/api/scl/`

#### 3.6.1 路由设计

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/scl/files` | 列出所有 SCL 文件 |
| POST | `/api/scl/files/upload` | 上传 SCL 文件 |
| GET | `/api/scl/files/{filename}` | 获取文件内容 (原始 XML) |
| DELETE | `/api/scl/files/{filename}` | 删除文件 |
| GET | `/api/scl/files/{filename}/info` | 获取文件摘要信息 |
| GET | `/api/scl/files/{filename}/tree` | 获取 SCL 树形结构 (LD→LN→DO→DA) |
| GET | `/api/scl/files/{filename}/validate` | 校验文件 (结构+语义) |
| POST | `/api/scl/files/{filename}/import` | 执行导入 (测点/GOOSE/Report) |
| POST | `/api/scl/files/{filename}/preview` | 预览导入内容 (不持久化) |
| GET | `/api/scl/files/{filename}/points` | 提取测点列表 |
| GET | `/api/scl/files/{filename}/goose` | 提取 GOOSE 配置 |
| GET | `/api/scl/files/{filename}/reports` | 提取 Report 配置 |
| POST | `/api/scl/diff` | 对比两个 SCL 文件差异 |

#### 3.6.2 Pydantic Schema

```python
# schemas/scl.py

class SclFileUploadRequest(BaseModel):
    """文件上传请求"""
    file: UploadFile

class SclFileListResponse(BaseModel):
    """文件列表响应"""
    files: List[SclFileInfoResponse]

class SclFileInfoResponse(BaseModel):
    """文件信息响应"""
    file_name: str
    file_type: str
    file_size: int
    upload_time: str
    ied_name: str = ""
    ied_count: int = 0
    ld_count: int = 0
    point_counts: Dict[str, int] = {}

class SclImportRequest(BaseModel):
    """导入请求"""
    channel_id: int
    import_points: bool = True
    include_metadata_da: bool = True
    clear_existing: bool = True
    import_goose: bool = False
    import_reports: bool = False
    validate_before_import: bool = True

class SclImportResponse(BaseModel):
    """导入响应"""
    success: bool
    point_counts: Dict[str, int] = {}
    goose_count: int = 0
    report_count: int = 0
    validation_errors: List[str] = []

class SclTreeNode(BaseModel):
    """SCL 树节点"""
    label: str
    type: str             # "ied" / "ld" / "ln" / "do" / "da" / "dataset" / "gse_control" / "report_control"
    ref: str              # 引用路径
    children: List['SclTreeNode'] = []

class SclDiffRequest(BaseModel):
    """文件对比请求"""
    file_a: str
    file_b: str

class SclValidateResponse(BaseModel):
    """校验响应"""
    is_valid: bool
    errors: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
```

### 3.7 前端 UI

#### 3.7.1 SclFileManager 组件

**文件：** `front/src/components/scl/SclFileManager.vue`

```
┌──────────────────────────────────────────────────────────────────────┐
│  SCL 文件管理                                                        │
│  ────────────────────────────────────────────────────────────────     │
│  [上传文件]  [刷新]                                                   │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  文件名          │ 类型 │ 大小   │ IED名  │ 测点数   │ 操作    │  │
│  │  KG_BAMS.icd     │ ICD  │ 1.1MB │ KG_BAMS│ YC:120  │ 📋🗑️  │  │
│  │                  │      │       │        │ YX:85   │         │  │
│  │                  │      │       │        │ YK:12   │         │  │
│  │  Substation.scd  │ SCD  │ 3.5MB │ 3 IEDs │ YC:350  │ 📋🗑️  │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌────────────────────────┐  ┌────────────────────────────────────┐  │
│  │  SCL 树形浏览器         │  │  详情面板                          │  │
│  │  ▼ KG_BAMS (IED)      │  │  ┌──────────────────────────────┐  │  │
│  │    ▼ LD0              │  │  │  [测点] [GOOSE] [Report] [XML]│  │  │
│  │      ▼ LLN0           │  │  │                              │  │  │
│  │        ├ dsGOOSE1      │  │  │  测点预览 (表格)              │  │  │
│  │        ├ gcb1          │  │  │  ┌────┬──────┬────┬──────┐ │  │  │
│  │        ├ rpRack1       │  │  │  │类型│引用   │CDC │FC    │ │  │  │
│  │      ▼ MMXU1          │  │  │  ├────┼──────┼────┼──────┤ │  │  │
│  │        ├ TotW          │  │  │  │YC  │LD0/..│MV  │MX    │ │  │  │
│  │        ├ TotV          │  │  │  │YX  │LD0/..│SPS │ST    │ │  │  │
│  │        └ A             │  │  │  └────┴──────┴────┴──────┘ │  │  │
│  │    ▼ LD1              │  │  │                              │  │  │
│  │      ...              │  │  │  [导入到通道] → 选择通道 + 选项│  │  │
│  └────────────────────────┘  │  └──────────────────────────────┘  │  │
│                              └────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

#### 3.7.2 导入向导

**文件：** `front/src/components/scl/SclImportWizard.vue`

```
┌──────────────────────────────────────────────────────────────────────┐
│  导入向导 - KG_BAMS.icd                                              │
│  ────────────────────────────────────────────────────────────────     │
│                                                                      │
│  步骤 1/3: 校验结果                                                  │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  ✅ 结构校验通过                                                │  │
│  │  ⚠️ 语义校验: 2 个警告                                         │  │
│  │    - GSEControl "gcb1" 在 Communication 中未找到 GSE 地址       │  │
│  │    - ReportControl "rp1" 的 DataSet "dsRpt1" 为空              │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  步骤 2/3: 导入选项                                                  │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  目标通道: [KG_BAMS - IEC61850 ▼]                              │  │
│  │                                                                │  │
│  │  ☑ 导入测点                                                    │  │
│  │    ☑ 包含元数据 DA (q, t, du 等)                                │  │
│  │    ☑ 清除已有测点                                               │  │
│  │    预计: YC=120, YX=85, YK=12, YT=8                           │  │
│  │                                                                │  │
│  │  ☐ 导入 GOOSE 配置                                             │  │
│  │    网络接口: [eth0 ▼]                                           │  │
│  │    预计: 3 个 Publisher, 3 个 Subscription                     │  │
│  │                                                                │  │
│  │  ☐ 导入 Report 配置                                            │  │
│  │    预计: 2 个 BRCB, 1 个 URCB                                  │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  步骤 3/3: 确认导入                                                  │
│                    [取消]  [上一步]  [开始导入]                        │
└──────────────────────────────────────────────────────────────────────┘
```

#### 3.7.3 前端 API 封装

**文件：** `front/src/api/sclApi.ts`

```typescript
// 文件管理
export async function listSclFiles(): Promise<SclFileInfo[]>
export async function uploadSclFile(file: File): Promise<SclFileInfo>
export async function deleteSclFile(fileName: string): Promise<boolean>
export async function getSclFileContent(fileName: string): Promise<string>
export async function getSclFileInfo(fileName: string): Promise<SclFileInfo>

// 预览与浏览
export async function getSclTree(fileName: string): Promise<SclTreeNode>
export async function validateSclFile(fileName: string): Promise<SclValidateResult>
export async function previewImport(fileName: string, options: ImportOptions): Promise<ImportPreview>

// 导入
export async function importSclFile(fileName: string, request: SclImportRequest): Promise<SclImportResponse>

// 提取
export async function getSclPoints(fileName: string): Promise<PointData[]>
export async function getSclGooseConfig(fileName: string): Promise<GooseConfig>
export async function getSclReportConfig(fileName: string): Promise<ReportConfig[]>

// 对比
export async function diffSclFiles(fileA: string, fileB: string): Promise<SclDiffResult>
```

---

## 4. 分阶段实施计划

### Phase 1: SCL 对象模型与解析引擎 (Priority: P0 | 预估: 3 天)

**目标**: 建立统一的 SCL 解析基础设施

| 任务 | 说明 | 产出 |
|------|------|------|
| **1.1 创建 `src/proto/iec61850/plugins/scl/` 模块结构** | 建立 model/parser/validator/transformer/service 子包 | 目录结构 |
| **1.2 实现 SCL 对象模型** | 实现 `model/` 下所有 dataclass (SclDocument, SclIED, SclLDevice 等) | `src/proto/iec61850/plugins/scl/model/` |
| **1.3 实现 SclParser** | 统一解析 ICD/SCD/CID，构建 SclDocument，替代分散的 XML 解析 | `src/proto/iec61850/plugins/scl/parser/scl_parser.py` |
| **1.4 实现 NamespaceHelper** | 命名空间检测与处理 | `src/proto/iec61850/plugins/scl/parser/namespace.py` |
| **1.5 编写解析器单元测试** | 使用现有 KG_BAMS.icd 作为测试用例 | `tests/` |

**验收标准：**
- [ ] `SclParser.parse_file("KG_BAMS.icd")` 成功构建 `SclDocument`
- [ ] SclDocument 包含完整的 IED/LDevice/LN/DOType/DAType/DataSet/GSEControl/ReportControl/Communication 层级
- [ ] `doc.build_type_index()` 后可通过 `get_ln_type/get_do_type/get_da_type` 查找类型定义
- [ ] 兼容有命名空间和无命名空间两种 XML 格式
- [ ] 解析结果与现有 `IcdPointImporter` 的解析结果一致

### Phase 2: 校验引擎与模型转换器 (Priority: P0 | 预估: 3 天)

**目标**: 实现校验和转换，替代现有的分散导入逻辑

| 任务 | 说明 | 产出 |
|------|------|------|
| **2.1 实现 SclSchemaValidator** | 结构校验 (IED 存在性、DataTypeTemplates 完整性等) | `src/proto/iec61850/plugins/scl/validator/schema_validator.py` |
| **2.2 实现 SclSemanticValidator** | 语义校验 (引用完整性、FC 一致性、DataSet 非空等) | `src/proto/iec61850/plugins/scl/validator/semantic_validator.py` |
| **2.3 实现 SclPointTransformer** | SclDocument → 测点数据，逻辑对标 `IcdPointImporter` | `src/proto/iec61850/plugins/scl/transformer/point_transformer.py` |
| **2.4 实现 SclGooseTransformer** | SclDocument → GOOSE 配置，逻辑对标 `IcdGooseImporter` | `src/proto/iec61850/plugins/scl/transformer/goose_transformer.py` |
| **2.5 实现 SclReportTransformer** | SclDocument → Report 配置，替代 `IcdGooseImporter._parse_report_control` | `src/proto/iec61850/plugins/scl/transformer/report_transformer.py` |
| **2.6 对比验证** | 用 KG_BAMS.icd 验证转换结果与现有 Importer 一致 | 测试报告 |

**验收标准：**
- [ ] `SclPointTransformer.transform(doc)` 的输出与 `IcdPointImporter.import_from_icd()` 的测点列表完全一致
- [ ] `SclGooseTransformer.transform(doc)` 的输出与 `IcdGooseImporter.parse_icd()` 的 GOOSE 配置一致
- [ ] `SclReportTransformer.transform(doc)` 的输出与 `IcdGooseImporter._parse_report_control()` 一致
- [ ] 校验器能检测出无效引用、缺失 DataSet 等常见错误

### Phase 3: 文件管理与导入服务 (Priority: P0 | 预估: 2 天)

**目标**: 实现文件管理和编排导入流程

| 任务 | 说明 | 产出 |
|------|------|------|
| **3.1 实现 SclFileManager** | 文件上传/存储/列表/删除，基于 `data/61850icd/` | `src/proto/iec61850/plugins/scl/service/file_manager.py` |
| **3.2 实现 SclImportService** | 编排 解析→校验→转换→持久化 完整流程 | `src/proto/iec61850/plugins/scl/service/import_service.py` |
| **3.3 集成到现有导入入口** | 修改 `import_points.py` 使用新 SclImportService | `src/web/api/channel/import_points.py` |
| **3.4 实现文件对比服务** | 对比两个 SCL 文件的 IED/LN/DO/DA 差异 | `src/proto/iec61850/plugins/scl/service/diff_service.py` |

**验收标准：**
- [ ] 上传 ICD 文件后可通过 API 查询文件列表和信息
- [ ] `SclImportService.import_file()` 成功执行完整的导入流程
- [ ] 现有 `/api/channels/import-icd` 接口行为不变（向后兼容）
- [ ] `SclImportService.preview()` 可在不持久化的情况下预览导入内容

### Phase 4: 后端 Web API (Priority: P0 | 预估: 2 天)

**目标**: 提供 SCL 文件管理 RESTful API

| 任务 | 说明 | 产出 |
|------|------|------|
| **4.1 创建 Pydantic Schema** | SclFileInfo/SclTreeNode/SclImportRequest 等模型 | `src/web/api/schemas/scl.py` |
| **4.2 实现文件管理路由** | CRUD + 上传 + 下载 + 删除 | `src/web/api/scl/router.py` |
| **4.3 实现预览浏览路由** | 树形结构 / 校验 / 预览 | `src/web/api/scl/preview.py` |
| **4.4 实现导入路由** | 导入 / 提取测点 / 提取GOOSE / 提取Report | `src/web/api/scl/import_wizard.py` |
| **4.5 实现文件对比路由** | Diff API | `src/web/api/scl/diff.py` |
| **4.6 注册路由** | 在 `app.py` 注册 scl_router | `src/web/app.py` |

**验收标准：**
- [ ] 13 个 API 端点全部可用
- [ ] 上传/列表/删除文件正常
- [ ] 树形结构 API 返回正确的 LD→LN→DO→DA 层级
- [ ] 校验 API 返回有意义的错误/警告信息
- [ ] 导入 API 成功将测点写入数据库

### Phase 5: 前端 UI (Priority: P1 | 预估: 3 天)

**目标**: 实现 SCL 文件管理前端界面

| 任务 | 说明 | 产出 |
|------|------|------|
| **5.1 创建 sclApi.ts** | TypeScript API 封装，类型定义 | `front/src/api/sclApi.ts` |
| **5.2 创建 SclFileManager.vue** | 文件列表 + 上传 + 树形浏览器 + 详情面板 | `front/src/components/scl/SclFileManager.vue` |
| **5.3 创建 SclImportWizard.vue** | 多步导入向导 (校验→选项→确认) | `front/src/components/scl/SclImportWizard.vue` |
| **5.4 创建 SclXmlViewer.vue** | XML 原始内容查看 (语法高亮) | `front/src/components/scl/SclXmlViewer.vue` |
| **5.5 创建 SclDiffViewer.vue** | 文件对比视图 | `front/src/components/scl/SclDiffViewer.vue` |
| **5.6 创建 SclView.vue** | SCL 页面视图 | `front/src/views/SclView.vue` |
| **5.7 注册路由与导航** | 添加 `/scl` 路由，侧边栏集成 | `router/index.ts`、`useIec61850Tree.ts` |
| **5.8 i18n 翻译** | 中英文 SCL 相关翻译 | `zh-CN.ts`、`en-US.ts` |

**验收标准：**
- [ ] 文件列表正确显示已上传的 ICD/SCD/CID 文件
- [ ] 上传文件后自动刷新列表
- [ ] 点击文件后左侧显示 SCL 树形结构
- [ ] 选择 DO/DA 节点后右侧显示属性详情
- [ ] 导入向导可逐步完成 (校验→选项→导入)
- [ ] XML 查看器显示带语法高亮的原始内容
- [ ] 侧边栏 IEC61850 设备下增加 "Files" 导航入口

### Phase 6: 迁移与增强 (Priority: P2 | 预估: 2 天)

**目标**: 迁移现有代码到新模块，增强高级功能

| 任务 | 说明 | 产出 |
|------|------|------|
| **6.1 迁移 IcdPointImporter** | 内部改用 SclParser + SclPointTransformer，保持接口不变 | `src/tools/icd_point_importer.py` |
| **6.2 迁移 IcdGooseImporter** | 内部改用 SclParser + SclGooseTransformer，保持接口不变 | `src/tools/icd_goose_importer.py` |
| **6.3 增强 FilesPlugin** | 实现 `get_file_list/get_file` 的完整逻辑 | `src/proto/iec61850/plugins/files/` |
| **6.4 实现 server_model_builder** | SclDocument → IedModel (动态创建服务端模型) | `src/proto/iec61850/plugins/scl/transformer/server_model_builder.py` |
| **6.5 SCD 合并支持** | 多 ICD 合并为 SCD 的基础能力 | `src/proto/iec61850/plugins/scl/service/merge_service.py` |
| **6.6 性能优化** | 大型 SCL 文件 (>5MB) 的流式解析与增量构建 | `src/proto/iec61850/plugins/scl/parser/` |

**验收标准：**
- [ ] 迁移后现有功能（ICD 导入测点、ICD 导入 GOOSE）行为不变
- [ ] FilesPlugin 可获取远程 IED 的文件列表
- [ ] server_model_builder 可从 SclDocument 构建 IedModel 实例
- [ ] 大型 SCL 文件（5MB+）解析时间 < 3s

---

## 5. 与现有模块的关系

### 5.1 依赖关系

```
                    ┌──────────────────────────────────┐
                    │  src/proto/iec61850/plugins/scl/  │  ← 新增 SCL 文件插件
                    │  (核心层)                          │
                    └───────────────┬──────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
             ┌──────▼──────┐ ┌─────▼──────┐ ┌──────▼──────┐
             │ Web API     │ │ tools/     │ │ proto/      │
             │ (scl 路由)  │ │ (Importer) │ │ (plugins)   │
             └─────────────┘ └────────────┘ └─────────────┘
```

**关键原则：**
- `src/proto/iec61850/plugins/scl/` 是纯 Python 模块，不依赖 `pyiec61850`
- `src/proto/iec61850/plugins/scl/` 不依赖 Web 框架 (FastAPI) 和数据库 (SQLAlchemy)
- 现有 `IcdPointImporter` 和 `IcdGooseImporter` 在 Phase 6 中迁移为 `src/proto/iec61850/plugins/scl/` 的薄封装
- `src/proto/iec61850/plugins/files/` 增强，利用 `src/proto/iec61850/plugins/scl/` 的解析能力

### 5.2 文件清单

#### 新增文件

| 文件 | 说明 |
|------|------|
| `src/proto/iec61850/plugins/scl/__init__.py` | 模块入口 |
| `src/proto/iec61850/plugins/scl/model/__init__.py` | 模型子包 |
| `src/proto/iec61850/plugins/scl/model/scl_base.py` | SCL 基础数据类 |
| `src/proto/iec61850/plugins/scl/model/scl_document.py` | SCL 文档顶层容器 |
| `src/proto/iec61850/plugins/scl/model/ied.py` | IED / AccessPoint / Server |
| `src/proto/iec61850/plugins/scl/model/logical_device.py` | LDevice / LN0 / LN |
| `src/proto/iec61850/plugins/scl/model/data_object.py` | DOI / DAI / SDI |
| `src/proto/iec61850/plugins/scl/model/data_type.py` | LNodeType / DOType / DAType / EnumType |
| `src/proto/iec61850/plugins/scl/model/dataset.py` | DataSet / FCDA |
| `src/proto/iec61850/plugins/scl/model/control_block.py` | GSEControl / ReportControl / SVControl |
| `src/proto/iec61850/plugins/scl/model/communication.py` | Communication / SubNetwork / ConnectedAP / GSE |
| `src/proto/iec61850/plugins/scl/parser/__init__.py` | 解析子包 |
| `src/proto/iec61850/plugins/scl/parser/scl_parser.py` | 统一 SCL 解析器 |
| `src/proto/iec61850/plugins/scl/parser/namespace.py` | 命名空间处理 |
| `src/proto/iec61850/plugins/scl/parser/type_resolver.py` | 数据类型引用解析 |
| `src/proto/iec61850/plugins/scl/validator/__init__.py` | 校验子包 |
| `src/proto/iec61850/plugins/scl/validator/schema_validator.py` | 结构校验 |
| `src/proto/iec61850/plugins/scl/validator/semantic_validator.py` | 语义校验 |
| `src/proto/iec61850/plugins/scl/transformer/__init__.py` | 转换子包 |
| `src/proto/iec61850/plugins/scl/transformer/point_transformer.py` | 测点转换器 |
| `src/proto/iec61850/plugins/scl/transformer/goose_transformer.py` | GOOSE 转换器 |
| `src/proto/iec61850/plugins/scl/transformer/report_transformer.py` | Report 转换器 |
| `src/proto/iec61850/plugins/scl/transformer/server_model_builder.py` | 服务端模型构建器 |
| `src/proto/iec61850/plugins/scl/service/__init__.py` | 服务子包 |
| `src/proto/iec61850/plugins/scl/service/file_manager.py` | 文件管理器 |
| `src/proto/iec61850/plugins/scl/service/import_service.py` | 导入服务 |
| `src/proto/iec61850/plugins/scl/service/diff_service.py` | 文件对比服务 |
| `src/web/api/scl/__init__.py` | Web API 子包 |
| `src/web/api/scl/router.py` | 文件管理路由 |
| `src/web/api/scl/preview.py` | 预览浏览路由 |
| `src/web/api/scl/import_wizard.py` | 导入路由 |
| `src/web/api/scl/diff.py` | 对比路由 |
| `src/web/api/schemas/scl.py` | Pydantic 数据模型 |
| `front/src/api/sclApi.ts` | 前端 API 层 |
| `front/src/components/scl/SclFileManager.vue` | 文件管理主组件 |
| `front/src/components/scl/SclImportWizard.vue` | 导入向导组件 |
| `front/src/components/scl/SclXmlViewer.vue` | XML 查看器 |
| `front/src/components/scl/SclDiffViewer.vue` | 对比查看器 |
| `front/src/views/SclView.vue` | SCL 页面视图 |

#### 修改文件

| 文件 | 修改内容 |
|------|---------|
| `src/tools/icd_point_importer.py` | Phase 6: 内部改用 SclParser + SclPointTransformer |
| `src/tools/icd_goose_importer.py` | Phase 6: 内部改用 SclParser + SclGooseTransformer |
| `src/web/api/channel/import_points.py` | Phase 3: 使用 SclImportService |
| `src/web/api/channel/iec61850.py` | Phase 5: Structure 端点增加 Files 分类 |
| `src/web/app.py` | Phase 4: 注册 scl_router |
| `src/proto/iec61850/plugins/files/__init__.py` | Phase 6: 完整实现 FilesPlugin |
| `front/src/router/index.ts` | Phase 5: 新增 `/scl` 路由 |
| `front/src/composables/useIec61850Tree.ts` | Phase 5: Files 分类支持导航 |
| `front/src/i18n/locales/zh-CN.ts` | Phase 5: SCL 相关中文翻译 |
| `front/src/i18n/locales/en-US.ts` | Phase 5: SCL 相关英文翻译 |

---

## 6. 设计模式

| 模式 | 应用位置 | 说明 |
|------|----------|------|
| **Builder** | `SclParser` | 逐步构建 SclDocument 对象树 |
| **Strategy** | `transformer/` | 不同转换策略 (测点/GOOSE/Report) |
| **Facade** | `SclImportService` | 编排解析→校验→转换→持久化完整流程 |
| **Value Object** | `model/` | 不可变 dataclass 表示 SCL 元素 |
| **Index** | `SclDocument._ln_type_index` 等 | 类型 ID → 对象的快速查找索引 |
| **Null Object** | 校验结果 | ValidationResult 无错误时仍返回有效对象 |
| **Template Method** | `SclTransformer` 基类 | 定义转换流程骨架，子类实现具体转换 |

---

## 7. 向后兼容策略

1. **`IcdPointImporter` 接口不变** — Phase 6 迁移后，`import_from_icd()` 和 `preview_from_icd()` 签名和行为保持一致
2. **`IcdGooseImporter` 接口不变** — `parse_icd()` 和 `import_goose_from_icd()` 保持兼容
3. **现有 `/api/channels/import-icd` 端点不变** — 行为不变，内部实现改用 SclImportService
4. **`data/61850icd/` 目录结构不变** — 文件管理器复用现有存储路径
5. **新增 API 独立前缀** — 所有新 API 在 `/api/scl/` 前缀下，不影响现有端点

---

## 8. 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| **SCL 格式差异大** | 高 | 中 | 建立广泛的 ICD 样本库（不同厂商），优先兼容常见格式 |
| **大型 SCL 文件性能** | 中 | 中 | Phase 6 引入流式解析，5MB 以下文件无需优化 |
| **与现有 Importer 行为不一致** | 中 | 高 | Phase 2 对比验证，用 KG_BAMS.icd 做回归测试 |
| **SCL XSD Schema 版本差异** | 中 | 低 | 校验器采用宽松模式，Warning 不阻塞导入 |
| **前端 XML 查看器性能** | 低 | 中 | 使用虚拟滚动，限制 10000 行以上文件的高亮渲染 |
| **SCD 合并复杂度** | 高 | 中 | Phase 6 仅实现基础合并，复杂场景后续迭代 |

---

## 9. 验收标准

### Phase 1 验收
- [ ] `SclParser` 能解析现有 `KG_BAMS.icd` 文件，构建完整的 `SclDocument`
- [ ] 对象模型覆盖 IED/LDevice/LN/DOType/DAType/DataSet/GSEControl/ReportControl/Communication
- [ ] 命名空间兼容性：有/无命名空间的 ICD 文件均可解析

### Phase 2 验收
- [ ] `SclPointTransformer` 输出与 `IcdPointImporter` 完全一致
- [ ] `SclGooseTransformer` 输出与 `IcdGooseImporter` 完全一致
- [ ] 校验器能检测引用缺失、DataSet 为空等常见语义错误

### Phase 3 验收
- [ ] `SclImportService.import_file()` 成功将 ICD 测点导入数据库
- [ ] 现有 `/api/channels/import-icd` 接口行为不变
- [ ] 文件管理器支持上传/列表/删除操作

### Phase 4 验收
- [ ] 13 个 API 端点全部可用，响应格式符合 Pydantic Schema
- [ ] 树形结构 API 返回正确的层级关系
- [ ] 校验 API 返回有意义的错误/警告

### Phase 5 验收
- [ ] 文件管理页面完整可用（上传/浏览/预览/导入）
- [ ] 导入向导可逐步完成
- [ ] XML 查看器正确显示原始内容
- [ ] 中英文界面正常

### 最终验收
- [ ] 全部 6 个 Phase 验收项通过
- [ ] 现有功能无回归（ICD 导入测点/GOOSE 配置正常）
- [ ] 新增模块与现有插件架构 (defs/core/plugins) 无冲突
- [ ] 大型 SCL 文件 (5MB+) 解析时间 < 3s

---

## 10. 参考文档

1. IEC 61850-6: SCL (Substation Configuration Language) 配置描述语言
2. IEC 61850-7-1 ~ 7-4: 公共数据类 (CDC) 和逻辑节点定义
3. IEC 61850-8-1: SCSM - MMS 映射
4. libIEC61850 官方文档: [https://libiec61850.com/](https://libiec61850.com/)
5. 项目现有文档: `docs/changelog/iec61850-refactoring-plan.md`（插件架构参考）
6. 项目现有文档: `docs/changelog/goose-support.md`（GOOSE 实现参考）
7. 项目现有文档: `docs/changelog/iec61850-reports-support.md`（Reports 实现参考）
8. 项目现有 ICD 样本: `data/61850icd/KG_BAMS.icd`（测试基准）
