# Ruff 代码质量工具引入计划

> 版本: 1.1  
> 日期: 2026-06-01  
> 状态: 第 1~2 阶段已完成


## 1. 背景与现状

### 1.1 当前代码质量工具栈

| 项目 | 值 | 说明 |
|------|-----|------|
| **Python 版本** | 3.9+ (PyInstaller 打包) | 支持现代语法 |
| **Python 文件数** | 270 个 | 分布在 `src/` 的 9 个子包中 |
| **现有 Linter** | `pylint==1.4.3` | 发布于 2016 年，久未更新，功能极其有限 |
| **现有 Formatter** | 无 | 项目没有代码格式化标准 |
| **现有配置** | 无 | 无 `pyproject.toml`、`setup.cfg`、`.flake8`、`.pylintrc` 等配置文件 |
| **代码规模** | ~70K LOC (估算) | 中等规模 Python 项目 |

### 1.2 核心痛点

| 问题 | 影响 |
|------|------|
| **代码风格不统一** | 多人协作时 diff 噪音大，Code Review 耗时 |
| **潜在 Bug 未被捕获** | 无类型检查、未使用变量、常见陷阱等无法早期发现 |
| **pylint 1.4.3 极为过时** | 不支持 f-string 检查、类型注解检查、Python 3.9+ 新特性 |
| **无自动化修复能力** | 重复手动修改琐碎的代码规范问题 |
| **缺乏 CI 门禁** | 无法在 CI 流程中自动阻断低质量代码合入 |


## 2. 为什么选择 Ruff

### 2.1 Ruff 的核心优势

| 特性 | Ruff | Flake8 | Pylint | Black + isort |
|------|------|--------|--------|---------------|
| **速度** | ~1-2s (Rust 实现) | ~30s+ | ~2min+ | ~15s+ |
| **规则数量** | 800+ (集成 flake8/pylint/isort/pycodestyle) | ~200 (需插件) | ~600 | 仅格式化 + 排序 |
| **自动修复** | ✅ 大量规则支持 `--fix` | ❌ | ❌ | 部分 |
| **格式化器** | ✅ 内置 (Ruff Formatter，兼容 Black) | ❌ | ❌ | Black 单独 |
| **单依赖** | ✅ 一个工具覆盖全部 | ❌ 需多个插件 | ❌ 需多个插件 | ❌ Black + isort 两个 |
| **pyproject.toml** | ✅ 原生支持 | ❌ 需 .flake8 | ❌ 需 .pylintrc | 部分支持 |

### 2.2 与现有依赖的关系

`requirements.txt` 中存在 `pylint==1.4.3`，引入 Ruff 后：

1. **第 1~2 阶段**：Ruff 与 pylint 并存，Ruff 为主，pylint 作为补充检查
2. **第 3 阶段**：确认 Ruff 覆盖充分后，移除 pylint 依赖

### 2.3 不适合 Ruff 的场景及应对

| 场景 | 说明 | 替代方案 |
|------|------|---------|
| **复杂的类型推断** | Ruff 的 type checking 规则有限 | 保留 mypy (可选，不在本计划范围内) |
| **复杂的代码复杂度度量** | Ruff 的 McCabe 复杂度检查较基础 | 在关键模块手动 review |
| **自定义 Pylint 插件** | 项目没有自定义 pylint 插件 | 无需关注 |


## 3. 总体计划

### 3.1 路线图概览

```
第 1 阶段 (1 周) ──→ 第 2 阶段 (2 周) ──→ 第 3 阶段 (1 周) ──→ 第 4 阶段 (持续)
  基础配置          渐进修复            全面启用            持续维护
  + 安全规则        增量引入规则        CI 集成            定期规则升级
  + 格式化基准      逐模块修复         移出 pylint          代码审查参考
```

### 3.2 里程碑

