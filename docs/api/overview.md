# API 概述

EMS Simulate 提供 RESTful API 用于设备管理和数据操作。

## API 基础

**基础 URL:** `http://localhost:8000/api`

**响应格式:** JSON

**通用响应结构:**

```json
{
  "code": 200,
  "message": "success",
  "data": { ... }
}
```

## API 分类

### 设备管理 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/channel/list` | GET | 获取设备通道列表 |
| `/channel/add` | POST | 添加设备通道 |
| `/channel/update` | PUT | 更新设备通道 |
| `/channel/delete` | DELETE | 删除设备通道 |
| `/device/start` | POST | 启动设备 |
| `/device/stop` | POST | 停止设备 |

### 测点操作 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/device/table` | GET | 获取测点表格数据 |
| `/device/update_point` | PUT | 更新测点值 |
| `/device/read_single_point` | POST | 手动读取单个测点 |

### 数据导入导出 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/data/export` | GET | 导出测点配置 |
| `/data/import` | POST | 导入测点配置 |

## WebSocket 接口

用于实时数据推送：

**端点:** `ws://localhost:8000/ws/{channel_id}`

**消息格式:**

```json
{
  "type": "point_update",
  "data": {
    "point_id": 1,
    "value": 100.5
  }
}
```

---

详细的 API 文档请参考：
- [设备管理 API](./device.md)
- [测点操作 API](./points.md)
