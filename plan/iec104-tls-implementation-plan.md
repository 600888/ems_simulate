# IEC 104 TLS 实现计划

## 1. 目标

为 IEC 104 TCP 客户端和服务端增加可配置的 TLS，适用于完全无法访问公网的生产内网，并提供基础 TLS 和双向认证 TLS 两种模式。

验收要求：

- 基础 TLS 配置本端证书和私钥，仅加密链路，不验证对端身份。
- 双向认证 TLS 额外配置内网 CA；双方校验对端证书链，客户端额外校验服务端证书主机名/IP。
- TLS 握手不访问公网 CA、AIA、OCSP 等服务。
- TLS 失败时连接失败，不回退为明文。
- TLS 关闭时保持现有 IEC 104 行为。
- TLS 模式兼容多 Station、总召唤、遥测/遥信、遥控/遥调和报文捕获。

## 2. 技术方案

### 2.1 c104 版本

使用 c104 2.2.2。该版本增加 `TransportSecurity.set_hostname_verification(hostname)`，并修复启用证书校验时的 TLS 握手行为。

当前 2.2.2 尚未发布到 PyPI，因此 `pyproject.toml` 固定到官方仓库的明确提交：

```text
f9ded6f77f6582a85cad6f541205c2f8d58b0bc3
```

待官方发布 2.2.2 wheel 后，将依赖改为 `c104==2.2.2`，并继续使用同一套 API。构建和发布流水线需预先生成并缓存 Windows/Linux wheel，生产内网安装不依赖公网。

### 2.2 原生 TLS

直接使用 c104 原生传输安全，不增加 TCP 代理或回环转发层：

```python
tls = c104.TransportSecurity(validate=mutual_authentication, only_known=False)
tls.set_certificate(identity_certificate, identity_private_key)
if mutual_authentication:
    tls.set_ca_certificate(ca_certificate)
tls.set_version(c104.TlsVersion.TLS_1_2, c104.TlsVersion.TLS_1_3)
tls.set_hostname_verification(server_hostname)  # 仅客户端

client = c104.Client(transport_security=tls)
server = c104.Server(..., transport_security=tls)
```

基础模式使用 `validate=False`，只提供机密性，不验证对端证书。双向认证模式使用 `validate=True`：服务端通过内网 CA 校验合法客户端证书；客户端在 CA 链校验外，通过 2.2.2 的 hostname API 校验服务端身份。

### 2.3 证书模型

每个 IEC 104 TLS 通道配置三类文件：

| 文件 | 用途 |
| --- | --- |
| 本端证书 | 客户端或服务端在握手中出示的身份证书，可包含中间证书链 |
| 本端私钥 | 与本端证书匹配的私钥 |
| CA 证书 | 仅双向认证模式需要，用于离线验证对端证书的根 CA/中间 CA PEM 包 |

约束：

- CA 文件必须是 CA 证书，不能把本端叶子证书当作 CA。
- 客户端连接地址必须出现在服务端证书 SAN 中；兼容证书可同时保留 CN。
- 服务端证书使用 Server Authentication EKU，客户端证书使用 Client Authentication EKU。
- 私钥不出现在查询 API、日志或前端回显中。
- 基础 TLS 必须由用户显式选择；握手失败时仍禁止自动降级为明文。

## 3. 改造项

### 3.1 数据与迁移

- `ChannelSecurityConfig` 增加 `ca_certificate_path` 和 `ca_certificate_filename`。
- SQLite、MySQL 初始化时对旧表执行安全的增量补列。
- 旧通道默认 `tls_enabled=false`，无需补录证书即可继续运行。
- 通道删除时沿用现有安全目录清理逻辑。

### 3.2 上传 API

扩展 `POST /api/channels/security-upload`：

- TLS 支持协议类型 1（Modbus）和 2（IEC 104）。
- IEC 104 开启 TLS 时，本端证书和私钥必填；双向认证模式额外要求 CA 证书。
- 验证证书/私钥配对、证书有效期、CA BasicConstraints 和 PEM 格式。
- 全部材料验证完成后再写入正式目录和数据库。
- 保存后触发设备重载；加载失败必须返回明确错误，不能启动明文实例。

文件布局：

```text
data/security/<channel_id>/
├── certificate.pem
├── private_key.pem
└── ca_certificate.pem
```

### 3.3 运行层

在 `src/proto/iec104/tls.py` 实现 `build_transport_security()`：

