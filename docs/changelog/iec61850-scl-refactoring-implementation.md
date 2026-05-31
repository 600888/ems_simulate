# IEC 61850 SCL 文件模块重构实施计划

> 版本: 2.0  
> 日期: 2026-05-31  
> 基于: [iec61850-scl-file-module.md](./iec61850-scl-file-module.md) v1.0  
> 状态: 实施规划  
> 目标: 以现代 Python 设计模式重构 SCL 模块，提升可维护性、可测试性和可扩展性

---

## 1. 设计原则与模式总览

### 1.1 核心设计原则

| 原则 | 说明 | 应用 |
|------|------|------|
| **单一职责 (SRP)** | 每个类/模块只有一个变更原因 | Parser 只解析，Validator 只校验，Transformer 只转换 |
| **开闭原则 (OCP)** | 对扩展开放，对修改关闭 | 新增 Transformer 无需修改 ImportService |
| **依赖倒置 (DIP)** | 依赖抽象而非具体实现 | Service 层依赖 Protocol 接口，不依赖具体 Parser |
| **接口隔离 (ISP)** | 客户端不应被迫依赖不使用的接口 | 拆分校验规则为独立 Rule |
| **组合优于继承** | 优先使用组合和委托 | SclDocument 组合 SclIED，而非继承 |

### 1.2 现代 Python 设计模式应用

| 模式 | Python 实现 | 应用位置 |
|------|-------------|----------|
| **Protocol (结构化子类型)** | `typing.Protocol` + `@runtime_checkable` | `SclParserProtocol`, `SclValidatorProtocol`, `SclTransformerProtocol` |
| **dataclass + slots** | `@dataclass(slots=True, frozen=True)` | 不可变 SCL 模型 (`model/`) |
| **Builder** | 流式 API + `__enter__`/`__exit__` | `SclParser` 构建 `SclDocument` |
| **Strategy** | 函数/类实现 Protocol | `transformer/` 中不同转换策略 |
| **Facade** | 编排类 | `SclImportService` |
| **Registry** | 字典 + 工厂函数 | 校验规则注册 (`ValidationRuleRegistry`) |
| **Result/Either** | `Success[T]` / `Failure[E]` 替代异常 | 解析和校验结果 |
| **Null Object** | `EmptyValidationResult` | 无错误时返回有效空对象 |
| **Iterator/Generator** | `yield` 惰性遍历 | 大型 SCL 文件的流式解析 |
| **Context Manager** | `with` 语句 | 文件操作、临时缓存 |

### 1.3 Python 版本要求

- **最低版本**: Python 3.10+（支持 `match` 语句、`TypeAlias`、`ParamSpec`）
- **推荐版本**: Python 3.11+（`ExceptionGroup`、`TaskGroup`、性能优化）

---

## 2. SCL 对象模型设计

### 2.1 设计决策

**采用 `@dataclass(slots=True)` 而非 Pydantic BaseModel 用于内部模型：**

- `model/` 层是纯 Python 数据类，不依赖 Web 框架
- `slots=True` 减少内存占用约 40%，提升属性访问速度
- 不可变模型使用 `frozen=True`，可变模型使用 `slots=True` + `__post_init__` 校验
- Web API 层使用 Pydantic v2 做序列化/反序列化，与内部模型分离

**类型索引采用延迟构建 + 缓存：**

- `SclDocument.build_type_index()` 在解析后调用一次
- 后续通过 `get_*_type()` O(1) 查找
- 支持 `functools.cached_property` 按需计算派生属性

### 2.2 基础类型 (`model/scl_base.py`)

```python
"""SCL 基础数据类"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(slots=True)
class SclElement:
    """SCL 元素基类
    
    所有 SCL 模型类的公共基类，提供通用属性。
    使用 slots=True 优化内存和属性访问速度。
    """
    desc: str = ""
    _source_line: int = field(default=0, repr=False)
    
    @property
    def source_line(self) -> int:
        """原始 XML 行号 (用于校验报告定位)"""
        return self._source_line
```

### 2.3 SCL 文档 (`model/scl_document.py`)

```python
"""SCL 文档 - 顶层容器"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from functools import cached_property
from typing import Dict, List, Optional

from .scl_base import SclElement
from .ied import SclIED
from .data_type import SclLNodeType, SclDOType, SclDAType, SclEnumType
from .communication import SclCommunication


class SclFileType(Enum):
    """SCL 文件类型枚举"""
    ICD = "ICD"   # IED 能力描述
    SCD = "SCD"   # 变电站配置描述
    CID = "CID"   # IED 实例配置


@dataclass
class SclDataTypeTemplates:
    """DataTypeTemplates 节"""
    ln_types: List[SclLNodeType] = field(default_factory=list)
    do_types: List[SclDOType] = field(default_factory=list)
    da_types: List[SclDAType] = field(default_factory=list)
    enum_types: List[SclEnumType] = field(default_factory=list)


@dataclass
class SclDocument:
    """SCL 文档对象模型
    
    对应 SCL XML 根元素 <SCL>，包含 IED 配置、数据类型模板、通信配置。
    支持 ICD/SCD/CID 三种文件类型。
    
    设计模式:
    - Composite: 文档包含 IED/DataTypeTemplates/Communication 子结构
    - Index: 通过 build_type_index() 构建类型 ID → 对象的快速查找索引
    - cached_property: 按需计算派生属性，避免重复计算
    """
    # 文件元信息
    file_path: str = ""
    file_type: SclFileType = SclFileType.ICD
    scl_revision: str = ""
    
    # 顶级节 (Composite)
    ieds: List[SclIED] = field(default_factory=list)
    data_type_templates: SclDataTypeTemplates = field(default_factory=SclDataTypeTemplates)
    communication: Optional[SclCommunication] = None
    
    # 类型索引 (延迟构建，不序列化)
    _ln_type_index: Dict[str, SclLNodeType] = field(default_factory=dict, repr=False, init=False)
    _do_type_index: Dict[str, SclDOType] = field(default_factory=dict, repr=False, init=False)
    _da_type_index: Dict[str, SclDAType] = field(default_factory=dict, repr=False, init=False)
    _enum_type_index: Dict[str, SclEnumType] = field(default_factory=dict, repr=False, init=False)
    _index_built: bool = field(default=False, repr=False, init=False)
    
    def build_type_index(self) -> None:
        """构建数据类型索引 (解析后调用一次)"""
        self._ln_type_index = {t.id: t for t in self.data_type_templates.ln_types}
        self._do_type_index = {t.id: t for t in self.data_type_templates.do_types}
        self._da_type_index = {t.id: t for t in self.data_type_templates.da_types}
        self._enum_type_index = {t.id: t for t in self.data_type_templates.enum_types}
        self._index_built = True
    
    def get_ln_type(self, type_id: str) -> Optional[SclLNodeType]:
        return self._ln_type_index.get(type_id)
    
    def get_do_type(self, type_id: str) -> Optional[SclDOType]:
        return self._do_type_index.get(type_id)
    
    def get_da_type(self, type_id: str) -> Optional[SclDAType]:
        return self._da_type_index.get(type_id)
    
    def get_enum_type(self, type_id: str) -> Optional[SclEnumType]:
        return self._enum_type_index.get(type_id)
    
    @cached_property
    def ied_names(self) -> List[str]:
        """所有 IED 名称列表"""
        return [ied.name for ied in self.ieds]
    
    @cached_property
    def all_logical_devices(self) -> List[tuple]:
        """所有逻辑设备 (ied_name, ld) 的扁平列表"""
        result = []
        for ied in self.ieds:
            for ap in ied.access_points:
                if ap.server:
                    for ld in ap.server.logical_devices:
                        result.append((ied.name, ld))
        return result
    
    @cached_property
    def all_data_sets(self) -> List[tuple]:
        """所有数据集 (ied_name, ld_inst, dataset) 的扁平列表"""
        result = []
        for ied in self.ieds:
            for ap in ied.access_points:
                if ap.server:
                    for ld in ap.server.logical_devices:
                        if ld.ln0:
                            for ds in ld.ln0.data_sets:
                                result.append((ied.name, ld.inst, ds))
        return result
```

