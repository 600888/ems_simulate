# 安装部署

本文档介绍 EMS Simulate 的详细安装和生产环境部署方法。

## 开发环境安装

### 1. 安装 Python 依赖

项目使用 `pyproject.toml` 声明依赖，并通过 `uv`（`uv.lock`）锁定版本，推荐使用 `uv` 安装：

```bash
# 安装 uv（如未安装）
pip install uv

# 创建虚拟环境并安装依赖（含开发/测试依赖）
uv sync --extra dev

# 激活虚拟环境 (Windows)
.venv\Scripts\activate

# 激活虚拟环境 (Linux/Mac)
source .venv/bin/activate
```

> [!NOTE]
> `uv sync` 会自动创建 `.venv` 虚拟环境并依据 `uv.lock` 安装锁定版本的依赖，无需手动执行 `pip install`。

### 2. 前端构建

```bash
cd front

# 安装依赖
npm install

# 开发模式
npm run dev

# 构建生产版本
npm run build
```

前端构建产物输出到项目根目录的 `www/` 目录（由 `front/vite.config.ts` 中的 `outDir` 配置），后端启动时会自动挂载。

## 生产环境部署

### 方式一：Debian/Ubuntu 使用 deb 包（推荐）

对于 Linux 生产环境，推荐使用打包好的 `.deb` 安装包。安装后会自动注册为 systemd 服务 `ems-simulate-web`（安装时即自动启动并设置开机自启）：

```bash
# 安装（文件名中的版本号以实际构建产物为准）
sudo dpkg -i ems-simulate-web_4.4.0_amd64.deb

# 启动服务
sudo systemctl start ems-simulate-web

# 停止服务
sudo systemctl stop ems-simulate-web

# 重启服务
sudo systemctl restart ems-simulate-web

# 查看状态
sudo systemctl status ems-simulate-web

# 设置开机自启
sudo systemctl enable ems-simulate-web
```

详细的打包与安装步骤见 [Debian 打包与部署指南](./packaging_deb.md)。

### 方式二：源码手动部署

#### 1. 构建前端

```bash
cd front
npm run build
```

构建产物将输出到项目根目录的 `www/` 目录。

#### 2. 启动后端服务

后端入口为 `start_back_end.py`，默认监听 `127.0.0.1:8991`，并自动挂载 `www/` 下的前端静态文件：

```bash
# 启动服务（默认端口 8991）
python start_back_end.py

# 指定端口
python start_back_end.py --port 8991

# 指定数据根目录（数据库、日志、配置等均存放于该目录下）
python start_back_end.py --root-dir ./data
```

#### 3. 使用 Nginx 反向代理

如需通过域名/80 端口对外提供服务，可将 Nginx 配置为反向代理：

```nginx
server {
    listen 80;
    server_name your-domain.com;

    # 前端静态文件
    location / {
        root /path/to/ems_simulate/www;
        try_files $uri $uri/ /index.html;
    }

    # 后端 API 代理
    location /api {
        proxy_pass http://127.0.0.1:8991;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # WebSocket 代理
    location /ws {
        proxy_pass http://127.0.0.1:8991;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

> [!NOTE]
> 后端服务默认监听 `127.0.0.1:8991`，可通过 `config.ini` 的 `[server] port` 修改。示例中 `proxy_pass` 的端口需与后端实际端口保持一致。

## Docker 部署（可选）

> [!NOTE]
> Docker 支持正在开发中，敬请期待。

## 常见问题

### 端口冲突

- **HTTP 服务端口**：默认 `8991`（`config.ini` 中 `[server] port`），源码运行时可使用 `start_back_end.py --port` 指定。
- **协议模拟端口**：Modbus TCP `502`、IEC 104 `2404`、DLT645 `8899`。如被占用，请修改 `config.ini` 中的端口配置。

### 数据库位置

SQLite 数据库默认存储在 `data/` 目录下（源码运行时为项目根目录下的 `data/`；使用 `--root-dir` 时位于指定目录）。确保该目录有写入权限。
