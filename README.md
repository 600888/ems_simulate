# EMS Simulate - 能源管理系统模拟器

一个用于模拟能源管理系统（EMS）中关键设备行为的软件系统，主要用于测试和开发场景。系统支持多种工业通信协议（Modbus TCP/RTU、IEC 60870-5-101/104、DL/T 645-2007、IEC 61850、DNP3），可模拟真实工业设备（如PCS储能变流器、BMS电池管理系统、电表、断路器等）的数据交互。

> 📖 **[查看在线文档 / Online Documentation](https://600888.github.io/ems_simulate/)**

---

## 🏪 Microsoft Store

EMS Simulate 已上架微软应用商店，可直接在 Windows 10/11 上安装使用。

[![Microsoft Store](resources/img/microsoft.png)](https://apps.microsoft.com/detail/9N3MMM0CH93F?hl=zh-cn&gl=CN&ocid=pdpshare)

> 点击上方图片，或 [直接访问 Microsoft Store 下载页面](https://apps.microsoft.com/detail/9N3MMM0CH93F?hl=zh-cn&gl=CN&ocid=pdpshare)。

---

## 功能特性

| 功能 | 说明 |
|------|------|
| **多协议联调** | Modbus TCP/RTU、IEC 60870-5-101/104、DL/T 645-2007、IEC 61850、DNP3，支持设备模拟与客户端采集 |
| **设备管理** | 设备分组与子分组、通道与从站管理、启停、连接监视；支持批量复制及名称、IP、端口偏移配置 |
| **测点管理** | YC/YX/YK/YT 分类管理、测点编辑、Excel 点表导入与导出、协议属性配置和运行时更新 |
| **数据模拟** | 固定值、随机、递增、递减、正弦波、斜坡、脉冲；支持单点配置、批量配置和模拟数据监视 |
| **读取与控制** | 单点读取、批量读取、后台自动读取，以及各协议支持的遥控、遥调操作 |
| **测点联动** | 乘法/加法系数、自定义公式、跨设备测点映射，构建设备间的数据关联 |
| **变化追踪** | 查看测点变化时间、前后值和来源，区分手动修改、模拟、映射、协议写入和客户端读取 |
| **报文分析** | 在各协议设备下查看收发报文、原始字节与字段解析，辅助定位通信问题 |
| **IEC 61850 工具** | 数据模型与 DataSet、MMS、GOOSE、Reports、Files、定值组、日志，以及 SCL 文件管理和图形化建模 |
| **界面与运行环境** | Vue 3 Web 界面、Tauri 桌面客户端、中英文切换、界面缩放、存储目录配置及应用日志查看 |

## 技术架构

![技术架构图](resources/img/architecture.png)

### 技术栈

| 层次 | 技术 |
|------|------|
| **前端** | Vue 3, TypeScript, Vite, Element Plus |
| **后端** | Python 3.11+, FastAPI, SQLAlchemy |
| **协议** | pymodbus 3.12, c104, dlt645, pyiec61850-ng, pydnp3-pure，以及 IEC101 FT1.2 实现 |
| **数据库** | SQLite (默认) / MySQL |
| **桌面壳** | Tauri v2 + Rust |

---

## 界面展示

已有截图直接展示；待补截图以“截图待补”标记，并附建议文件名和图片语法。将截图放入 `resources/img/` 后，取消对应图片语法的 HTML 注释，即可替换占位说明。

### 通用功能

#### 设备与测点管理

1. **主界面** — 设备分组树 + 设备详情面板

   ![主界面与设备分组树](resources/img/1.png)

2. **添加设备分组**

   ![添加设备分组](resources/img/2.png)

3. **添加子设备组**

   ![添加子设备组](resources/img/3.png)

4. **新增设备** — 选择设备类型与协议

   ![新增设备](resources/img/4.png)

5. **展开列表行编辑测点值**

   ![展开测点并编辑数值](resources/img/5.png)

6. **设置数据模拟方式** — 随机 / 步进 / 固定值

   ![设置测点模拟方式](resources/img/6.png)

7. **编辑测点信息** — 地址、系数、解析码等

   ![编辑测点信息](resources/img/7.png)

#### 批量复制、从站与连接管理

支持复制单个或多个设备，配置名称前后缀、IP 和端口偏移；通过从站管理和连接监视查看设备通信状态。

> ![](resources/img/device-copy.png)

> ![](resources/img/device-connections.png)

#### 点表导入与导出

通过 Excel 模板批量配置测点，支持导出点表。仓库提供 [Modbus](data/point_csv/point_sample_modbus.xlsx)、[IEC104](data/point_csv/point_sample_iec104.xlsx)、[DL/T 645](data/point_csv/point_sample_dlt645.xlsx) 和 [DNP3](data/point_csv/point_sample_dnp3.xlsx) 示例点表。


![](resources/img/point-import-export.png)

#### 模拟配置与实时监视

支持固定值、随机、递增、递减、正弦波、斜坡、脉冲等模拟方式，可按测点设置参数，并批量选择参与模拟的测点。

![测点模拟配置](resources/img/simulate-config.png)

![模拟数据监视](resources/img/simulate-monitor.png)

客户端支持单点、批量和后台自动读取。自动读取在切换页面后继续运行，回到设备页面可恢复查看任务状态；停止设备时结束对应任务。

> ![](E:\github_project\ems_simulate\resources\img\point-auto-read.png)

#### 测点映射、公式与变化追踪

支持以多个源测点构建公式，并将结果映射到目标测点，实现跨设备、跨协议的数据联动。变化历史记录时间、前后值及变化来源，便于追查模拟和通信写入的结果。

> ![](resources/img/point-mapping.png)

> ![](E:\github_project\ems_simulate\resources\img\point-change-history.png)

#### 应用设置与日志

提供中英文切换、界面缩放、存储目录配置和应用运行日志查看。

> **应用设置** — 展示界面、语言和存储配置。
>
> ![](resources/img/settings.png)

> **应用日志** — 展示日志筛选和日志详情。
> ![](resources/img/logs.png)

---

### 协议模块

以下按协议介绍配置、数据操作与报文查看。各协议支持**服务端/从站**（模拟设备）和**客户端/主站**（采集或控制设备）角色，具体功能见对应模块。

#### Modbus TCP / RTU

工业自动化领域应用最广泛的通信协议，支持 TCP 网络连接和 RTU 串口连接两种模式。

| 属性 | TCP | RTU |
|------|-----|-----|
| 默认端口 | 502 | —（串口） |
| 数据操作 | 线圈、离散输入、保持寄存器、输入寄存器的读取及可写区写入 | 同 TCP |
| 解析码 | 8/16/32/64 位、大小端、字交换 | 同 TCP |


##### 设备配置与数据操作

![Modbus 设备配置](resources/img/modbus-add.png)

![Modbus 运行参数](resources/img/modbus-parameter.png)

![Modbus 协议操作](resources/img/modbus-operation.png)

> 支持线圈、离散输入、保持寄存器、输入寄存器四类数据区，内置完整解析码系统适配不同厂商设备。

##### 报文查看

![Modbus 报文查看](resources/img/modbus-message.png)

---

#### IEC 60870-5-104

电力系统远动通信标准协议，广泛用于变电站与调度中心之间的数据传输。

| 属性 | 说明 |
|------|------|
| 默认端口 | 2404 |
| 帧类型 | YC(遥测)、YX(遥信)、YK(遥控)、YT(遥调) |
| 品质描述 | IV/NT/SB/BL/OV 等标准品质位 |
| 传输原因 | 周期、自发、总召等 |

##### 参数配置与四遥操作

![IEC104 运行参数](resources/img/iec104-parameter.png)

![IEC104 协议操作](resources/img/iec104-operation.png)

> 支持四遥（YC/YX/YK/YT）、ASDU 类型配置与筛选、总召、时钟同步及品质描述符。

##### 报文查看

![IEC104 协议报文](resources/img/iec104-message.png)

---

#### IEC 60870-5-101

IEC104 的串行远动协议版本，与 IEC104 共用 ASDU、四遥点表、品质描述符、传送原因和数值换算。

| 属性 | 说明 |
|------|------|
| 传输介质 | 串口（主站 / 从站） |
| 链路层 | FT1.2 定长帧、变长帧、单字符确认、校验和、FCB/FCV |
| 地址长度 | 链路地址 1/2 字节、COT 1/2 字节、公共地址 1/2 字节、IOA 1~3 字节 |
| 应用功能 | 一级/二级数据轮询、总召唤、读命令、遥控/遥调、时钟同步、自发上送 |

> 默认采用非平衡传输模式；协议运行参数中可以配置地址宽度、响应超时与轮询间隔。

##### 参数配置与数据操作

> 📷 **IEC101 配置与操作** — 展示串口、链路地址、ASDU 地址宽度和四遥测点。
![](resources/img/iec101-config.png)

##### 报文查看

> 📷 **IEC101 报文查看** — 展示 FT1.2 收发帧及链路层、ASDU 字段解析。
![](E:\github_project\ems_simulate\resources\img\iec101-message.png)

---

#### DL/T 645-2007

中国电力行业多功能电能表通信协议标准，用于电表数据采集。

| 属性 | 说明 |
|------|------|
| 默认端口 | 8899 |
| 数据标识 | 按 DI 配置电能、功率、电压、电流等数据项 |
| 系数转换 | 乘法系数 + 加法系数 → 真实值 |

##### 电表配置与读写验证

![DLT645 设备配置](resources/img/dlt645-add.png)

![DLT645 操作](resources/img/dlt645-operation.png)

**DL/T645 协议测试** — 验证读取值与系数转换的正确性

![DLT645 读取与系数转换验证](resources/img/8.png)

> 支持电表数据项标识解析，自动应用乘法/加法系数转换真实值，提供客户端读取验证。

##### 报文查看

![DLT645 报文查看](resources/img/dlt645-message.png)

---

#### IEC 61850

面向智能变电站的设备模拟与联调，提供 MMS 数据访问、GOOSE 发布/订阅、报告控制、文件浏览、定值组和日志功能，并配套 SCL 管理与图形化建模工具。

| 子模块 | 功能 |
|--------|------|
| **MMS / Data Models** | 服务端建模、客户端模型发现、树形浏览、数据读写与模型导出 |
| **Data Sets** | 数据集成员浏览与批量读取 |
| **GOOSE** | 发布、订阅、接收历史与报文抓包解析 |
| **Reports** | BRCB/URCB 控制块配置、启停、GI 与报告接收 |
| **Files** | 客户端远程目录浏览和文件下载 |
| **Setting Groups** | 定值组发现、读取、选择编辑组、写入、确认和激活 |
| **Logs** | 日志控制块发现与启停、按时间范围查询日志 |
| **SCL 文件管理** | ICD/CID/SCD 文件上传、预览、校验、导入与差异对比 |
| **图形化建模** | 模型工程、LD/LN/DO/DA 编辑、CDC 模板、DataSet 与控制块配置、模型校验、版本管理及发布 |

##### MMS、数据模型与 DataSet

![IEC61850 设备配置](resources/img/iec61850-add.png)

![IEC61850 MMS 操作](resources/img/datamodel.png)

支持客户端模型发现和模型导出；DataSet 可用于组织测点并进行批量读取。

📷 **DataSet 与模型导出** — 展示模型导出格式。

![](resources/img/model-export.png)

##### GOOSE 发布、订阅与抓包

![IEC61850 GOOSE 配置](resources/img/goose.png)

![IEC61850 GOOSE 抓包](resources/img/goose-catch.png)

##### Reports 报告控制

![IEC61850 报告控制与接收](resources/img/reports.png)

##### Files 文件服务

![IEC61850 远程文件浏览与下载](resources/img/files.png)

##### Setting Groups 定值组

查看定值组控制块，选择编辑组、修改定值并确认，再激活目标定值组。

> 📷 **IEC61850 定值组** — 展示当前激活组、编辑组、定值列表及操作结果。
>
> ![](resources/img/iec61850-setting-groups.png)


##### Logs 日志服务

管理日志控制块

![](resources/img/iec61850-logs.png)


##### SCL 文件管理与图形化建模

支持 SCL 文件预览、导入和差异对比；图形化建模工作区可创建或导入模型工程，编辑逻辑设备、逻辑节点和数据对象，配置数据集与控制块，执行校验、保存版本并发布模型。

![IEC61850 SCL 导入建模](resources/img/iec61850-build.png)

##### 报文查看

**MMS 报文**

![IEC61850 MMS 报文查看](resources/img/mms-package.png)

**GOOSE 报文**

![IEC61850 GOOSE 报文解析](resources/img/goose-message.png)

**Reports 报文**

![IEC61850 报告报文解析](resources/img/report-packet.png)

---

#### DNP3

支持 **Master（主站/客户端）** 与 **Outstation（从站/服务端）**，用于 DNP3 设备的数据采集、事件上送与控制联调。

| 属性 | 说明 |
|------|------|
| 传输与端口 | TCP，默认端口 `20000`；支持 TLS 配置 |
| 站点配置 | 本端与对端站点地址、请求超时、重试与重连参数 |
| 点表配置 | 点索引、静态/事件 Variation、事件 Class、死区、品质位及时间戳 |
| 数据采集 | Class 0 完整性轮询、Class 1/2/3 事件读取、单点与批量读取 |
| 事件上送 | 可配置 Unsolicited 未请求上报，接收后同步测点值与运行元数据 |
| 控制操作 | CROB 二进制控制、模拟量输出，支持 Select/Operate 和 Direct Operate |
| 其他操作 | 时间同步、计数器冻结；支持 Excel 点表导入 |

##### 主从站配置与数据操作

![](resources/img/dnp3-operation.png)

##### 测点属性与事件配置

![](resources/img/dnp3-point-config.png)

##### 报文查看

> 📷 **DNP3 报文查看** — 展示收发方向、链路地址、应用功能码、对象组/变体及原始字节。
>
> ![](resources\img\dnp3-message.png)

---

## 快速开始

### 环境要求

- Python >= 3.11
- Node.js >= 18
- uv、npm、Git（部分 Python 协议依赖从 Git 仓库安装）

### 安装依赖

在项目根目录安装 Python 依赖并启动后端：

```bash
# 如未安装 uv，先执行：pip install uv
uv sync --extra dev
uv run python start_back_end.py
```

另开一个终端，从项目根目录启动前端：

```bash
cd front
npm install
npm run dev
```

在浏览器中打开 Vite 输出的本地地址。后端配置见 [配置说明](docs/guide/install/configuration.md)。

### Tauri 桌面应用构建

Windows 构建需安装 Rust、MSVC 构建工具及 Tauri CLI。使用仓库打包脚本构建前端、Python 后端及桌面客户端：

```powershell
# 在项目根目录执行
uv sync --extra dev --extra build
npm install -g @tauri-apps/cli

# 构建 Windows 安装包
.\scripts\build_tauri_windows.ps1
```

脚本默认生成 MSI 安装包；MSIX 打包入口及额外工具要求见 [Windows 打包脚本](scripts/build_tauri_windows.ps1)。Linux 部署见 [Debian 打包与部署指南](docs/guide/install/packaging_deb.md)。

---

## 文档资源

-   📚 **[项目文档](docs/index.md)**: 完整的项目使用说明和 API 参考
-   **[设备批量复制](docs/guide/device/device-copy.md)**、**[测点映射](docs/guide/point/mapping.md)**、**[公式使用](docs/guide/point/formula.md)**、**[变化追踪](docs/guide/point/change-tracking.md)**
-   **[模拟配置](docs/guide/simulation/point-config.md)**、**[数据监视与自动读取](docs/guide/simulation/data-monitor.md)**
-   📦 **[Debian 打包与部署指南](docs/guide/install/packaging_deb.md)**: 详细介绍了如何在 Linux 环境下构建 deb 安装包

---

## 核心概念

### 测点类型

系统支持四种测点类型：

| 类型 | 代码 | 说明 | 典型用途 |
|------|------|------|----------|
| **遥测 (YC)** | frame_type=0 | 模拟量测量 | 电压、电流、功率、温度 |
| **遥信 (YX)** | frame_type=1 | 开关量状态 | 运行状态、故障标志 |
| **遥控 (YK)** | frame_type=2 | 开关量命令 | 启停命令、合分闸 |
| **遥调 (YT)** | frame_type=3 | 模拟量命令 | 功率设定、温度设定 |

### 协议类型

| 协议 | 服务端 | 客户端 | 默认端口 |
|------|--------|--------|----------|
| Modbus TCP | ✅ | ✅ | 502 |
| Modbus RTU | ✅ | ✅ | 串口 |
| IEC 60870-5-104 | ✅ | ✅ | 2404 |
| IEC 60870-5-101 | ✅ | ✅ | 串口 |
| DL/T 645-2007 | ✅ | ✅ | 8899 |
| DNP3 | ✅（Outstation） | ✅（Master） | 20000 |
| IEC 61850 MMS | ✅ | ✅ | 102 |
| IEC 61850 GOOSE | ✅（发布） | ✅（订阅） | —（以太网二层） |
| IEC 61850 Reports | ✅ | ✅ | 复用 MMS 连接 |
| IEC 61850 Files | ✅ | ✅ | — |
| IEC 61850 Setting Groups | ✅ | ✅ | 复用 MMS 连接 |
| IEC 61850 Logs | ✅ | ✅ | 复用 MMS 连接 |

---

## 解析码系统 (Decode)

解析码定义了 Modbus 寄存器数据的解析方式，包括数据类型、字节序和位数。

### 解析码一览表

#### 16位整数 (1个寄存器)

| 解析码 | 名称 | 说明 | 字节序 |
|--------|------|------|--------|
| `0x20` | UINT16_BE | 16位无符号整数 | 大端 (AB) |
| `0x21` | INT16_BE | 16位有符号整数 | 大端 (AB) |
| `0xC0` | UINT16_LE | 16位无符号整数 | 小端 (BA) |
| `0xC1` | INT16_LE | 16位有符号整数 | 小端 (BA) |
| `0xB0` | UINT16_BE_SWAP | 16位无符号整数 | 大端字交换 |
| `0xB1` | INT16_BE_SWAP | 16位有符号整数 | 大端字交换 |

#### 32位整数/浮点 (2个寄存器)

| 解析码 | 名称 | 说明 | 字节序 |
|--------|------|------|--------|
| `0x40` | UINT32_BE | 32位无符号整数 | 大端 (ABCD) |
| `0x41` | INT32_BE | 32位有符号整数 | 大端 (ABCD) |
| `0x42` | FLOAT_BE | 32位浮点数 | 大端 (ABCD) |
| `0xD0` | UINT32_LE | 32位无符号整数 | 小端 (DCBA) |
| `0xD1` | INT32_LE | 32位有符号整数 | 小端 (DCBA) |
| `0xD2` | FLOAT_LE | 32位浮点数 | 小端 (DCBA) |
| `0x43` | UINT32_BE_SWAP | 32位无符号整数 | 大端字交换 (CDAB) |
| `0x44` | INT32_BE_SWAP | 32位有符号整数 | 大端字交换 (CDAB) |
| `0x45` | FLOAT_BE_SWAP | 32位浮点数 | 大端字交换 (CDAB) |
| `0xD4` | UINT32_LE_SWAP | 32位无符号整数 | 小端字交换 (BADC) |
| `0xD5` | INT32_LE_SWAP | 32位有符号整数 | 小端字交换 (BADC) |
| `0xD3` | FLOAT_LE_SWAP | 32位浮点数 | 小端字交换 (BADC) |

#### 64位整数/浮点 (4个寄存器)

| 解析码 | 名称 | 说明 | 字节序 |
|--------|------|------|--------|
| `0x60` | UINT64_BE | 64位无符号整数 | 大端 |
| `0x61` | INT64_BE | 64位有符号整数 | 大端 |
| `0x62` | DOUBLE_BE | 64位双精度浮点 | 大端 |
| `0xE0` | UINT64_LE | 64位无符号整数 | 小端 |
| `0xE1` | INT64_LE | 64位有符号整数 | 小端 |
| `0xE2` | DOUBLE_LE | 64位双精度浮点 | 小端 |

#### 8位字符 (1个寄存器)

| 解析码 | 名称 | 说明 |
|--------|------|------|
| `0x10` | CHAR_8_BE | 8位无符号字符 |
| `0x11` | CHAR_8_BE_SIGNED | 8位有符号字符 |

### 字节序说明

以32位浮点数 `1234.5` 为例，其十六进制表示为 `449A5000`：

| 字节序类型 | 存储顺序 | 说明 |
|------------|----------|------|
| **大端 (BE)** | `44 9A 50 00` | 高字节在前，标准网络字节序 |
| **小端 (LE)** | `00 50 9A 44` | 低字节在前，x86架构常用 |
| **大端字交换 (BE_SWAP)** | `50 00 44 9A` | 寄存器内大端，寄存器间交换 |
| **小端字交换 (LE_SWAP)** | `9A 44 00 50` | 寄存器内小端，寄存器间交换 |

### 代码使用示例

```python
from src.enums.modbus_register import Decode, DecodeCode

# 方式一：使用解析码字符串
info = Decode.get_info("0x41")
print(f"寄存器数量: {info.register_cnt}")  # 2
print(f"是否有符号: {info.is_signed}")      # True
print(f"字节序: {info.endian}")             # >

# 方式二：使用枚举（推荐）
info = DecodeCode.FLOAT_BE.value
print(f"解析码: {info.code}")              # 0x42
print(f"描述: {info.description}")         # 32位浮点数(大端)

# 数据打包/解包
packed = Decode.pack_value(info.pack_format, 1234.5)
value = Decode.unpack_value(info.pack_format, packed)

# 获取所有解析码（供前端下拉菜单使用）
all_codes = Decode.get_all_codes()
```

### 真实值转换

遥测和遥调类型支持系数转换：

```
真实值 = 寄存器值 × 乘法系数 + 加法系数
寄存器值 = (真实值 - 加法系数) ÷ 乘法系数
```

| 属性 | 说明 | 默认值 |
|------|------|--------|
| `mul_coe` | 乘法系数 | 1.0 |
| `add_coe` | 加法系数 | 0.0 |

---

## 项目结构

```
ems_simulate/
├── src/                        # 后端源码
│   ├── config/                 # 配置管理
│   │   ├── config.py          # 全局配置
│   │   └── log/               # 日志配置
│   ├── data/                   # 数据层
│   │   ├── dao/               # 数据访问对象
│   │   └── service/           # 业务服务
│   ├── device/                 # 设备模拟器 ⭐
│   │   ├── core/              # 核心类
│   │   │   ├── device.py      # Device 主类
│   │   │   ├── point/        # 测点管理与计算
│   │   │   └── data/         # 数据读取与导出
│   │   ├── protocol/          # 协议处理器
│   │   │   ├── base_handler.py      # 基类
│   │   │   ├── modbus_handler.py    # Modbus
│   │   │   ├── iec104_handler.py    # IEC104
│   │   │   ├── iec101_handler.py    # IEC101
│   │   │   ├── dlt645_handler.py    # DLT645
│   │   │   ├── dnp3_handler.py      # DNP3 Master/Outstation
│   │   │   └── iec61850_handler.py  # IEC61850
│   │   ├── simulator/         # 模拟控制
│   │   ├── factory/           # 设备工厂
│   │   └── types/             # 设备类型
│   ├── enums/                  # 枚举和数据结构
│   │   ├── modbus_register.py # 解析码定义 ⭐
│   │   └── points/            # 测点类型
│   ├── proto/                  # 底层协议实现
│   │   ├── pyModbus/          # Modbus 服务端/客户端
│   │   ├── iec104/            # IEC104 服务端/客户端
│   │   ├── iec101/            # IEC101 FT1.2 主站/从站
│   │   ├── iec60870/           # IEC101/IEC104 公共 ASDU 层
│   │   ├── dlt645/            # DLT645 协议库
│   │   ├── dnp3/              # DNP3 主站/从站、事件、控制与 TLS
│   │   └── iec61850/          # IEC61850 MMS/GOOSE/Reports/Files/SV
│   ├── modeling/               # IEC61850 模型工程、校验与版本管理
│   └── web/                    # Web API
│       └── api/
│           ├── device/        # 设备控制接口
│           ├── channel/       # 通道与协议管理
│           ├── point/         # 测点与映射接口
│           ├── modeling/      # IEC61850 图形化建模接口
│           └── scl/           # SCL/ICD 文件管理
├── front/                      # 前端源码 (Vue3)
│   ├── src/
│   │   ├── components/        # 组件
│   │   ├── views/             # 页面
│   │   └── api/               # API封装
│   └── package.json
├── src-tauri/                  # Tauri 桌面壳 (Rust)
│   ├── src/
│   │   ├── lib.rs             # Tauri Builder
│   │   └── backend.rs         # 后端进程管理
│   └── tauri.conf.json
├── data/                       # SQLite 数据库
├── start_back_end.py          # 后端入口
├── pyproject.toml             # Python 依赖与配置
└── uv.lock                    # Python 依赖锁定文件
```

---

## 开发指南

### 添加新设备类型

1. 在 `src/device/types/` 下创建新设备类
2. 继承 `Device` 基类
3. 实现 `setSpecialDataPointValues()` 方法（可选）

```python
from src.device.core.device import Device, DeviceType

class MyDevice(Device):
    def __init__(self):
        super().__init__()
        self.device_type = DeviceType.Other

    def setSpecialDataPointValues(self):
        # 设置特殊测点关联逻辑
        pass
```

### 扩展新协议

1. 在 `src/device/protocol/` 下创建处理器
2. 继承 `ServerHandler` 或 `ClientHandler`
3. 实现抽象方法

```python
from src.device.protocol.base_handler import ServerHandler

class MyProtocolHandler(ServerHandler):
    def initialize(self, config):
        pass

    async def start(self) -> bool:
        self._is_running = True
        return True

    async def stop(self) -> bool:
        self._is_running = False
        return True

    def read_value(self, point):
        pass

    def write_value(self, point, value):
        pass

    def add_points(self, points):
        pass
```

---

## 许可证

本项目采用 **GNU General Public License v3.0（GPL-3.0）**，详见 [LICENSE](LICENSE)。

## 贡献

欢迎提交 Issue 和 Pull Request！