### 2.4 枚举与常量改进

```python
# model/enums.py
from enum import Enum, auto


class FunctionalConstraint(str, Enum):
    """IEC 61850 功能约束 (FC)"""
    ST = "ST"    # 状态信息
    MX = "MX"    # 测量值
    SP = "SP"    # 设定参数
    SV = "SV"    # 替代值
    CF = "CF"    # 配置
    DC = "DC"    # 描述
    SG = "SG"    # 定值组
    SE = "SE"    # 定值组编辑
    SR = "SR"    # 服务响应
    OR = "OR"    # 操作员操作
    BL = "BL"    # 闭锁
    EX = "EX"    # 扩展定义
    CO = "CO"    # 控制操作


class CommonDataClass(str, Enum):
    """IEC 61850 公共数据类 (CDC)"""
    # 遥测
    MV = "MV"
    CMV = "CMV"
    SAV = "SAV"
    WYE = "WYE"
    DEL = "DEL"
    SEQ = "SEQ"
    HMV = "HMV"
    # 遥信
    SPS = "SPS"
    DPS = "DPS"
    INS = "INS"
    ENS = "ENS"
    ENC = "ENC"
    ACT = "ACT"
    ACD = "ACD"
    SEC = "SEC"
    BCR = "BCR"
    # 遥控
    SPC = "SPC"
    DPC = "DPC"
    # 遥调
    APC = "APC"
    INC = "INC"
    ASG = "ASG"
    ING = "ING"
    SPG = "SPG"
    BAC = "BAC"


class PointCategory(Enum):
    """测点分类"""
    YC = auto()  # 遥测
    YX = auto()  # 遥信
    YK = auto()  # 遥控
    YT = auto()  # 遥调


# CDC → 测点分类映射 (使用 frozenset 实现 O(1) 查找)
CDC_CATEGORY_MAP: dict[str, PointCategory] = {
    **{cdc.value: PointCategory.YC for cdc in (
        CommonDataClass.MV, CommonDataClass.CMV, CommonDataClass.SAV,
        CommonDataClass.WYE, CommonDataClass.DEL, CommonDataClass.SEQ, CommonDataClass.HMV,
    )},
    **{cdc.value: PointCategory.YX for cdc in (
        CommonDataClass.SPS, CommonDataClass.DPS, CommonDataClass.INS,
        CommonDataClass.ENS, CommonDataClass.ENC, CommonDataClass.ACT,
        CommonDataClass.ACD, CommonDataClass.SEC, CommonDataClass.BCR,
    )},
    **{cdc.value: PointCategory.YK for cdc in (
        CommonDataClass.SPC, CommonDataClass.DPC,
    )},
    **{cdc.value: PointCategory.YT for cdc in (
        CommonDataClass.APC, CommonDataClass.INC, CommonDataClass.ASG,
        CommonDataClass.ING, CommonDataClass.SPG, CommonDataClass.BAC,
    )},
}
```

---

## 3. 解析引擎设计

### 3.1 Protocol 接口定义

```python
# parser/protocols.py
from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..model.scl_document import SclDocument


@runtime_checkable
class SclParserProtocol(Protocol):
    """SCL 解析器协议
    
    定义解析器的公共接口，允许替换实现
    (例如: 标准库解析器 vs lxml 解析器 vs 流式解析器)。
    """
    def parse_file(self, file_path: str) -> SclDocument: ...
    def parse_string(self, xml_string: str) -> SclDocument: ...
```

### 3.2 统一解析器 (`parser/scl_parser.py`)

```python
"""统一 SCL 解析器

设计模式:
- Builder: 逐步构建 SclDocument 对象树
- Template Method: _parse_root 定义解析骨架，子方法实现具体解析
- Protocol: 符合 SclParserProtocol 接口
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Optional

from ..model.scl_document import SclDocument, SclFileType
from .namespace import NamespaceHelper


class SclParserError(Exception):
    """SCL 解析错误"""
    def __init__(self, message: str, file_path: str = "", line: int = 0):
        self.file_path = file_path
        self.line = line
        super().__init__(f"{message} (file={file_path}, line={line})" if file_path else message)


class SclParser:
    """SCL 文件解析器
    
    用法:
        parser = SclParser()
        doc = parser.parse_file("path/to/file.icd")
        # 或
        doc = parser.parse_string(scl_xml_string)
    
    特性:
    - 统一解析 ICD/SCD/CID
    - 自动检测 XML 命名空间
    - 构建完整的 SclDocument 对象模型
    - 支持 type_resolver 进行类型引用解析
    """
    
    def __init__(self):
        self._ns = NamespaceHelper()
    
    def parse_file(self, file_path: str) -> SclDocument:
        """解析 SCL 文件
        
        Raises:
            FileNotFoundError: 文件不存在
            SclParserError: XML 解析错误
        """
        try:
            tree = ET.parse(file_path)
        except ET.ParseError as e:
            raise SclParserError(
                f"XML 解析错误: {e}",
                file_path=file_path,
                line=getattr(e, 'position', (0,))[0],
            ) from e
        except FileNotFoundError:
            raise
        
        root = tree.getroot()
        return self._parse_root(root, file_path=file_path)
    
    def parse_string(self, xml_string: str) -> SclDocument:
        """解析 SCL XML 字符串"""
        try:
            root = ET.fromstring(xml_string)
        except ET.ParseError as e:
            raise SclParserError(f"XML 解析错误: {e}") from e
        return self._parse_root(root)
    
    def _parse_root(self, root: ET.Element, *, file_path: str = "") -> SclDocument:
        """解析 <SCL> 根元素 (Template Method 骨架)"""
        self._ns.detect(root)
        
        doc = SclDocument(
            file_path=file_path,
            scl_revision=root.get("revision", ""),
            file_type=self._infer_file_type(root),
        )
        
        # 解析各子节
        for ied_elem in root.findall(self._ns.tag("IED")):
            doc.ieds.append(self._parse_ied(ied_elem))
        
        dtt = root.find(self._ns.tag("DataTypeTemplates"))
        if dtt is not None:
            doc.data_type_templates = self._parse_data_type_templates(dtt)
            doc.build_type_index()
        
        comm = root.find(self._ns.tag("Communication"))
        if comm is not None:
            doc.communication = self._parse_communication(comm)
        
        return doc
    
    def _infer_file_type(self, root: ET.Element) -> SclFileType:
        """推断 SCL 文件类型"""
        ieds = root.findall(self._ns.tag("IED"))
        match len(ieds):
            case 0:
                return SclFileType.ICD
            case 1:
                if root.find(self._ns.tag("DataTypeTemplates")) is not None:
                    return SclFileType.ICD
                return SclFileType.CID
            case _:
                return SclFileType.SCD
    
    # --- 以下为各元素的解析方法 (Builder 步骤) ---
    
    def _parse_ied(self, elem: ET.Element) -> SclIED:
        """解析 IED 元素"""
        ied = SclIED(
            name=elem.get("name", ""),
            manufacturer=elem.get("manufacturer", ""),
            type=elem.get("type", ""),
            config_revision=elem.get("configRevision", ""),
            original_scl_revision=elem.get("originalSclRevision", ""),
            desc=elem.get("desc", ""),
        )
        for ap_elem in elem.findall(self._ns.tag("AccessPoint")):
            ied.access_points.append(self._parse_access_point(ap_elem))
        return ied
    
    # ... 其他 _parse_* 方法实现 (见文档 v1.0 中的接口定义)
```

