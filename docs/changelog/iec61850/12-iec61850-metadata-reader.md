# IEC 61850 元数据按需读取服务

> 版本: 1.0  
> 日期: 2026-06-03  
> 状态: 已实现  
> 关联: `iec61850-point-registry-optimization.md`


## 1. 背景

### 1.1 问题

上一轮优化将 `q`（Quality）和 `t`（Timestamp）子属性从 `PointRegistry` 中移除，
避免了 41K→5K 的 8 倍测点膨胀。但这导致前端无法按需查看某个测点的品质和时标。

需要一种**不纳入常规轮询、不占用 PointRegistry、按需调用**的独立读取方案。

### 1.2 约束

| 约束 | 说明 |
|------|------|
| 不进入 PointRegistry | 不能回到 41K 测点膨胀 |
| 按需调用 | 仅当前端请求时才发起 MMS 读取 |
| 不阻塞主流程 | 独立于批量读取/定时轮询 |
| 优雅降级 | 部分子属性不可读时（如 BAMS error=22），不抛异常 |


## 2. 设计

### 2.1 架构图

```
前端 "查看品质"
  │
  ▼
REST API / WebSocket Handler
  │
  ▼
MetadataReader (core/metadata.py)        ← 新增
  │
  ├── read_quality()     → IntegerReader / BooleanReader
  ├── read_timestamp()   → IntegerReader / BooleanReader
  └── read_metadata()    → QualityInfo + TimestampInfo
  │
  ▼
Iec61850Connection
  │
  ▼
pyiec61850 (IedConnection_readIntegerValue / readBooleanValue)
```

### 2.2 设计模式

| 模式 | 位置 | 用途 |
|------|------|------|
| **Strategy** | `IntegerReader` / `BooleanReader` | 复用已有读取策略，每个子属性按类型分派 |
| **Template Method** | `MetadataReader._read_struct()` | 统一的结构化属性遍历+构造逻辑 |
| **Dataclass (frozen + slots)** | `QualityInfo` / `TimestampInfo` | 不可变产出，线程安全，内存紧凑 |
| **Null Object** | `.empty()` 类方法 | 读取完全失败时返回空对象，避免 None 判断 |
| **Facade** | 模块级函数 `read_quality()` | 便捷入口，零配置使用 |

### 2.3 产出类型

```python
@dataclass(slots=True, frozen=True)
class QualityInfo:
    validity: int | None           # 0=good, 1=invalid, 2=questionable
    detail_quality: int | None     # 详细品质码
    source: int | None             # 0=process, 1=substituted
    operator_blocked: bool | None  # 操作员闭锁
    test: bool | None             # 测试模式

@dataclass(slots=True, frozen=True)
class TimestampInfo:
    seconds: int | None               # Unix 秒
    fraction: int | None              # 小数部分
    time_accuracy: int | None         # 精度等级
    leap_seconds_known: bool | None   # 闰秒已知
    clock_failure: bool | None        # 时钟故障
    clock_not_synchronized: bool | None  # 未同步

    # 派生属性
    unix_timestamp_ms: int | None     # 合并为毫秒时间戳
```

### 2.4 读取流程

```
read_quality(conn, "KG_BAMSCTMP01/MMCL1.Temp001", fc="MX")
  │
  ├── ref = "KG_BAMSCTMP01/MMCL1.Temp001.q.validity"
  │   IntegerReader.read() → 0 (good)       ✅
  ├── ref = "... .q.detailQuality"
  │   IntegerReader.read() → 0              ✅
  ├── ref = "... .q.source"
  │   IntegerReader.read() → 0              ✅
  ├── ref = "... .q.operatorBlocked"
  │   BooleanReader.read() → False          ✅
  └── ref = "... .q.test"
      BooleanReader.read() → False          ✅
  │
  ▼
  QualityInfo(validity=0, detail_quality=0, source=0,
              operator_blocked=False, test=False)
```

### 2.5 错误处理

每个子属性**独立读取**，单个失败不影响其他：

```
q.operatorBlocked → BooleanReader.read() → error=22 (ACCESS_DENIED)
q.test           → BooleanReader.read() → True

结果: QualityInfo(operator_blocked=None, test=True)  ← 部分成功，不抛异常
```

`log.debug` 级别记录失败原因，不污染 INFO/ERROR 日志。


## 3. 文件结构

| 文件 | 作用 |
|------|------|
| `src/proto/iec61850/core/metadata.py` | MetadataReader + QualityInfo / TimestampInfo |
| `tests/iec61850/test_read.py` | `TestMetadataReader` 类 (3 个测试) |


## 4. 用法示例

### 4.1 在 Handler 中按需读取

```python
from src.proto.iec61850.core.metadata import MetadataReader

class Iec61850Handler:
    def __init__(self):
        self._metadata_reader = MetadataReader()

    def read_point_metadata(self, address: str) -> dict:
        """API: 读取单点元数据"""
        # 从 address 反推 do_ref
        do_ref = self._address_to_do_ref(address)
        meta = self._metadata_reader.read_metadata(
            self._client._conn, do_ref, fc="MX"
        )
        return meta.to_dict()
```

### 4.2 模块级便捷函数

```python
from src.proto.iec61850.core.metadata import read_quality, read_timestamp

q = read_quality(conn, "KG_BAMSCTMP01/MMCL1.Temp001")
if not q.is_valid:
    print(f"数据品质异常: validity={q.validity}")

t = read_timestamp(conn, "KG_BAMSCTMP01/MMCL1.Temp001")
print(f"时标: {t.unix_timestamp_ms}ms")
```


## 5. 与 PointRegistry 的关系

```
┌─────────────────────────────────────────┐
│                PointRegistry            │
│  主值测点 (mag.f / stVal / ctlVal)      │
│  批量读取 / 定时轮询                     │
│  ~5K 条目                               │
└─────────────────────────────────────────┘
                    │
                    │ 互补，不重复
                    ▼
┌─────────────────────────────────────────┐
│             MetadataReader              │
│  q / t 子属性 (validity / seconds ...)  │
│  按需调用 / 用户点击时读取                │
│  0 条目 (不在 Registry 中)               │
└─────────────────────────────────────────┘
```


## 6. 后续扩展

- [ ] 前端「查看品质/时标」按钮对接
- [ ] `MetadataReader.read_batch_metadata()` 批量读取优化（减少网络往返）
- [ ] 缓存策略：短时间内对同一 DO 不重复读取
- [ ] 扩展支持 `subQ`（替代品质）、`origin`（来源）等其它元数据
