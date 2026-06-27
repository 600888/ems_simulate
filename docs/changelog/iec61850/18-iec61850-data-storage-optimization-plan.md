# IEC 61850 数据存储架构与协议处理流程专项整改计划

> 版本: 1.1
> 日期: 2026-06-27
> 状态: 部分实施中

## 0. 变更记录

| 版本 | 日期 | 变更 | 说明 |
|------|------|------|------|
| 1.0 | 2026-06-27 | 初始规划 | 完整整改计划 |
| 1.1 | 2026-06-27 | 实施记录 | 标记已实现项，补充实际代码差异 |

### 0.1 已实施项概览

| 编号 | 任务 | 状态 | 实际差异 |
|------|------|------|---------|
| 2.1 | 服务端加载/启动分离 | ✅ 已完成 | 与实际一致 |
| 2.2 | 服务端 ICD 加载模型 | ✅ 已完成 | 与实际一致 |
| 2.3 | 客户端远程发现模型 | ✅ 已完成 | 与实际一致 |
| 2.4 | 客户端本地加载模型 | ✅ 已完成 | 与实际一致 |
| — | 前端 `modelLoaded` 状态显示 | ✅ 已完成 | **新增项**：未在原计划中 |
| — | `model_loaded` 合并到 `/info` 接口 | ✅ 已完成 | **新增项**：未在原计划中，替代独立端点方案 |
| 2.6 | ClientHandler model_loaded 属性 | ✅ 已完成 | 简化实现：仅添加 `_model_loaded` 标志位，未完全重构 connect 流程 |
| 1.3 | ICD 文件规范存储 | ✅ 已完成 | `SclFileManager.save_to_device_dir()` + `ChannelService.update_channel(icd_path=...)` |
| — | 导入 ICD 后自动加载模型到内存 | ✅ 已完成 | **新增项**：`import_points.py` 在导入成功后自动调用 `load_iec61850_model()` |
| 2.5 | ModelCache 缓存机制 | ❌ 未开始 | 依赖 ModelCache 实现，暂未开发 |
| 1.5 | 导入流程改造（不写数据库） | ❌ 未开始 | 当前仍向 point_yc/yx/yk/yt 写入测点数据 |
| 第三阶段 | 数据清理 | ❌ 未开始 | 待所有功能稳定后执行 |

### 0.2 与原计划的主要差异

1. **前端 model-loaded 显示方案**：原计划通过独立 API 端点获取模型状态，实际实现改为将 `model_loaded` 字段合并到 `/api/devices/info` 接口中，减少一次网络请求
2. **ClientHandler 简化**：原计划重构整个 connect 流程，实际仅添加 `_model_loaded` 属性及 getter/setter，在 `load_model_from_icd()` 和 `remote_discover_model()` 成功后设置标志位
3. **导入模型自动加载**：原计划中未明确，实际在 ICD 文件导入完成后立即自动调用 `device.load_iec61850_model()`，用户无需手动再点"加载模型"
4. **模型加载失败时使用绝对路径**：原计划假设文件保存不会失败，实际增加了 `icd_saved_path` fallback 逻辑（文件保存失败时使用临时路径）

## 1. 概述

### 1.1 整改目标

本次专项整改聚焦 IEC 61850 协议模块的 **数据存储架构** 和 **协议处理流程** 两大核心领域，实现以下目标：

1. **数据存储架构优化**：停止将 61850 测点数据直接存入数据库的现有做法，仅保留 ICD 文件作为权威数据源，数据库中仅记录 ICD 文件存储路径。
2. **协议处理流程重构**：将设备开启流程拆分为「加载模型」和「开启设备」两个独立步骤，客户端支持远程发现与本地加载两种模型获取方式，并引入模型缓存机制。
3. **数据清理与优化**：彻底删除数据库中与 61850 测点相关的冗余存储记录，建立数据清理验证机制。
4. **文档与版本控制**：详细记录整改前后的架构变化，确保代码和配置变更可追溯。