| 里程碑 | 时间 | 状态 | 交付物 |
|--------|------|------|--------|
| M1: 基础配置上线 | Day 1 | ✅ 完成 | `pyproject.toml` 创建，零报错验证通过 |
| M2: 格式化基准 | Day 1 | ✅ 完成 | 230 个文件格式化，187 个文件变更 |
| M3: 安全规则修复 | Day 1 | ✅ 完成 | 修复 F/E 类错误（含 3 个 F821 真实 Bug） |
| M4: 增量规则覆盖 | Day 1 | ✅ 完成 | 启用 I/UP/N/YTT/RSE/B/SIM/ARG/PTH 规则 |
| M5: CI 集成 | Day 1 | ⏳ 待办 | GitHub Actions / GitLab CI 中添加 Ruff 检查步骤 |
| M6: 全面启用 | Day 1 | ✅ 部分完成 | 已启用 F/E/W/I/UP/N/B 等核心组，`PL`/`RUF` 暂未开启 |
| M7: pylint 退役 | Day 1 | ✅ 完成 | 从 `requirements.txt` 中移除，替换为 `ruff==0.15.15` |
| M8: 文档与规范 | Day 1 | ✅ 完成 | 本计划文档 + CHANGELOG 记录 |


## 4. 第 1 阶段：基础配置

### 4.1 创建 `pyproject.toml`

在项目根目录新建 `pyproject.toml`，作为所有 Python 工具的统一配置入口。

#### 4.1.1 推荐的 Ruff 配置（初始版本，零报错）

```toml
[project]
name = "ems_simulate"
version = "0.1.0"
requires-python = ">=3.9"

[tool.ruff]
# 目标 Python 版本
target-version = "py39"

# 排除目录
exclude = [
    ".git",
    ".codebuddy",
    ".claude",
    "debian",
    "front",
    "resources",
    "scripts",
    "src-tauri",
    "data",
    "docs",
]

# 行长度
line-length = 120

# 编码
source-type = "auto"

[tool.ruff.lint]
# 第 1 阶段：仅启用安全且无报错的核心规则
select = [
    "F",    # pyflakes - 检测未使用导入、未定义变量等关键错误
]

# 忽略所有已知规则（第 1 阶段零报错目标）
ignore = [
    "F401", # 允许未使用的导入（第 1 阶段暂不启用）
    "F403", # 允许 from XXX import *
    "F405", # 允许 * 导入的变量在后续使用
]

# 允许未使用的导入（在 __init__.py 中很常见）
[tool.ruff.lint.per-file-ignores]
"__init__.py" = ["F401"]
"src/tests/**" = ["F401", "F841"]  # 测试中未使用变量较常见

[tool.ruff.format]
# 与 Black 兼容的格式化配置
quote-style = "double"
indent-style = "space"
line-ending = "lf"
```

**零报错验证方法**：运行 `ruff check src/`，如果零报错则表示基础配置生效。

#### 4.1.2 配置说明

| 配置项 | 选择理由 |
|--------|---------|
| `line-length = 120` | 项目中存在较长的协议调用链、类型注解，80/88 太严格 |
| `target-version = "py39"` | PyInstaller 打包环境的最低 Python 版本 |
| `quote-style = "double"` | 项目中双引号占多数，与现有风格一致 |
| `line-ending = "lf"` | 跨平台一致性，与现有 `.gitattributes` 配合 |

### 4.2 安装 Ruff

```bash
# 推荐：使用 pip 安装（纳入依赖管理）
pip install ruff

# 可选：将其加入 requirements.txt
# 在 requirements.txt 中追加：
# ruff==0.11.0
```

**IDE 集成建议**：

| IDE | 集成方式 |
|-----|---------|
| **VS Code** | 安装 Ruff 扩展，设置 `"ruff.enable": true` |
| **PyCharm** | 使用 File Watchers 或 Ruff 插件 |
| **其他编辑器** | 配置 pre-commit hook 即可 |

### 4.3 建立格式化基准

在基础配置上线后，立即对全项目执行格式化，建立首个"格式化基准 commit"：

```bash
# 格式化所有 Python 文件
ruff format src/

# 检查格式化后的状态（应无输出）
ruff format src/ --check
```

**注意事项**：
- 这会产生大量的格式化 diff（主要是空白字符、引号统一、import 顺序等）
- 建议将这个提交放在一个独立的 commit 中，commit message：`chore: apply ruff format baseline`
- 后续的规则修复 commit 应基于此 commit 之上
- 建议将此 commit 标记为 `git blame` 忽略（在 `.git-blame-ignore-revs` 中添加该 commit hash）

### 4.4 配置 pre-commit hook（可选但推荐）

