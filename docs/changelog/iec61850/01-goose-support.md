# IEC 61850 GOOSE 功能支持

> 版本：未发布 | 日期：2026-05-03

## 概述

本次修改为 EMS 仿真平台新增了 IEC 61850 GOOSE (Generic Object Oriented Substation Event) 功能，支持 GOOSE 报文的发布（Publisher）和订阅（Receiver/Subscriber），实现变电站快速事件信号的仿真收发。

GOOSE 是 IEC 61850 标准中用于快速可靠地传输变电站事件的二层组播协议，主要用于跳闸/告警等实时信号传输，传输延迟要求在 4ms 以内。本次实现覆盖完整的 GOOSE 生命周期管理，包括创建、配置、启停控制、数据集管理、订阅管理、状态监控等。

---

## 功能特性

### GOOSE Publisher（发布端）

- 创建 GOOSE 控制块 (GoCB) 并在指定网络接口上发布 GOOSE 组播报文
- 数据集动态管理：添加、修改、删除数据集条目
- 支持 6 种 IEC 数据类型：`boolean`、`integer`、`float`、`string`、`bitstring`、`timestamp`
- stNum/sqNum 自动管理：数据变化时自动递增 stNum 并重置 sqNum
- 定时重发（TAL）：按照 IEC 61850 规范周期性重发 GOOSE 报文
- 手动触发发布：支持立即发布单次 GOOSE 报文
- 仿真模式标记：支持 `simulation=True` 标记测试报文
- VLAN 标签支持：可配置 VLAN ID 和优先级
- 自动组播 MAC 地址：根据 APPID 自动生成 IEC 61850 规定的组播 MAC 地址

### GOOSE Receiver/Subscriber（订阅端）

- 在指定网络接口上监听 GOOSE 组播报文
- 每个 Receiver 支持多个 Subscription 订阅
- 按 GoCBRef、APPID、目标 MAC 过滤报文
- 报文接收回调通知
- 订阅状态实时监控：`init` → `connected` → `lost` → `error`
- 超时检测：当超过 `timeAllowedToLive` 未收到报文时标记为 `lost`
- 数据集值解析：自动解析 MMS 数据类型（Boolean、Integer、Float、String、BitString、Timestamp）

---

## 架构设计

### 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                      Frontend (Vue 3)                    │
│  ┌─────────────────────────────────────────────────┐    │
│  │              GooseManager.vue                    │    │
│  │  ┌──────────────┐    ┌──────────────────────┐   │    │
│  │  │ Publisher Tab │    │   Receiver Tab       │   │    │
│  │  └──────────────┘    └──────────────────────┘   │    │
│  └─────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────┐    │
│  │              gooseApi.ts (API 层)                │    │
│  └─────────────────────────────────────────────────┘    │
└──────────────────────────┬──────────────────────────────┘
                           │ HTTP JSON
┌──────────────────────────▼──────────────────────────────┐
│                   Backend (FastAPI)                       │
│  ┌─────────────────────────────────────────────────┐    │
│  │          channel/goose.py (路由层)               │    │
│  │          schemas/goose.py (Pydantic 模型)        │    │
│  └─────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────┐    │
│  │         GooseManager (资源管理器 Singleton)       │    │
│  │  ┌────────────────┐    ┌────────────────────┐   │    │
│  │  │ GoosePublisher  │    │   GooseReceiver    │   │    │
│  │  │  (发布端实例)   │    │   (接收端实例)     │   │    │
│  │  └────────────────┘    └────────────────────┘   │    │
│  └─────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────┐    │
│  │        pyiec61850 (libiec61850 Python 绑定)      │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

### 设计模式

#### 后端设计模式

