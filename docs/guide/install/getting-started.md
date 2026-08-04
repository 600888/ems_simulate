# 快速开始

本指南将帮助您快速部署和运行 EMS Simulate 能源管理系统模拟器。

## 环境要求

在开始之前，请确保您的系统满足以下要求：

| 软件 | 最低版本 | 说明 |
|------|----------|------|
| Python | 3.11+ | 后端运行环境 |
| Node.js | 18+ | 前端构建/开发环境 |
| uv | 最新版 | Python 依赖管理（安装 `pip install uv`） |

## 安装步骤

### 1. 克隆项目

```bash
git clone https://github.com/600888/ems_simulate.git
cd ems_simulate
```

### 2. 安装 Python 依赖

项目使用 `pyproject.toml` 声明依赖，并以 `uv.lock` 锁定版本，请使用 `uv` 安装：

```bash
# 创建虚拟环境并安装依赖（含开发/测试依赖）
uv sync --extra dev
```

### 3. 安装前端依赖

```bash
cd front
npm install
```

### 4. 启动服务

**方式一：源码运行（开发调试）**

在两个终端窗口中分别执行：

**终端 1 - 启动后端服务：**
```bash
python start_back_end.py
```

**终端 2 - 启动前端开发服务器：**
```bash
cd front
npm run dev
```

**方式二：Linux 生产部署（deb 包 + systemd）**

构建 `.deb` 安装包并安装后，服务会注册为 systemd 服务，直接使用 `systemctl` 管理：

```bash
sudo dpkg -i build/dist_deb/ems-simulate-web_<版本号>_amd64.deb
sudo systemctl status ems-simulate-web
```

详细步骤见 [Debian 打包与部署指南](./packaging_deb.md)。

### 5. 访问系统

- 开发模式：打开浏览器访问 `http://localhost:5173`
- 生产模式（源码）：访问 `http://localhost:8991`（后端自动挂载 `www/` 前端静态文件）

## 目录结构

```
ems_simulate/
├── src/                    # 后端源码
│   ├── config/            # 配置管理
│   ├── data/              # 数据层 (DAO/Service)
│   ├── device/            # 设备模拟器核心
│   ├── enums/             # 枚举和数据结构
│   ├── proto/             # 协议实现
│   └── web/               # Web API
├── front/                  # 前端源码 (Vue3)
├── www/                    # 前端构建产物（vite build 输出）
├── data/                   # SQLite 数据库
├── start_back_end.py      # 后端入口
├── pyproject.toml         # Python 依赖与配置
└── uv.lock                # Python 依赖锁定文件
```

## 下一步

- [安装部署](./installation.md) - 详细的生产环境部署指南
- [配置说明](./configuration.md) - 了解配置选项
- [测点类型](../point/point-types.md) - 了解四种测点类型
