# IEC61850 报告回调崩溃与禁用逻辑修复

> 版本: 1.0  
> 日期: 2026-06-19  
> 状态: 已实施


## 1. 问题背景

在 IEC61850 报告控制块 (RCB) 的使能/禁用操作中，频繁出现以下问题：

| 现象 | 触发场景 | 严重程度 |
|------|---------|---------|
| **程序崩溃 (段错误)** | 禁用报告后立即崩溃，或禁用后再次使能时崩溃 | 🔴 致命 |
| `EventSubscriber::subscribe() failed: the subscriber is already registered` | 使能→禁用→再次使能 | 🟡 功能异常 |
| `EventSubscriber::unregisterSubscriber() failed: '' is not registered` | 禁用报告时 | 🟡 日志告警 |
| URCB 禁用失败 `error=26` | 禁用 URCB 报告 | 🟡 功能异常 |
| URCB Resv 预约冲突 | 使能→禁用→修改配置→使能 | 🟡 功能异常 |

问题集中在三个模块：
1. **`callback.py`** — 报告回调注册/注销的 C++ 对象生命周期管理
2. **`urcb.py`** — URCB 禁用逻辑过于复杂，引入不必要的 Resv 预约
3. **`__init__.py`** — `apply_config` 流程编排与禁用路径路由


## 2. 根因分析

### 2.1 RCBSubscriber 没有 unsubscribe 方法（崩溃根本原因）

通过查看 pyiec61850 源码 (`E:\python\Lib\site-packages\pyiec61850\pyiec61850.py`) 发现：

```python
class RCBSubscriber(EventSubscriber):
    def subscribe(self): ...
    def setIedConnection(self, i_ied_connection): ...
    def setRcbReference(self, i_rcb_reference): ...
    def setRcbRptId(self, i_rcb_rpt_id): ...
    # ❌ 没有 unsubscribe 方法！

class EventSubscriber(object):  # 父类
    def subscribe(self): ...
    def deleteEventHandler(self): ...
    def setEventHandler(self, i_event_handler_p): ...
    # ❌ 也没有 unsubscribe 方法！
```

**`RCBSubscriber` 和 `EventSubscriber` 都没有 `unsubscribe` 方法。** 之前的代码尝试调用 `subscriber.unsubscribe()` 会直接抛出 `AttributeError`，且 C++ 侧的订阅记录未被清理。

### 2.2 SWIG Director 回调链未断开（崩溃直接原因）

`_PyRCBHandler` 继承自 `iec61850.RCBHandler`（SWIG director 子类），C++ 接收线程通过 vtable 回调 Python 的 `trigger()` 方法：

```python
class _PyRCBHandler(iec61850.RCBHandler):
    def trigger(self):
        _dispatch_report(self._rcb_ref, self._client_report)  # C++ 回调 Python
```

注销时如果直接释放 Python 侧的 `subscriber`/`handler` 引用，而 C++ 接收线程仍在通过 vtable 回调 `trigger()`，就会访问已释放的 Python 对象导致**段错误崩溃**。

### 2.3 C++ 侧订阅记录未清理（"already registered" 原因）

`RCBSubscriber.subscribe()` 在 C++ 侧按 `rcbReference` 注册订阅。即使 Python 侧释放了 subscriber 对象，C++ 的 `IedConnection` 内部仍保留着按 rcbReference 索引的订阅记录。再次 `subscribe()` 同一 rcbReference 时，C++ 检测到已注册就报：

```
EventSubscriber::subscribe() failed: the subscriber is already registered
```

### 2.4 URCB 禁用走 set_rpt_ena 的复杂逻辑

`UrcbHandler.set_rpt_ena()` 方法同时处理使能和禁用，禁用时会执行大量不必要的逻辑：

```python
def set_rpt_ena(connection, rcb_ref, enable, trg_ops=None, opt_fields=None, intg_period=0):
    # 1. 读取当前 RCB 值 (getRCBValues) — 禁用不需要
    # 2. 读取当前 RptEna 状态 — 禁用不需要
    # 3. 幂等保护判断 — 禁用不需要
    # 4. 设置 RptEna + TrgOps + OptFields + IntgPd — 禁用只需 RptEna
    # 5. setRCBValues 写回
```

禁用 URCB 本质上只需设置 `RptEna=False`，不需要读取当前值、不需要处理 TrgOps/OptFields。复杂逻辑增加了出错概率（如 `error=26`）。


## 3. 修复方案

