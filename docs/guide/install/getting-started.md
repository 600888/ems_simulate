# 快速开始

本指南帮助您在 **5 分钟内**完成 EMS Simulate 的安装并模拟出第一个设备。

## 方式一：桌面客户端（推荐）

### 1. 获取安装包

从以下任一渠道获取 Windows 安装包：

- **微软应用商店**：搜索 "EMS Simulate" 或访问 [商店页面](https://apps.microsoft.com/detail/9N3MMM0CH93F)；
- **安装包分发**：直接运行项目提供的 `CDY.emsSimulate_<版本>_x64.msix` 安装包。

### 2. 安装

双击 MSIX 安装包，按提示完成安装（Windows 10/11 均支持）。

### 3. 启动

从开始菜单启动 **EMS Simulate**，应用会自动启动后端服务并打开主界面。

### 4. 添加第一个设备

1. 点击左侧工具栏的"添加设备"；
2. 选择协议（如 **Modbus TCP**）与连接方式（服务端）；
3. 填写设备名称，保存。

### 5. 添加测点并启动模拟

1. 进入设备详情，点击"添加测点"（或选择"标准点表/Excel 导入"批量生成）；
2. 点击"开启设备"，设备即开始模拟运行；
3. 在测点表格中展开行，可为测点设置**数据模拟方式**（随机、正弦波、自增等）。

### 6. 查看报文

点击设备右上角的"报文"图标，实时查看该设备与对端交互的通讯报文。

> ✅ 至此，您已完成第一个设备的模拟。接下来可参考各协议的操作指南：
>
> - [Modbus 操作指南](../protocols/modbus/operation)
> - [IEC 104 操作指南](../protocols/iec104/operation)
> - [DL/T 645 操作指南](../protocols/dlt645/operation)
> - [IEC 61850 操作指南](../protocols/iec61850/operation)

## 方式二：源码运行（开发者）

### 1. 环境要求

| 软件 | 最低版本 | 说明 |
|------|----------|------|
| Python | 3.11+ | 后端运行环境 |
| Node.js | 18+ | 前端构建/开发环境 |
| uv | 最新版 | Python 依赖管理（安装 `pip install uv`） |

### 2. 克隆项目并安装依赖

```bash
git clone https://github.com/600888/ems_simulate.git
cd ems_simulate

# 创建虚拟环境并安装后端依赖（含开发/测试依赖）
uv sync --extra dev

# 安装前端依赖
cd front
npm install
```

### 3. 启动服务

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

### 4. 访问系统

- 开发模式：浏览器访问 `http://localhost:5173`
- 生产模式（源码）：访问 `http://localhost:8991`（后端自动挂载 `www/` 前端静态文件）

## 下一步

- [安装指南](./installation.md) - 详细的生产环境部署指南
- [配置说明](./configuration.md) - 了解配置选项
- [协议支持](../protocols/) - 各协议介绍、操作与报文查看
- [测点类型](../point/point-types.md) - 了解四种测点类型