1. TLS 关闭返回 `None`。
2. TLS 开启时检查三类文件存在。
3. 基础模式创建 `c104.TransportSecurity(validate=False, only_known=False)`。
4. 双向认证模式创建 `c104.TransportSecurity(validate=True, only_known=False)` 并加载 CA。
5. 两种模式都加载本端证书/私钥并限定 TLS 1.2～1.3。
6. 双向认证客户端调用 `set_hostname_verification()`；基础模式不执行身份校验。
6. c104 版本缺少该 API 时立即报错，提示必须使用 2.2.2 或更高版本。

`IEC104Client` 和 `IEC104Server` 构造器接收 `transport_security`，分别原生传给 `c104.Client`、`c104.Server`。Handler 从 `config["security"]` 构造配置；客户端以目标 IP/主机名作为期望服务端身份。

### 3.4 前端

- IEC 104 与 Modbus TCP 均可开启 TLS。
- IEC 104 TLS 表单提供基础 TLS、双向认证 TLS 模式选择。
- 两种模式都展示本端证书和私钥；双向认证模式额外展示 CA 证书。
- 只展示原始文件名和“已配置”状态，不展示服务器内部路径。

## 4. 测试计划

### 4.1 自动化测试

- TLS 关闭时不要求证书。
- TLS 开启时缺少任一文件立即失败。
- 基础 TLS 不配置 CA 时可以建立加密连接。
- 叶子证书作为 CA 时上传失败。
- 同一私有 CA 签发的客户端/服务端证书可完成 mTLS 连接。
- 客户端证书由未知 CA 签发时，服务端拒绝连接。
- 服务端证书 hostname/SAN 不匹配时，客户端拒绝连接。
- 服务停止再启动后仍可使用同一 TLS 配置建立连接。
- 既有运行配置、数据库兼容和前端类型检查继续通过。

### 4.2 发布前验证

- Windows 和 Linux 分别构建 c104 2.2.2 wheel，并在无公网环境安装。
- 使用抓包确认外部 TCP 载荷为 TLS record，不出现明文 IEC 104 APDU。
- 与至少一种第三方 IEC 104 TLS 实现互操作。
- 验证根 CA + 中间 CA + 叶子证书完整链。
- 验证证书过期、错误 EKU、错误 SAN、错误私钥和缺失中间证书均失败。
- 反复执行设备重载和服务启停，确认无端口占用和旧证书继续服务。

## 5. 实施状态

- [x] CA 字段、数据库兼容迁移和服务层映射
- [x] 基础 TLS / 双向认证 TLS 模式字段与兼容迁移
- [x] IEC 104 证书/私钥/CA 上传与校验
- [x] 前端 IEC 104 TLS 配置
- [x] c104 2.2.2 提交锁定
- [x] c104 原生 `TransportSecurity` 客户端/服务端接入
- [ ] c104 2.2.2 Windows/Linux wheel 纳入离线发布制品
- [ ] 第三方设备/实现互操作测试
- [ ] 离线证书轮换和应急信任替换操作文档

## 6. 风险与回退

- **2.2.2 未正式发布**：源码依赖会触发本地 C++ 编译。发布流水线应构建签名 wheel 并放入内网包仓库；官方 wheel 发布后切换为精确版本号。
- **基础 TLS 实现差异**：c104 2.2.2 即使设置 `validate=False`，无 CA 时仍会保留叶子证书不受信错误；基础模式因此使用进程内标准库 TLS 转发，外部链路保持加密，内部 c104 仅监听回环地址。
- **Windows 证书路径**：c104 2.2.2 的本地文件加载不支持包含中文等非 ASCII 字符的路径；运行层会拒绝此类路径并提示将数据目录设为纯英文路径。
- **离线链不完整**：隔离网不能联网下载中间证书，部署包必须包含完整链。
- **吊销检查**：当前 Python API 未提供 CRL/OCSP 配置；使用短有效期证书、快速替换 CA 信任包和设备重载作为第一版补偿措施。
- **证书切换**：`TransportSecurity` 注入 Client/Server 后只读，证书更新必须完整重建协议实例。
- **回退**：新增字段和证书文件可保留供后续版本使用；只能由用户显式关闭 TLS，程序不得因错误自动降级。

## 7. 参考

- c104 变更日志：https://iec104-python.readthedocs.io/latest/changelog.html
- c104 TransportSecurity：https://iec104-python.readthedocs.io/latest/python/transportsecurity.html
- c104 官方仓库：https://github.com/Fraunhofer-FIT-DIEN/iec104-python
- IEC 62351-3：https://webstore.iec.ch/en/publication/6906
