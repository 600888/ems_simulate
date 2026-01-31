# 快速开始

本指南将帮助您快速部署和运行 EMS Simulate 能源管理系统模拟器。

## 环境要求

在开始之前，请确保您的系统满足以下要求：

| 软件 | 最低版本 |
|------|----------|
| Python | 3.11+ |
| Node.js | 18+ |
| pip | 最新版本 |
| npm | 最新版本 |

## 安装步骤

### 1. 克隆项目

```bash
git clone https://github.com/600888/ems_simulate.git
cd ems_simulate
```

### 2. 安装 Python 依赖

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 3. 安装前端依赖

```bash
cd front
npm install
```

### 4. 启动服务

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

### 5. 访问系统

打开浏览器访问 [http://localhost:5173](http://localhost:5173)

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
├── data/                   # SQLite 数据库
├── start_back_end.py      # 后端入口
└── requirements.txt       # Python 依赖
```

## 下一步

- [安装部署](./installation.md) - 详细的生产环境部署指南
- [配置说明](./configuration.md) - 了解配置选项
- [测点类型](./point-types.md) - 了解四种测点类型
