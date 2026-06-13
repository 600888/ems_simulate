# Web API 层重构

> 版本：未发布 | 日期：2026-05-01

## 概述

本次修改对后端 Web API 层进行了全面重构，将原来分散的控制器文件重新组织为统一的 `src/web/api/` 模块化结构，同时将所有 API 路径从扁平的 `/xxx` 风格迁移到 RESTful 的 `/api/xxx` 风格，子路径命名从 `snake_case` 改为 `kebab-case`。前端所有 API 调用路径同步更新。

---

## 变更动机

1. **模块化**：原来 `channel_controller.py` 单文件超过 1100 行，将不同职责混在一起，难以维护
2. **RESTful 规范**：统一使用 `/api` 前缀，路径命名更规范
3. **命名一致性**：将 `snake_case` 路径（如 `import_points`）改为 `kebab-case`（如 `import-points`）
4. **Schema 分离**：将 Pydantic 模型按业务域拆分到独立文件

---

## 目录结构变更

### 旧结构（已删除）

```
src/web/
├── app.py
├── channel/
│   ├── __init__.py
│   └── channel_controller.py          (1120 行，全部通道逻辑)
├── device/
│   ├── __init__.py
│   └── device_controller.py           (361 行)
├── device_group/
│   ├── __init__.py
│   └── device_group_controller.py     (283 行)
├── point/
│   ├── point_controller.py            (384 行)
│   ├── point_mapping.py               (126 行)
│   └── point_tree.py                  (12 行)
└── schemas/
    ├── schemas.py                      (270 行，所有模型混在一起)
    ├── schemas_point_mapping.py
    └── schemas_tree.py
```

### 新结构

```
src/web/
├── app.py
└── api/
    ├── __init__.py                     (统一导出所有路由器)
    ├── channel/
    │   ├── __init__.py                 (合并子路由为 channel_router)
    │   ├── router.py                   (通道 CRUD)
    │   ├── device_manage.py            (设备启动/停止/重启/重载/复制)
    │   ├── import_points.py            (Excel/ICD 点表导入)
    │   ├── iec61850.py                 (IEC61850 相关操作)
    │   └── helpers.py                  (公共辅助函数)
    ├── device/
    │   ├── __init__.py
    │   └── router.py                   (设备操作路由)
    ├── device_group/
    │   ├── __init__.py
    │   └── router.py                   (设备组管理路由)
    ├── point/
    │   ├── __init__.py
    │   ├── router.py                   (测点操作路由)
    │   ├── mapping.py                  (测点映射路由)
    │   └── tree.py                     (测点树路由)
    └── schemas/
        ├── __init__.py                 (统一导出所有 Schema)
        ├── base.py                     (BaseResponse)
        ├── channel.py                  (通道相关请求模型)
        ├── device.py                   (设备相关请求模型)
        ├── device_group.py             (设备组相关请求模型)
        ├── point.py                    (测点相关请求模型)
        ├── point_mapping.py            (测点映射相关模型)
        └── tree.py                     (树结构模型)
```

---

## API 路径映射

### 通道管理 (`/channel` → `/api/channels`)

| 旧路径 | 新路径 | HTTP 方法 |
|--------|--------|-----------|
| `GET /channel/protocols` | `GET /api/channels/protocols` | 不变 |
| `GET /channel/serial_ports` | `GET /api/channels/serial-ports` | 不变 |
| `POST /channel/create` | `POST /api/channels/create` | 不变 |
| `POST /channel/import_points` | `POST /api/channels/import-points` | 不变 |
| `POST /channel/import_icd` | `POST /api/channels/import-icd` | 不变 |
| `POST /channel/create_and_start` | `POST /api/channels/create-and-start` | 不变 |
| `POST /channel/restart/{channel_id}` | `POST /api/channels/restart/{channel_id}` | 不变 |
| `POST /channel/reload_config/{channel_id}` | `POST /api/channels/reload-config/{channel_id}` | 不变 |
| `DELETE /channel/{channel_id}` | `DELETE /api/channels/{channel_id}` | 不变 |
| `GET /channel/list` | `GET /api/channels/list` | 不变 |
| `GET /channel/iec61850_structure/{channel_id}` | `GET /api/channels/iec61850-structure/{channel_id}` | 不变 |
| `GET /channel/iec61850_table_data/{channel_id}` | `GET /api/channels/iec61850-table-data/{channel_id}` | 不变 |
| `POST /channel/iec61850_read_points/{channel_id}` | `POST /api/channels/iec61850-read-points/{channel_id}` | 不变 |
| `GET /channel/{channel_id}` | `GET /api/channels/{channel_id}` | 不变 |
| `PUT /channel/{channel_id}` | `PUT /api/channels/{channel_id}` | 不变 |
| `POST /channel/copy` | `POST /api/channels/copy` | 不变 |