### 3.3 类型引用解析器 (`parser/type_resolver.py`)

```python
"""数据类型引用解析器

设计模式:
- Visitor: 遍历 SclDocument 树，解析类型引用
- Index: 利用 SclDocument 的类型索引进行快速查找
"""
from __future__ import annotations

from typing import Optional

from ..model.scl_document import SclDocument
from ..model.data_type import SclLNodeType, SclDOType, SclDAType
from ..model.logical_device import SclLN0, SclLN


class TypeResolver:
    """数据类型引用解析器
    
    将 LN 的 lnType 引用解析为完整的 LNodeType → DOType → DAType 链，
    替代原 IcdPointImporter 中分散的类型缓存逻辑。
    """
    
    def __init__(self, doc: SclDocument):
        self._doc = doc
    
    def resolve_ln_type(self, ln: SclLN0 | SclLN) -> Optional[SclLNodeType]:
        """解析 LN 的 lnType 引用"""
        return self._doc.get_ln_type(ln.ln_type)
    
    def resolve_do_type(self, type_id: str) -> Optional[SclDOType]:
        """解析 DO 的 type 引用"""
        return self._doc.get_do_type(type_id)
    
    def resolve_da_type(self, type_id: str) -> Optional[SclDAType]:
        """解析 DA 的 type 引用"""
        return self._doc.get_da_type(type_id)
    
    def resolve_da_path(self, cdc: str, da_name: str) -> str:
        """推断结构体 DA 的完整路径
        
        替代原 IcdGooseImporter._KNOWN_STRUCT_DA_TO_FULL_PATH 硬编码
        """
        # 结构体 DA 路径映射表 (从 IcdGooseImporter 迁移)
        STRUCT_DA_PATHS: dict[str, str] = {
            "mag": "mag.f",
            "instMag": "instMag.f",
            "cVal": "cVal.mag.f",
            "mxVal": "mxVal.f",
            "fCVal": "fCVal.mag.f",
            "wVal": "wVal.f",
            "setMag": "setMag.f",
            "Oper": "Oper.ctlVal",
            "SBOw": "SBOw.ctlVal",
            "Cancel": "Cancel.ctlVal",
            "origin": "origin.orCat",
        }
        return STRUCT_DA_PATHS.get(da_name, da_name)
```

---

## 4. 校验引擎设计

### 4.1 Result 模式替代异常

```python
# validator/result.py
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Generic, TypeVar, List


class Severity(Enum):
    ERROR = auto()
    WARNING = auto()
    INFO = auto()


@dataclass(slots=True, frozen=True)
class ValidationIssue:
    """不可变校验问题"""
    severity: Severity
    message: str
    xpath: str = ""
    line: int = 0
    element_name: str = ""


@dataclass
class ValidationResult:
    """校验结果 (Null Object 模式: 空结果也是有效对象)"""
    issues: List[ValidationIssue] = field(default_factory=list)
    
    @property
    def is_valid(self) -> bool:
        return not any(i.severity == Severity.ERROR for i in self.issues)
    
    @property
    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.ERROR]
    
    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.WARNING]
    
    def merge(self, other: ValidationResult) -> ValidationResult:
        """合并两个校验结果"""
        return ValidationResult(issues=self.issues + other.issues)
    
    @classmethod
    def empty(cls) -> ValidationResult:
        """Null Object: 空的校验结果"""
        return cls()


EMPTY_VALIDATION_RESULT = ValidationResult.empty()
```

### 4.2 规则注册表 (Strategy + Registry)

```python
# validator/rules.py
from __future__ import annotations

from typing import Protocol, runtime_checkable, Dict, Type

from ..model.scl_document import SclDocument
from .result import ValidationResult


@runtime_checkable
class ValidationRule(Protocol):
    """校验规则协议 (Strategy 模式)
    
    每个规则独立校验一个方面，可自由组合。
    """
    def check(self, doc: SclDocument) -> ValidationResult: ...


class ValidationRuleRegistry:
    """校验规则注册表 (Registry 模式)
    
    支持动态注册、按需选择校验规则。
    """
    
    def __init__(self):
        self._rules: Dict[str, ValidationRule] = {}
    
    def register(self, name: str, rule: ValidationRule) -> None:
        self._rules[name] = rule
    
    def get(self, name: str) -> ValidationRule | None:
        return self._rules.get(name)
    
    def all_rules(self) -> list[ValidationRule]:
        return list(self._rules.values())
    
    def check_all(self, doc: SclDocument) -> ValidationResult:
        """运行所有注册规则"""
        result = ValidationResult.empty()
        for rule in self._rules.values():
            result = result.merge(rule.check(doc))
        return result
    
    def check_selected(self, doc: SclDocument, rule_names: list[str]) -> ValidationResult:
        """运行指定规则"""
        result = ValidationResult.empty()
        for name in rule_names:
            rule = self._rules.get(name)
            if rule:
                result = result.merge(rule.check(doc))
        return result
```

### 4.3 内置校验规则实现