1. **Singleton + Manager 模式**：`GooseManager` 作为全局单例，统一管理所有 GOOSE Publisher 和 Receiver 实例的完整生命周期，通过 `app.state.goose_manager` 挂载到 FastAPI 应用
2. **Pydantic V2 验证模式**：所有 Web API 请求/响应均通过 Pydantic 模型进行 JSON 序列化和字段校验
3. **线程安全**：Publisher 和 Receiver 均使用 `threading.Lock` 保护共享状态，底层重发/接收运行在独立守护线程
4. **优雅降级**：`pyiec61850` 未安装时 GOOSE 功能自动降级，不影响其他模块运行

#### 前端设计模式

1. **Composables 模式**：通过 API 层封装所有后端调用
2. **自动刷新**：GOOSE 管理页面每 5 秒自动轮询更新状态
3. **响应式状态**：订阅状态通过颜色编码实时展示

---

## 核心类设计

### GoosePublisher

```python
class GoosePublisher:
    """GOOSE 发布者
    
    核心属性:
    - interface: 网络接口名称 (如 "eth0")
    - go_cb_ref: GOOSE 控制块引用 (MMS 格式, 如 "LD0/LLN0$GO$gcb1")
    - go_id: GOOSE 标识符
    - data_set_ref: 数据集引用
    - app_id: APPID (0x0001 ~ 0xFFFF)
    - conf_rev: 配置修订号
    - time_allowed_to_live: 报文存活时间 (ms)
    - dst_mac: 目标组播 MAC 地址
    - vlan_id/vlan_prio: VLAN 标签
    - simulation: 仿真模式标记
    
    核心方法:
    - start() / stop(): 启停 Publisher 和定时重发线程
    - publish(): 立即发布 GOOSE 报文
    - add_entry() / remove_entry() / update_entry(): 数据集条目管理
    - get_status(): 获取完整状态信息
    """
```

#### stNum/sqNum 管理策略

| 事件 | stNum | sqNum | 说明 |
|------|-------|-------|------|
| 初始创建 | 1 | 0 | 默认值 |
| 数据集值变化 | +1 | 0 | 状态变化时递增 stNum，重置 sqNum |
| 定时重发 | 不变 | +1 | 每次重发递增 sqNum |
| 手动发布 | 不变 | +1 | 手动触发发布递增 sqNum |

#### 定时重发策略

```
重发间隔 = time_allowed_to_live / 2000 (秒)
```

按照 IEC 61850 规范，GOOSE 报文应在 TAL/2 时间内重发，确保接收端在超时前至少收到一次重发。

#### 组播 MAC 地址生成

```
默认 MAC = 01:0C:CD:01:XX:YY
其中 XX = (app_id >> 8) & 0xFF
     YY = app_id & 0xFF
```

符合 IEC 61850 规定的 GOOSE 组播 MAC 地址范围 `01-0C-CD-01-00-00` ~ `01-0C-CD-01-01-FF`。

### GooseReceiver / GooseSubscription

```python
class GooseReceiver:
    """GOOSE 接收器
    
    核心属性:
    - interface: 网络接口名称
    - _subscriptions: 订阅字典 (go_cb_ref -> GooseSubscription)
    
    核心方法:
    - add_subscription() / remove_subscription(): 订阅管理
    - set_callback(): 设置报文接收回调
    - start() / stop(): 启停 Receiver 和监控线程
    - get_status(): 获取完整状态信息
    """

class GooseSubscription:
    """GOOSE 订阅信息
    
    核心属性:
    - go_cb_ref: 控制块引用
    - app_id: APPID 过滤
    - state: 订阅状态 (init/connected/lost/error)
    - st_num / sq_num: 最新序号
    - data_values: 数据集值列表
    - last_update: 最后更新时间
    """
```

#### 订阅状态机

```
         启动接收
 init ──────────→ connected
                     │
                     │ 超时 (TAL)
                     ↓
                   lost ←──────┐
                     │         │
                     │ 收到报文 │ 超时
                     ↓         │
                  connected ───┘
                     │
                     │ 解析错误
                     ↓
                   error
```

