---
layout: home

hero:
  name: "EMS Simulate"
  text: "能源管理系统模拟器"
  tagline: 模拟 PCS、BMS、电表等工业设备的数据交互
  image:
    src: /img/architecture.png
    alt: EMS Simulate 架构图
  actions:
    - theme: brand
      text: 快速开始 →
      link: /guide/install/getting-started
    - theme: alt
      text: 在 GitHub 上查看
      link: https://github.com/600888/ems_simulate

features:
  - icon: 🔌
    title: 多协议支持
    details: 支持 Modbus TCP/RTU、IEC 60870-5-101/104、DL/T 645-2007、IEC 61850、DNP3、OPC UA 等工业通信协议
  - icon: 🎯
    title: 设备模拟
    details: 可模拟 PCS 储能变流器、BMS 电池管理系统、电表、断路器等设备
  - icon: ⚙️
    title: 灵活配置
    details: 支持数据库配置和 CSV 文件导入，运行时热重载测点属性
  - icon: 📊
    title: 现代化界面
    details: Vue3 + TypeScript 构建的 Web 管理界面，操作直观便捷
---

## 技术栈

| 层次 | 技术 |
|------|------|
| **前端** | Vue 3, TypeScript, Vite, Element Plus |
| **后端** | Python 3.11+, FastAPI, SQLAlchemy |
| **协议** | pymodbus 3.12, c104, dlt645, pyiec61850-ng, pydnp3-pure, asyncua 2.0.1, aiomqtt |
| **数据库** | SQLite (默认) / MySQL |

## OPC UA

支持服务端与客户端，提供地址空间建模、变量读写、数据模拟、原生实时订阅、历史查询、事件、MQTT/JSON 发布、证书与安全配置，以及会话与通信日志。

[协议介绍](./guide/protocols/opcua/) · [操作指南](./guide/protocols/opcua/operation) · [报文与诊断查看](./guide/protocols/opcua/packet-view)

> 📷 **截图待补：OPC UA 地址空间与变量定义** — 展示 NodeId、BrowseName、数据类型、初始值及可写权限。
> 建议文件名：`opcua-address-space.png`

<!-- ![OPC UA 地址空间与变量定义](/img/opcua-address-space.png) -->

> 📷 **截图待补：OPC UA 客户端实时订阅** — 展示地址空间树、监控变量、发布与采样间隔，以及实时表格或趋势。
> 建议文件名：`opcua-subscription.png`

<!-- ![OPC UA 客户端实时订阅](/img/opcua-subscription.png) -->

## 快速安装

```bash
# 安装 Python 依赖（基于 pyproject.toml / uv.lock，需先安装 uv: pip install uv）
uv sync --extra dev

# 前端开发环境
cd front && npm install && npm run dev

# 启动后端服务
python start_back_end.py
```

<style>
:root {
  --vp-home-hero-name-color: transparent;
  --vp-home-hero-name-background: -webkit-linear-gradient(120deg, #1e88e5 30%, #42b883);
}
</style>