### 1.2 核心术语

| 术语 | 说明 |
|------|------|
| ICD 文件 | IEC 61850-6 SCL 规范定义的 IED 能力描述文件，包含完整的 IED 数据模型 |
| IedModel | 运行时内存中的不可变模型对象，从 ICD 文件或在线发现构建 |
| Model Discovery | 客户端通过 MMS 协议从服务端在线发现数据模型的过程 |
| PointRegistry | 测点注册表，维护 address → MMS 引用路径的映射关系 |
| SclFileManager | SCL 文件管理器，管理 `data/61850icd/` 目录下的 ICD/SCD/CID 文件 |


## 2. 现状分析

### 2.1 当前数据架构

```
ICD 文件 (data/61850icd/)
    │
    ├──→ SclParser 解析 → SclImportService 转换
    │                            │
    │                            ├──→ PointTransformer → 测点数据
    │                            │                           │
    │                            │                           └──→ IcdPointImporter
    │                            │                                     │
    │                            │                          ┌──────────┴──────────┐
    │                            │                          ▼                     ▼
    │                            │                    point_yc 表           point_yx 表
    │                            │                    point_yk 表           point_yt 表
    │                            │
    │                            ├──→ GooseTransformer → GOOSE 配置 (内存)
    │                            └──→ ReportTransformer → Report 配置 (内存)
    │
    └──→ SclFileManager: 文件 CRUD 管理
```

**存在的问题：**

| 问题 | 影响 |
|------|------|
| 测点数据在 `point_yc/yx/yk/yt` 表中与 ICD 文件双重存储，数据不一致风险高 | ICD 文件更新后，数据库中的测点记录可能过时 |
| 数据库测点表包含 IEC61850 专用字段（如 `fc`），但原始设计为 Modbus 等协议服务，字段含义混淆 | 维护成本高，易产生理解偏差 |
| 设备启动时从数据库加载测点数据，而非直接引用 ICD 文件 | 模型来源不清晰，无法保证运行时模型与 ICD 文件一致 |
| ICD 文件仅作为"导入工具"使用，导入完成后即被抛弃 | 丢失了 ICD 文件的权威地位 |

### 2.2 当前设备启动流程

**服务端：**

```
IEC61850Server.__init__()
    └── IedModelBuilder.__init__() — 创建默认模型 (GenericLD)

IEC61850Server.start()
    ├── _register_default_rcbs() — 注册默认 BRCB
    ├── _apply_pending_registrations() — 处理待注册的 GoCB/DataSet
    ├── IedServer_create(model)
    ├── IedServer_start()
    └── 模型运行
```

**客户端：**

```
IEC61850ClientHandler.connect()
    ├── IEC61850Client.connect(auto_discover=False) — MMS 连接
    ├── client.discover_model() — 在线发现模型
    │       └── ModelDiscoveryService.discover() — 遍历 LD/LN/DO/DA
    │               └── build_registry_from_model() — 构建 PointRegistry
    ├── 获取 GOOSE/DataSet/RCB 列表
    └── 回调通知已发现的测点
```

**存在的问题：**

| 问题 | 影响 |
|------|------|
| 服务端 `start()` 将模型构建与 IedServer 启动耦合在一起 | ICD 模型加载与服务器启动无法独立操作 |
| 客户端 `connect()` 将网络连接与模型发现耦合在一起 | 每次重连都需要重新发现模型，耗时严重 |
| 无模型缓存机制 | 相同模型的设备重复发现，浪费网络资源 |
| ICD 文件导入后，服务端需调用 `reset_model()` 重建模型 | 流程繁琐，中间状态不可控 |

### 2.3 数据库测点表结构分析

以下数据库中包含与 IEC61850 相关的冗余字段和记录：