| 状态 | 含义 | 颜色 |
|------|------|------|
| `init` | 初始化，尚未收到报文 | 灰色 (#909399) |
| `connected` | 已收到有效 GOOSE 报文 | 绿色 (#67C23A) |
| `lost` | 超时未收到报文 (超过 TAL) | 橙色 (#E6A23C) |
| `error` | 报文解析错误 | 红色 (#F56C6C) |

#### MMS 数据类型解析映射

| MMS 类型常量 | 类型值 | 解析类型 | Python 类型 |
|-------------|--------|---------|-------------|
| MMS_BOOLEAN | 0 | boolean | bool |
| MMS_BIT_STRING | 1 | bitstring | int |
| MMS_INTEGER | 2 | integer | int32 |
| MMS_UNSIGNED | 3 | unsigned | uint32 |
| MMS_FLOAT | 4 | float | float |
| MMS_VISIBLE_STRING | 10 | string | str |
| MMS_UTC_TIME | 17 | timestamp | int (ms) |

### GooseManager

```python
class GooseManager:
    """GOOSE 资源管理器 (Singleton)
    
    管理:
    - _publishers: Dict[str, GoosePublisher]   # id -> publisher
    - _receivers: Dict[str, GooseReceiver]     # id -> receiver
    - _gocbref_to_pid: Dict[str, str]          # go_cb_ref -> publisher_id
    - _interface_to_rid: Dict[str, str]        # interface -> receiver_id
    
    提供方法:
    - create_publisher / list_publishers / get_publisher_status
    - update_publisher / delete_publisher
    - start_publisher / stop_publisher / publish_now
    - add_publisher_entry / update_publisher_entry / remove_publisher_entry
    - create_receiver / list_receivers / get_receiver_status
    - delete_receiver / start_receiver / stop_receiver
    - add_subscription / remove_subscription
    - stop_all / get_all_status
    """
```

**Publisher ID 策略**：优先使用 `go_cb_ref` 作为 Publisher ID，若为空则使用 UUID。相同 `go_cb_ref` 不会重复创建。

**Receiver ID 策略**：使用网络接口名作为 Receiver ID。同一接口只允许一个 Receiver。

---

## API 设计

所有 GOOSE API 挂载在 `/api/channels/goose/` 前缀下，采用 RESTful 风格设计，请求参数使用 JSON body 传递，通过 Pydantic V2 模型进行验证。

### Publisher 端点

| 方法 | 路径 | 说明 | 请求体 |
|------|------|------|--------|
| POST | `/goose/publishers` | 创建 Publisher | `GoosePublisherCreate` |
| GET | `/goose/publishers` | 列出所有 Publisher | - |
| GET | `/goose/publishers/{id}` | 获取 Publisher 状态 | - |
| PUT | `/goose/publishers/{id}` | 更新 Publisher 配置 | `GoosePublisherUpdate` |
| DELETE | `/goose/publishers/{id}` | 删除 Publisher | - |
| POST | `/goose/publishers/{id}/start` | 启动 Publisher | - |
| POST | `/goose/publishers/{id}/stop` | 停止 Publisher | - |
| POST | `/goose/publishers/{id}/publish` | 立即发布 GOOSE 报文 | - |
| POST | `/goose/publishers/{id}/entries` | 添加数据集条目 | `GoosePublisherEntryAdd` |
| PUT | `/goose/publishers/{id}/entries/{index}` | 更新数据集条目值 | `GoosePublisherEntryUpdate` |
| DELETE | `/goose/publishers/{id}/entries/{index}` | 移除数据集条目 | - |

### Receiver 端点

| 方法 | 路径 | 说明 | 请求体 |
|------|------|------|--------|
| POST | `/goose/receivers` | 创建 Receiver | `GooseReceiverCreate` |
| GET | `/goose/receivers` | 列出所有 Receiver | - |
| GET | `/goose/receivers/{id}` | 获取 Receiver 状态 | - |
| DELETE | `/goose/receivers/{id}` | 删除 Receiver | - |
| POST | `/goose/receivers/{id}/start` | 启动 Receiver | - |
| POST | `/goose/receivers/{id}/stop` | 停止 Receiver | - |
| POST | `/goose/receivers/{id}/subscriptions` | 添加订阅 | `GooseSubscriptionCreate` |
| DELETE | `/goose/receivers/{id}/subscriptions` | 移除订阅 | `GooseSubscriptionRemove` |

### Pydantic Schema 设计

#### GoosePublisherCreate

| 字段 | 类型 | 必填 | 默认值 | 校验规则 |
|------|------|------|--------|---------|
| interface | str | 否 | "eth0" | min_length=1 |
| go_cb_ref | str | **是** | - | min_length=1 |
| go_id | str | 否 | "" | - |
| data_set_ref | str | 否 | "" | - |
| app_id | int | 否 | 0x0001 | ge=0, le=0xFFFF |
| conf_rev | int | 否 | 1 | ge=1 |
| time_allowed_to_live | int | 否 | 1000 | ge=100, le=60000 |
| dst_mac | List[int] \| None | 否 | None | 长度=6, 每字节 0-255 |
| vlan_id | int | 否 | 0 | ge=0, le=4095 |
| vlan_prio | int | 否 | 4 | ge=0, le=7 |
| simulation | bool | 否 | True | - |
| entries | List[GooseDataSetEntryCreate] | 否 | [] | - |

#### GooseDataSetEntryCreate

| 字段 | 类型 | 必填 | 默认值 | 校验规则 |
|------|------|------|--------|---------|
| name | str | **是** | - | min_length=1, max_length=128 |
| value | bool \| int \| float \| str | 否 | False | - |
| iec_type | str | 否 | "boolean" | 枚举: boolean/integer/float/string/bitstring/timestamp |

#### GooseReceiverCreate

| 字段 | 类型 | 必填 | 默认值 | 校验规则 |
|------|------|------|--------|---------|
| interface | str | 否 | "eth0" | min_length=1 |
| subscriptions | List[GooseSubscriptionCreate] | 否 | [] | - |

#### GooseSubscriptionCreate

| 字段 | 类型 | 必填 | 默认值 | 校验规则 |
|------|------|------|--------|---------|
| go_cb_ref | str | **是** | - | min_length=1 |
| app_id | int \| None | 否 | None | ge=0, le=0xFFFF |
| dst_mac | List[int] \| None | 否 | None | 长度=6, 每字节 0-255 |
| description | str | 否 | "" | - |

### 请求示例

**创建 GOOSE Publisher：**

```json
POST /api/channels/goose/publishers
{
  "interface": "eth0",
  "go_cb_ref": "LD0/LLN0$GO$gcb1",
  "go_id": "gcb1",
  "data_set_ref": "LD0/LLN0$dsGOOSE1",
  "app_id": 1,
  "conf_rev": 1,
  "time_allowed_to_live": 1000,
  "simulation": true,
  "entries": [
    { "name": "stVal", "value": true, "iec_type": "boolean" },
    { "name": "q", "value": 0, "iec_type": "integer" },
    { "name": "t", "value": 0, "iec_type": "timestamp" }
  ]
}
```

**创建 GOOSE Receiver 并添加订阅：**

```json
POST /api/channels/goose/receivers
{
  "interface": "eth0",
  "subscriptions": [
    {
      "go_cb_ref": "LD0/LLN0$GO$gcb1",
      "app_id": 1,
      "description": "断路器跳闸信号"
    }
  ]
}
```

---

## 文件清单

### 后端 — 新增文件

| 文件 | 说明 |
|------|------|
| `src/proto/iec61850/goose_publisher.py` | GOOSE Publisher 核心封装，支持数据集管理、序号管理、定时重发 |
| `src/proto/iec61850/goose_subscriber.py` | GOOSE Subscriber/Receiver 封装，支持多订阅、回调通知、超时检测、数据集解析 |
| `src/proto/iec61850/goose_manager.py` | GOOSE 资源管理器 (Singleton)，统一管理 Publisher/Receiver 生命周期 |
| `src/web/api/schemas/goose.py` | GOOSE Pydantic V2 数据模型，所有请求/响应 Schema |
| `src/web/api/channel/goose.py` | GOOSE Web API 路由 (17 个端点) |

### 后端 — 修改文件

| 文件 | 修改内容 |
|------|---------|
| `src/web/api/channel/__init__.py` | 注册 `goose_router` |
| `src/web/api/schemas/__init__.py` | 导出 GOOSE Schema |
| `src/web/app.py` | startup 时初始化 `GooseManager` 并挂载到 `app.state.goose_manager` |
| `src/web/api/channel/iec61850.py` | `iec61850-structure` 端点返回 GOOSE Publisher/Receiver 信息 |

### 前端 — 新增文件

| 文件 | 说明 |
|------|------|
| `front/src/api/gooseApi.ts` | GOOSE API 调用层，完整 TypeScript 类型定义 + 17 个 API 函数 |
| `front/src/components/goose/GooseManager.vue` | GOOSE 管理主组件 (双 Tab: Publisher/Receiver)，含创建/编辑/启停/数据集/订阅对话框 |
| `front/src/views/GooseView.vue` | GOOSE 页面视图 |

### 前端 — 修改文件

| 文件 | 修改内容 |
|------|---------|
| `front/src/constants/api.ts` | 新增 `GOOSE_API` 常量 (17 个 API 路径) |
| `front/src/constants/protocol.ts` | 新增 `GOOSE_SUB_STATE`、`GOOSE_STATE_COLOR`、`GOOSE_STATE_LABEL`、`GOOSE_IEC_TYPE_OPTIONS` |
| `front/src/router/index.ts` | 新增 `/goose` 路由指向 `GooseView.vue` |
| `front/src/composables/useIec61850Tree.ts` | GOOSE 分类项支持 `linkTo` 导航；`TreeNode` 类型新增 `linkTo` 字段 |
| `front/src/views/SideBar.vue` | 处理 GOOSE 节点 `linkTo` 导航到 `/goose` 页面 |
| `front/src/components/header/AppHeader.vue` | 新增 GOOSE 管理导航按钮 + Connection 图标；面包屑支持 GOOSE 路由 |

---

## 线程模型

```
┌─────────────────────────────────────────────────────────┐
│                    主线程 (FastAPI)                       │
│  - HTTP 请求处理                                         │
│  - GooseManager CRUD 操作                                │
│  - app.state.goose_manager 状态管理                      │
└──────────┬──────────────────────────┬───────────────────┘
           │                          │
    ┌──────▼──────┐           ┌──────▼──────┐
    │ Publisher   │           │ Receiver    │
    │ 重发线程     │           │ 接收线程     │
    │ (daemon)    │           │ (C 线程)    │
    │             │           │             │
    │ 定时调用     │           │ 回调触发     │
    │ publish()   │           │ _on_goose   │
    │             │           │ _message()  │
    └─────────────┘           └──────┬──────┘
                                    │
                             ┌──────▼──────┐
                             │ 状态监控线程  │
                             │ (daemon)    │
                             │             │
                             │ 1秒轮询     │
                             │ 检测超时     │
                             └─────────────┘
```

### 线程安全保证

- `GoosePublisher`：使用 `threading.Lock` 保护 `_entries`、`_st_num`、`_sq_num` 等共享状态
- `GooseReceiver`：使用 `threading.Lock` 保护 `_subscriptions` 字典
- `GooseManager`：所有操作委托给 Publisher/Receiver，不维护独立可变状态
- 重发线程和监控线程均为 daemon 线程，随主进程退出

---

## IEC 61850 侧边栏集成

GOOSE 功能集成到现有 IEC61850 设备的侧边栏树结构中：

1. 后端 `iec61850-structure` 端点返回的 `GOOSE` 分类列表中，填充当前 GooseManager 中的 Publisher 和 Receiver 信息
2. 前端 `useIec61850Tree` 中，GOOSE 分类条目携带 `linkTo: '/goose'` 属性
3. 用户点击 GOOSE 树节点时，通过 `router.push('/goose')` 导航到 GOOSE 管理页面

### 导航入口

| 入口 | 位置 | 说明 |
|------|------|------|
| 顶部导航栏 | AppHeader Connection 图标 | 全局 GOOSE 管理入口 |
| 侧边栏 | IEC61850 设备 → GOOSE 节点 | 设备级 GOOSE 入口 |
| URL | `/goose` | 直接访问 |

---

## 依赖要求

### Python 依赖

| 包 | 版本要求 | 说明 |
|----|---------|------|
| pyiec61850 | 可选 | libiec61850 Python 绑定，提供 GOOSE Publisher/Receiver 底层实现 |
| pydantic | ≥2.0 | 数据模型验证 |
| fastapi | - | Web 框架 |

> **注意**：`pyiec61850` 为可选依赖，未安装时 GOOSE 功能自动降级为不可用状态，不影响其他功能。

### 前端依赖

无新增依赖，使用项目已有的 Vue 3 + Element Plus + TypeScript。

---

## 配置参数说明

### GOOSE Publisher 关键参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| interface | eth0 | 发送 GOOSE 报文的网络接口 |
| go_cb_ref | (必填) | GOOSE 控制块引用，MMS 格式如 `LD0/LLN0$GO$gcb1` |
| go_id | "" | GOOSE 标识符，用于接收端识别 |
| data_set_ref | "" | 数据集引用，如 `LD0/LLN0$dsGOOSE1` |
| app_id | 0x0001 | APPID，用于 GOOSE 报文标识和组播 MAC 生成 |
| conf_rev | 1 | 配置修订号，配置变更时递增 |
| time_allowed_to_live | 1000 | 报文存活时间 (ms)，接收端据此判断超时 |
| simulation | true | 仿真模式标记，测试时设为 true |
| vlan_id | 0 | VLAN ID，0 表示不带 VLAN 标签 |
| vlan_prio | 4 | VLAN 优先级 (0-7)，GOOSE 通常使用 4-7 |

### GOOSE Receiver 关键参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| interface | eth0 | 监听 GOOSE 报文的网络接口 |
| go_cb_ref | (必填) | 要订阅的 GOOSE 控制块引用 |
| app_id | null | APPID 过滤，null 表示不过滤 |
| dst_mac | null | 目标 MAC 过滤，null 表示不过滤 |

---

## 操作约束

| 操作 | 约束条件 | 原因 |
|------|---------|------|
| 更新 Publisher 配置 | Publisher 未运行 | 运行中配置可能导致报文不一致 |
| 添加/移除 Receiver 订阅 | Receiver 未运行 | 底层 C 库需要重启才能更新订阅列表 |
| 同一 go_cb_ref 创建 Publisher | 不允许重复 | 避免同一 GoCB 发布冲突 |
| 同一 interface 创建 Receiver | 不允许重复 | 避免网络接口抢占 |
| 启动 Publisher | pyiec61850 已安装 | 依赖底层 C 库 |
| 启动 Receiver | pyiec61850 已安装 | 依赖底层 C 库 |

---

## 未来扩展

1. **持久化**：将 GOOSE 配置保存到数据库，重启后自动恢复
2. **GOOSE 与测点联动**：将 GOOSE 数据集条目与 EMS 测点绑定，实现测点值变化自动触发 GOOSE 发布
3. **GOOSE 报文抓包**：集成报文捕获和解析功能
4. **GOOSE SCL 导入**：支持从 SCL/ICD 文件自动创建 GOOSE 配置
5. **GOOSE 仿真场景**：预定义 GOOSE 事件序列（如断路器跳闸 → 重合闸），一键执行
6. **WebSocket 实时推送**：通过 WebSocket 将 GOOSE 状态变化实时推送到前端，替代轮询