```python
# validator/builtin_rules.py
"""内置校验规则实现"""
from __future__ import annotations

from ..model.scl_document import SclDocument
from .result import ValidationResult, ValidationIssue, Severity
from .rules import ValidationRule


class IedExistenceRule:
    """规则: SCL 文件至少包含一个 IED"""
    
    def check(self, doc: SclDocument) -> ValidationResult:
        if not doc.ieds:
            return ValidationResult([
                ValidationIssue(
                    severity=Severity.ERROR,
                    message="SCL 文件中未找到 IED 元素",
                    xpath="/SCL/IED",
                )
            ])
        return ValidationResult.empty()


class DataTypeTemplatesRule:
    """规则: DataTypeTemplates 必须存在且非空"""
    
    def check(self, doc: SclDocument) -> ValidationResult:
        issues = []
        if not doc.data_type_templates.ln_types:
            issues.append(ValidationIssue(
                severity=Severity.WARNING,
                message="DataTypeTemplates 中无 LNodeType 定义",
                xpath="/SCL/DataTypeTemplates",
            ))
        return ValidationResult(issues)


class TypeReferenceIntegrityRule:
    """规则: 类型引用必须完整 (LNodeType→DOType→DAType/EnumType)"""
    
    def check(self, doc: SclDocument) -> ValidationResult:
        issues = []
        for ln_type in doc.data_type_templates.ln_types:
            for do in ln_type.do_list:
                if do.type and not doc.get_do_type(do.type):
                    issues.append(ValidationIssue(
                        severity=Severity.ERROR,
                        message=f"LNodeType '{ln_type.id}' 的 DO '{do.name}' "
                                f"引用了不存在的 DOType '{do.type}'",
                        xpath=f"/SCL/DataTypeTemplates/LNodeType[@id='{ln_type.id}']",
                        element_name=do.name,
                    ))
        return ValidationResult(issues)


class ControlBlockDataSetRule:
    """规则: GSEControl/ReportControl 的 datSet 必须引用存在的 DataSet"""
    
    def check(self, doc: SclDocument) -> ValidationResult:
        issues = []
        for ied_name, ld_inst, ds in doc.all_data_sets:
            pass  # 校验 DataSet 引用
        
        for ied in doc.ieds:
            for ap in ied.access_points:
                if not ap.server:
                    continue
                for ld in ap.server.logical_devices:
                    if not ld.ln0:
                        continue
                    # 收集当前 LD0 的所有 DataSet 名称
                    ds_names = {ds.name for ds in ld.ln0.data_sets}
                    # 校验 GSEControl
                    for gcb in ld.ln0.gse_controls:
                        if gcb.dat_set and gcb.dat_set not in ds_names:
                            issues.append(ValidationIssue(
                                severity=Severity.WARNING,
                                message=f"GSEControl '{gcb.name}' 引用了不存在的 "
                                        f"DataSet '{gcb.dat_set}'",
                                element_name=gcb.name,
                            ))
                    # 校验 ReportControl
                    for rcb in ld.ln0.report_controls:
                        if rcb.dat_set and rcb.dat_set not in ds_names:
                            issues.append(ValidationIssue(
                                severity=Severity.WARNING,
                                message=f"ReportControl '{rcb.name}' 引用了不存在的 "
                                        f"DataSet '{rcb.dat_set}'",
                                element_name=rcb.name,
                            ))
        return ValidationResult(issues)


def create_default_rule_registry() -> ValidationRuleRegistry:
    """创建默认校验规则注册表"""
    from .rules import ValidationRuleRegistry
    registry = ValidationRuleRegistry()
    registry.register("ied_existence", IedExistenceRule())
    registry.register("data_type_templates", DataTypeTemplatesRule())
    registry.register("type_reference_integrity", TypeReferenceIntegrityRule())
    registry.register("control_block_dataset", ControlBlockDataSetRule())
    return registry
```

---

## 5. 转换器设计

### 5.1 Transformer Protocol (Strategy 模式)

```python
# transformer/protocols.py
from __future__ import annotations

from typing import Protocol, TypeVar, Generic, Any

from ..model.scl_document import SclDocument


T = TypeVar("T")


class SclTransformerProtocol(Protocol, Generic[T]):
    """SCL 模型转换器协议
    
    将 SclDocument 转换为目标数据结构 T。
    不同转换器实现此协议，支持策略模式替换。
    """
    def transform(self, doc: SclDocument, **kwargs) -> T: ...
```

### 5.2 转换器基类 (Template Method)

```python
# transformer/base.py
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from ..model.scl_document import SclDocument
from ..model.ied import SclIED
from ..model.logical_device import SclLogicalDevice, SclLN0, SclLN
from ..parser.type_resolver import TypeResolver

T = TypeVar("T")


class SclTransformerBase(ABC, Generic[T]):
    """SCL 转换器基类
    
    Template Method 模式:
    - transform() 定义转换骨架
    - _transform_ied/ld/ln 为钩子方法，子类可选择性覆盖
    """
    
    def transform(self, doc: SclDocument, **kwargs) -> T:
        """模板方法: 定义转换流程骨架"""
        self._resolver = TypeResolver(doc)
        return self._do_transform(doc, **kwargs)
    
    @abstractmethod
    def _do_transform(self, doc: SclDocument, **kwargs) -> T:
        """子类实现具体转换逻辑"""
        ...
    
    def _iter_all_lns(self, doc: SclDocument):
        """遍历所有 LN0/LN (Generator 模式，惰性遍历)"""
        for ied in doc.ieds:
            for ap in ied.access_points:
                if not ap.server:
                    continue
                for ld in ap.server.logical_devices:
                    if ld.ln0:
                        yield ied, ld, "LLN0", ld.ln0
                    for ln in ld.logical_nodes:
                        yield ied, ld, ln.ln_name, ln
```

### 5.3 测点转换器

```python
# transformer/point_transformer.py
"""SCL → 测点数据转换器

替代原 IcdPointImporter 的核心解析逻辑。
设计模式: Strategy (符合 SclTransformerProtocol) + Template Method
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..model.scl_document import SclDocument
from ..model.data_type import SclDOType, SclDA
from ..model.enums import CDC_CATEGORY_MAP, PointCategory
from .base import SclTransformerBase


@dataclass(slots=True, frozen=True)
class PointData:
    """不可变测点数据"""
    code: str
    name: str
    reg_addr: str          # 完整引用路径
    cdc: str
    da_name: str           # DA 路径
    fc: str
    frame_type: int        # 0=遥测 1=遥信 2=遥控 3=遥调
    ied_name: str = ""
    ld_inst: str = ""


@dataclass
class PointTransformResult:
    """测点转换结果"""
    yc: List[PointData] = field(default_factory=list)
    yx: List[PointData] = field(default_factory=list)
    yk: List[PointData] = field(default_factory=list)
    yt: List[PointData] = field(default_factory=list)
    
    @property
    def total(self) -> int:
        return len(self.yc) + len(self.yx) + len(self.yk) + len(self.yt)
    
    def to_dict(self) -> Dict[str, List[PointData]]:
        return {"yc": self.yc, "yx": self.yx, "yk": self.yk, "yt": self.yt}


class SclPointTransformer(SclTransformerBase[PointTransformResult]):
    """SCL 测点转换器
    
    从 SclDocument 提取测点信息。
    优势: 解析与转换解耦，同一 SclDocument 可用于多种转换。
    """
    
    # 主值 DA 路径映射 (CDC → 默认值 DA 路径)
    _CDC_VALUE_DA: dict[str, tuple[str, str]] = {
        "MV": ("mag.f", "MX"),
        "CMV": ("cVal.mag.f", "MX"),
        "SAV": ("instMag.f", "MX"),
        "SPS": ("stVal", "ST"),
        "DPS": ("stVal", "ST"),
        "INS": ("stVal", "ST"),
        "ENS": ("stVal", "ST"),
        "SPC": ("Oper.ctlVal", "CO"),
        "DPC": ("Oper.ctlVal", "CO"),
        "APC": ("Oper.ctlVal", "CO"),
        "INC": ("Oper.ctlVal", "CO"),
    }
    
    def _do_transform(self, doc: SclDocument, *,
                      include_metadata: bool = True,
                      cdc_filter: set[str] | None = None,
                      ) -> PointTransformResult:
        result = PointTransformResult()
        
        for ied, ld, ln_name, ln_elem in self._iter_all_lns(doc):
            ln_type = self._resolver.resolve_ln_type(ln_elem)
            if not ln_type:
                continue
            
            for do in ln_type.do_list:
                do_type = self._resolver.resolve_do_type(do.type)
                if not do_type:
                    continue
                
                cdc = do_type.cdc
                if cdc_filter and cdc not in cdc_filter:
                    continue
                
                category = CDC_CATEGORY_MAP.get(cdc)
                if not category:
                    continue
                
                self._transform_do(
                    doc, ied.name, ld.inst, ln_name, do.name, do_type,
                    category, result, include_metadata,
                )
        
        return result
    
    def _transform_do(self, doc, ied_name, ld_inst, ln_name,
                      do_name, do_type, category, result, include_metadata):
        """转换单个 DO 为测点数据"""
        value_da_path, fc = self._CDC_VALUE_DA.get(
            do_type.cdc, ("", do_type.da_list[0].fc if do_type.da_list else "")
        )
        
        ref = f"{ld_inst}/{ln_name}.{do_name}"
        point = PointData(
            code=do_name,
            name=do_name,
            reg_addr=f"{ref}.{value_da_path}" if value_da_path else ref,
            cdc=do_type.cdc,
            da_name=value_da_path,
            fc=fc,
            frame_type=category.value - 1,  # PointCategory.YC=1 → frame_type=0
            ied_name=ied_name,
            ld_inst=ld_inst,
        )
        
        match category:
            case PointCategory.YC:
                result.yc.append(point)
            case PointCategory.YX:
                result.yx.append(point)
            case PointCategory.YK:
                result.yk.append(point)
            case PointCategory.YT:
                result.yt.append(point)
```