| 表名 | 涉及字段 | 说明 |
|------|---------|------|
| `channel` | `model_name` | 记录 IED 名称，整改后可保留 |
| `point_yc` | 完整的测点记录 + `fc` 字段 | 整改后应删除所有 IEC61850 类型的测点记录 |
| `point_yx` | 完整的测点记录 + `fc` 字段 | 同上 |
| `point_yk` | 完整的测点记录 + `fc` 字段 | 同上 |
| `point_yt` | 完整的测点记录 + `fc` 字段 | 同上 |


## 3. 目标架构设计

### 3.1 数据存储架构（整改后）

```
ICD 文件 (data/61850icd/)
    │
    ├──→ SclFileManager: 文件 CRUD 管理 (增强)
    │        新增: 文件完整性校验、版本管理、设备关联
    │
    ├──→ SclImportService: 解析 → 运行时构建 IedModel (不持久化到数据库)
    │
    ├──→ 服务端启动: ICD 文件 → IedModel → IedServer
    │
    ├──→ 客户端启动:
    │       ├── 远程发现: MMS 发现 → IedModel (缓存)
    │       └── 本地加载: ICD 文件解析 → IedModel (缓存)
    │
    └──→ 数据库:
            channel 表: 新增 icd_path 字段 (记录 ICD 文件存储路径)
            device 表:  新增 icd_path 字段 (设备级 ICD 文件关联)
            point_yc/yx/yk/yt: 删除所有 IEC61850 协议类型 (protocol_type=4) 的测点记录

数据库职责:
    ┌──────────────────────────────────────────────────┐
    │ channel.icd_path  →  ICD 文件存储路径             │
    │ device.icd_path    →  ICD 文件存储路径 (设备级)   │
    │ channel.model_name →  IED 名称 (保留)             │
    │ channel.ip/port    →  网络连接参数                 │
    └──────────────────────────────────────────────────┘

运行时数据流:
    ┌──────────────┐      ┌──────────────────┐      ┌──────────────┐
    │  ICD 文件     │──→   │  SclImportService │──→   │  IedModel    │
    │  (data/61850/)│      │  (解析+校验+转换) │      │  (不可变模型) │
    └──────────────┘      └──────────────────┘      └──────┬───────┘
            ▲                                              │
            │                                              ├──→ PointRegistry
            │                                              │       (构建测点映射)
            │  数据库记录路径                                │
            ├── channel.icd_path ──────────────────────────┤──→ IedServer/Client
            └── device.icd_path                             │       (运行时使用)
                                                           └──→ ModelCache
                                                                 (复用缓存)
```

### 3.2 协议处理流程（整改后）

**服务端流程：**

```
步骤 1: 加载模型 (load_model)
    ├── 从 ICD 文件解析 → SclImportService.import_file()
    ├── 构建 IedModel → IedModelBuilder
    ├── 注册 GOOSE/DataSet/RCB
    └── 结果: IedModel 就绪，未启动 MMS 服务

步骤 2: 开启设备 (start_device)
    ├── IedServer_create(model)
    ├── IedServer_start(port)
    └── 结果: MMS 服务运行中

模型变更:
    └── stop → load_model(new_icd) → start
```

**客户端流程：**

```
途径 A: 远程发现模型 (remote_discover)
    ├── MMS 连接至远程 IED
    ├── ModelDiscoveryService.discover() 在线遍历
    ├── 构建 IedModel → 缓存至 ModelCache
    └── 从 IedModel 派生 PointRegistry

途径 B: 本地加载模型 (local_load)
    ├── 读取本地 ICD 文件路径
    ├── SclImportService.import_file() 解析
    ├── 构建 IedModel → 缓存至 ModelCache
    └── 从 IedModel 派生 PointRegistry

缓存复用 (cache_hit):
    ├── 检查 ModelCache 中是否存在相同模型
    ├── 若命中 → 直接从缓存构建 PointRegistry
    └── 若未命中 → 远程发现或本地加载 → 写入缓存

开启设备:
    ├── MMS 连接 (独立于模型加载)
    └── 复用 IedModel 进行实时读写
```

