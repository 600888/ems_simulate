# 更新日志
## 未发布的更新
### 代码质量
1. 引入 Ruff (v0.15.15) 替代 pylint 1.4.3，作为统一 Python linter + formatter
2. 创建 `pyproject.toml` 作为 Python 工具统一配置入口
3. 启用 12 个规则组：F, E, W, I, UP, N, YTT, RSE, B, SIM, ARG, PTH
4. 全项目 230 个 Python 文件完成格式化基准（`ruff format`）
5. 修复 672 个代码问题：
   - 181 个 import 排序重排
   - 537 个 UP 语法升级（`typing.Dict` → `dict`, `typing.List` → `list` 等）
   - 10 个 F 类关键错误（未定义名称 `Dlt645`/`Yc`/`manager` 等真实 Bug）
   - 17 个 E 类风格错误（行超长、bare except 等）
   - 7 个 B 类 Bug 模式（异常链丢失、未使用抽象方法等）
   - 其他 N/RSE/YTT/SIM 规则修复

### 新增 Tauri 2.x 桌面客户端支持**（Phase 1 概念验证）
    - Rust 核心：窗口管理、系统托盘、菜单
    - Python 后端生命周期管理（启动/健康检查/优雅关闭）
    - 后端新增 `/api/health` 健康检查端点
    - 前端新增 `@tauri-apps/api` 原生能力集成
    - Windows `.msi` / Linux `.deb` / `.AppImage` 打包支持
    - 安装包体积预估 ~40MB（相比 Electron 方案减少 60%+）
### 主要更新
1. 增加IEC61850客户端导出模型功能，支持icd、xml、json、csv、text等格式
2. 优化程序初始化逻辑，大幅提升程序启动速度
3. 完成界面基础设置功能（屏幕缩放比例、中英文切换）
4. 优化部分界面显示，如表格样式
5. IEC61850增加报告支持
6. IEC61850增加文件服务支持

## [3.0.0] - 2026-5-12
### 新增功能
1. 增加IEC61850树形结构展示
2. IEC61850分为GOOSE、Reports、Logs、Setting Groups、Data Sets、Data Models、Files
3. IEC61850可以按照分类查看对应模型数据
4. IEC104协议支持所有ASDU类型（25种），不再局限于短浮点遥测和单点遥信
5. 新增 iec104_type 模块（StrEnum + frozen dataclass 设计模式）
6. 前端添加/编辑测点时支持选择 IEC104 ASDU 类型
7. 测点表格显示 IEC104 类型标识列（仅 IEC104 协议设备可见）
8. 增加按照104测点类型筛选测点功能
9. 增加104品质描述功能
10. 增加IEC61850测点下详细信息展示, 重构IEC61850测点表格和后台接口

### 修复
1. 修复ModbusRtu协议无法正确读取和写入寄存器的Bug


## [2.0.2] - 2026-4-26
1. 修复IEC61850客户端连接超时阻塞问题(底层C API是同步阻塞方案, python侧改为线程后台调用)
2. IEC61850导入点表改为完整引用导入(同时修改服务端和客户端)
3. 修复IEC61850客户端动态发现时无法识别带前缀的逻辑节点名(如METMMXU1→MMXU)导致测点跳过的问题
4. 增加IEC61850标准系统DO(Mod/Beh/Health/Op/Str/Tr等)的frame_type推断支持
5. 扩展IEC61850 LN class识别表,覆盖测量/保护/控制/调节等常见逻辑节点类型
6. 修复IEC61850服务端导入ICD点表后内存模型不更新的问题(需重建设备实例)
7. 修复前端连接失败连接弹窗的bug

## [2.0.1] - 2026-4-19
1.增加设备批量复制功能（支持自定义前缀后缀、IP偏移量、端口偏移量）

## [2.0.0] - 2026-4-18
1.增加IEC61850协议支持
2.修复一些bug
3.增加windows版本软件包

## [1.0.0] - 2026-2-21
- 初始版本发布