创建 `.pre-commit-config.yaml`：

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.11.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
```

安装：

```bash
pip install pre-commit
pre-commit install
```


## 5. 第 2 阶段：渐进引入与修复

### 5.1 规则分组与引入顺序

规则按风险从低到高分 4 个批次引入，每个批次针对特定模块进行修复。

#### 批次 A：安全修复

| 规则 | 说明 | 预计报错数 | 自动修复 |
|------|------|-----------|---------|
| `F` (完整启用) | 未使用导入、未定义变量、重复键 | 50~80 | ✅ 大部分 |
| `E` | PEP 8 风格错误 (行尾空格、空行数等) | 100~200 | ✅ 全部 |

**操作步骤**：

```txt
1. 将 [tool.ruff.lint.select] 更新为 ["F", "E"]
2. 去掉 ignore 中的 F401/F403/F405
3. 运行 ruff check src/ --fix
4. 手动检查并修复剩余的 F、E 报错
5. 提交 commit: "fix: resolve F/E rule violations across codebase"
```

**要关注的关键问题**：
- `F401` (未使用导入)：需逐个判断是"真未使用"还是"导入即使用"（如 signal handler 注册）
- `F811` (重复定义)：可能存在测试模块中的 fixture 重定义问题
- `E402` (导入顺序)：`src/device/` 和 `src/proto/` 中有 `try/except` 包裹的导入，需用 `noqa` 处理
- `E501` (行超长)：配置 `line-length = 120` 后仍超长的行需要手动换行

#### 批次 B：导入整理

| 规则 | 说明 | 预计报错数 | 自动修复 |
|------|------|-----------|---------|
| `I` | import 排序 (isort 规则) | 200~300 | ✅ 全部 |

**操作步骤**：

```txt
1. 配置 [tool.ruff.lint.isort]
   known-first-party = ["src"]
   force-sort-within-types = true
2. 运行 ruff check src/ --fix --select I
3. 提交 commit: "style: organize imports with ruff isort rules"
```

**关键关注点**：
- `src/__init__.py` 中的交叉导入可能受 import 顺序影响，需注意
- 如果某些文件依赖隐式的导入顺序（较少见），会报错，需手动调整

#### 批次 C：现代化与清理

| 规则 | 说明 | 预计报错数 | 自动修复 |
|------|------|-----------|---------|
| `UP` | pyupgrade (Python 3.9+ 语法升级) | 40~80 | ✅ 全部 |
| `N` | PEP 8 命名规范 | 10~30 | ❌ 需手动 |
| `YTT` | 日期/时区相关 | 0~5 | ✅ |
| `RSE` | 空字符串/序列判断 | 5~15 | ✅ 全部 |

**操作步骤**：

```txt
1. 更新 select = ["F", "E", "I", "UP", "N", "YTT", "RSE"]
2. 运行 ruff check src/ --fix (自动修复 UP/YTT/RSE)
3. 手动审查 N 类告警（命名规范），逐个判断是否修正
4. 提交 commit: "refactor: modernize Python 3.9+ syntax and naming"
```

**要关注的关键问题**：
- `UP007`：`Optional[X]` → `X | None`，如果项目同时需要支持 Sphinx 文档生成，`X | None` 可能不兼容，建议保留或统一处理
- `UP009` / `UP010`：UTF-8 编码声明 / 旧式 `from __future__` 导入，可直接修复
- `N802` ~ `N806`：函数/变量命名不符合 PEP 8。项目中 IEC61850、Modbus 等协议代码包含大量 `_parseXXX`、`getMMSDataObject` 等驼峰命名，应使用 `per-file-ignores` 保留协议层代码

```toml
[tool.ruff.lint.per-file-ignores]
"src/proto/**" = ["N802", "N803", "N806"]  # 协议代码遵循外部标准命名
"src/device/**" = ["N802", "N803"]         # 设备模拟代码中协议相关命名
"src/tests/**" = ["N802", "N803", "N806"]  # 测试方法名使用 snake_case 自定
```

#### 批次 D：正确性与 Bug 检测

| 规则 | 说明 | 预计报错数 | 自动修复 |
|------|------|-----------|---------|
| `B` | flake8-bugbear (Bug 检测) | 20~60 | ❌ 部分 |
| `SIM` | 代码简化 (简化 if/return/表达式) | 30~80 | ✅ 大部分 |
| `ARG` | 未使用的函数参数 | 40~100 | ❌ |
| `PTH` | pathlib 建议 | 10~30 | ✅ 大部分 |
| `PL` | Pylint 兼容规则 (R/C 类) | 80~200 | ❌ 部分 |

**操作步骤**：

```txt
1. 将 select 扩展为完整规则
2. 运行 ruff check src/ --statistics 评估报错分布
3. 逐规则修复，必要时通过 per-file-ignores 跳过不适用模块
4. 提交多个 commit，每个 commit 针对一个规则群
5. 最终目标：全项目零 warning
```

### 5.2 模块修复顺序

考虑到 `src/proto/iec61850` 和 `src/device/` 是项目中代码量最大、逻辑最复杂的部分，建议按以下顺序逐模块修复：

```
第 1 步: src/config/          (12 个文件，简单，快速上手)
第 2 步: src/tools/           (9 个文件，工具类)
第 3 步: src/enums/           (17 个文件，枚举定义)
第 4 步: src/web/             (32 个文件，FastAPI)
第 5 步: src/data/            (37 个文件，业务逻辑)
第 6 步: src/device/          (32 个文件，设备模拟)
第 7 步: src/proto/pyModbus/  (模块化较好)
第 8 步: src/proto/iec104/    (协议客户端/服务端)
第 9 步: src/proto/iec61850/  (最复杂的协议栈，最后处理)
第 10 步: src/tests/          (测试文件，宽松要求)
```

**每个模块的标准修复流程**：

```txt
1. 运行 ruff check <module_dir> --statistics    # 查看报错分布
2. 运行 ruff check <module_dir> --fix            # 自动修复
3. 手动检查剩余不可自动修复的报错
4. 判断是否需要 per-file-ignores
5. 运行测试确认修复未引入回归
6. commit
```


## 6. 第 3 阶段：CI 集成与全面启用

### 6.1 CI 配置

#### GitHub Actions (`.github/workflows/lint.yml`)

```yaml
name: Lint

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  ruff:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - uses: astral-sh/ruff-action@v3
        with:
          version: latest
