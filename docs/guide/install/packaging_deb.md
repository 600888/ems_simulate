# Debian 打包与部署指南

本文档介绍如何在 Debian/Ubuntu 环境下构建 `ems-simulate-web` 的 `.deb` 安装包，以及如何安装和管理服务。

## 1. 环境准备

在开始构建之前，请确保您的构建机器（推荐 Ubuntu 20.04+ 或 Debian 10+）已安装以下必要工具：

-   **基础工具**: `git`, `dpkg-dev`, `binutils`
-   **Python 环境**: `python3`, `uv` (Python 3.11+)
-   **Node.js 环境**: `npm` (用于构建前端)

安装命令示例：
```bash
sudo apt update
sudo apt install -y git dpkg-dev binutils python3 python3-pip npm
pip install uv
```

## 2. 构建步骤

项目的 `scripts` 目录下提供了自动化构建脚本 `scripts/build_web_deb.sh`，会自动处理前端编译、后端打包（PyInstaller）以及生成 `.deb` 包。

1.  **拉取代码**：
    ```bash
    git clone https://github.com/600888/ems_simulate.git
    cd ems_simulate
    ```

2.  **安装 Python 依赖**（使用 `pyproject.toml` / `uv.lock`，含构建所需 PyInstaller）：
    ```bash
    uv sync --extra build --extra dev
    ```

3.  **运行构建脚本**：
    ```bash
    chmod +x scripts/build_web_deb.sh
    ./scripts/build_web_deb.sh
    ```

4.  **等待构建完成**：
    脚本执行完毕后，终端会显示构建成功的提示以及生成的包路径。

    **输出产物**：
    -   目录：`build/dist_deb/`
    -   文件：`ems-simulate-web_<版本号>_amd64.deb` (版本号取自 `pyproject.toml`)

## 3. 安装与卸载

### 安装

使用 `dpkg` 命令安装生成的 deb 包：

```bash
# 请根据实际生成的文件名替换
sudo dpkg -i build/dist_deb/ems-simulate-web_4.4.0_amd64.deb
```

安装完成后，`postinst` 脚本会自动注册 systemd 服务并启动、设置开机自启。

### 卸载

#### 保留配置卸载 (推荐)
仅删除程序文件，保留配置文件 (`config.ini`) 和运行时数据 (`data/` 目录)：

```bash
sudo dpkg -r ems-simulate-web
```

#### 完全清除 (慎用)
删除程序文件、配置文件以及产生的所有数据（包括数据库）：

```bash
sudo dpkg -P ems-simulate-web
```

## 4. 服务管理

安装包会自动安装 systemd 服务文件 `ems-simulate-web.service`。您可以使用标准 `systemctl` 命令进行管理。

-   **启动服务**：
    ```bash
    sudo systemctl start ems-simulate-web
    ```

-   **停止服务**：
    ```bash
    sudo systemctl stop ems-simulate-web
    ```

-   **重启服务**：
    ```bash
    sudo systemctl restart ems-simulate-web
    ```

-   **查看状态**：
    ```bash
    sudo systemctl status ems-simulate-web
    ```

-   **查看日志**：
    ```bash
    # 查看实时日志
    journalctl -u ems-simulate-web -f
    ```

-   **设置开机自启**：
    ```bash
    sudo systemctl enable ems-simulate-web
    ```

## 5. 目录结构说明

安装后的主要文件位置：

-   **程序主目录**: `/usr/share/ems-simulate-web/`
    -   `ems_simulate_web`: 主程序二进制文件 (PyInstaller onedir 打包)
    -   `www/`: 前端静态资源
    -   `data/`: SQLite 数据库文件 (运行时生成)
    -   `config.ini`: 配置文件
-   **服务文件**: `/lib/systemd/system/ems-simulate-web.service`
-   **可执行链接**: `/usr/bin/ems-simulate-web`
