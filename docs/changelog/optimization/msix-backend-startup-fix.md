# MSIX 打包后端进程启动修复

> 日期：2026-06-17
> 标签：`MSIX` `后端启动` `进程管理` `代码重构`

## 问题描述

MSIX 格式打包安装后，应用启动时一直显示加载动画（转圈圈），无法访问后台服务。MSI 格式正常。

## 根因分析

### 原因 1：MSIX 环境检测失效

`is_msix_env()` 函数通过检查 `PACKAGE_FAMILY_NAME` / `PACKAGE_FULL_NAME` 环境变量来判断是否运行在 MSIX 环境中。

但此 MSIX 包的 `Package.appxmanifest` 中 `EntryPoint="Windows.FullTrustApplication"`（完全信任模式），**不会设置这两个环境变量**，导致检测永远返回 `false`，代码走了 Tauri shell 插件 sidecar 路径，而 MSIX 包内没有对应的资源结构，后端无法启动。

**修复**：改用 `current_exe()` 路径是否包含 `WindowsApps` 来判断。MSIX 安装的 exe 一定在 `C:\Program Files\WindowsApps\` 目录下。

### 原因 2：DETACHED_PROCESS 在 MSIX 下无效

MSIX 完全信任模式下，`DETACHED_PROCESS`（`0x00000008`）进程标志没有生效，子进程仍然附着在父进程的控制台上，出现控制台黑框，且关闭黑框会导致后端进程退出。

**修复**：改用 `CREATE_NO_WINDOW`（`0x08000000`），直接不分配控制台，进程在后台静默运行。

### 原因 3：代码耦合度高，MSIX 与 MSI 逻辑混杂

MSIX 和 MSI/NSIS 的后端启动逻辑完全不同（进程标志、端口分配、进程句柄管理），混在同一个文件中维护困难，修改 MSIX 逻辑容易影响 MSI。

**修复**：将代码拆分为三个文件：

| 文件 | 职责 |
|------|------|
| `backend/mod.rs` | 公共入口：环境检测、`#[tauri::command]`、按环境转发 |
| `backend/msix.rs` | MSIX 独立逻辑：`Mutex<Option<Child>>`、固定端口 8991、`CREATE_NO_WINDOW` |
| `backend/normal.rs` | 非 MSIX 逻辑：`ProcessHandle` 枚举、Tauri shell 插件 sidecar、动态端口 |

## 解决方案

### 1. MSIX 环境检测

```rust
fn is_msix_env() -> bool {
    #[cfg(target_os = "windows")]
    {
        if let Ok(exe) = std::env::current_exe() {
            if let Some(path) = exe.to_str() {
                return path.contains("WindowsApps");
            }
        }
        false
    }
    #[cfg(not(target_os = "windows"))]
    { false }
}
```

### 2. MSIX 进程标志

```rust
fn new_detached_cmd(program: &str) -> Command {
    let mut cmd = Command::new(program);
    #[cfg(target_os = "windows")]
    cmd.creation_flags(0x08000000); // CREATE_NO_WINDOW
    cmd
}
```

### 3. 代码拆分

```
src-tauri/src/backend/
├── mod.rs      # 公共入口 + #[tauri::command] + 统一转发
├── msix.rs     # MSIX 独立逻辑
└── normal.rs   # 非 MSIX 逻辑
```

`mod.rs` 中的 `is_msix_env()` 在每次公开 API 调用时实时检测，根据结果转发到 `msix::` 或 `normal::` 对应函数，两者完全隔离，不共享全局状态。

## 涉及文件

| 文件 | 改动 |
|------|------|
| `src-tauri/src/backend.rs` | 已删除，拆分为 backend/ 子目录 |
| `src-tauri/src/backend/mod.rs` | 新建：公共入口、环境检测、统一转发 |
| `src-tauri/src/backend/msix.rs` | 新建：MSIX 独立逻辑 |
| `src-tauri/src/backend/normal.rs` | 新建：非 MSIX 逻辑 |

## 效果验证

- ✅ MSIX 安装包：后端正常启动，无控制台黑框
- ✅ MSI 安装包：后端正常启动，无控制台黑框（不受拆分影响）
- ✅ 开发模式：后端正常启动
- ✅ MSIX 关闭应用时后端进程正确清理
