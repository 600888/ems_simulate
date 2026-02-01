# 配置说明

EMS Simulate 支持通过配置文件和环境变量进行灵活配置。

## 配置文件

主配置文件位于项目根目录的 `config.ini`：

```ini
[server]
host = 0.0.0.0
port = 8000

[database]
type = sqlite
path = data/ems.db

[modbus]
default_port = 502

[iec104]
default_port = 2404

[dlt645]
default_port = 8899
```

## 数据库配置

### SQLite（默认）

无需额外配置，数据库文件自动创建在 `data/` 目录下。

### MySQL

修改 `config.ini`：

```ini
[database]
type = mysql
host = localhost
port = 3306
user = your_user
password = your_password
database = ems_simulate
```

## 日志配置

日志配置位于 `src/config/log/` 目录，支持：

- 日志级别调整
- 文件滚动策略
- 控制台和文件输出

## 协议默认端口

| 协议 | 服务端端口 | 说明 |
|------|------------|------|
| Modbus TCP | 502 | 标准 Modbus TCP 端口 |
| IEC 104 | 2404 | 标准 IEC 104 端口 |
| DLT645 | 8899 | 自定义端口 |

## 前端配置

前端开发环境配置文件 `front/.env.development`：

```properties
VITE_API_BASE_URL=http://localhost:8991
```

生产环境创建 `front/.env.production` 文件配置 API 地址。