### 3.1 正确的回调注销顺序（参考 GOOSE 清理模式）

通过分析 pyiec61850 中 GOOSE 订阅器的 `_cleanup()` 方法 (`goose/subscriber.py`)，发现了正确的 C++ 对象清理模式，将其应用到 RCB 回调注销：

```
注销四步走:
1. 锁内从 _CALLBACK_REGISTRY 移除 → 阻止 _dispatch_report 继续分发
2. 锁外 subscriber.deleteEventHandler() → 断开 SWIG director 链，C++ 不再回调 Python
3. 锁外 IedConnection_uninstallReportHandler(conn, nref) → 清理 C++ 侧订阅记录
4. handler.thisown = 0 + 释放 Python 引用 → 防止 SWIG 重复析构
```

**修复后 `uninstall()` 方法**:

```python
@staticmethod
def uninstall(connection, rcb_ref: str) -> bool:
    # 1. 锁内从注册表移除
    with _CALLBACK_LOCK:
        if rcb_ref not in _CALLBACK_REGISTRY:
            return True
        info = _CALLBACK_REGISTRY.pop(rcb_ref)

    subscriber = info.subscriber
    handler = info.handler
    nref = _normalize_ref(rcb_ref)

    # 2. 锁外断开 SWIG director 链接 (C++ 不再回调 Python)
    if subscriber is not None:
        try:
            subscriber.deleteEventHandler()
        except Exception as e:
            log.debug(f"deleteEventHandler 异常 (非致命): {rcb_ref}, {e}")

    # 3. 按 rcbReference 注销 C++ 侧订阅记录 (确保可重新订阅)
    try:
        iec61850.IedConnection_uninstallReportHandler(conn, nref)
    except Exception as e:
        log.debug(f"uninstallReportHandler 异常 (非致命): {rcb_ref}, {e}")

    # 4. 释放 Python 引用 + 防止 SWIG 重复析构
    info.subscriber = None
    info.handler = None
    if handler is not None and hasattr(handler, "thisown"):
        try:
            handler.thisown = 0
        except Exception:
            pass

    log.info(f"报告回调已注销: {rcb_ref}")
    return True
```

**关键点**:
- `deleteEventHandler()` — `EventSubscriber` 的方法，断开 C++→Python 的 director 回调链
- `IedConnection_uninstallReportHandler()` — 按 rcbReference 清理 C++ 连接中的订阅记录
- `handler.thisown = 0` — 防止 SWIG 在 C++ 对象已释放后再次调用 Python 析构函数

### 3.2 install 时先注销旧回调

`install()` 方法中，如果检测到同一 rcb_ref 已注册，先调用 `uninstall()` 注销旧回调，再重新安装：

```python
# 如果已注册，先注销
with _CALLBACK_LOCK:
    already_registered = rcb_ref in _CALLBACK_REGISTRY
if already_registered:
    ReportCallbackHandler.uninstall(connection, rcb_ref)
```

避免重复 `subscribe()` 时报 "already registered"。

### 3.3 URCB 新增 disable_direct 方法

禁用 URCB 只需设置 `RptEna=False`，不涉及 TrgOps/OptFields/IntgPd，单独实现一个简洁的禁用方法：

```python
@staticmethod
def disable_direct(connection, rcb_ref: str) -> bool:
    """直接禁用 URCB，仅设置 RptEna=False，不涉及其他属性"""
    conn = connection.connection
    nref = UrcbHandler._normalize_ref(rcb_ref)
    rcb = UrcbHandler._create_rcb_block(nref)

    try:
        iec61850.ClientReportControlBlock_setRptEna(rcb, False)
        result = iec61850.IedConnection_setRCBValues(conn, rcb, UrcbHandler.RCB_RPT_ENA, True)
        set_error = result[1] if len(result) > 1 else 0

        if set_error != iec61850.IED_ERROR_OK:
            log.warning(f"URCB 禁用失败: ref={rcb_ref}, error={set_error}")
            return False

        log.info(f"URCB 已禁用: {rcb_ref}")
        return True
    finally:
        iec61850.ClientReportControlBlock_destroy(rcb)
```

**对比 `set_rpt_ena` 禁用路径**:

| 步骤 | `set_rpt_ena(False)` | `disable_direct()` |
|------|---------------------|-------------------|
| getRCBValues 读取当前值 | ✅ 执行 | ❌ 跳过 |
| 读取当前 RptEna | ✅ 执行 | ❌ 跳过 |
| 幂等保护判断 | ✅ 执行 | ❌ 跳过 |
| TrgOps/OptFields/IntgPd 处理 | ✅ 执行 | ❌ 跳过 |
| setRptEna(False) | ✅ 执行 | ✅ 执行 |
| setRCBValues 写回 | ✅ 执行 | ✅ 执行 |

