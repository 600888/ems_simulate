# EMS Simulate - 能源管理系统模拟器

一个用于模拟能源管理系统（EMS）中关键设备行为的软件系统，主要用于测试和开发场景。系统通过 Modbus/TCP 协议模拟真实工业设备（如PCS储能变流器、BMS电池管理系统）的数据交互，支持远程客户端读取和写入数据。

## 功能特性

- 🔌 **Modbus服务器模拟**：基于 pymodbus 实现 TCP/串口服务端，支持线圈、寄存器读写
- 🎯 **自动数据模拟**：每秒随机生成 PCS/BMS 数据并更新至 Modbus 寄存器
- ⚙️ **设备配置管理**：支持时间轴事件设定、配置文件导入导出
- 📊 **数据可视化**：电池堆界面显示实时数据及变化曲线
- 🌐 **Web界面**：Vue3 + TypeScript 构建的现代化前端界面
- 📡 **多协议支持**：内置 DLT645、IEC104 等电力行业通信协议

## 技术架构

```
[Web 前端] ←HTTP/API→ [Flask 后端] ←Modbus→ [模拟设备]
                         ↓
                  [数据库存储]
```

### 技术栈

**前端**
- Vue 3 + TypeScript
- Vite 构建工具
- Element Plus 组件库

**后端**  
- Python 3 + Flask
- pymodbus==3.6.2（Modbus 协议栈）
- SQLAlchemy + MySQL/PyMySQL
- loguru（日志处理）

**协议支持**
- Modbus TCP/RTU
- DLT645 电表通信协议
- IEC104 电力系统通信协议

## 快速开始

### 环境要求

- Python >= 3.7
- Node.js >= 16
- pip、npm

### 安装依赖

```bash
# 1. 安装 Python 依赖
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 2. 前端开发环境
cd frontnew
npm install
npm run dev

# 3. 启动后端服务
python start_back_end.py
```

### Docker 部署

```bash
# 构建镜像
docker build -t ems_simulate .

# 运行容器
docker run -d --name ems -p 502:502 ems_simulate
```

## DLT645协议模块构建指南

项目内置了完整的DLT645电表通信协议实现库，位于 `src/proto/dlt645/` 目录。该库可以独立打包并分发使用。

### DLT645协议简介

DLT645协议是中国电力行业标准，用于电能表与主站系统之间的通信。本项目实现了完整的DLT645协议栈，支持：

- ✅ **多种通信方式**：TCP和RTU（串口）通信
- ✅ **完整数据类型**：电能量、最大需量、变量数据的读写
- ✅ **设备安全**：设备地址验证和密码保护  
- ✅ **双端支持**：客户端和服务端功能
- ✅ **标准兼容**：符合DLT/T 645-2007规约标准

### 环境准备

生成DLT645安装包前，确保系统已安装以下依赖：

```bash
# 安装Python构建工具
pip install build wheel setuptools

# 安装运行时依赖
pip install loguru>=0.5.0 pyserial>=3.4

# 可选：安装开发依赖
pip install pytest pytest-cov black flake8 mypy
```

### 生成DLT645安装包

#### 方法一：使用自动构建脚本（推荐）

DLT645目录提供了智能构建脚本 `build.sh`，支持多种构建模式：

```bash
# 进入DLT645协议目录
cd src/proto/dlt645

# 给脚本执行权限（首次运行）
chmod +x build.sh

# 查看所有构建选项
./build.sh

# === 推荐构建流程 ===

# 1. 完整构建（清理+测试+构建+验证）
./build.sh build

# 2. 快速构建（跳过测试，适用于开发环境）
./build.sh quick

# 3. 完整验证构建（包含安装测试）
./build.sh all

# === 单独操作 ===

# 清理构建文件
./build.sh clean

# 仅运行测试
./build.sh test
```

**构建脚本功能说明**：
- ✨ **智能检查**：自动检查构建依赖和环境
- 🧪 **内置测试**：运行基本功能测试确保质量
- 🎨 **彩色输出**：清晰的构建状态反馈
- 🔍 **结果验证**：构建后自动检查生成的包文件
- 📋 **安装指南**：构建完成后显示安装说明

#### 方法二：手动构建

如需更精细的控制，可使用手动构建：

```bash
# 进入DLT645目录
cd src/proto/dlt645

# 1. 清理之前的构建文件
rm -rf build/ dist/ *.egg-info/ __pycache__/
find . -name "*.pyc" -delete

# 2. 运行基本测试（可选但推荐）
python test_basic.py

# 3. 使用现代构建工具（推荐）
python -m build

# 或者使用传统setuptools方法
python setup.py sdist bdist_wheel

# 4. 检查构建结果
ls -la dist/
```