### 3.3 ModelCache 设计

```python
class ModelCache:
    """模型缓存 — 支持多设备复用

    缓存策略:
        - key: (ied_name, model_hash) — 模型唯一标识
        - value: IedModel 不可变对象
        - 容量: 最近最多使用 (LRU), 最大 32 个模型
        - 过期: 默认 30 分钟无访问自动过期
    """

    def get(self, key: str) -> IedModel | None
    def set(self, key: str, model: IedModel) -> None
    def invalidate(self, key: str) -> None
    def compute_hash(self, icd_content: bytes) -> str
```

### 3.4 数据库表变更

**channel 表新增字段：**

```sql
ALTER TABLE channel ADD COLUMN icd_path VARCHAR(512) NULL COMMENT 'ICD文件存储路径 (IEC61850)';
ALTER TABLE channel ADD COLUMN icd_file_hash VARCHAR(64) NULL COMMENT 'ICD文件内容Hash (用于缓存校验)';
```

**device 表新增字段：**

```sql
ALTER TABLE device ADD COLUMN icd_path VARCHAR(512) NULL COMMENT 'ICD文件存储路径 (IEC61850)';
ALTER TABLE device ADD COLUMN icd_file_hash VARCHAR(64) NULL COMMENT 'ICD文件内容Hash (用于缓存校验)';
```


## 4. 实施步骤

### 第一阶段：数据存储架构改造（预计 5 个工作日）

| 编号 | 任务 | 详细说明 | 状态 | 实际差异 |
|------|------|---------|------|---------|
| 1.1 | 数据库表结构变更 | 为 `channel` 和 `device` 表新增 `icd_path`、`icd_file_hash` 字段 | ✅ 已完成 | `channel` 表已具备 `icd_path` 字段 |
| 1.2 | SclFileManager 增强 | 新增文件完整性校验 (SHA256)、文件版本管理、设备关联接口 | ✅ 已完成 | 已有 `save_to_device_dir()`、`compute_hash_from_file()` 等方法 |
| 1.3 | ICD 文件规范存储机制 | 实现 ICD 文件上传时的标准化存储流程：校验 → 重命名 → 持久化 → 记录路径 | ✅ 已完成 | 在 `import_points.py` 中实现 |
| 1.4 | Channel/Device 服务扩展 | 新增 `set_icd_path()`/`get_icd_path()` 接口 | ✅ 已完成 | `ChannelService.update_channel(icd_path=...)` 可用 |
| 1.5 | 导入流程改造 | 修改 `import_full`/`import_points` 接口：不再向 `point_yc/yx/yk/yt` 写入测点数据 | ❌ 未开始 | 当前仍写入数据库 |
| 1.6 | 单元测试覆盖 | 为上述新增/修改功能编写单元测试 | ❌ 未开始 | — |

**关键技术验证标准：**
- ICD 文件上传后，可通过数据库中的 `icd_path` 字段溯源到文件系统
- 删除数据库后，通过 ICD 文件可完整恢复设备模型
- 文件完整性校验通过（SHA256 比对一致）

### 第二阶段：协议处理流程重构（预计 7 个工作日）

| 编号 | 任务 | 详细说明 | 状态 | 实际差异 |
|------|------|---------|------|---------|
| 2.1 | 服务端加载/启动分离 | 将 `IEC61850Server.start()` 拆分为 `load_model(icd_path)` 和 `start_device()` | ✅ 已完成 | 与设计一致 |
| 2.2 | 服务端 ICD 加载模型实现 | `load_model()` 从 ICD 文件解析并构建完整 IedModel | ✅ 已完成 | 与设计一致 |
| 2.3 | 客户端远程发现模型 | `remote_discover_model()` 通过 MMS 在线遍历 | ✅ 已完成 | 与设计一致 |
| 2.4 | 客户端本地加载模型 | `load_model_from_icd(icd_path)` 解析 ICD 构建模型 | ✅ 已完成 | 与设计一致 |
| 2.5 | ModelCache 缓存机制 | 实现 LRU 缓存、哈希计算、过期策略 | ❌ 未开始 | 暂未开发 |
| 2.6 | ClientHandler 模型状态属性 | 添加 `_model_loaded` 标志位，getter/setter | ✅ 已完成 | **简化实现**：仅添加标志位，未完全重构 connect 流程。另新增前端路由调整（`/info` 接口合并 `model_loaded`、移除独立 `/model-status` 端点） |
| 2.7 | 集成测试 | 覆盖四种场景：服务端ICD启动/客户端远程发现/客户端本地加载/缓存复用 | ❌ 未开始 | — |