### 5.4 GOOSE 转换器

```python
# transformer/goose_transformer.py
"""SCL → GOOSE 配置转换器

替代原 IcdGooseImporter 的核心解析逻辑。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from ..model.scl_document import SclDocument
from .base import SclTransformerBase


@dataclass
class GooseTransformResult:
    """GOOSE 转换结果"""
    publishers: List[Dict[str, Any]] = field(default_factory=list)
    subscriptions: List[Dict[str, Any]] = field(default_factory=list)
    pure_datasets: List[Dict[str, Any]] = field(default_factory=list)
    
    @property
    def publisher_count(self) -> int:
        return len(self.publishers)
    
    @property
    def subscription_count(self) -> int:
        return len(self.subscriptions)


class SclGooseTransformer(SclTransformerBase[GooseTransformResult]):
    """SCL GOOSE 配置转换器"""
    
    def _do_transform(self, doc: SclDocument, *,
                      interface: str = "eth0",
                      ) -> GooseTransformResult:
        result = GooseTransformResult()
        
        # 构建 GSE 通信地址索引
        gse_address_index = self._build_gse_address_index(doc)
        
        # 遍历所有 GSEControl
        for ied in doc.ieds:
            for ap in ied.access_points:
                if not ap.server:
                    continue
                for ld in ap.server.logical_devices:
                    if not ld.ln0:
                        continue
                    
                    # DataSet 索引 (name → SclDataSet)
                    ds_index = {ds.name: ds for ds in ld.ln0.data_sets}
                    # 已被 GSEControl 引用的 DataSet 名称
                    referenced_ds = set()
                    
                    for gcb in ld.ln0.gse_controls:
                        referenced_ds.add(gcb.dat_set)
                        self._transform_gse_control(
                            doc, ied.name, ld, gcb, ds_index, gse_address_index,
                            interface, result,
                        )
                    
                    # 收集纯 DataSet (未被 GSEControl 引用)
                    for ds in ld.ln0.data_sets:
                        if ds.name not in referenced_ds:
                            result.pure_datasets.append(
                                self._build_pure_dataset_dict(ied.name, ld.inst, ds, doc)
                            )
        
        return result
    
    def _build_gse_address_index(self, doc: SclDocument) -> dict:
        """构建 GSE 通信地址索引: (ied_name, ld_inst, cb_name) → SclGSE"""
        index = {}
        if not doc.communication:
            return index
        for subnet in doc.communication.sub_networks:
            for cap in subnet.connected_aps:
                for gse in cap.gse_list:
                    key = (cap.ied_name, gse.ld_inst, gse.cb_name)
                    index[key] = gse
        return index
    
    # ... _transform_gse_control / _build_pure_dataset_dict 实现
```

---

## 6. 服务层设计

### 6.1 依赖注入 (DI) 模式

```python
# service/container.py
"""轻量级依赖容器

使用 Python dataclass + 默认参数实现依赖注入，
无需引入第三方 DI 框架。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..parser.scl_parser import SclParser
from ..parser.protocols import SclParserProtocol
from ..validator.rules import ValidationRuleRegistry
from ..validator.builtin_rules import create_default_rule_registry
from ..transformer.point_transformer import SclPointTransformer
from ..transformer.goose_transformer import SclGooseTransformer
from ..transformer.report_transformer import SclReportTransformer


@dataclass
class SclServiceContainer:
    """SCL 服务容器
    
    通过默认参数实现依赖注入:
    - 生产环境: 使用默认实现
    - 测试环境: 替换为 Mock 实现
    
    用法:
        # 生产环境
        container = SclServiceContainer()
        
        # 测试环境
        container = SclServiceContainer(parser=MockParser())
    """
    parser: SclParserProtocol = field(default_factory=SclParser)
    rule_registry: ValidationRuleRegistry = field(default_factory=create_default_rule_registry)
    point_transformer: SclPointTransformer = field(default_factory=SclPointTransformer)
    goose_transformer: SclGooseTransformer = field(default_factory=SclGooseTransformer)
    report_transformer: SclReportTransformer = field(default_factory=SclReportTransformer)
```

### 6.2 导入服务 (Facade)