### DLT645安装包文件说明

构建成功后，在 `dist/` 目录会生成以下文件：

```
dist/
├── dlt645-1.0.0-py3-none-any.whl    # Wheel格式安装包（推荐）
└── dlt645-1.0.0.tar.gz              # 源码分发包
```

- **Wheel包** (`.whl`)：编译后的二进制格式，安装速度快
- **源码包** (`.tar.gz`)：包含完整源码，兼容性更好

### 安装DLT645协议包

#### 本地安装

```bash
# === 推荐方式 ===
# 安装wheel包（速度快，推荐）
pip install dist/dlt645-1.0.0-py3-none-any.whl

# 强制重新安装（用于更新）
pip install dist/dlt645-1.0.0-py3-none-any.whl --force-reinstall

# === 其他方式 ===
# 从源码包安装
pip install dist/dlt645-1.0.0.tar.gz

# 开发模式安装（修改代码立即生效）
cd src/proto/dlt645
pip install -e .

# 用户级安装（无需管理员权限）
pip install --user dist/dlt645-1.0.0-py3-none-any.whl
```

#### 从在线源安装

如果包已发布到PyPI：

```bash
# 从PyPI安装（如果已发布）
pip install dlt645

# 指定版本安装
pip install dlt645==1.0.0

# 安装开发版本
pip install dlt645[dev]
```

### 验证安装

#### 基本验证

```bash
# 测试包导入
python -c "import dlt645; print('✅ DLT645协议包安装成功！')"

# 查看包信息
pip show dlt645

# 检查包文件
python -c "import dlt645; print(dlt645.__file__)"
```

#### 功能测试

```bash
# 运行内置示例
cd src/proto/dlt645
python examples.py

# 运行完整测试（如果安装了开发依赖）
pytest test/

# 运行基本功能测试
python test_basic.py
```

#### 创建简单测试脚本

```python
# test_dlt645_install.py
try:
    from dlt645 import new_tcp_server, MeterClientService
    print("✅ 导入成功")
    
    # 测试服务器创建
    server = new_tcp_server("127.0.0.1", 8021, 3000)
    print("✅ 服务器创建成功")
    
    # 测试客户端创建  
    client = MeterClientService.new_tcp_client("127.0.0.1", 8021, 30.0)
    print("✅ 客户端创建成功")
    
    print("🎉 DLT645协议包安装验证通过！")
except Exception as e:
    print(f"❌ 验证失败: {e}")
```

### 卸载DLT645包

```bash
# 卸载已安装的包
pip uninstall dlt645 -y

# 清理缓存
pip cache purge
```

### 发布DLT645包到PyPI（可选）

如果需要将DLT645协议包发布到Python Package Index (PyPI)，可以按照以下步骤操作：

#### 准备发布

1. **注册PyPI账户**
   - 访问 https://pypi.org/account/register/ 注册账户
   - 访问 https://test.pypi.org/account/register/ 注册测试账户

2. **安装发布工具**
   ```bash
   pip install twine
   ```

3. **配置认证信息**
   ```bash
   # 创建~/.pypirc文件
   cat > ~/.pypirc << EOF
   [distutils]
   index-servers =
       pypi
       testpypi
   
   [pypi]
   username = __token__
   password = <your-pypi-api-token>
   
   [testpypi]
   repository = https://test.pypi.org/legacy/
   username = __token__
   password = <your-test-pypi-api-token>
   EOF
   
   # 设置合适的权限
   chmod 600 ~/.pypirc
   ```

#### 发布流程

1. **构建发布包**
   ```bash
   cd src/proto/dlt645
   
   # 清理并构建
   ./build.sh clean
   ./build.sh build
   
   # 检查构建结果
   ls -la dist/
   ```

2. **验证包质量**
   ```bash
   # 检查包的格式和内容
   twine check dist/*
   
   # 检查包的元数据
   python -m pip install pkginfo
   python -c "from pkginfo import Wheel; w=Wheel('dist/dlt645-1.0.0-py3-none-any.whl'); print(w.name, w.version)"
   ```

3. **测试发布（推荐）**
   ```bash
   # 发布到测试PyPI
   twine upload --repository testpypi dist/*
   
   # 从测试PyPI安装验证
   pip install --index-url https://test.pypi.org/simple/ dlt645
   python -c "import dlt645; print('测试安装成功')"
   ```

4. **正式发布**
   ```bash
   # 发布到正式PyPI
   twine upload dist/*
   
   # 验证正式发布
   pip install dlt645
   python -c "import dlt645; print('正式发布成功')"
   ```