```

#### 或使用 pip 方式的 GitHub Actions

```yaml
- name: Install ruff
  run: pip install ruff

- name: Run ruff check
  run: ruff check src/ --output-format=github

- name: Run ruff format check
  run: ruff format src/ --check
```

### 6.2 质量门禁设置

| 检查项 | 阻断级别 | 说明 |
|--------|---------|------|
| `ruff check src/` | ❌ 阻断 | 零 warning 策略 |
| `ruff format src/ --check` | ❌ 阻断 | 格式不一致即阻断 |
| `ruff check src/ --no-fix` | ⚠️ 警告 | 输出所有可自动修复的问题 |

### 6.3 移除 pylint

确认 Ruff 覆盖充分后：

1. 从 `requirements.txt` 中移除 `pylint==1.4.3`
2. 搜索项目中所有对 pylint 的引用（如 `# pylint: disable=...` 注释），转为 Ruff 对应的 `# noqa: ...` 注释

```bash
# 搜索所有 pylint disable 注释
rg "# pylint" src/ --no-heading -n

# 逐个转换为 Ruff noqa 注释
# e.g. # pylint: disable=unused-import -> # noqa: F401
```


## 7. 第 4 阶段：持续维护

### 7.1 版本升级策略

| 频率 | 操作 |
|------|------|
| **每月** | 运行 `pip install --upgrade ruff`，检查新规则 |
| **每季度** | review 规则集，根据团队反馈调整 |
| **每次 Code Review** | 使用自动修复功能减少 review 噪音 |

### 7.2 新规则引入流程

```txt
1. 在本地启用新规则，运行 ruff check src/ --statistics
2. 评估报错数量和修复难度
3. 如果报错少 (< 10)：立即修复并添加到 select
4. 如果报错多 (> 10)：创建一个追踪 issue，分批修复
5. 修复完成后提交配置变更
```

### 7.3 推荐的最终规则集（第 4 阶段基准）