**关键技术验证标准：**
- 服务端可在不启动 MMS 服务的情况下独立加载模型
- 客户端本地加载 ICD 文件耗时 < 远程发现耗时
- 缓存命中时模型构建速度提升 > 80%
- 同一 ICD 文件的多次设备启动共享缓存模型

### 第三阶段：数据清理（预计 2 个工作日）

| 编号 | 任务 | 详细说明 | 状态 | 实际差异 |
|------|------|---------|------|---------|
| 3.1 | 清理脚本编写 | 编写数据库清理脚本：删除 `point_yc/yx/yk/yt` 中 `protocol_type=4` 的记录 | ❌ 未开始 | — |
| 3.2 | 清理前数据备份 | 自动备份待删除数据到 JSON 文件 | ❌ 未开始 | — |
| 3.3 | 清理执行与验证 | 在生产环境执行清理，验证记录已清除且不影响其他模块 | ❌ 未开始 | — |
| 3.4 | 功能回归测试 | 验证非 61850 协议的 Modbus/IEC104/DLT645 模块不受影响 | ❌ 未开始 | — |

**关键技术验证标准：**
- 清理后 `point_yc/yx/yk/yt` 表中无 `protocol_type=4` 的记录
- Modbus/IEC104/DLT645 通道的测点数据完整无缺
- 所有非 61850 协议功能正常运行

### 第四阶段：文档与版本控制（贯穿全程）

| 编号 | 任务 | 详细说明 | 责任人 | 预计工时 |
|------|------|---------|--------|---------|
| 4.1 | 架构变更文档 | 更新模块架构说明，记录整改前后架构变化 | 后端开发 | 1d |
| 4.2 | 操作指南编写 | 编写新流程下的模型管理和设备启动操作指南 | 后端开发 | 1d |
| 4.3 | API 文档更新 | 更新相关 REST API 接口文档 | 后端开发 | 0.5d |
| 4.4 | Git 版本管理 | 确保所有代码修改按功能分支管理，提交信息规范 | 全员 | 全程 |


## 5. 详细实现方案

### 5.1 ICD 文件规范存储机制

**文件存储规约：**

```
data/61850icd/
├── {ied_name}/
│   ├── {ied_name}_v{revision}.icd    # 规范存储
│   ├── {ied_name}_v{revision}.icd.sha256  # 完整性校验文件
│   └── {ied_name}_v{revision}.icd.meta    # 元数据文件 (JSON)
└── temp/                              # 临时上传目录 (定期清理)
```

**元数据文件内容 (`*.meta`)：**

```json
{
  "ied_name": "PCS001G",
  "version": "1.0",
  "revision": "A",
  "file_hash": "sha256:xxxxxxxx...",
  "upload_time": "2026-06-27T10:30:00",
  "device_ids": [1, 2],
  "channel_ids": [3, 4],
  "description": "PCS 储能变流器 ICD 文件"
}
```

### 5.2 服务端加载/启动分离实现

> ✅ **已实现**。代码位于 `src/proto/iec61850/iec61850_server.py`。
>
> 实际实现与设计一致：
> - `load_model(icd_path)` — 独立加载 ICD 文件构建 IedModel
> - `start_device()` — 在模型已加载前提下启动 MMS 服务
> - `start()` — 向后兼容，自动判断是否已加载模型

