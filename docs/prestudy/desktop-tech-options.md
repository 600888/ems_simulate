# EMS Simulate 桌面端技术选型方案

> 文档版本：v1.0  
> 日期：2026-05-20  
> 作者：EMS Simulate 项目组  
> 目标：将现有 Web 应用封装为跨平台桌面应用，要求高性能、小体积

---

## 目录

1. [项目现状分析](#1-项目现状分析)
2. [技术方案概览](#2-技术方案概览)
3. [方案一：Electron](#3-方案一electron)
4. [方案二：Tauri](#4-方案二tauri)
5. [架构设计方案](#5-架构设计方案)
6. [多维对比分析](#6-多维对比分析)
7. [方案推荐与路线图](#7-方案推荐与路线图)
8. [风险评估](#8-风险评估)

---

## 1. 项目现状分析

### 1.1 当前技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 前端 | Vue 3 + Vite + TypeScript + Element Plus | SPA 单页应用，构建产物输出至 `www/` 目录 |
| 后端 | Python 3.11+ / FastAPI + Uvicorn | RESTful API，集成 PyInstaller 打包为独立可执行文件 |
| 数据库 | SQLite（默认）/ MySQL | 配置文件驱动切换 |
| 协议栈 | pymodbus / c104 / dlt645 / pyiec61850-ng | Modbus TCP/RTU、IEC104、DLT645、IEC61850 |
| 现有分发 | PyInstaller + .deb / .zip | 当前产物 ~30 MB（不含 Python 运行时） |

### 1.2 桌面化的核心挑战

1. **Python 后端不可替代**：项目中约 226 个 Python 源文件，涵盖 Modbus、IEC104、DLT645、IEC61850 等工业协议的底层实现，用其他语言重写代价极高
2. **前后端分离架构**：前端通过 HTTP API 与后端通信，天然适合「壳应用 + 内置服务器」模式
3. **跨平台需求**：需同时支持 Linux 和 Windows（当前 .deb 和 .zip 分发方式已覆盖）
4. **性能敏感**：设备模拟涉及大量实时通信，后端响应延迟需尽可能低
5. **体积敏感**：工业部署场景下，安装包体积是重要考量

### 1.3 桌面化核心思路

无论选用哪种方案，总体思路一致：

```
┌─────────────────────────────────────────────┐
│                  桌面壳应用                    │
│  ┌──────────────┐    ┌────────────────────┐  │
│  │  前端 WebView  │◄──►│  Python 后端进程    │  │
│  │  (Vue 3 SPA)  │HTTP │  (FastAPI+Uvicorn) │  │
│  └──────────────┘    └────────┬───────────┘  │
│                               │               │
│                        ┌──────▼──────┐        │
│                        │   SQLite DB  │        │
│                        └─────────────┘        │
└─────────────────────────────────────────────┘
```

---

## 2. 技术方案概览

| 维度 | Electron | Tauri |
|------|----------|-------|
| Web 引擎 | Chromium（系统内置或内嵌） | 系统 WebView（Edge WebView2 / WebKitGTK） |
| 后端语言 | Node.js | Rust |
| 包管理器 | npm / yarn / pnpm | Cargo + npm |
| 当前最新版本 | v37.x | v2.x |
| 许可证 | MIT | Apache 2.0 / MIT |
| 社区规模 | 大（GitHub 115k+ stars） | 快速增长（GitHub 95k+ stars） |

---

## 3. 方案一：Electron

### 3.1 技术架构

```
┌──────────────────────────────────────────────────┐
│                  Electron App                     │
│                                                   │
│  ┌─────────────┐          ┌───────────────────┐  │
│  │ Main Process │ ──IPC──► │ Renderer Process  │  │
│  │  (Node.js)   │          │  (Chromium)       │  │
│  │              │          │  ┌─────────────┐  │  │
│  │  - 启动管理   │          │  │  Vue 3 SPA   │  │  │
│  │  - 窗口管理   │          │  │  (www/)      │  │  │
│  │  - 托盘/菜单  │          │  └─────────────┘  │  │
│  │  - 子进程管理 │          └───────────────────┘  │
│  │  - 系统集成   │                                 │
│  └──────┬───────┘                                 │
│         │ spawn                                    │
│  ┌──────▼───────┐                                 │
│  │ Python 后端   │  (PyInstaller 打包为独立 exe)    │
│  │ FastAPI:8991  │                                 │
│  └──────────────┘                                 │
└──────────────────────────────────────────────────┘
```

### 3.2 关键技术点

| 项目 | 说明 |
|------|------|
| **打包工具** | `electron-builder` 或 `electron-forge` |
| **Python 集成** | Main Process 通过 `child_process.spawn()` 启动 PyInstaller 打包的 Python 后端 |
| **进程通信** | 前端通过 HTTP `localhost:8991` 与 Python 后端通信；Main Process 与 Renderer 通过 IPC 通信 |
| **窗口管理** | `BrowserWindow` 创建主窗口；`Tray` 实现系统托盘 |
| **自动更新** | `electron-updater` 支持增量更新 |
| **兼容性** | Chromium 版本固定，不受系统 WebView 版本影响 |

### 3.3 指标预估

| 指标 | 预估值 | 说明 |
|------|--------|------|
| **安装包体积** | 120 ~ 200 MB | Chromium ~100MB + Python 运行时 ~60MB + 应用 ~30MB |
| **运行时内存** | 300 ~ 600 MB | Chromium ~200MB + Node.js ~50MB + Python ~100MB |
| **冷启动时间** | 3 ~ 8 秒 | 取决于系统性能和首次加载 |
| **CPU 占用** | 中 | Chromium GPU 进程 + 渲染开销 |
| **开发门槛** | 低 | 团队已有 Vue/Node.js 经验，学习曲线平缓 |

### 3.4 优势

- ✅ **成熟稳定**：业界最主流的桌面方案，VSCode / Slack / Discord / Figma 均基于 Electron
- ✅ **开发体验好**：DevTools 调试、热重载、丰富插件生态
- ✅ **兼容性强**：内嵌 Chromium，不受系统 WebView 版本差异影响
- ✅ **社区资源丰富**：大量现成方案和最佳实践，遇到问题容易找到答案
- ✅ **与现有体系兼容**：Vue 3 + Vite 可直接迁移，无需改造前端代码

### 3.5 劣势

- ❌ **体积大**：即使最简单的 Hello World 也要 ~120MB+
- ❌ **内存占用高**：多进程架构导致内存开销大
- ❌ **启动较慢**：Chromium 初始化需要时间
- ❌ **安全攻击面大**：Chromium CVE 披露频率高，需持续升级

---

## 4. 方案二：Tauri

### 4.1 技术架构

```
┌──────────────────────────────────────────────────┐
│                    Tauri App                      │
│                                                   │
│  ┌─────────────┐          ┌───────────────────┐  │
│  │ Rust Core    │ ──IPC──► │  WebView          │  │
│  │  (tauri)     │          │  (系统原生)        │  │
│  │              │          │  ┌─────────────┐  │  │
│  │  - 启动管理   │          │  │  Vue 3 SPA   │  │  │
│  │  - 窗口管理   │          │  │  (www/)      │  │  │
│  │  - 托盘/菜单  │          │  └─────────────┘  │  │
│  │  - 系统集成   │          └───────────────────┘  │
│  │  - Sidecar   │                                 │
│  └──────┬───────┘                                 │
│         │ spawn sidecar                            │
│  ┌──────▼───────┐                                 │
│  │ Python 后端   │  (PyInstaller 作为 Sidecar)      │
│  │ FastAPI:8991  │                                 │
│  └──────────────┘                                 │
└──────────────────────────────────────────────────┘
```

### 4.2 关键技术点

| 项目 | 说明 |
|------|------|
| **打包工具** | `tauri-cli` + Cargo |
| **Python 集成** | Tauri Sidecar 机制：将 PyInstaller 打包的 Python 可执行文件作为外部二进制文件，通过 `tauri::api::process::Command` 管理其生命周期 |
| **进程通信** | 前端通过 HTTP `localhost:8991` 与 Python 后端通信；前端与 Rust Core 通过 `invoke` / `emit` IPC |
| **窗口管理** | `tauri::Window` API；托盘通过 `tauri-plugin-tray` |
| **自动更新** | `tauri-plugin-updater` 支持差分更新 |
| **WebView** | Windows 使用 Edge WebView2（Win11 内置，Win10 自动安装），Linux 使用 WebKitGTK，macOS 使用 WKWebView |

### 4.3 指标预估

| 指标 | 预估值 | 说明 |
|------|--------|------|
| **安装包体积** | 30 ~ 60 MB | Rust Core ~5MB + Python 运行时 ~60MB + 前端 ~2MB；（WebView2 系统提供，不计入） |
| **运行时内存** | 100 ~ 250 MB | WebView ~50MB + Rust ~10MB + Python ~100MB |
| **冷启动时间** | 1 ~ 4 秒 | Rust 原生启动快，WebView 初始化快 |
| **CPU 占用** | 低 | 无独立 GPU 进程，WebView 由系统级管理 |

### 4.4 优势

- ✅ **体积小**：不含 Chromium，安装包可控制在 50 MB 以内
- ✅ **内存低**：复用系统 WebView，内存开销远小于 Electron
- ✅ **启动快**：Rust 原生二进制 + 系统 WebView，亚秒级冷启动
- ✅ **安全性高**：Rust 内存安全保证；系统 WebView 安全补丁由 OS 统一管理
- ✅ **差分更新**：Tauri 原生支持二进制差分更新，更新包仅几 MB

### 4.5 劣势

- ❌ **Rust 学习成本**：团队需要掌握 Rust 进行 Tauri Core 开发（Windows 管理、Sidecar 管理等）
- ❌ **WebView 兼容性风险**：不同 OS / 不同版本的 WebView 可能存在渲染差异
- ❌ **Linux WebKitGTK 依赖**：部分精简 Linux 发行版可能未预装 WebKitGTK，需要额外安装
- ❌ **生态成熟度不如 Electron**：Tauri Plugin 生态仍在快速发展中，部分功能可能需要自研
- ❌ **Windows 7 不支持**：WebView2 不支持 Win7（若需兼容则无法使用）

---

## 5. 架构设计方案

无论选用 Electron 还是 Tauri，本项目的 Python 后端均无法替代，需要统一的 Python 进程管理方案。

### 5.1 通用架构：Python 后端进程管理

```
桌面壳应用启动
       │
       ▼
  ┌─────────────┐
  │ 检测 Python   │  ← 查找到 PyInstaller 打包的 Python 可执行文件
  │ 后端可执行文件 │
  └──────┬──────┘
         │
    ┌────┴────┐
    │ 存在？    │
    └────┬────┘
    否   │   是
    ▼    │   ▼
  报错   │  ┌──────────────┐
  退出   │  │ spawn 子进程   │
         │  │ 启动 FastAPI   │
         │  └──────┬───────┘
         │         │
         │    ┌────▼────┐
         │    │ 健康检查  │  ← 轮询 http://127.0.0.1:8991/api/health
         │    │ (retry)  │
         │    └────┬────┘
         │         │ 就绪
         │         ▼
         │  ┌──────────────┐
         │  │ 加载 WebView   │  ← 加载 localhost:8991
         │  │ 显示前端界面    │
         │  └──────────────┘
         │         │
         │    ┌────▼────┐
         │    │ 窗口关闭  │
         │    └────┬────┘
         │         │
         │         ▼
         │  ┌──────────────┐
         │  │ kill 子进程   │  ← SIGTERM → wait → SIGKILL
         │  │ 清理资源      │
         │  └──────────────┘
```

### 5.2 进程通信方式

| 通信路径 | 方式 | 说明 |
|----------|------|------|
| 前端 → Python 后端 | HTTP REST API | 现有方案，无需改动 |
| 桌面壳 → Python 后端 | HTTP 健康检查 + 进程信号 | 生命周期管理 |
| 前端 ↔ 桌面壳 | IPC (Electron: contextBridge / Tauri: invoke) | 窗口控制、系统菜单、托盘、文件对话框等原生能力 |

### 5.3 Python 后端打包策略（共用）

当前项目已使用 PyInstaller `--onedir` 模式打包，此方案在两种桌面方案中均可复用：

```
build/
├── ems_simulate_backend/        # PyInstaller --onedir 产物
│   ├── ems_simulate_backend     # 入口可执行文件
│   ├── _internal/               # Python 运行时 + 依赖
│   ├── config.ini               # 配置文件
│   ├── data/                    # 数据库文件
│   └── www/                     # 前端静态资源
```

**优化建议**：
- 使用 `--onedir` 而非 `--onefile`，避免每次启动解压临时目录
- 启用 UPX 压缩可进一步减小体积
- 将 www/ 从 Python 后端剥离，由桌面壳直接加载文件，减少一步网络传输

---

## 6. 多维对比分析

### 6.1 量化对比

| 对比维度 | Electron | Tauri | 权重 | Electron 得分 | Tauri 得分 |
|----------|----------|-------|------|:---:|:---:|
| **安装包体积** | 120~200 MB | 30~60 MB | ⭐⭐⭐⭐⭐ | 1 | 5 |
| **运行时内存** | 300~600 MB | 100~250 MB | ⭐⭐⭐⭐ | 1 | 4 |
| **冷启动速度** | 3~8 秒 | 1~4 秒 | ⭐⭐⭐ | 2 | 4 |
| **开发效率** | 高（JS/TS 全栈） | 中高（需 Rust） | ⭐⭐⭐ | 4 | 2 |
| **跨平台兼容性** | 优秀（Chromium 统一） | 良好（依赖系统 WebView） | ⭐⭐⭐ | 4 | 3 |
| **生态成熟度** | 非常成熟 | 快速发展中 | ⭐⭐⭐ | 5 | 3 |
| **安全性** | 中（需关注 CVE） | 高（系统级 WebView） | ⭐⭐ | 2 | 4 |
| **长期维护成本** | 中（Chromium 升级） | 低（OS 管理 WebView） | ⭐⭐⭐ | 3 | 4 |

> 得分标准：1 = 最差，5 = 最好

### 6.2 加权评分

| 方案 | 加权总分 | 排名 |
|------|:------:|:----:|
| **Electron** | `1×5 + 1×4 + 2×3 + 4×3 + 4×3 + 5×3 + 2×2 + 3×3 = 75` | 2 |
| **Tauri** | `5×5 + 4×4 + 4×3 + 2×3 + 3×3 + 3×3 + 4×2 + 4×3 = 98` | 1 |

### 6.3 关键场景对比

#### 场景一：工业内网部署（本项目主要场景）

```
环境特点：离线安装、低配工控机、Ubuntu 20.04/22.04 LTS
┌──────────┬─────────────────────┬─────────────────────┐
│          │      Electron       │       Tauri          │
├──────────┼─────────────────────┼─────────────────────┤
│ 安装包   │ ~150MB .deb         │ ~40MB .deb          │
│ 额外依赖  │ 无                  │ libwebkit2gtk-4.1   │
│ 内存占用  │ ~400MB             │ ~150MB              │
│ USB 拷贝  │ 较慢（大文件）       │ 快                  │
│ 评价      │ 可用，但体积大       │ 非常适合             │
└──────────┴─────────────────────┴─────────────────────┘
```

#### 场景二：Windows 工控机

```
环境特点：Windows 10 LTSC / Windows 11
┌──────────┬─────────────────────┬─────────────────────┐
│          │      Electron       │       Tauri          │
├──────────┼─────────────────────┼─────────────────────┤
│ 安装包   │ ~170MB .exe/.msi    │ ~45MB .msi          │
│ WebView  │ 内置 Chromium       │ WebView2（Win11内置）│
│ Win10支持 │ 完全支持            │ 需安装 WebView2 运行时 │
│ 评价      │ 兼容性好            │ 需额外处理 WebView2   │
└──────────┴─────────────────────┴─────────────────────┘
```

---

## 7. 方案推荐与路线图

### 7.1 推荐方案：Tauri（首选）

基于项目对**性能和小体积**的核心诉求，以及工控场景部署特点，**推荐优先采用 Tauri 方案**。

**核心理由**：
1. **安装包体积减少 60%+**：从 150MB 降至 ~40MB
2. **内存占用降低 50%+**：对低配工控机友好
3. **安全性更高**：Rust 内存安全 + OS 管理 WebView 安全更新
4. **启动速度更快**：亚秒级启动，用户体验更好

**需克服的挑战**：
- Rust 学习投入（预估 1-2 周上手 Tauri 基本用法）
- Linux 需确保 `libwebkit2gtk-4.1` 作为依赖安装
- Windows 需附带 WebView2 引导安装程序

### 7.2 备选方案：Electron

如果团队在以下情况下可选用 Electron：
- 需要快速交付，无法投入 Rust 学习时间
- 需要支持 Windows 7/8 等老旧系统
- 对安装包体积不敏感（如内网文件服务器分发）

### 7.3 推荐实施路线

```
Phase 1: 概念验证（1-2 周）
├── 搭建 Tauri 2.x + Vue 3 最小原型
├── 验证 Sidecar 机制启动 PyInstaller 打包的 Python 后端
├── 验证 Linux WebKitGTK 兼容性
└── 输出：《POC 验证报告》

Phase 2: 核心开发（3-4 周）
├── 实现窗口管理（大小、最小化托盘）
├── 实现 Python 后端生命周期管理（启动、健康检查、优雅关闭）
├── 实现自动更新机制
├── 迁移现有前端路由到 Tauri 环境
└── CI/CD 构建流水线（Linux + Windows）

Phase 3: 测试与优化（1-2 周）
├── 多平台兼容性测试（Ubuntu 20.04/22.04, Win10/11）
├── 性能压测（内存、CPU、启动速度）
├── 安装包体积优化
└── 用户验收测试

Phase 4: 发布（1 周）
├── 文档与用户手册更新
├── 发布 .deb 和 .msi 安装包
└── 线上自动更新渠道搭建
```

### 7.4 备选实施路线（Electron）

```
Phase 1: 概念验证（1 周）
├── 搭建 Electron + Vue 3 最小原型
├── 验证 child_process 启动 Python 后端
└── 输出：《POC 验证报告》

Phase 2: 核心开发（2-3 周）
├── Main Process 实现窗口/托盘/菜单管理
├── Python 进程生命周期管理
├── electron-updater 自动更新
├── electron-builder 打包配置
└── CI/CD 构建流水线

Phase 3: 测试与发布（1 周）
├── 多平台测试
└── 发布
```

---

## 8. 风险评估

### 8.1 Tauri 方案风险

| 风险 | 概率 | 影响 | 缓解措施 |
|------|:----:|:----:|----------|
| Rust 学习曲线导致开发延期 | 中 | 高 | 预留学习时间；核心功能可先用 Electron 原型验证思路 |
| Linux WebKitGTK 兼容性问题 | 低 | 中 | 测试覆盖 Ubuntu 20.04/22.04；添加依赖检测安装脚本 |
| Windows WebView2 未安装 | 中 | 中 | 安装包内嵌 WebView2 引导安装程序（~2MB） |
| Tauri Plugin 功能不满足需求 | 低 | 中 | 调研插件列表提前确认；必要时用 Rust 自实现 |

### 8.2 Electron 方案风险

| 风险 | 概率 | 影响 | 缓解措施 |
|------|:----:|:----:|----------|
| 安装包体积过大遭用户抵触 | 高 | 中 | 提供精简版/完整版选择；利用内网分发缓解 |
| 低配工控机内存不足 | 中 | 高 | 设置内存限制；使用 `--disable-gpu` 等优化参数 |
| Chromium CVE 安全漏洞 | 中 | 低 | 建立定期升级 Electron 版本的流程 |
| 启动速度过慢 | 高 | 低 | 使用启动画面掩盖加载时间 |

---

## 附录

### A. 相关资源

- Tauri 官方文档：https://v2.tauri.app/
- Tauri Sidecar 文档：https://v2.tauri.app/develop/sidecar/
- Electron 官方文档：https://www.electronjs.org/docs
- electron-builder：https://www.electron.build/
- PyInstaller 文档：https://pyinstaller.org/

### B. 团队能力自评清单

- [ ] 是否有 Rust 开发经验？
- [ ] 对 Linux 桌面环境（GTK/WebKit）熟悉程度？
- [ ] 目标部署环境中是否已安装 WebView2 / WebKitGTK？
- [ ] 用户对安装包体积的容忍上限是多少？
- [ ] 是否需要支持 Windows 7/8？
- [ ] 交付时间是否紧张？

### C. 环境依赖速查

#### Tauri 2.x 开发环境

| 平台 | 系统依赖 |
|------|----------|
| Ubuntu/Debian | `libwebkit2gtk-4.1-dev libgtk-3-dev libayatana-appindicator3-dev librsvg2-dev` |
| Windows | WebView2 Runtime（Win11 内置，Win10 需安装）；MSVC Build Tools |
| macOS | Xcode Command Line Tools |

#### Tauri 2.x 运行环境

| 平台 | 系统依赖 |
|------|----------|
| Ubuntu/Debian | `libwebkit2gtk-4.1-0 libgtk-3-0 libayatana-appindicator3-1` |
| Windows | WebView2 Runtime（可内嵌引导安装器） |
| macOS | 系统内置 WebView |

---

> **下一步**：根据团队讨论确定首选方案后，进入 Phase 1 概念验证阶段。