### 设备管理 (`/device` → `/api/devices`)

| 旧路径 | 新路径 | HTTP 方法变更 |
|--------|--------|--------------|
| `POST /device/get_device_list` | `GET /api/devices/list` | POST → **GET** |
| `POST /device/get_device_info` | `POST /api/devices/info` | 不变 |
| `POST /device/get_slave_id_list` | `POST /api/devices/slave-id-list` | 不变 |
| `POST /device/get_device_table` | `POST /api/devices/table` | 不变 |
| `POST /device/start_simulation` | `POST /api/devices/start-simulation` | 不变 |
| `POST /device/stop_simulation` | `POST /api/devices/stop-simulation` | 不变 |
| `GET /device/current_table/` | `GET /api/devices/current-table` | 不变 |
| `POST /device/start` | `POST /api/devices/start` | 不变 |
| `POST /device/stop` | `POST /api/devices/stop` | 不变 |
| `POST /device/get_auto_read_status` | `POST /api/devices/auto-read-status` | 不变 |
| `POST /device/start_auto_read` | `POST /api/devices/start-auto-read` | 不变 |
| `POST /device/stop_auto_read` | `POST /api/devices/stop-auto-read` | 不变 |
| `POST /device/manual_read` | `POST /api/devices/manual-read` | 不变 |
| `POST /device/get_messages` | `POST /api/devices/messages` | 不变 |
| `POST /device/clear_messages` | `POST /api/devices/clear-messages` | 不变 |
| `POST /device/get_avg_time` | `POST /api/devices/avg-time` | 不变 |
| `POST /device/add_slave` | `POST /api/devices/add-slave` | 不变 |
| `POST /device/delete_slave` | `POST /api/devices/delete-slave` | 不变 |
| `POST /device/edit_slave` | `POST /api/devices/edit-slave` | 不变 |

### 测点管理 (`/point` → `/api/points`)

| 旧路径 | 新路径 | HTTP 方法 |
|--------|--------|-----------|
| `POST /point/edit_point_data/` | `POST /api/points/edit-data` | 不变 |
| `POST /point/edit_point_limit/` | `POST /api/points/edit-limit` | 不变 |
| `POST /point/get_point_limit/` | `POST /api/points/get-limit` | 不变 |
| `POST /point/set_single_point_simulate_method` | `POST /api/points/set-simulate-method` | 不变 |
| `POST /point/set_single_point_step` | `POST /api/points/set-simulate-step` | 不变 |
| `POST /point/get_point_info` | `POST /api/points/info` | 不变 |
| `POST /point/set_point_simulation_range` | `POST /api/points/set-simulation-range` | 不变 |
| `POST /point/edit_point_metadata/` | `POST /api/points/edit-metadata` | 不变 |
| `POST /point/read_single_point` | `POST /api/points/read-single` | 不变 |
| `POST /point/add_point` | `POST /api/points/add` | 不变 |
| `POST /point/add_points_batch` | `POST /api/points/add-batch` | 不变 |
| `POST /point/delete_point` | `POST /api/points/delete` | 不变 |
| `POST /point/clear_points` | `POST /api/points/clear-by-slave` | 不变 |
| `POST /point/reset_point_data` | `POST /api/points/reset-data` | 不变 |
| `POST /point/get_point_change_history` | `POST /api/points/change-history` | 不变 |
| `POST /point/set_change_tracking` | `POST /api/points/set-change-tracking` | 不变 |
| `POST /point/clear_point_change_history` | `POST /api/points/clear-change-history` | 不变 |

### 测点映射 (`/point_mapping` → `/api/point-mappings`)

| 旧路径 | 新路径 | HTTP 方法 |
|--------|--------|-----------|
| `POST /point_mapping/create` | `POST /api/point-mappings/create` | 不变 |
| `POST /point_mapping/update` | `POST /api/point-mappings/update` | 不变 |
| `POST /point_mapping/delete` | `POST /api/point-mappings/delete` | 不变 |
| `GET /point_mapping/list` | `GET /api/point-mappings/list` | 不变 |

### 测点树 (`/point_tree` → `/api/point-tree`)

| 旧路径 | 新路径 | HTTP 方法 |
|--------|--------|-----------|
| `GET /point_tree/tree` | `GET /api/point-tree/tree` | 不变 |

### 设备组 (`/device_group` → `/api/device-groups`)

> 设备组路由为本次重构中新增的模块，旧版为 `/device_group` 前缀，现已迁移至 `/api/device-groups`。

---

## 修改文件清单

### 后端 — 删除文件