```toml
[tool.ruff.lint]
select = [
    "F",    # pyflakes - 关键错误
    "E",    # pycodestyle - PEP 8
    "W",    # pycodestyle - 警告
    "I",    # isort - 导入排序
    "N",    # PEP 8 命名规范
    "UP",   # pyupgrade - Python 现代化
    "B",    # bugbear - Bug 检测
    "SIM",  # 代码简化
    "ARG",  # 未使用参数
    "PTH",  # pathlib 建议
    "RSE",  # 空序列检测
    "RUF",  # Ruff 特有规则
    "PLC",  # Pylint 约定
    "PLE",  # Pylint 错误
    "RUF100", # noqa 注释有效性
]

# 在协议层放宽命名规则
[tool.ruff.lint.per-file-ignores]
"__init__.py" = ["F401"]
"src/proto/**" = ["N802", "N803", "N806", "ARG"]
"src/device/**" = ["N802", "N803"]
"src/tests/**" = ["F401", "F841", "N802", "N803", "N806", "ARG"]
```




## 8. 工作量估算

### 8.1 按阶段估算

| 阶段 | 预估工时 | 主要工作 |
|------|---------|---------|
| **第 1 阶段** | 0.5 人天 | ✅ 创建 pyproject.toml、安装 ruff、全项目格式化（187 文件变更） |
| **第 2 阶段 - 批次 A** | 1~2 人天 | ✅ 修复 F/E 规则 + 3 个 F821 真实 Bug |
| **第 2 阶段 - 批次 B** | 0.5 人天 | ✅ import 自动排序（181 处修复） |
| **第 2 阶段 - 批次 C** | 1 人天 | ✅ UP 语法升级（537 处自动修复）+ N/YTT/RSE |
| **第 2 阶段 - 批次 D** | 3~5 人天 | ✅ B/SIM/ARG/PTH 规则，7 处 B 类 Bug 修复 |
| **第 3 阶段** | 0.5 人天 | ⏳ 待办：CI 配置（GitHub Actions） |
| **第 4 阶段** | 持续 | ⏳ 待办：版本升级、`UP035`/`PL`/`RUF` 规则开启 |

**已执行总计：~0.5 人天（自动化工具辅助）**

### 8.2 潜在风险与缓解措施

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| 格式化导致大规模 diff，影响 Code Review | 高 | 中 | 独立 commit + `.git-blame-ignore-revs` |
| 某些模块的 import 顺序依赖隐式行为 | 低 | 高 | 在配置中排除特定文件，手动处理 |
| `X | None` 与 Sphinx/文档工具不兼容 | 中 | 低 | 保留 `Optional[X]` 在特定模块 |
| 测试模块中大量 fixture 重定义 | 高 | 低 | 在 `src/tests/**` 放宽规则 |
| CI 时间过长 | 低 | 低 | Ruff 速度快 (~1s)，对 CI 无影响 |


## 9. 附录

### 9.1 常用命令速查

```bash
# 检查
ruff check src/                                           # 检查所有
ruff check src/proto/iec61850/                            # 检查特定模块
ruff check src/ --statistics                              # 按规则统计报错数
ruff check src/ --select F401                             # 仅检查特定规则
ruff check src/ --fix                                     # 自动修复
ruff check src/ --diff                                    # 预览修改内容
ruff check src/ --output-format=concise                   # 简洁输出
ruff check src/ --show-files                              # 仅显示有问题的文件

# 格式化
ruff format src/                                          # 格式化所有
ruff format src/ --check                                  # 仅检查，不修改
ruff format src/ --diff                                   # 预览格式化diff

# 配置验证
ruff check src/ --show-settings                           # 显示当前生效配置
ruff rule                                                 # 交互查看规则解释
ruff rule F401                                            # 查看特定规则详解
```

### 9.2 常用 noqa 分类

| 场景 | 写法 |
|------|------|
| 单行忽略 | `import some_module  # noqa: F401` |
| 单行多个规则 | `code_here  # noqa: F401, E501` |
| 整个模块 (pyproject.toml) | `per-file-ignores = {"src/foo/*" = ["F401"]}` |
| 整个文件 (顶部注释) | `# ruff: noqa: F401, E501` |
| 整个文件所有规则 | `# ruff: noqa` |
| 文件内某段 (不推荐) | 重构比忽略更合理 |

### 9.3 参考资源

- [Ruff 官方文档](https://docs.astral.sh/ruff/)
- [Ruff 规则索引](https://docs.astral.sh/ruff/rules/)
- [Ruff VS Code 插件](https://marketplace.visualstudio.com/items?itemName=charliermarsh.ruff)
- [Ruff pre-commit hook](https://github.com/astral-sh/ruff-pre-commit)
- [GitHub Actions - Ruff Action](https://github.com/astral-sh/ruff-action)