```python
# service/import_service.py
"""SCL 导入服务 (Facade 模式)

编排完整导入流程: 解析 → 校验 → 转换 → 持久化
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from ..parser.scl_parser import SclParser, SclParserError
from ..model.scl_document import SclDocument
from ..validator.result import ValidationResult, EMPTY_VALIDATION_RESULT
from ..transformer.point_transformer import SclPointTransformer, PointTransformResult
from ..transformer.goose_transformer import SclGooseTransformer, GooseTransformResult
from ..transformer.report_transformer import SclReportTransformer
from .container import SclServiceContainer


@dataclass
class ImportOptions:
    """导入选项 (值对象模式)"""
    import_points: bool = True
    include_metadata_da: bool = True
    clear_existing: bool = True
    import_goose: bool = False
    goose_interface: str = "eth0"
    import_reports: bool = False
    validate_before_import: bool = True
    fail_on_validation_error: bool = False


@dataclass
class ImportResult:
    """导入结果"""
    success: bool = True
    file_type: str = ""
    validation: ValidationResult = field(default_factory=ValidationResult.empty)
    point_result: Optional[PointTransformResult] = None
    goose_result: Optional[GooseTransformResult] = None
    report_count: int = 0
    errors: List[str] = field(default_factory=list)
    
    @property
    def point_counts(self) -> Dict[str, int]:
        if not self.point_result:
            return {}
        return {
            "yc": len(self.point_result.yc),
            "yx": len(self.point_result.yx),
            "yk": len(self.point_result.yk),
            "yt": len(self.point_result.yt),
        }


class SclImportService:
    """SCL 导入服务 (Facade)
    
    编排: 解析 → 校验 → 转换 → 持久化
    通过 SclServiceContainer 注入依赖，便于测试。
    """
    
    def __init__(self, container: SclServiceContainer | None = None):
        self._container = container or SclServiceContainer()
    
    def import_file(self, file_path: str, channel_id: int,
                    options: ImportOptions | None = None) -> ImportResult:
        """完整导入流程"""
        options = options or ImportOptions()
        result = ImportResult()
        
        try:
            # 1. 解析
            doc = self._container.parser.parse_file(file_path)
            result.file_type = doc.file_type.value
            
            # 2. 校验
            if options.validate_before_import:
                result.validation = self._container.rule_registry.check_all(doc)
                if not result.validation.is_valid and options.fail_on_validation_error:
                    result.success = False
                    return result
            
            # 3. 转换
            if options.import_points:
                result.point_result = self._container.point_transformer.transform(
                    doc, include_metadata=options.include_metadata_da
                )
                self._save_points(channel_id, result.point_result, options.clear_existing)
            
            if options.import_goose:
                result.goose_result = self._container.goose_transformer.transform(
                    doc, interface=options.goose_interface
                )
            
            if options.import_reports:
                report_result = self._container.report_transformer.transform(doc)
                result.report_count = len(report_result)
            
        except SclParserError as e:
            result.success = False
            result.errors.append(str(e))
        except Exception as e:
            result.success = False
            result.errors.append(f"导入失败: {e}")
        
        return result
    
    def preview(self, file_path: str) -> Dict[str, Any]:
        """预览导入内容 (不执行持久化)"""
        doc = self._container.parser.parse_file(file_path)
        validation = self._container.rule_registry.check_all(doc)
        
        points = self._container.point_transformer.transform(doc)
        goose = self._container.goose_transformer.transform(doc)
        
        return {
            "file_type": doc.file_type.value,
            "ied_names": doc.ied_names,
            "validation": validation,
            "point_counts": points.to_dict() if points else {},
            "goose": goose,
        }
    
    def _save_points(self, channel_id: int, points: PointTransformResult,
                     clear_existing: bool) -> None:
        """持久化测点到数据库"""
        from src.data.controller.db import local_session
        from src.data.model.point_yc import PointYc
        from src.data.model.point_yx import PointYx
        from src.data.model.point_yk import PointYk
        from src.data.model.point_yt import PointYt
        
        with local_session() as session:
            with session.begin():
                if clear_existing:
                    session.query(PointYc).where(PointYc.channel_id == channel_id).delete()
                    session.query(PointYx).where(PointYx.channel_id == channel_id).delete()
                    session.query(PointYk).where(PointYk.channel_id == channel_id).delete()
                    session.query(PointYt).where(PointYt.channel_id == channel_id).delete()
                
                # 批量插入
                for point in points.yc:
                    session.add(PointYc(
                        channel_id=channel_id,
                        code=point.code,
                        name=point.name,
                        rtu_addr=point.reg_addr,
                        # ... 其他字段映射
                    ))
                # ... yx, yk, yt 类似
```

### 6.3 文件管理器

```python
# service/file_manager.py
"""SCL 文件管理器

使用 Context Manager 管理文件操作，
支持上传/存储/列表/删除。
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from ..parser.scl_parser import SclParser
from ..model.scl_document import SclDocument


@dataclass(slots=True)
class SclFileInfo:
    """SCL 文件信息 (不可变值对象)"""
    file_name: str
    file_path: str
    file_type: str           # "ICD" / "SCD" / "CID"
    file_size: int           # bytes
    upload_time: str         # ISO 格式
    ied_name: str = ""
    ied_count: int = 0
    ld_count: int = 0
    point_counts: dict[str, int] = field(default_factory=dict)


class SclFileManager:
    """SCL 文件管理器
    
    使用 Path 替代 os.path，使用 Context Manager 管理资源。
    """
    
    def __init__(self, base_dir: str | Path = "data/61850icd"):
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._parser = SclParser()
    
    def upload(self, file_name: str, file_content: bytes) -> SclFileInfo:
        """上传 SCL 文件"""
        file_path = self._base_dir / file_name
        file_path.write_bytes(file_content)
        
        # 解析获取摘要信息
        doc = self._parser.parse_file(str(file_path))
        
        return SclFileInfo(
            file_name=file_name,
            file_path=str(file_path),
            file_type=doc.file_type.value,
            file_size=len(file_content),
            upload_time=datetime.now(timezone.utc).isoformat(),
            ied_name=doc.ied_names[0] if doc.ied_names else "",
            ied_count=len(doc.ieds),
            ld_count=sum(len(t[1]) for t in doc.all_logical_devices),
        )
    
    def list_files(self) -> List[SclFileInfo]:
        """列出所有已上传的 SCL 文件"""
        result = []
        for path in self._base_dir.glob("*.icd"):
            result.append(self._build_file_info(path))
        for path in self._base_dir.glob("*.scd"):
            result.append(self._build_file_info(path))
        for path in self._base_dir.glob("*.cid"):
            result.append(self._build_file_info(path))
        return result
    
    def get_file_content(self, file_name: str) -> str | None:
        """获取文件内容 (原始 XML)"""
        file_path = self._base_dir / file_name
        if file_path.exists():
            return file_path.read_text(encoding="utf-8")
        return None
    
    def delete(self, file_name: str) -> bool:
        """删除文件"""
        file_path = self._base_dir / file_name
        if file_path.exists():
            file_path.unlink()
            return True
        return False
    
    def _build_file_info(self, path: Path) -> SclFileInfo:
        """从文件路径构建 SclFileInfo"""
        stat = path.stat()
        try:
            doc = self._parser.parse_file(str(path))
            return SclFileInfo(
                file_name=path.name,
                file_path=str(path),
                file_type=doc.file_type.value,
                file_size=stat.st_size,
                upload_time=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                ied_name=doc.ied_names[0] if doc.ied_names else "",
                ied_count=len(doc.ieds),
            )
        except Exception:
            return SclFileInfo(
                file_name=path.name,
                file_path=str(path),
                file_type="UNKNOWN",
                file_size=stat.st_size,
                upload_time=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            )
```

---

## 7. 与现有代码的集成策略

### 7.1 迁移路径

```
阶段 1: 新模块并行存在
┌──────────────────────┐     ┌──────────────────────┐
│  IcdPointImporter    │     │  SclParser           │
│  (旧，不修改)         │     │  SclPointTransformer │
│                      │     │  (新，独立运行)        │
└──────────────────────┘     └──────────────────────┘

阶段 2: 旧模块改为薄封装
┌──────────────────────┐     ┌──────────────────────┐
│  IcdPointImporter    │────▶│  SclParser           │
│  (薄封装，委托)       │     │  SclPointTransformer │
└──────────────────────┘     └──────────────────────┘

阶段 3: 旧模块废弃
┌──────────────────────┐
│  SclImportService    │  ← 统一入口
│  SclParser           │
│  SclPointTransformer │
└──────────────────────┘
```

### 7.2 旧模块薄封装 (Phase 6)