| 文件 | 说明 |
|------|------|
| `src/web/channel/__init__.py` | 旧通道模块入口 |
| `src/web/channel/channel_controller.py` | 旧通道控制器（1120 行） |
| `src/web/device/__init__.py` | 旧设备模块入口 |
| `src/web/device/device_controller.py` | 旧设备控制器 |
| `src/web/device_group/__init__.py` | 旧设备组模块入口 |
| `src/web/device_group/device_group_controller.py` | 旧设备组控制器 |
| `src/web/point/point_controller.py` | 旧测点控制器 |
| `src/web/point/point_mapping.py` | 旧测点映射路由 |
| `src/web/point/point_tree.py` | 旧测点树路由 |
| `src/web/schemas/schemas.py` | 旧 Schema（270 行混合模型） |
| `src/web/schemas/schemas_point_mapping.py` | 旧映射 Schema |
| `src/web/schemas/schemas_tree.py` | 旧树 Schema |

### 后端 — 新增文件

| 文件 | 说明 |
|------|------|
| `src/web/api/__init__.py` | API 模块统一导出 |
| `src/web/api/channel/__init__.py` | 通道模块入口（合并子路由） |
| `src/web/api/channel/router.py` | 通道 CRUD 路由 |
| `src/web/api/channel/device_manage.py` | 设备管理操作路由 |
| `src/web/api/channel/import_points.py` | 点表导入路由 |
| `src/web/api/channel/iec61850.py` | IEC61850 操作路由 |
| `src/web/api/channel/helpers.py` | 公共辅助函数 |
| `src/web/api/device/__init__.py` | 设备模块入口 |
| `src/web/api/device/router.py` | 设备操作路由 |
| `src/web/api/device_group/__init__.py` | 设备组模块入口 |
| `src/web/api/device_group/router.py` | 设备组管理路由 |
| `src/web/api/point/__init__.py` | 测点模块入口 |
| `src/web/api/point/router.py` | 测点操作路由 |
| `src/web/api/point/mapping.py` | 测点映射路由 |
| `src/web/api/point/tree.py` | 测点树路由 |
| `src/web/api/schemas/__init__.py` | Schema 统一导出 |
| `src/web/api/schemas/base.py` | BaseResponse |
| `src/web/api/schemas/channel.py` | 通道请求模型 |
| `src/web/api/schemas/device.py` | 设备请求模型 |
| `src/web/api/schemas/device_group.py` | 设备组请求模型 |
| `src/web/api/schemas/point.py` | 测点请求模型 |
| `src/web/api/schemas/point_mapping.py` | 映射请求模型 |
| `src/web/api/schemas/tree.py` | 树结构模型 |

### 后端 — 修改文件

| 文件 | 修改内容 |
|------|---------|
| `src/web/app.py` | 路由导入路径从旧模块切换到 `src.web.api`；路由注册去掉 `prefix=""` |
| `src/data/service/point_tree_service.py` | Schema 导入路径从 `src.web.schemas.schemas_tree` 改为 `src.web.api.schemas.tree` |
| `src/enums/points/base_point.py` | 类型注解优化：`address` 属性返回类型改为 `int|str`；`is_valid` 加 `Optional[bool]` 注解；`list()` 返回类型加 `list[str|int|bool]` |
| `src/tests/test_api_live.py` | 测试路径从 `/api/point_mapping` 改为 `/api/point-mappings` |

### 前端 — 修改文件

| 文件 | 修改内容 |
|------|---------|
| `front/src/api/channelApi.ts` | 所有路径从 `/channel/*` 改为 `/api/channels/*`，`snake_case` 改为 `kebab-case` |
| `front/src/api/deviceApi.ts` | 所有路径从 `/device/*` 改为 `/api/devices/*`，`snake_case` 改为 `kebab-case` |
| `front/src/api/pointApi.ts` | 所有路径从 `/point/*` 改为 `/api/points/*`，`snake_case` 改为 `kebab-case` |
| `front/src/api/pointMappingApi.ts` | `BASE_URL` 从 `/point_mapping` 改为 `/api/point-mappings` |
| `front/src/api/pointTreeApi.ts` | `BASE_URL` 从 `/point_tree` 改为 `/api/point-tree` |

---

## 破坏性变更

> **所有 API 路径均已变更，前后端必须同时部署。**

### 不兼容变更

1. **所有 API 路径前缀从无变为 `/api`**，Vite 代理配置需确保 `/api` 正确代理到后端
2. **子路径 `snake_case` → `kebab-case`**：如 `import_points` → `import-points`、`serial_ports` → `serial-ports`
3. **设备列表接口 HTTP 方法变更**：`POST /device/get_device_list` → `GET /api/devices/list`
4. **部分路径简化**：如 `get_device_info` → `info`、`get_point_info` → `info`

### 升级步骤

1. 部署后端新代码
2. 部署前端新代码
3. 确认 Vite 代理配置中 `/api` 路径正确代理到后端端口