#### 版本管理

1. **更新版本号**
   - 编辑 `setup.py` 中的 `version` 字段
   - 编辑 `pyproject.toml` 中的 `version` 字段
   - 遵循语义化版本控制（Semantic Versioning）

2. **标记Git版本**
   ```bash
   git tag -a v1.0.0 -m "DLT645协议包 v1.0.0 发布"
   git push origin v1.0.0
   ```

3. **维护CHANGELOG**
   ```bash
   # 创建CHANGELOG.md记录版本变更
   cat > CHANGELOG.md << EOF
   # 更新日志
   
   ## [1.0.0] - 2024-XX-XX
   ### 新增
   - 初始版本发布
   - TCP和RTU通信支持
   - 电能量、需量、变量数据读写
   - 完整的客户端和服务端实现
   EOF
   ```

#### 自动化发布

创建GitHub Actions或GitLab CI自动发布脚本：

```yaml
# .github/workflows/publish.yml
name: Publish DLT645 Package

on:
  push:
    tags:
      - 'v*'

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.9'
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install build twine
    
    - name: Build package
      run: |
        cd src/proto/dlt645
        python -m build
    
    - name: Publish to PyPI
      env:
        TWINE_USERNAME: __token__
        TWINE_PASSWORD: ${{ secrets.PYPI_API_TOKEN }}
      run: |
        cd src/proto/dlt645
        twine upload dist/*
```

#### 注意事项

- ⚠️ **版本唯一性**：PyPI不允许重复发布相同版本号
- 🔒 **安全性**：保护好API Token，不要提交到代码仓库
- 📝 **文档完整性**：确保README.md和包描述信息准确
- 🧪 **充分测试**：发布前确保包功能正常
- 📋 **许可证明确**：确认开源许可证设置正确

通过以上步骤，DLT645协议包可以发布到PyPI，供全球开发者使用。

### DLT645使用示例

#### 创建DLT645服务器

```python
from dlt645 import new_tcp_server

# 创建TCP服务器
server = new_tcp_server("127.0.0.1", 8021, 3000)

# 设置电能量数据
server.set_00(0x00000000, 100.0)  # 总有功电能

# 设置变量数据  
server.set_02(0x02010100, 220.0)  # A相电压

# 启动服务器
server.server.start()
```

#### 创建DLT645客户端

```python
from dlt645 import MeterClientService

# 创建TCP客户端
client = MeterClientService.new_tcp_client("127.0.0.1", 8021, 30.0)

# 设置设备地址
client.set_address(b'\x00\x00\x00\x00\x00\x00')

# 读取电能量数据
data = client.read_01(0x00000000)
if data:
    print(f"电能量: {data.value}")
```

### 故障排除

#### 构建相关问题

1. **Python命令不存在或版本不对**
   ```bash
   # 检查Python版本
   python --version
   python3 --version
   
   # 使用python3替代python
   python3 -m build
   python3 setup.py sdist bdist_wheel
   ```

2. **缺少构建依赖**
   ```bash
   # 安装基础构建工具
   pip install build wheel setuptools
   
   # 或使用指定源
   pip install build wheel setuptools -i https://pypi.tuna.tsinghua.edu.cn/simple
   ```

3. **权限问题**
   ```bash
   # Linux/Mac下添加执行权限
   chmod +x build.sh
   
   # 使用用户级安装避免权限问题
   pip install --user dist/dlt645-1.0.0-py3-none-any.whl
   ```

4. **构建脚本执行失败**
   ```bash
   # 检查shell类型
   echo $SHELL
   
   # 使用bash明确执行
   bash build.sh build
   
   # 或直接查看错误详情
   ./build.sh build 2>&1 | tee build.log
   ```

5. **依赖包版本冲突**
   ```bash
   # 创建独立虚拟环境
   python -m venv dlt645_build_env
   source dlt645_build_env/bin/activate  # Linux/Mac
   # 或 dlt645_build_env\Scripts\activate  # Windows
   
   # 安装构建依赖
   pip install build wheel setuptools
   
   # 构建包
   python -m build
   ```

#### 安装相关问题

1. **导入模块失败**
   ```bash
   # 检查安装状态
   pip show dlt645
   
   # 检查Python路径
   python -c "import sys; print(sys.path)"
   
   # 重新安装
   pip uninstall dlt645 -y
   pip install dist/dlt645-1.0.0-py3-none-any.whl
   ```