```python
class IEC61850Server:
    # === 已实现 ===

    def load_model(self, icd_path: str) -> bool:
        """加载 ICD 文件模型 (不启动 MMS 服务)

        Args:
            icd_path: ICD 文件路径

        Returns:
            是否加载成功
        """
        # 1. 解析 ICD 文件
        service = SclImportService()
        result = service.import_file(icd_path)
        if not result.is_valid:
            log.error(f"ICD 文件校验失败: {icd_path}")
            return False

        # 2. 重置现有模型
        self.reset_model()

        # 3. 根据解析结果构建 IedModel
        #    从 result.points/result.goose/result.reports 创建模型节点
        #    调用 _get_or_create_ld()/_get_or_create_ln() 等接口
        # 4. 注册 GOOSE/DataSet/RCB
        self._apply_pending_registrations()

        self._model_loaded = True
        self._loaded_icd_path = icd_path
        return True

    def start_device(self) -> bool:
        """启动 MMS 服务 (模型必须已加载)"""
        if not self._model_loaded:
            log.error("模型未加载，请先调用 load_model()")
            return False

        # 原来的 start() 逻辑，但使用已加载的模型
        self._server = iec61850.IedServer_create(self._builder.model)
        # ... 启动逻辑 ...
        self._is_running = True
        return True

    # === 修改 ===
    def start(self, register_default_rcbs: bool = True):
        """保持向后兼容：若未加载模型则使用默认模型"""
        if not self._model_loaded:
            # 向后兼容：使用默认 GenericLD
            if register_default_rcbs:
                self._register_default_rcbs()
            self._apply_pending_registrations()
        # ... 启动逻辑 ...
```

### 5.3 客户端模型获取与缓存

> ✅ **`load_model_from_icd()` 和 `remote_discover_model()`** 已实现。
>
> 实际实现（代码位于 `src/proto/iec61850/iec61850_client.py` 和 `src/device/protocol/iec61850_handler.py`）：
> - **`IEC61850Client.load_model_from_icd(icd_path)`** — 解析 ICD 构建 IedModel + PointRegistry
> - **`IEC61850Client.remote_discover_model()`** — 通过 MMS 在线发现构建模型
> - **`ClientHandler._model_loaded`** — 标志位记录模型是否已加载
>
> ❌ **`ModelCache` 未实现**，当前每次加载都重新构建模型。

```python
class IEC61850Client:
    # === 已实现 ===

    def load_model_from_icd(self, icd_path: str) -> IedModel:
        """从本地 ICD 文件加载模型"""
        service = SclImportService()
        result = service.import_file(icd_path)
        # 将 SclImportResult 转换为 IedModel
        model = self._build_model_from_result(result)
        # 从 model 构建 PointRegistry
        build_registry_from_model(model, self._registry)
        return model

    def remote_discover_model(self) -> IedModel:
        """远程发现模型"""
        # 在线发现
        model = self._discovery.discover(self._conn)
        return model

    def connect(self, auto_discover: bool = True) -> bool:
        """连接 — 仅建立 MMS 连接"""
        return self._conn.connect()
```

> **实际差异**：原计划的 ModelCache 缓存机制尚未实现；`connect()` 流程未完全重构为"获取模型"和"连接设备"两步，当前由调用方（`ClientHandler`）自行控制顺序。

```python
# ClientHandler 简化实现 (iec61850_handler.py)
class ClientHandler:
    _model_loaded: bool = False

    @property
    def model_loaded(self) -> bool:
        return self._model_loaded

    def load_model_from_icd(self, icd_path: str) -> bool:
        success = self._client.load_model_from_icd(icd_path)
        if success:
            self._model_loaded = True
        return success

    def remote_discover_model(self) -> bool:
        # ... 发现逻辑 ...
        self._model_loaded = True
        return True
```

### 5.4 ModelCache 详细设计

