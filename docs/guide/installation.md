# 安装部署

本文档介绍 EMS Simulate 的详细安装和生产环境部署方法。

## 开发环境安装

### 使用虚拟环境（推荐）

```bash
# 创建虚拟环境
python -m venv .venv

# 激活虚拟环境 (Windows)
.venv\Scripts\activate

# 激活虚拟环境 (Linux/Mac)
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 前端构建

```bash
cd front

# 安装依赖
npm install

# 开发模式
npm run dev

# 构建生产版本
npm run build
```

## 生产环境部署

### 1. 构建前端

```bash
cd front
npm run build
```

构建产物将输出到 `front/dist` 目录。

### 2. 部署后端

使用 `control.sh` 脚本管理服务：

```bash
# 启动服务
./control.sh start

# 停止服务
./control.sh stop

# 重启服务
./control.sh restart

# 查看状态
./control.sh status
```

### 3. 使用 Nginx 反向代理

配置示例：

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
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # WebSocket 代理
    location /ws {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

## Docker 部署（可选）

> [!NOTE]
> Docker 支持正在开发中，敬请期待。

## 常见问题

### 端口冲突

如果默认端口 (502, 2404, 8899) 被占用，请修改 `config.ini` 中的端口配置。

### 数据库位置

SQLite 数据库默认存储在 `data/` 目录下。确保该目录有写入权限。