2. **包版本冲突**
   ```bash
   # 检查已安装包
   pip list | grep dlt
   
   # 强制重新安装
   pip install dist/dlt645-1.0.0-py3-none-any.whl --force-reinstall
   
   # 使用虚拟环境隔离
   python -m venv test_env
   source test_env/bin/activate
   pip install dist/dlt645-1.0.0-py3-none-any.whl
   ```

3. **缺少运行时依赖**
   ```bash
   # 手动安装依赖
   pip install loguru>=0.5.0 pyserial>=3.4
   
   # 检查依赖是否满足
   python -c "import loguru, serial; print('依赖检查通过')"
   ```

#### 运行相关问题

1. **串口权限问题（Linux）**
   ```bash
   # 添加用户到dialout组
   sudo usermod -a -G dialout $USER
   
   # 重新登录或立即生效
   newgrp dialout
   
   # 检查串口权限
   ls -l /dev/ttyUSB* /dev/ttyACM*
   ```

2. **网络端口被占用**
   ```bash
   # 检查端口占用情况
   netstat -tlnp | grep :8021
   # 或
   lsof -i :8021
   
   # 杀死占用进程
   sudo kill -9 <进程ID>
   
   # 或使用其他端口
   server = new_tcp_server("127.0.0.1", 8022, 3000)
   ```

3. **防火墙阻止连接**
   ```bash
   # Ubuntu/Debian
   sudo ufw allow 8021
   
   # CentOS/RHEL
   sudo firewall-cmd --permanent --add-port=8021/tcp
   sudo firewall-cmd --reload
   ```

4. **内存不足或资源限制**
   ```bash
   # 检查系统资源
   free -h
   df -h
   
   # 优化Python内存使用
   export PYTHONDONTWRITEBYTECODE=1
   export PYTHONUNBUFFERED=1
   ```

#### 开发调试问题

1. **启用详细日志**
   ```python
   from loguru import logger
   import sys
   
   # 添加调试日志
   logger.remove()
   logger.add(sys.stderr, level="DEBUG")
   logger.add("dlt645_debug.log", level="DEBUG", rotation="10 MB")
   ```

2. **测试连接问题**
   ```python
   # 简单连接测试
   import socket
   
   def test_connection(host, port):
       try:
           sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
           sock.settimeout(5)
           result = sock.connect_ex((host, port))
           sock.close()
           return result == 0
       except:
           return False
   
   print(f"端口8021连通性: {test_connection('127.0.0.1', 8021)}")
   ```

3. **协议数据调试**
   ```python
   # 在DLT645客户端代码中添加
   import binascii
   
   def debug_frame(data, direction="send"):
       hex_data = binascii.hexlify(data).decode()
       print(f"[{direction}] {hex_data}")
   ```

#### 获取技术支持

如果问题仍未解决，请收集以下信息并提交Issue：

```bash
# 收集环境信息
echo "=== 系统信息 ==="
uname -a

echo "=== Python信息 ==="
python --version
which python

echo "=== 包信息 ==="
pip show dlt645
pip list | grep -E "(dlt645|loguru|pyserial|build|wheel|setuptools)"

echo "=== 构建日志 ==="
# 重新构建并保存日志
cd src/proto/dlt645
./build.sh build 2>&1 | tee build.log
cat build.log
```

## 项目结构

```
ems_simulate/
├── src/                    # 后端源码
│   ├── config/            # 配置管理
│   ├── data/              # 数据层（DAO/Service）
│   ├── device/            # 设备模拟器
│   ├── flask/             # Web API
│   ├── proto/             # 通信协议
│   │   ├── dlt645/        # DLT645协议实现
│   │   ├── iec104/        # IEC104协议
│   │   └── pyModbus/      # Modbus协议
│   └── tests/             # 测试用例
├── frontnew/              # 前端源码（Vue3）
├── config/                # 配置文件
├── resources/             # 资源文件
└── requirements.txt       # Python依赖
```

## 开发指南

### 添加新设备类型

1. 在 `src/device/` 下创建新设备类
2. 继承 `GeneralDevice` 基类
3. 在 `general_device_builder.py` 中注册设备工厂
4. 添加对应的数据模板

### 扩展通信协议

1. 在 `src/proto/` 下创建协议目录
2. 实现协议解析和数据转换
3. 集成到设备控制器中

### 前端界面开发

```bash
cd frontnew
npm run dev    # 开发模式
npm run build  # 生产构建
npm run test   # 运行测试
```

## 许可证

Apache License 2.0

## 贡献

欢迎提交Issue和Pull Request！

## 联系方式

- 项目地址：https://gitee.com/your-project/ems_simulate
- 技术支持：请提交Issue