```python
from collections import OrderedDict
import hashlib
import time


class ModelCache:
    """线程安全的 LRU 模型缓存"""

    _instance = None
    _lock = threading.Lock()

    MAX_SIZE = 32
    TTL_SECONDS = 1800  # 30 分钟

    def __init__(self):
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()

    @classmethod
    def instance(cls) -> 'ModelCache':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def get(self, key: str) -> IedModel | None:
        with self._lock:
            entry = self._cache.get(key)
            if not entry:
                return None
            if time.time() - entry.timestamp > self.TTL_SECONDS:
                del self._cache[key]
                return None
            # LRU: 移动到末尾
            self._cache.move_to_end(key)
            return entry.model

    def set(self, key: str, model: IedModel) -> None:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = CacheEntry(model=model, timestamp=time.time())
            # LRU 淘汰
            while len(self._cache) > self.MAX_SIZE:
                self._cache.popitem(last=False)

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._cache.pop(key, None)

    @staticmethod
    def compute_hash(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()


@dataclass
class CacheEntry:
    model: IedModel
    timestamp: float
```

### 5.5 前端模型加载状态显示

> ✅ **已实现**。未在原计划中，实际开发中新增。

#### 后端路由调整

将 `model_loaded` 状态从独立端点合并到 `/api/devices/info` 接口，减少一次网络请求。

```python
# src/web/api/device/router.py
@device_router.post("/info")
async def get_device_info(req, request):
    device = _get_device(req.device_name, request)
    info_dict = {
        # ... 原有字段 ...
        "iec61850_model_loaded": device.iec61850_model_loaded,  # 新增
    }
    return BaseResponse(data=info_dict)

# 移除独立端点:
# DELETE /api/devices/iec61850/model-status
```

#### 前端读取

```typescript
// Device.vue - fetchDeviceInfo()
modelLoaded.value = info.get("iec61850_model_loaded") === true;
```

不再需要单独的 `fetchIec61850ModelStatus()` 轮询调用。

#### Device.iec61850_model_loaded 属性链

```
Device.iec61850_model_loaded
  → protocol_handler.model_loaded
    → ServerHandler: self._server.model_loaded (IEC61850Server._model_loaded)
    → ClientHandler: self._model_loaded (新标志位)
```

#### 导入 ICD 后的自动加载

在 `import_points.py` 中，ICD 文件解析并保存后，立即自动调用：

```python
device = device_controller.get_device_by_id(channel_id)
if device and hasattr(device, "load_iec61850_model"):
    device.load_iec61850_model(icd_path)
    # → load_iec61850_model() → ClientHandler.load_model_from_icd()
    #   → self._model_loaded = True
```


## 6. 回滚方案

### 6.1 回滚触发条件

以下情况触发回滚：

1. **功能阻断性 Bug**：整改后任一协议模块（非 IEC61850）无法正常运行
2. **数据完整性受损**：数据清理导致非 61850 协议的测点数据丢失
3. **性能严重倒退**：设备启动时间整改后比整改前增加 >50%
4. **兼容性断裂**：现有前端页面无法正常显示设备数据和结构树

### 6.2 数据库回滚

```sql
-- 回滚 1: 删除新增字段
ALTER TABLE channel DROP COLUMN icd_path;
ALTER TABLE channel DROP COLUMN icd_file_hash;
ALTER TABLE device DROP COLUMN icd_path;
ALTER TABLE device DROP COLUMN icd_file_hash;

-- 回滚 2: 恢复 IEC61850 测点数据
-- 从备份 JSON 文件导入恢复
```

### 6.3 代码回滚

```
git revert <commit_hash>    # 使用 Git revert 精确回滚
git checkout <old_tag>      # 或整体回退到上一版本标签
```

### 6.4 回滚验证清单

- [ ] 数据库表结构恢复至整改前状态
- [ ] ICD 文件导入功能恢复正常（含测点写入数据库）
- [ ] 服务端设备启动流程恢复
- [ ] 客户端连接/发现流程恢复
- [ ] 所有前端页面正常加载设备数据


