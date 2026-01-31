# 设备管理 API

设备管理相关的 API 接口文档。

## 获取设备通道列表

```http
GET /api/channel/list
```

**响应示例:**

```json
{
  "code": 200,
  "data": [
    {
      "id": 1,
      "name": "PCS模拟器",
      "protocol_type": 1,
      "conn_type": 1,
      "ip": "0.0.0.0",
      "port": 502,
      "status": "running"
    }
  ]
}
```

## 添加设备通道

```http
POST /api/channel/add
Content-Type: application/json
```

**请求体:**

```json
{
  "name": "新设备",
  "protocol_type": 1,
  "conn_type": 1,
  "ip": "0.0.0.0",
  "port": 503
}
```

## 启动设备

```http
POST /api/device/start
Content-Type: application/json
```

**请求体:**

```json
{
  "channel_id": 1
}
```

## 停止设备

```http
POST /api/device/stop
Content-Type: application/json
```

**请求体:**

```json
{
  "channel_id": 1
}
```

## 协议类型枚举

| 值 | 协议 |
|----|------|
| 1 | Modbus TCP |
| 2 | Modbus RTU |
| 3 | IEC 104 |
| 4 | DLT645 |

## 连接类型枚举

| 值 | 类型 |
|----|------|
| 0 | RTU 主站 |
| 1 | TCP 服务端 |
| 2 | TCP 客户端 |
| 3 | RTU 从站 |
