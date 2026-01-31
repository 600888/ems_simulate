# 测点操作 API

测点数据读写相关的 API 接口文档。

## 获取测点表格数据

```http
GET /api/device/table?channel_id={id}&page={page}&page_size={size}
```

**查询参数:**

| 参数 | 类型 | 说明 |
|------|------|------|
| channel_id | int | 设备通道 ID |
| page | int | 页码，从 1 开始 |
| page_size | int | 每页数量 |
| frame_type | int | 测点类型过滤（可选） |

**响应示例:**

```json
{
  "code": 200,
  "data": {
    "total": 100,
    "items": [
      {
        "id": 1,
        "name": "A相电压",
        "address": 0,
        "value": 220.5,
        "frame_type": 0,
        "decode": "0x42"
      }
    ]
  }
}
```

## 更新测点值

```http
PUT /api/device/update_point
Content-Type: application/json
```

**请求体:**

```json
{
  "point_id": 1,
  "value": 230.0,
  "frame_type": 0
}
```

## 手动读取单个测点

```http
POST /api/device/read_single_point
Content-Type: application/json
```

**请求体:**

```json
{
  "channel_id": 1,
  "point_id": 1,
  "frame_type": 0
}
```

## 测点类型枚举

| 值 | 类型 | 说明 |
|----|------|------|
| 0 | YC | 遥测（模拟量测量） |
| 1 | YX | 遥信（开关量状态） |
| 2 | YK | 遥控（开关量命令） |
| 3 | YT | 遥调（模拟量命令） |