## 7. 风险与应对

| 风险 | 影响 | 概率 | 应对措施 |
|------|------|------|---------|
| 数据清理误删非 61850 记录 | 高 | 低 | 清理前逐一确认 `protocol_type` 过滤条件；执行前备份 |
| 客户端缓存模型与 IED 实际模型不一致 | 中 | 中 | 缓存标记 `model_hash`，启动时与 IED 远程比对 hash |
| ICD 文件版本更新后缓存未及时失效 | 中 | 中 | 提供手动清缓存 API；ICD 文件变更时自动 invalidate 关联缓存 |
| 前端兼容性断裂 | 高 | 低 | 后端保持原有 API 签名不变；前端按需适配新增接口 |
| ICD 文件解析失败导致设备无法启动 | 高 | 低 | 加载失败时保持旧模型不变，提供详细错误提示 |


## 8. 附录

### 8.1 文件变更清单

| 文件路径 | 变更类型 | 变更说明 |
|---------|---------|---------|
| `src/proto/iec61850/iec61850_server.py` | 修改 | 新增 `load_model()`、`start_device()`；修改`start()` |
| `src/proto/iec61850/iec61850_client.py` | 修改 | 新增 `load_model_from_icd()`、`remote_discover_model()` |
| `src/proto/iec61850/model/cache.py` | 新增 | ModelCache 实现 |
| `src/proto/iec61850/plugins/scl/service/file_manager.py` | 修改 | 新增完整性校验、元数据管理 |
| `src/device/protocol/iec61850_handler.py` | 修改 | ClientHandler/ServerHandler 适配新流程 |
| `src/device/factory/general_device_builder.py` | 修改 | 拆分模型加载与设备启动步骤 |
| `src/data/model/channel.py` | 修改 | 新增 `icd_path`、`icd_file_hash` 字段 |
| `src/data/model/device.py` | 修改 | 新增 `icd_path`、`icd_file_hash` 字段 |
| `src/data/dao/channel_dao.py` | 修改 | 新增 ICD 路径相关 DAO 方法 |
| `src/web/api/scl/router.py` | 修改 | 导入接口不再写数据库测点表 |
| `docs/changelog/iec61850/18-iec61850-data-storage-optimization-plan.md` | 新增 | 本文档 |

### 8.2 API 变更清单

| 接口 | 变更 | 说明 |
|------|------|------|
| `POST /api/scl/import-points` | 修改 | 不再写入 `point_yc/yx/yk/yt`，改为记录 `icd_path` |
| `POST /api/scl/import-full` | 修改 | 同上 |
| `POST /api/device/{id}/load-model` | 新增 | 加载 ICD 模型（不启动设备） |
| `POST /api/device/{id}/start-device` | 新增 | 启动已加载模型的设备 |
| `POST /api/device/{id}/load-model-from-remote` | 新增 | 客户端：远程发现模型 |
| `GET  /api/device/{id}/model-cache-status` | 新增 | 查询模型缓存命中状态 |
| `DELETE /api/device/{id}/model-cache` | 新增 | 清除指定设备的模型缓存 |

### 8.3 时间线总表

| 阶段 | 内容 | 计划工期 | 建议开始 | 当前状态 |
|------|------|---------|---------|---------|
| 第一阶段 | 数据存储架构改造 | 5 个工作日 | 第 1 天 | **1.1-1.4 已完成**；1.5-1.6 待开始 |
| 第二阶段 | 协议处理流程重构 | 7 个工作日 | 第 6 天 | **2.1-2.4、2.6 已完成**；2.5、2.7 待开始 |
| 第三阶段 | 数据清理 | 2 个工作日 | 第 13 天 | **未开始** |
| 第四阶段 | 文档与验收 | 贯穿全程 | 第 1 天起 | 持续中 |

> **当前进度**：第二阶段核心功能已完成，其余项待排期。合计约 **4 个工作日**的待完成任务。