```python
# src/tools/icd_point_importer.py (迁移后)
"""ICD 文件解析导入模块 (薄封装)

内部委托给 SclParser + SclPointTransformer，
保持原有公共接口不变 (向后兼容)。
"""
from src.proto.iec61850.plugins.scl.parser.scl_parser import SclParser
from src.proto.iec61850.plugins.scl.transformer.point_transformer import SclPointTransformer


class IcdPointImporter:
    """ICD 文件解析导入器 (向后兼容薄封装)"""
    
    def __init__(self, channel_id: int):
        self.channel_id = channel_id
        self._parser = SclParser()
        self._transformer = SclPointTransformer()
        self._ied_name: str | None = None
    
    def import_from_icd(self, icd_path: str) -> tuple[int, int, int, int]:
        """从 ICD 文件导入测点 (保持原接口签名)"""
        doc = self._parser.parse_file(icd_path)
        self._ied_name = doc.ieds[0].name if doc.ieds else None
        
        result = self._transformer.transform(doc)
        
        # 委托 SclImportService._save_points 持久化
        self._clear_existing_points()
        self._save_points(result)
        
        return len(result.yc), len(result.yx), len(result.yk), len(result.yt)
    
    def preview_from_icd(self, icd_path: str) -> tuple[int, int, int, int]:
        """预览 ICD 文件 (保持原接口签名)"""
        doc = self._parser.parse_file(icd_path)
        self._ied_name = doc.ieds[0].name if doc.ieds else None
        result = self._transformer.transform(doc)
        return len(result.yc), len(result.yx), len(result.yk), len(result.yt)
    
    def get_ied_name(self) -> str | None:
        return self._ied_name
    
    # _clear_existing_points / _save_points 保持不变
```

### 7.3 Web API 集成

```python
# src/web/api/channel/import_points.py (修改后)
# 在 import_icd 中使用 SclImportService

@router.post("/import-icd", response_model=BaseResponse)
async def import_icd(request: Request, ...):
    """导入 ICD 文件 - 内部改用 SclImportService"""
    from src.proto.iec61850.plugins.scl.service.import_service import (
        SclImportService, ImportOptions,
    )
    
    service = SclImportService()
    options = ImportOptions(
        import_points=True,
        import_goose=True,
        goose_interface=interface,
        import_reports=True,
    )
    
    result = service.import_file(tmp_path, channel_id, options)
    # ... 后续处理不变
```

---

## 8. 分阶段实施计划

### Phase 1: SCL 对象模型与解析引擎 (3 天) [P0]

| # | 任务 | 文件 | 验收标准 |
|---|------|------|----------|
| 1.1 | 创建 `scl/` 模块结构 | `src/proto/iec61850/plugins/scl/__init__.py` | 子包可导入 |
| 1.2 | 实现 `model/enums.py` | `model/enums.py` | `CDC_CATEGORY_MAP` 覆盖所有 CDC |
| 1.3 | 实现 `model/scl_base.py` | `model/scl_base.py` | `SclElement` 可实例化 |
| 1.4 | 实现 `model/` 全部模型类 | `model/*.py` | 所有 dataclass 定义完成 |
| 1.5 | 实现 `parser/namespace.py` | `parser/namespace.py` | 有/无命名空间均可处理 |
| 1.6 | 实现 `parser/scl_parser.py` | `parser/scl_parser.py` | 解析 KG_BAMS.icd 成功 |
| 1.7 | 实现 `parser/type_resolver.py` | `parser/type_resolver.py` | 类型引用可解析 |
| 1.8 | 编写单元测试 | `tests/test_scl_parser.py` | 解析结果与现有 Importer 一致 |

**关键约束:**
- `model/` 不依赖 `pyiec61850`、FastAPI、SQLAlchemy
- `parser/` 仅依赖 `xml.etree.ElementTree` + `model/`
- 使用 `from __future__ import annotations` 支持 Python 3.10+ 类型语法

### Phase 2: 校验引擎与模型转换器 (3 天) [P0]

| # | 任务 | 文件 | 验收标准 |
|---|------|------|----------|
| 2.1 | 实现 `validator/result.py` | `validator/result.py` | `ValidationResult` 可合并 |
| 2.2 | 实现 `validator/rules.py` | `validator/rules.py` | Protocol + Registry 可用 |
| 2.3 | 实现 4 个内置校验规则 | `validator/builtin_rules.py` | 可检测引用缺失等错误 |
| 2.4 | 实现 `transformer/base.py` | `transformer/base.py` | 模板方法可扩展 |
| 2.5 | 实现 `transformer/point_transformer.py` | `transformer/point_transformer.py` | 输出与 `IcdPointImporter` 一致 |
| 2.6 | 实现 `transformer/goose_transformer.py` | `transformer/goose_transformer.py` | 输出与 `IcdGooseImporter` 一致 |
| 2.7 | 实现 `transformer/report_transformer.py` | `transformer/report_transformer.py` | ReportControl 正确提取 |
| 2.8 | 对比验证测试 | `tests/test_scl_transformers.py` | 与旧 Importer 结果一致 |

### Phase 3: 文件管理与导入服务 (2 天) [P0]

| # | 任务 | 文件 | 验收标准 |
|---|------|------|----------|
| 3.1 | 实现 `service/container.py` | `service/container.py` | DI 容器可注入 Mock |
| 3.2 | 实现 `service/file_manager.py` | `service/file_manager.py` | 上传/列表/删除正常 |
| 3.3 | 实现 `service/import_service.py` | `service/import_service.py` | 完整导入流程正常 |
| 3.4 | 修改 `import_points.py` | `src/web/api/channel/import_points.py` | 现有接口行为不变 |

### Phase 4: 后端 Web API (2 天) [P0]

| # | 任务 | 文件 | 验收标准 |
|---|------|------|----------|
| 4.1 | 创建 Pydantic Schema | `src/web/api/schemas/scl.py` | 请求/响应模型定义 |
| 4.2 | 实现文件管理路由 | `src/web/api/scl/router.py` | CRUD + 上传/下载/删除 |
| 4.3 | 实现预览浏览路由 | `src/web/api/scl/preview.py` | 树形结构/校验/预览 |
| 4.4 | 实现导入路由 | `src/web/api/scl/import_wizard.py` | 导入/提取端点 |
| 4.5 | 实现文件对比路由 | `src/web/api/scl/diff.py` | Diff API |
| 4.6 | 注册路由 | `src/web/app.py` | `scl_router` 挂载 |

### Phase 5: 前端 UI (3 天) [P1]

| # | 任务 | 文件 | 验收标准 |
|---|------|------|----------|
| 5.1 | 创建 `sclApi.ts` | `front/src/api/sclApi.ts` | API 封装完成 |
| 5.2 | 创建 `SclFileManager.vue` | `front/src/components/scl/SclFileManager.vue` | 文件管理主界面 |
| 5.3 | 创建 `SclImportWizard.vue` | `front/src/components/scl/SclImportWizard.vue` | 导入向导 |
| 5.4 | 创建 `SclXmlViewer.vue` | `front/src/components/scl/SclXmlViewer.vue` | XML 查看 |
| 5.5 | 创建 `SclDiffViewer.vue` | `front/src/components/scl/SclDiffViewer.vue` | 文件对比 |
| 5.6 | 创建 `SclView.vue` + 路由 | `front/src/views/SclView.vue` | 页面可访问 |
| 5.7 | 注册导航与 i18n | `router/index.ts`, `zh-CN.ts`, `en-US.ts` | 侧边栏集成 |

### Phase 6: 迁移与增强 (2 天) [P2]

| # | 任务 | 文件 | 验收标准 |
|---|------|------|----------|
| 6.1 | 迁移 `IcdPointImporter` | `src/tools/icd_point_importer.py` | 接口不变，内部委托 SclParser |
| 6.2 | 迁移 `IcdGooseImporter` | `src/tools/icd_goose_importer.py` | 接口不变，内部委托 SclParser |
| 6.3 | 增强 `FilesPlugin` | `src/proto/iec61850/plugins/files/` | 文件列表可用 |
| 6.4 | 实现 `server_model_builder` | `transformer/server_model_builder.py` | SclDocument → IedModel |
| 6.5 | SCD 合并基础支持 | `service/merge_service.py` | 多 ICD 合并为 SCD |