### 3.4 _disable_report 统一走 disable_direct

`__init__.py` 中 `_disable_report()` 的 URCB 和 BRCB 分支都改为调用 `disable_direct`：

```python
def _disable_report(self, rcb_ref: str) -> bool:
    rcb_type = self._infer_rcb_type(rcb_ref)
    try:
        if rcb_type == "BRCB":
            success = BrcbHandler.disable_direct(self._connection, rcb_ref)
        else:
            success = UrcbHandler.disable_direct(self._connection, rcb_ref)  # ← 改为 disable_direct

        if not success:
            return False
    except Exception as e:
        log.error(f"禁用报告异常: {rcb_ref}, {e}")
        return False

    # 短暂等待，确保报告源完全停止
    time.sleep(0.1)

    # 再注销回调（此时已无新报告产生，更安全）
    try:
        ReportCallbackHandler.uninstall(self._connection, rcb_ref)
    except Exception as e:
        log.error(f"注销回调失败: {rcb_ref}, {e}")

    return True
```

### 3.5 _set_rpt_ena_raw 禁用分支也走 disable_direct

`_set_rpt_ena_raw()` 在 `_enable_report` 回滚场景中被调用（传 `False`），也属于禁用场景，统一走 `disable_direct`：

```python
def _set_rpt_ena_raw(self, rcb_ref: str, enable: bool) -> bool:
    rcb_type = self._infer_rcb_type(rcb_ref)
    if not enable:
        # 禁用走 disable_direct，简单直接
        if rcb_type == "BRCB":
            return BrcbHandler.disable_direct(self._connection, rcb_ref)
        else:
            return UrcbHandler.disable_direct(self._connection, rcb_ref)
    # 使能
    if rcb_type == "BRCB":
        return BrcbHandler.set_rpt_ena(self._connection, rcb_ref, True)
    else:
        return UrcbHandler.set_rpt_ena(self._connection, rcb_ref, True)
```

### 3.6 shutdown_all 同步修复

`shutdown_all()` 采用与 `uninstall` 相同的清理模式：

```python
@staticmethod
def shutdown_all(connection) -> None:
    conn = connection.connection if connection else None

    # 1. 锁内清空注册表
    with _CALLBACK_LOCK:
        refs = list(_CALLBACK_REGISTRY.keys())
        infos = [_CALLBACK_REGISTRY.pop(ref) for ref in refs]

    # 2. 锁外逐个清理
    for ref, info in zip(refs, infos, strict=True):
        subscriber = info.subscriber
        handler = info.handler
        if subscriber is not None:
            try:
                subscriber.deleteEventHandler()
            except Exception:
                pass
        if conn is not None:
            try:
                iec61850.IedConnection_uninstallReportHandler(conn, _normalize_ref(ref))
            except Exception:
                pass
        if handler is not None and hasattr(handler, "thisown"):
            try:
                handler.thisown = 0
            except Exception:
                pass

    # 3. 释放引用
    for info in infos:
        info.subscriber = None
        info.handler = None
```


## 4. 线程安全分析

### 4.1 死锁规避

`_dispatch_report` 在 `_CALLBACK_LOCK` 内读取注册表，在锁外解析报告和调用用户回调。`uninstall` 中的 C 层操作 (`deleteEventHandler`、`uninstallReportHandler`) 是同步调用，会等待 C++ 接收线程完成当前回调。

如果在持有 `_CALLBACK_LOCK` 时调用 C 层注销：
```
线程A (uninstall):     持有 _CALLBACK_LOCK → 调用 deleteEventHandler → 等待接收线程
线程B (C++接收线程):   调用 _dispatch_report → 等待 _CALLBACK_LOCK → 死锁
```

**解决方案**: 严格遵循"锁内操作注册表，锁外操作 C 层"的原则：

| 操作 | 持锁? | 说明 |
|------|-------|------|
| `_CALLBACK_REGISTRY.pop()` | ✅ 锁内 | 快速操作，不阻塞 |
| `subscriber.deleteEventHandler()` | ❌ 锁外 | 同步等待 C++ 线程 |
| `IedConnection_uninstallReportHandler()` | ❌ 锁外 | 同步等待 C++ 线程 |
| `handler.thisown = 0` | ❌ 锁外 | SWIG 属性设置 |
| 释放 Python 引用 | ❌ 锁外 | GC 回收 |

