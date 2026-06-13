# IEC104 协议全 ASDU 类型支持

> 版本：未发布 | 日期：2026-04-28

## 概述

本次修改将 IEC104 协议的测点类型支持从原来的 **2 种**（短浮点遥测 `M_ME_NC_1`、单点遥信 `M_SP_NA_1`）扩展到 **25 种** ASDU 类型，覆盖 IEC 60870-5-104 标准中遥测、遥信、遥控、遥调四个方向的所有常用类型。同时采用现代 Python 设计模式重构类型定义，前端也相应增加了类型选择功能。

---

## 支持的 ASDU 类型一览

### 遥测（frame_type=0，监视方向）

| 类型标识 | 类型编号 | 中文标签 | 值类型 | 时标 |
|----------|---------|----------|--------|------|
| M_ME_NC_1 | 13 | 短浮点遥测 | float | - |
| M_ME_NA_1 | 9 | 归一化遥测 | float | - |
| M_ME_NB_1 | 11 | 标度化遥测 | float | - |
| M_ME_ND_1 | 21 | 归一化遥测(不带品质) | float | - |
| M_ME_TD_1 | 34 | 归一化遥测(CP56) | float | CP56 |
| M_ME_TE_1 | 35 | 标度化遥测(CP56) | float | CP56 |
| M_ME_TF_1 | 36 | 短浮点遥测(CP56) | float | CP56 |

### 遥信（frame_type=1，监视方向）

| 类型标识 | 类型编号 | 中文标签 | 值类型 | 时标 |
|----------|---------|----------|--------|------|
| M_SP_NA_1 | 1 | 单点遥信 | single | - |
| M_SP_TA_1 | 2 | 单点遥信(带时标) | single | CP16 |
| M_DP_NA_1 | 3 | 双点遥信 | double | - |
| M_DP_TA_1 | 4 | 双点遥信(带时标) | double | CP16 |
| M_SP_TB_1 | 30 | 单点遥信(CP56) | single | CP56 |
| M_DP_TB_1 | 31 | 双点遥信(CP56) | double | CP56 |

### 遥控（frame_type=2，控制方向）

| 类型标识 | 类型编号 | 中文标签 | 值类型 | 时标 |
|----------|---------|----------|--------|------|
| C_SC_NA_1 | 45 | 单点遥控 | single | - |
| C_DC_NA_1 | 46 | 双点遥控 | double | - |
| C_RC_NA_1 | 47 | 步调节命令 | step | - |
| C_SC_TA_1 | 58 | 单点遥控(CP56) | single | CP56 |
| C_DC_TA_1 | 59 | 双点遥控(CP56) | double | CP56 |
| C_RC_TA_1 | 60 | 步调节命令(CP56) | step | CP56 |

### 遥调（frame_type=3，控制方向）

| 类型标识 | 类型编号 | 中文标签 | 值类型 | 时标 |
|----------|---------|----------|--------|------|
| C_SE_NC_1 | 50 | 设定值(短浮点) | float | - |
| C_SE_NA_1 | 48 | 设定值(归一化) | float | - |
| C_SE_NB_1 | 49 | 设定值(标度化) | float | - |
| C_SE_TA_1 | 61 | 设定值归一化(CP56) | float | CP56 |
| C_SE_TB_1 | 62 | 设定值标度化(CP56) | float | CP56 |
| C_SE_TC_1 | 63 | 设定值短浮点(CP56) | float | CP56 |

---

## 设计模式

### 后端：StrEnum + frozen dataclass 注册表模式

新增模块 `src/enums/points/iec104_type.py`，采用以下设计：

- **`IEC104Type(StrEnum)`** — ASDU 类型标识枚举，成员值即为标准标识符字符串（如 `"M_ME_NC_1"`），可直接用于 c104 库查找和数据库存储
- **`IEC104TypeInfo(frozen dataclass)`** — 不可变的类型元数据，包含类型编号、中文标签、传输方向、值类型、帧类型、时标信息等
- **`IEC104_TYPE_REGISTRY`** — 类型元数据注册表字典，以 `IEC104Type` 为 key，`IEC104TypeInfo` 为 value
- **辅助枚举** — `IEC104Direction`（监视/控制方向）、`IEC104ValueType`（float/integer/single/double/step）
- **工具函数**：
  - `get_iec104_types_by_frame_type()` — 按帧类型筛选可用类型
  - `get_iec104_type_info()` — 根据类型标识获取元数据
  - `resolve_iec104_type()` — 解析类型（优先指定值，回退到默认值）
  - `is_double_point_type()` / `is_step_type()` — 判断值类型

### 向后兼容

通过 `IEC104_DEFAULT_TYPE` 映射保证向后兼容：

| 帧类型 | 默认 ASDU 类型 |
|--------|---------------|
| 遥测 (0) | M_ME_NC_1（短浮点遥测） |
| 遥信 (1) | M_SP_NA_1（单点遥信） |
| 遥控 (2) | C_SC_NA_1（单点遥控） |
| 遥调 (3) | C_SE_NC_1（设定值短浮点） |

未设置 `iec_type_id` 的已有测点将自动使用上述默认类型，行为与修改前一致。

---

## 修改文件清单