---

## 9. 测试策略

### 9.1 测试金字塔

```
         ┌──────────────┐
         │   E2E 测试    │  import_service 完整流程
         │   (少量)      │  → 上传 → 解析 → 校验 → 导入
         ├──────────────┤
         │  集成测试     │  parser + transformer 组合
         │  (适量)       │  → KG_BAMS.icd 全流程
         ├──────────────┤
         │  单元测试     │  每个 dataclass / parser method
         │  (大量)       │  → 校验规则 / DA 路径推断
         └──────────────┘
```

### 9.2 关键测试用例

```python
# tests/test_scl_parser.py
class TestSclParser:
    """解析器测试"""
    
    def test_parse_kg_bams_icd(self):
        """解析 KG_BAMS.icd 成功"""
        parser = SclParser()
        doc = parser.parse_file("data/61850icd/KG_BAMS.icd")
        assert doc.file_type == SclFileType.ICD
        assert len(doc.ieds) >= 1
        assert doc._index_built is True
    
    def test_namespace_compatibility(self):
        """有/无命名空间均可解析"""
        # 无命名空间
        doc1 = SclParser().parse_string('<SCL><IED name="T1"/></SCL>')
        assert doc1.ieds[0].name == "T1"
        # 有命名空间
        doc2 = SclParser().parse_string(
            '<SCL xmlns="http://www.iec.ch/61850/2003/SCL"><IED name="T2"/></SCL>'
        )
        assert doc2.ieds[0].name == "T2"
    
    def test_result_consistency_with_icd_point_importer(self):
        """解析结果与 IcdPointImporter 一致"""
        parser = SclParser()
        doc = parser.parse_file("data/61850icd/KG_BAMS.icd")
        
        transformer = SclPointTransformer()
        new_result = transformer.transform(doc)
        
        # 使用旧 Importer 对比
        from src.tools.icd_point_importer import IcdPointImporter
        old_importer = IcdPointImporter(channel_id=0)
        old_counts = old_importer.preview_from_icd("data/61850icd/KG_BAMS.icd")
        
        assert len(new_result.yc) == old_counts[0]
        assert len(new_result.yx) == old_counts[1]
        assert len(new_result.yk) == old_counts[2]
        assert len(new_result.yt) == old_counts[3]


# tests/test_scl_validator.py
class TestSclValidator:
    def test_empty_ied_error(self):
        """无 IED 时应报 ERROR"""
        doc = SclDocument()
        result = IedExistenceRule().check(doc)
        assert not result.is_valid
    
    def test_type_reference_integrity(self):
        """类型引用不完整时报错"""
        # 构造缺失 DOType 引用的 doc
        ...


# tests/test_scl_transformers.py
class TestPointTransformer:
    def test_cdc_category_mapping(self):
        """CDC → 测点分类正确"""
        assert CDC_CATEGORY_MAP["MV"] == PointCategory.YC
        assert CDC_CATEGORY_MAP["SPS"] == PointCategory.YX
        assert CDC_CATEGORY_MAP["SPC"] == PointCategory.YK
        assert CDC_CATEGORY_MAP["APC"] == PointCategory.YT
```

---

## 10. 性能考量

### 10.1 大型 SCL 文件优化 (>5MB)

```python
# 未来优化: 流式解析 (Phase 6)
# parser/streaming_parser.py

class SclStreamingParser:
    """流式 SCL 解析器 (SAX 风格)
    
    使用 xml.etree.ElementTree.iterparse 实现:
    - 增量解析，不一次性加载整个 XML 到内存
    - 解析完一个 IED 后立即返回
    - 适合 >5MB 的 SCD 文件
    """
    
    def parse_file_lazy(self, file_path: str):
        """惰性解析，yield 每个 IED"""
        for event, elem in ET.iterparse(file_path, events=["end"]):
            if elem.tag.endswith("}IED") or elem.tag == "IED":
                yield self._parse_ied(elem)
                elem.clear()  # 释放内存
```

### 10.2 类型索引缓存

```python
# SclDocument.build_type_index() 使用字典推导式
# O(n) 构建，O(1) 查找，无需 LRU Cache
def build_type_index(self) -> None:
    self._ln_type_index = {t.id: t for t in self.data_type_templates.ln_types}
    # ... 其他类型索引
```

---

## 11. 模块依赖关系图

```
src/proto/iec61850/plugins/scl/
│
├── model/                     ← 纯数据类，无外部依赖
│   ├── enums.py               (CDC, FC, PointCategory)
│   ├── scl_base.py            (SclElement)
│   ├── scl_document.py        (SclDocument, SclDataTypeTemplates)
│   ├── ied.py                 (SclIED, SclAccessPoint, SclServer)
│   ├── logical_device.py      (SclLDevice, SclLN0, SclLN)
│   ├── data_object.py         (SclDOI, SclDAI, SclSDI)
│   ├── data_type.py           (SclLNodeType, SclDOType, SclDAType, ...)
│   ├── dataset.py             (SclDataSet, SclFCDA)
│   ├── control_block.py       (SclGSEControl, SclReportControl, ...)
│   └── communication.py       (SclCommunication, SclSubNetwork, ...)
│
├── parser/                    ← 依赖 model/ + xml.etree
│   ├── protocols.py           (SclParserProtocol)
│   ├── namespace.py           (NamespaceHelper)
│   ├── scl_parser.py          (SclParser)
│   └── type_resolver.py       (TypeResolver)
│
├── validator/                 ← 依赖 model/
│   ├── result.py              (ValidationResult, ValidationIssue)
│   ├── rules.py               (ValidationRule Protocol + Registry)
│   └── builtin_rules.py       (内置校验规则)
│
├── transformer/               ← 依赖 model/ + parser/
│   ├── protocols.py           (SclTransformerProtocol)
│   ├── base.py                (SclTransformerBase)
│   ├── point_transformer.py   (SclPointTransformer)
│   ├── goose_transformer.py   (SclGooseTransformer)
│   ├── report_transformer.py  (SclReportTransformer)
│   └── server_model_builder.py (Phase 6)
│
└── service/                   ← 依赖以上所有 + 可选 DB
    ├── container.py           (SclServiceContainer - DI)
    ├── file_manager.py        (SclFileManager)
    ├── import_service.py      (SclImportService - Facade)
    └── diff_service.py        (SclDiffService)
```

**依赖规则:**
- `model/` 是最底层，无外部依赖
- `parser/` 仅依赖 `model/` 和标准库
- `validator/` 仅依赖 `model/`
- `transformer/` 依赖 `model/` + `parser/` (TypeResolver)
- `service/` 依赖所有子模块，但 DB 操作通过延迟导入

---

## 12. 风险缓解补充

| 风险 | 缓解措施 |
|------|----------|
| SCL 格式差异大 | `NamespaceHelper` 兼容两种格式；`SclParser` 对缺失属性使用默认值 |
| 与现有 Importer 行为不一致 | Phase 2 对比验证 + 持续集成回归测试 |
| 大型 SCL 文件性能 | `slots=True` 减少内存；Phase 6 引入 `iterparse` 流式解析 |
| 前端 XML 查看器性能 | 虚拟滚动 + 限制高亮渲染行数 |
| 循环依赖 | 严格分层: model → parser → transformer → service；`from __future__ import annotations` |
