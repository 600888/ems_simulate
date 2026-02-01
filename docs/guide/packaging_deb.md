# Debian 打包与部署指南

本文档介绍如何在 Debian/Ubuntu 环境下构建 `ems-simulate` 的 `.deb` 安装包，以及如何安装和管理服务。

## 1. 环境准备

在开始构建之前，请确保您的构建机器（推荐 Ubuntu 20.04+ 或 Debian 10+）已安装以下必要工具：

-   **基础工具**: `git`, `dpkg-dev`, `binutils`
-   **Python 环境**: `python3`, `pip` (Python 3.11+)
-   **Node.js 环境**: `npm` (用于构建前端)

安装命令示例：
```bash
sudo apt update
sudo apt install -y git dpkg-dev binutils python3 python3-pip npm
```

## 2. 构建步骤

项目的 `scripts` 目录下提供了自动化构建脚本，会自动处理前端编译、后端打包（PyInstaller）以及生成 `.deb` 包。

1.  **拉取代码**：
    ```bash
    git clone https://github.com/600888/ems_simulate.git
    cd ems_simulate
    ```

2.  **运行构建脚本**：
    构建脚本会自动安装 Python 依赖（通过 `requirements.txt`）并开始构建。
    ```bash
    chmod +x scripts/build_deb.sh
    ./scripts/build_deb.sh
    ```

3.  **等待构建完成**：
    脚本执行完毕后，终端会显示构建成功的提示以及生成的包路径。
    
    **输出产物**：
    -   目录：`build/dist_deb/`
    -   文件：`ems-simulate_1.0.0_amd64.deb` (版本号可能随项目更新)

## 3. 安装与卸载

### 安装

使用 `dpkg` 命令安装生成的 deb 包：

```bash
# 请根据实际生成的文件名替换
sudo dpkg -i build/dist_deb/ems-simulate_1.0.0_amd64.deb
```

安装完成后，服务会自动注册并配置开机自启（视 `postinst` 脚本逻辑而定，通常需要手动启动一次）。

### 卸载

#### 保留配置卸载 (推荐)
仅删除程序文件，保留配置文件 (`config.ini`) 和运行时数据 (`data/` 目录)：

```bash
sudo dpkg -r ems-simulate
```

#### 完全清除 (慎用)
删除程序文件、配置文件以及产生的所有数据（包括数据库）：

```bash
sudo dpkg -P ems-simulate
```

## 4. 服务管理

安装包会自动安装 Systemd 服务文件 `ems-simulate.service`。您可以使用 standard `systemctl` 命令进行管理。

-   **启动服务**：
    ```bash
    sudo systemctl start ems-simulate
    ```

-   **停止服务**：
    ```bash
    sudo systemctl stop ems-simulate
    ```

-   **重启服务**：
    ```bash
    sudo systemctl restart ems-simulate
    ```

-   **查看状态**：
    ```bash
    sudo systemctl status ems-simulate
    ```

-   **查看日志**：
    ```bash
    # 查看实时日志
    journalctl -u ems-simulate -f
    ```

-   **设置开机自启**：
    ```bash
    sudo systemctl enable ems-simulate
    ```

## 5. 目录结构说明

安装后的主要文件位置：

-   **程序主目录**: `/usr/share/ems-simulate/`
    -   `ems_simulate`: 主程序二进制文件
    -   `www/`: 前端静态资源
    -   `data/`: SQLite 数据库文件 (运行时生成)
    -   `config.ini`: 配置文件
-   **服务文件**: `/lib/systemd/system/ems-simulate.service`
-   **可执行链接**: `/usr/bin/ems-simulate`