### 后端 — 新增文件

| 文件 | 说明 |
|------|------|
| `src/enums/points/iec104_type.py` | IEC104 ASDU 类型定义核心模块 |

### 后端 — 数据模型

| 文件 | 修改内容 |
|------|---------|
| `src/data/model/point_yc.py` | 新增 `iec_type_id: Optional[str]` 字段 |
| `src/data/model/point_yx.py` | 新增 `iec_type_id: Optional[str]` 字段 |
| `src/data/model/point_yk.py` | 新增 `iec_type_id: Optional[str]` 字段 |
| `src/data/model/point_yt.py` | 新增 `iec_type_id: Optional[str]` 字段 |

### 后端 — 数据访问与服务

| 文件 | 修改内容 |
|------|---------|
| `src/data/dao/point_dao.py` | create/update 方法支持 `iec_type_id` 字段 |
| `src/data/service/yc_service.py` | 传递 `iec_type_id` 到模型构造 |
| `src/data/service/yx_service.py` | 传递 `iec_type_id` 到模型构造 |
| `src/data/service/yk_service.py` | 传递 `iec_type_id` 到模型构造 |
| `src/data/service/yt_service.py` | 传递 `iec_type_id` 到模型构造 |

### 后端 — 设备核心

| 文件 | 修改内容 |
|------|---------|
| `src/enums/points/base_point.py` | 新增 `iec_type_id` 属性与 getter/setter |
| `src/enums/points/protocol_strategy.py` | `IEC104Strategy` 新增 `get_available_types()` 和 `resolve_type()` 方法 |
| `src/enums/points/__init__.py` | 导出新模块 |
| `src/enums/point_data.py` | 向后兼容导出 |
| `src/device/protocol/iec104_handler.py` | 使用 `resolve_iec104_type()` + `getattr(c104.Type, ...)` 动态解析类型 |
| `src/device/core/point/point_operator.py` | `edit_metadata()` 处理 `iec_type_id` 变更，变更时标记 `need_resync=True` |
| `src/device/core/data/data_exporter.py` | 导出增加 IEC104 类型列 |
| `src/device/simulator/simulation_controller.py` | `get_point_info()` 返回 `iec_type_id` |

### 后端 — Web 层

| 文件 | 修改内容 |
|------|---------|
| `src/web/schemas/schemas.py` | `PointCreateRequest` 和 `PointItem` 新增 `iec_type_id` 字段 |
| `src/web/point/point_controller.py` | `add_point` 接口传递 `iec_type_id` |

### 数据库

| 文件 | 修改内容 |
|------|---------|
| `data/ems_schema.sql` | 四张测点表均新增 `iec_type_id VARCHAR(16)` 列 |

### 前端

| 文件 | 修改内容 |
|------|---------|
| `front/src/types/point.ts` | 新增 `IEC104TypeInfo` 接口、`IEC104_TYPES_BY_FRAME_TYPE` 常量、`getDefaultIec104Type()` 和 `getIec104TypeLabel()` 工具函数 |
| `front/src/api/pointApi.ts` | `PointCreateData` 新增 `iec_type_id` 可选字段 |
| `front/src/components/device/AddPointDialog.vue` | 添加测点时显示 IEC104 类型选择器（仅 IEC104 协议设备可见），帧类型变更时自动设置默认类型 |
| `front/src/components/point/EditPointMetadata.vue` | 编辑测点元数据时支持修改 IEC104 类型，变更时触发重新同步 |
| `front/src/components/device/Table.vue` | 测点表格新增 IEC104 类型列（仅 IEC104 协议设备可见） |

---

## 数据库迁移

已有部署需要执行以下 SQL 为测点表添加新列：

```sql
ALTER TABLE point_yc ADD COLUMN iec_type_id VARCHAR(16);
ALTER TABLE point_yx ADD COLUMN iec_type_id VARCHAR(16);
ALTER TABLE point_yk ADD COLUMN iec_type_id VARCHAR(16);
ALTER TABLE point_yt ADD COLUMN iec_type_id VARCHAR(16);
```

> 新列允许 NULL，已有数据行将使用默认类型（见上方向后兼容表），无需数据回填。

---

## 关键实现细节

### c104 库动态类型解析

```python
# iec104_handler.py 中的核心逻辑
def _resolve_c104_type(self, point) -> c104.Type:
    iec_type = resolve_iec104_type(point.iec_type_id, point.frame_type)
    return getattr(c104.Type, iec_type.value)
```

通过 `getattr()` 将字符串标识（如 `"M_ME_NC_1"`）动态映射到 `c104.Type` 常量，替代了原来的硬编码 if/elif 链。

### 前端类型选择器联动

- 添加测点时，选择帧类型（遥测/遥信/遥控/遥调）后自动筛选该分类下的 IEC104 类型
- 默认选中各帧类型的默认类型（与后端 `IEC104_DEFAULT_TYPE` 一致）
- 非 IEC104 协议设备不显示类型选择器

### 测点元数据编辑

- 编辑 `iec_type_id` 后，`point_operator` 将 `need_resync` 标记为 `True`
- 下次同步周期会重新注册该测点到 IEC104 服务端，使用新的 ASDU 类型