### 4.2 禁用→注销的安全时序

`_disable_report` 中的操作顺序：

```
1. disable_direct()     → 设置 RptEna=False，停止报告源
2. time.sleep(0.1)      → 等待 C++ 接收线程处理完队列中残留报告
3. uninstall()          → 注销回调 (此时无新报告产生)
```

先停止报告源再注销回调，避免注销过程中 C++ 线程仍在接收新报告并回调 Python。


## 5. 修改文件清单

| 文件 | 改动量 | 说明 |
|------|-------|------|
| `src/proto/iec61850/plugins/reports/callback.py` | 大 (~80行) | `uninstall()` 重写为四步注销法；`shutdown_all()` 同步修复；`install()` 恢复重复注册检测 |
| `src/proto/iec61850/plugins/reports/urcb.py` | 中 (~45行) | 新增 `disable_direct()` 静态方法，仅设置 RptEna=False |
| `src/proto/iec61850/plugins/reports/__init__.py` | 小 (~15行) | `_disable_report()` URCB 分支改用 `disable_direct`；`_set_rpt_ena_raw()` 禁用分支改用 `disable_direct` |


## 6. 关键技术决策

### 6.1 为什么不只用 deleteEventHandler？

`deleteEventHandler()` 只断开 SWIG director 链（C++ 不再回调 Python），但不清理 C++ `IedConnection` 内部按 rcbReference 注册的订阅记录。再次 `subscribe()` 同一 rcbReference 时仍会报 "already registered"。

必须配合 `IedConnection_uninstallReportHandler(conn, nref)` 彻底清理 C++ 侧记录。

### 6.2 为什么需要 handler.thisown = 0？

`_PyRCBHandler` 是 SWIG director 子类，C++ 侧通过 `setEventHandler()` 持有它。当 `deleteEventHandler()` 断开链路后，C++ 析构 `RCBSubscriber` 时可能已释放 handler 的 C++ 部分。如果 SWIG 再调用 Python 析构函数，就会 double-free。

设置 `thisown = 0` 告诉 SWIG："这个对象的 C++ 部分不由 Python 管理"，避免重复析构。这一模式来自 pyiec61850 GOOSE 订阅器的 `_cleanup()` 方法。

### 6.3 为什么 URCB 不需要 Resv 预约？

Resv（预约）机制是 BRCB（缓冲报告控制块）才需要的，用于多客户端竞争场景下预约 RCB 的写权限。URCB（非缓冲报告控制块）按 IEC 61850 标准不需要 Resv，直接读写 RptEna 即可。

之前的代码在 URCB 中引入了 Resv 逻辑，导致禁用时出现 `error=26`（预约失败）等问题。移除 Resv 后 URCB 操作恢复正常。

### 6.4 为什么禁用要单独一个函数？

`set_rpt_ena()` 同时处理使能和禁用，禁用路径会执行大量不必要的逻辑（读取当前值、幂等判断、TrgOps/OptFields 处理）。这些逻辑在禁用场景下不仅无用，还增加了出错概率。

`disable_direct()` 只做一件事：设置 RptEna=False。简洁、可靠、无副作用。


## 7. 验证结果

| 测试场景 | 修复前 | 修复后 |
|---------|--------|--------|
| 使能 URCB 报告 | ✅ 正常 | ✅ 正常 |
| 禁用 URCB 报告 | ❌ `error=26` / 崩溃 | ✅ 正常 |
| 使能→禁用→再使能 | ❌ "already registered" / 崩溃 | ✅ 正常 |
| 禁用后立即操作 | ❌ 段错误崩溃 | ✅ 正常 |
| 使能状态下修改配置 | ❌ 写入失败 | ✅ 提示需先禁用 |
| 插件关闭 (shutdown_all) | ❌ 可能崩溃 | ✅ 正常 |


## 8. 后续建议

1. **监控 C++ 对象生命周期** — 考虑在 `_CallbackInfo` 中增加引用计数或弱引用机制，进一步防止 C++ 对象被提前 GC
2. **添加回调注册状态检查** — `install()` 前检查 C++ 侧是否已有同 rcbReference 的订阅，避免依赖异常信息判断
3. **统一 BRCB/URCB 禁用接口** — `disable_direct` 已在两者实现，可考虑提取到基类或协议接口
