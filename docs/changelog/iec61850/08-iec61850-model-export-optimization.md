# IEC 61850 模型导出优化方案

> ⚠️ **本文档已废弃**，已合并至 [iec61850-unified-model-refactoring.md](./09-iec61850-unified-model-refactoring.md) v3.0  
> 合并原因: 模型导出优化与统一模型发现去重、SCL 重构存在强关联，统一文档避免信息分裂  
> 废弃日期: 2026-06-02

> 版本: 1.0  
> 日期: 2026-06-02  
> 状态: 已废弃  
> 关联: [iec61850-unified-model-refactoring.md](./09-iec61850-unified-model-refactoring.md)

---

## 1. 问题描述

### 1.1 现象

IEC 61850 模型导出在大型 IED 设备上频繁失败，主要表现为两类错误：

**错误 A — 前端循环引用崩溃 (高频)**

```
TypeError: Converting circular structure to JSON
    --> starting at object with constructor 'Vb'
    |     property 'sub' -> object with constructor 'Np'
    --- property 'deps' closes the circle
    at JSON.stringify (<anonymous>)
    at X.deep (index-BSnTz1ay.js:2:55511)
```

Vue 响应式系统的 `reactive()` / `deep` 拷贝工具在处理大型嵌套数据时，内部 Signal/Effect 依赖图产生循环引用，导致 `JSON.stringify` 栈溢出。

**错误 B — 大模型导出超时/内存溢出 (中频)**

大型 IED（如 50+ LD、500+ LN、5000+ DO）导出时：
- 模型发现阶段耗时超过 60s，HTTP 请求超时
- 内存峰值可达 500MB+，触发 OOM
- `_model_to_scl_dict()` 构建 SCL 字典时递归层级过深

### 1.2 影响范围

| 影响面 | 严重度 | 说明 |
|--------|--------|------|
| 导出成功率 | 🔴 严重 | 大型 IED 导出成功率 < 30% |
| 用户体验 | 🔴 严重 | 无进度反馈，长时间无响应后崩溃 |
| 数据完整性 | 🟡 中等 | 部分 JSON 导出截断，SCL/ICD 格式不规范 |
| 系统稳定性 | 🟡 中等 | 导出期间其他请求阻塞（同步阻塞） |

---

## 2. 根因分析

### 2.1 循环引用根因 (错误 A)

```
前端调用链:
  exportModel() → fetch(/api/devices/export-model) → FileResponse(blob)
       ↓
  Vue 响应式系统尝试 reactive(data) → Pinia store deep clone → JSON.stringify 循环引用
```

**问题链**:

1. `exportModel()` 使用 `fetch()` 直接下载文件，响应是 `FileResponse`，数据本身不含循环引用
2. 但 Vue 的响应式拦截器（或 Pinia 的 `$state` 深拷贝）在请求拦截阶段对 `response` 对象执行 `deep reactive()`，触发了循环引用
3. 具体位置：`deviceApi.ts:273` 的 `fetch()` 调用结果被全局响应拦截器处理
4. `Vb` / `Np` 是 Vue 3.4+ 内部 `ComputedRefImpl` / `ReactiveEffect` 的压缩后类名，`sub.deps` 形成环是 Vue 响应式追踪机制的正常行为，但在 `deep clone` 场景下会崩溃

**本质**：大型二进制 `blob` 响应不应经过响应式系统的深拷贝管道。

### 2.2 大模型导出根因 (错误 B)

**发现阶段瓶颈** (`__init__.py:144-201`):

```python
# discover() 严格串行遍历
for ld_name in ld_names:              # N 次
    for ln_name in ln_names:          # M 次
        ln_info.dos = self._discover_data_objects(...)    # O(M*N)
        ln_info.datasets = self._discover_datasets(...)   # O(M)
        ln_info.rcb_list = self._discover_rcbs(...)       # O(M)
        ln_info.gocb_list = self._discover_gocbs(...)     # O(M)
```

每次 `IedConnection_getLogicalNodeDirectory` / `IedConnection_getDataDirectory` 都是同步 MMS 请求-响应，大型 IED 的 N×M 次调用耗时可达数分钟。

**序列化阶段瓶颈** (`__init__.py:628-698`):

```python
def _model_to_dict(self, model) -> dict:
    # 整棵模型树一次性构建为 dict，内存占用 ≈ 原始数据的 3-5 倍
    return {
        "logicalDevices": [{ ... for ld in model.lds }]  # 全量构建
    }
```

**SCL/ICD 导出瓶颈** (`__init__.py:962-1154`):

- `_build_data_type_templates()` 三重循环 LD→LN→DO→DA，每次都创建新 dict
- `_model_to_scl_dict()` 构建完整的 `xmltodict` 兼容结构后再一次性 `unparse()`
- 无增量序列化能力

**内存问题**:

| 阶段 | 内存倍率 | 说明 |
|------|----------|------|
| `ServerModel` 对象 | 1x | 原始数据 |
| `_model_to_dict()` | 3-5x | dict 重建 + 字符串拷贝 |
| `_model_to_scl_dict()` | 4-6x | SCL dict + 类型模板 |
| `xmltodict.unparse()` | 2-3x | XML 字符串缓冲 |
| **峰值合计** | **10-15x** | 大模型可达 GB 级 |

### 2.3 其他问题

| 问题 | 位置 | 说明 |
|------|------|------|
| 无进度反馈 | `router.py:383` | 同步阻塞，前端无进度 |
| 无缓存 | `discover()` | 每次导出重新发现 |
| 临时文件泄漏 | `router.py:432` | `tempfile.mkdtemp` 未清理 |
| 递归深度风险 | `_discover_sub_das()` | 无递归深度限制 |
| 错误恢复缺失 | `discover()` | 任一节点失败丢弃整个 LD |

---

## 3. 优化目标

| 指标 | 当前 | 目标 | 改善幅度 |
|------|------|------|----------|
| 大模型导出成功率 | < 30% | > 95% | 3x+ |
| 5000 DO 模型导出耗时 | ~60s | < 15s | 4x |
| 峰值内存占用 | 10-15x | 2-3x | 5x |
| 前端循环引用崩溃 | 频发 | 消除 | - |
| 进度反馈 | 无 | 实时百分比 | 新增 |
| 失败恢复 | 全量重试 | 增量重试 | 新增 |

---

## 4. 详细设计

### 4.1 前端：绕过响应式深拷贝

**核心思路**：文件下载场景不应经过 `axios` 拦截器 / Pinia 深拷贝管道。

#### 4.1.1 方案 A — 独立 fetch 通道（推荐）

当前 `deviceApi.ts:272-293` 已使用原生 `fetch()`，但可能被全局拦截器包装。修改为完全独立通道：

```typescript
// deviceApi.ts
export async function exportModel(
  deviceName: string,
  exportType: ExportModelType,
  iedName: string = '',
): Promise<void> {
  // 1. 先通过独立通道获取文件内容（不经过 axios 拦截器）
  const baseURL = import.meta.env.VUE_APP_API_BASE || '/';
  const response = await fetch(`${baseURL}${DEVICE_API.EXPORT_MODEL}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      device_name: deviceName,
      export_type: exportType,
      ied_name: iedName,
    }),
    // 关键：告知浏览器不缓存大响应
    cache: 'no-store',
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    throw new Error(errorData?.message || `导出失败 (HTTP ${response.status})`);
  }

  // 2. 使用流式读取 + File System Access API 写入
  const blob = await response.blob();

  // 3. 用户选择保存位置
  const fileHandle = await (window as any).showSaveFilePicker({
    suggestedName: `${deviceName}_model${extMap[exportType]}`,
    types: [{ description: `${exportType.toUpperCase()} 文件`, accept: { [mimeMap[exportType]]: [extMap[exportType]] } }],
  });

  // 4. 流式写入文件
  const writable = await fileHandle.createWritable();
  await writable.write(blob);
  await writable.close();
}
```

#### 4.1.2 方案 B — ReadableStream 流式下载

对超大模型（> 10MB），使用流式写入避免一次性加载到内存：

```typescript
export async function exportModelStream(
  deviceName: string,
  exportType: ExportModelType,
  onProgress?: (loaded: number, total: number) => void,
): Promise<void> {
  const response = await fetch(...);
  const contentLength = Number(response.headers.get('Content-Length')) || 0;
  const reader = response.body!.getReader();

  const fileHandle = await (window as any).showSaveFilePicker({ ... });
  const writable = await fileHandle.createWritable();

  let loaded = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    await writable.write(value);
    loaded += value.length;
    onProgress?.(loaded, contentLength);
  }

  await writable.close();
}
```

### 4.2 后端：异步导出 + 流式响应

**核心思路**：将同步阻塞的导出接口改为异步任务 + 流式响应。

#### 4.2.1 异步导出接口设计

```python
# src/web/api/device/router.py

import asyncio
import uuid
from fastapi.responses import StreamingResponse

# 导出任务状态存储
_export_tasks: dict[str, ExportTask] = {}


@dataclass
class ExportTask:
    """异步导出任务"""
    task_id: str
    device_name: str
    export_type: str
    status: Literal["pending", "discovering", "exporting", "done", "failed"]
    progress: float = 0.0       # 0.0 ~ 1.0
    message: str = ""
    result_path: str = ""
    created_at: float = 0.0
    error: str = ""


@device_router.post("/export-model")
async def export_model(req: ExportModelRequest, request: Request):
    """导出 IEC 61850 模型 — 流式响应"""

    device = _get_device(req.device_name, request)
    client = device.client

    # 方案 1: 小模型直接流式返回
    model_size = _estimate_model_size(client)
    if model_size < ESTIMATED_SIZE_THRESHOLD:
        return await _export_model_streaming(client, req)
    
    # 方案 2: 大模型异步任务
    task_id = str(uuid.uuid4())
    task = ExportTask(task_id=task_id, ...)
    _export_tasks[task_id] = task
    asyncio.create_task(_run_export_task(task, client, req))
    return BaseResponse(data={"task_id": task_id, "mode": "async"})


@device_router.post("/export-model-progress")
async def get_export_progress(req: ExportProgressRequest):
    """查询异步导出进度"""
    task = _export_tasks.get(req.task_id)
    if not task:
        return BaseResponse(code=404, message="任务不存在")
    return BaseResponse(data={
        "status": task.status,
        "progress": task.progress,
        "message": task.message,
    })


@device_router.post("/export-model-download")
async def download_export_result(req: ExportProgressRequest):
    """下载已完成的导出结果"""
    task = _export_tasks.get(req.task_id)
    if not task or task.status != "done":
        return BaseResponse(code=400, message="导出未完成")
    return FileResponse(path=task.result_path, filename=Path(task.result_path).name)
```

#### 4.2.2 流式 JSON 导出

使用 `ijson` 或自定义生成器实现流式序列化，避免全量 `dict` 构建：

```python
import ijson  # 或使用自研生成器

def export_json_streaming(self, model: ServerModel) -> Iterator[str]:
    """流式生成 JSON 字符串，避免全量 dict 构建"""
    yield '{"host":"' + model.host + '",'
    yield '"port":' + str(model.port) + ','
    yield '"discover_time":"' + model.discover_time + '",'
    yield '"logicalDevices":['
    
    first_ld = True
    for ld in model.lds:
        if not first_ld:
            yield ','
        first_ld = False
        
        yield '{"name":"' + ld.name + '","inst":"' + ld.inst + '","logicalNodes":['
        
        first_ln = True
        for ln in ld.lns:
            if not first_ln:
                yield ','
            first_ln = False
            yield from self._serialize_ln(ln)
        
        yield ']}'
    
    yield ']}'
```

更优雅的方式：使用 **Builder 模式 + 生成器**：

```python
class JsonStreamWriter:
    """流式 JSON 写入器 — 零中间 dict 分配"""

    __slots__ = ('_writer', '_first', '_stack')

    def __init__(self, writer: Callable[[str], None]):
        self._writer = writer
        self._first = True
        self._stack = []

    def _write(self, chunk: str) -> None:
        self._writer(chunk)

    def object_start(self) -> 'JsonStreamWriter':
        self._write('{')
        self._first = True
        self._stack.append(True)
        return self

    def object_end(self) -> 'JsonStreamWriter':
        self._stack.pop()
        self._write('}')
        self._first = not self._stack[-1] if self._stack else True
        return self

    def key(self, name: str) -> 'JsonStreamWriter':
        if not self._first:
            self._write(',')
        self._write(f'"{name}":')
        self._first = True
        return self

    def value(self, val: Any) -> 'JsonStreamWriter':
        if not self._first:
            self._write(',')
        self._write(json.dumps(val, ensure_ascii=False))
        self._first = False
        return self

    def array_start(self, name: str) -> 'JsonStreamWriter':
        self.key(name)._write('[')
        self._first = True
        self._stack.append(True)
        return self

    def array_end(self) -> 'JsonStreamWriter':
        self._stack.pop()
        self._write(']')
        self._first = False
        return self
```

### 4.3 模型发现优化

#### 4.3.1 并发发现

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

class IEC61850ModelExporter:
    """优化后的模型导出器"""

    def __init__(self, client: "IEC61850Client", max_workers: int = 4):
        self._client = client
        self._max_workers = max_workers
        self._cache: Optional[ServerModel] = None
        self._cache_timestamp: float = 0.0
        self._cache_ttl: float = 300.0  # 5 分钟缓存

    async def discover_async(
        self,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> ServerModel:
        """异步并发发现模型"""

        # 检查缓存
        if self._is_cache_valid():
            if progress_callback:
                progress_callback(1.0, "使用缓存模型")
            return self._cache  # type: ignore

        model = ServerModel(host=self._client.ip, port=self._client.port, ...)
        ld_names = self._client.browse_logical_devices()

        total_steps = len(ld_names)
        completed = 0

        # 使用线程池并发发现各 LD
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
            tasks = []
            for ld_name in ld_names:
                task = loop.run_in_executor(
                    pool,
                    self._discover_single_ld,  # 注意：需确保线程安全
                    ld_name,
                )
                tasks.append(task)

            for future in asyncio.as_completed(tasks):
                ld_info = await future
                model.lds.append(ld_info)
                completed += 1
                if progress_callback:
                    progress_callback(completed / total_steps, f"发现 LD: {ld_info.name}")

        self._cache = model
        self._cache_timestamp = time.time()
        return model

    def _discover_single_ld(self, ld_name: str) -> LDInfo:
        """发现单个 LD 的完整模型（线程安全）"""
        # 注意：pyiec61850 的 IedConnection 不是线程安全的
        # 需要使用连接池或串行化访问
        ld_info = LDInfo(name=ld_name, inst=ld_name)
        ln_names = self._client.browse_logical_nodes(ld_name)
        for ln_name in ln_names:
            ln_info = self._discover_single_ln(ld_name, ln_name)
            ld_info.lns.append(ln_info)
        return ld_info
```

> **⚠️ 重要约束**：`pyiec61850.IedConnection` 底层是 C 对象，**不是线程安全的**。并发方案需满足以下之一：
> 1. **连接池**：为每个工作线程创建独立 `IedConnection`
> 2. **串行化调度**：使用 `asyncio` 协程 + 单线程事件循环，I/O 等待时切换
> 3. **请求级锁**：对 `IedConnection` 加互斥锁，并发退化为串行但保持非阻塞

#### 4.3.2 增量发现与容错

```python
from contextlib import contextmanager

class IEC61850ModelExporter:
    # ...

    def discover(self, *, on_error: str = "skip", max_depth: int = 10) -> ServerModel:
        """增强的模型发现 — 增量容错
        
        Args:
            on_error: 节点发现失败时的策略 ("skip" | "abort" | "retry")
            max_depth: 递归发现子 DA 的最大深度
        """
        model = ServerModel(...)
        
        for ld_name in ld_names:
            ld_info = LDInfo(name=ld_name, inst=ld_name)
            try:
                ln_names = self._client.browse_logical_nodes(ld_name)
            except Exception as e:
                log.warning(f"跳过 LD {ld_name}: {e}")
                if on_error == "abort":
                    raise
                continue

            for ln_name in ln_names:
                try:
                    ln_info = self._discover_single_ln_safe(ld_name, ln_name, max_depth)
                    ld_info.lns.append(ln_info)
                except Exception as e:
                    log.warning(f"跳过 LN {ld_name}/{ln_name}: {e}")
                    if on_error == "abort":
                        raise

            model.lds.append(ld_info)
        
        return model

    @contextmanager
    def _error_guard(self, ref: str, on_error: str = "skip"):
        """节点发现错误守卫"""
        try:
            yield
        except Exception as e:
            log.warning(f"发现 {ref} 时出错: {e}")
            if on_error == "abort":
                raise

    def _discover_sub_das(self, parent_ref: str, parent_fc: str, path_prefix: str, *, 
                          depth: int = 0, max_depth: int = 10) -> list[DAInfo]:
        """递归发现子 DA — 带深度限制"""
        if depth >= max_depth:
            log.warning(f"递归深度达到上限 {max_depth}, 停止展开: {parent_ref}")
            return []
        # ... 原有逻辑，递归调用时传入 depth + 1
```

#### 4.3.3 模型缓存

```python
import hashlib
import json
from pathlib import Path

class ModelCache:
    """模型发现结果缓存 — 避免重复遍历"""

    def __init__(self, cache_dir: str = "data/61850_cache"):
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_key(self, host: str, port: int) -> str:
        return hashlib.md5(f"{host}:{port}".encode()).hexdigest()

    def get(self, host: str, port: int, max_age: float = 300.0) -> Optional[ServerModel]:
        """获取缓存模型"""
        cache_path = self._cache_dir / f"{self._cache_key(host, port)}.json"
        if not cache_path.exists():
            return None
        
        mtime = cache_path.stat().st_mtime
        if time.time() - mtime > max_age:
            return None
        
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            return self._deserialize_model(data)
        except Exception:
            return None

    def put(self, model: ServerModel) -> None:
        """缓存模型"""
        cache_path = self._cache_dir / f"{self._cache_key(model.host, model.port)}.json"
        data = self._serialize_model(model)
        cache_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def invalidate(self, host: str, port: int) -> None:
        """使缓存失效"""
        cache_path = self._cache_dir / f"{self._cache_key(host, port)}.json"
        cache_path.unlink(missing_ok=True)
```

### 4.4 数据模型优化

#### 4.4.1 不可变数据类 + 自定义序列化

```python
from dataclasses import dataclass, field, asdict
from typing import Any

@dataclass(frozen=True, slots=True)
class DAInfo:
    """数据属性 (DA) 信息 — 不可变、可哈希"""
    name: str = ""
    path: str = ""
    fc: str = ""
    iec_type: str = ""
    sub_das: tuple["DAInfo", ...] = ()  # 用 tuple 替代 list，不可变

    def to_dict(self) -> dict[str, Any]:
        """显式序列化 — 避免 dataclasses.asdict() 的递归深拷贝"""
        result = {"name": self.name, "path": self.path, "fc": self.fc, "iecType": self.iec_type}
        if self.sub_das:
            result["subDataAttributes"] = [bda.to_dict() for bda in self.sub_das]
        return result

    def to_flat_dict(self) -> dict[str, Any]:
        """扁平化序列化 — 无嵌套，适合 CSV/表格"""
        return {"name": self.name, "path": self.path, "fc": self.fc, "iecType": self.iec_type}


@dataclass(frozen=True, slots=True)
class DOInfo:
    """数据对象 (DO) 信息"""
    name: str = ""
    ref: str = ""
    frame_type: int = -1
    das: tuple[DAInfo, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ref": self.ref,
            "frameType": self.frame_type,
            "frameTypeDesc": FRAME_TYPE_DESC.get(self.frame_type, "未知"),
            "dataAttributes": [da.to_dict() for da in self.das],
        }


@dataclass(frozen=True, slots=True)
class LNInfo:
    """逻辑节点 (LN) 信息"""
    name: str = ""
    ln_class: str = ""
    ref: str = ""
    dos: tuple[DOInfo, ...] = ()
    datasets: tuple[DataSetInfo, ...] = ()
    rcb_list: tuple[RCBInfo, ...] = ()
    gocb_list: tuple[GoCBInfo, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"name": self.name, "lnClass": self.ln_class, "ref": self.ref}
        if self.dos:
            result["dataObjects"] = [do.to_dict() for do in self.dos]
        if self.datasets:
            result["dataSets"] = [ds.to_dict() for ds in self.datasets]
        if self.rcb_list:
            result["reportControlBlocks"] = [rcb.to_dict() for rcb in self.rcb_list]
        if self.gocb_list:
            result["gooseControlBlocks"] = [gocb.to_dict() for gocb in self.gocb_list]
        return result


@dataclass(frozen=True, slots=True)
class LDInfo:
    """逻辑设备 (LD) 信息"""
    name: str = ""
    inst: str = ""
    lns: tuple[LNInfo, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "inst": self.inst,
            "logicalNodes": [ln.to_dict() for ln in self.lns],
        }


@dataclass(frozen=True, slots=True)
class ServerModel:
    """服务端完整模型"""
    host: str = ""
    port: int = 102
    discover_time: str = ""
    lds: tuple[LDInfo, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """显式序列化 — 替代 _model_to_dict()"""
        return {
            "host": self.host,
            "port": self.port,
            "discover_time": self.discover_time,
            "logicalDevices": [ld.to_dict() for ld in self.lds],
            "summary": self._compute_summary(),
        }

    def _compute_summary(self) -> dict[str, int]:
        return {
            "totalLDs": len(self.lds),
            "totalLNs": sum(len(ld.lns) for ld in self.lds),
            "totalDOs": sum(len(ln.dos) for ld in self.lds for ln in ld.lns),
            "totalDAs": sum(len(do.das) for ld in self.lds for ln in ld.lns for do in ln.dos),
        }
```

**关键改进**：

| 改动 | 原设计 | 新设计 | 收益 |
|------|--------|--------|------|
| `frozen=True` | 可变 dataclass | 不可变 | 防止意外修改，可做缓存 key |
| `slots=True` | `__dict__` | `__slots__` | 内存减少 40-50%，属性访问更快 |
| `tuple` 替代 `list` | `list[DAInfo]` | `tuple[DAInfo, ...]` | 不可变，可哈希，更安全 |
| `to_dict()` | `_model_to_dict()` 外部方法 | 每个类自带 `to_dict()` | 职责内聚，避免巨型转换函数 |
| 无 `asdict()` | 隐式 `dataclasses.asdict()` | 显式 `to_dict()` | 避免深拷贝循环引用 |

#### 4.4.2 Builder 模式构建模型

```python
from typing import Protocol

class ModelBuilder(Protocol):
    """模型构建器协议 — 策略模式"""
    def add_ld(self, ld: LDInfo) -> None: ...
    def add_ln(self, ld_name: str, ln: LNInfo) -> None: ...
    def add_do(self, ld_name: str, ln_ref: str, do: DOInfo) -> None: ...
    def build(self) -> ServerModel: ...


class InMemoryModelBuilder:
    """内存模型构建器 — 适用于小/中模型"""

    def __init__(self, host: str, port: int):
        self._host = host
        self._port = port
        self._lds: dict[str, list[LNInfo]] = {}
        self._ln_map: dict[str, list[DOInfo]] = {}  # ln_ref -> [DOInfo]
        self._ds_map: dict[str, list[DataSetInfo]] = {}
        self._rcb_map: dict[str, list[RCBInfo]] = {}
        self._gocb_map: dict[str, list[GoCBInfo]] = {}

    def add_ld(self, ld: LDInfo) -> None:
        self._lds[ld.name] = []

    def add_ln(self, ld_name: str, ln: LNInfo) -> None:
        self._lds[ld_name].append(ln)

    def build(self) -> ServerModel:
        lds = []
        for ld_name, lns in self._lds.items():
            lds.append(LDInfo(name=ld_name, inst=ld_name, lns=tuple(lns)))
        return ServerModel(
            host=self._host, port=self._port,
            discover_time=time.strftime("%Y-%m-%d %H:%M:%S"),
            lds=tuple(lds),
        )


class StreamingModelBuilder:
    """流式模型构建器 — 边发现边序列化，内存占用恒定"""

    def __init__(self, writer: JsonStreamWriter, host: str, port: str):
        self._writer = writer
        self._host = host
        self._port = port

    def start(self) -> None:
        self._writer.object_start()
        self._writer.key("host").value(self._host)
        self._writer.key("port").value(self._port)
        self._writer.array_start("logicalDevices")

    def add_ld(self, ld: LDInfo) -> None:
        self._writer.object_start()
        self._writer.key("name").value(ld.name)
        self._writer.key("inst").value(ld.inst)
        self._writer.array_start("logicalNodes")

    def end_ld(self) -> None:
        self._writer.array_end()  # logicalNodes
        self._writer.object_end()  # LD

    def finish(self) -> None:
        self._writer.array_end()  # logicalDevices
        self._writer.object_end()  # root
```

### 4.5 导出格式优化

#### 4.5.1 JSON 流式导出

```python
def export_json_streaming(
    self,
    model: ServerModel,
    output_path: str,
) -> None:
    """流式 JSON 导出 — 内存占用 O(1)"""
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        writer = JsonStreamWriter(f.write)
        builder = StreamingModelBuilder(writer, model.host, model.port)
        
        builder.start()
        for ld in model.lds:
            builder.add_ld(ld)
            for ln in ld.lns:
                # 逐 LN 序列化，用完即丢弃
                writer._write(json.dumps(ln.to_dict(), ensure_ascii=False))
            builder.end_ld()
        builder.finish()

    log.info(f"模型已流式导出为 JSON: {output_path}")
```

#### 4.5.2 CSV 增量导出

```python
def export_csv_incremental(
    self,
    model: ServerModel,
    output_path: str,
) -> None:
    """增量 CSV 导出 — 逐行写入，内存 O(1)"""
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["LD", "LN", "LN类", "DO", "DA路径", "FC", "数据类型", "帧类型", "完整引用"])

        for ld in model.lds:
            for ln in ld.lns:
                for do_info in ln.dos:
                    for da in do_info.das:
                        writer.writerow([
                            ld.name, ln.name, ln.ln_class,
                            do_info.name, da.path, da.fc,
                            da.iec_type, str(do_info.frame_type),
                            f"{do_info.ref}.{da.path}",
                        ])
                        # sub_das 逐行写入
                        for bda in da.sub_das:
                            writer.writerow([
                                ld.name, ln.name, ln.ln_class,
                                do_info.name, bda.path, bda.fc,
                                bda.iec_type, str(do_info.frame_type),
                                f"{do_info.ref}.{bda.path}",
                            ])
```

#### 4.5.3 ICD/SCL 流式导出

`xmltodict` 需要完整 dict，无法流式。改用 `lxml` 的增量序列化：

```python
from lxml import etree

def export_icd_streaming(
    self,
    model: ServerModel,
    output_path: str,
    ied_name: str = "",
) -> None:
    """流式 ICD 导出 — 使用 lxml 增量序列化"""
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    nsmap = {"xmlns": "http://www.iec.ch/61850/2003/SCL"}
    
    with open(output_path, "wb") as f:
        # 使用 lxml 的 XML 文件写入器，增量生成
        writer = etree.xmlfile(f, encoding="utf-8", pretty_print=True)
        
        with writer.element("SCL", nsmap=nsmap):
            # Header
            with writer.element("Header"):
                writer.write(etree.Element("Header", id="", version="1", toolID="IEC61850ModelExporter"))
            
            # Communication
            with writer.element("Communication"):
                ...
            
            # IED — 逐 LD 增量写入
            with writer.element("IED", name=ied_name):
                with writer.element("AccessPoint", name="S1"):
                    with writer.element("Server"):
                        for ld in model.lds:
                            with writer.element("LDevice", inst=ld.name):
                                for ln in ld.lns:
                                    ln_elem = self._build_ln_element(ln)
                                    writer.write(ln_elem)
                                    # ln_elem 即时释放
            
            # DataTypeTemplates — 逐 LN 增量写入
            with writer.element("DataTypeTemplates"):
                for ld in model.lds:
                    for ln in ld.lns:
                        ln_type_elem = self._build_lnode_type_element(ln)
                        writer.write(ln_type_elem)
```

### 4.6 临时文件管理与资源清理

```python
import atexit
import shutil
from pathlib import Path

# 临时文件跟踪
_temp_dirs: list[str] = []

def _cleanup_temp_dirs() -> None:
    """进程退出时清理所有临时目录"""
    for d in _temp_dirs:
        shutil.rmtree(d, ignore_errors=True)

atexit.register(_cleanup_temp_dirs)


@device_router.post("/export-model")
async def export_model(req: ExportModelRequest, request: Request):
    """导出模型 — 带资源清理"""
    tmp_dir = tempfile.mkdtemp(prefix="ems_export_")
    _temp_dirs.append(tmp_dir)
    
    try:
        # ... 导出逻辑 ...
        response = FileResponse(path=tmp_path, filename=filename, media_type=media_type)
        
        # 使用 background task 清理临时文件
        from starlette.background import BackgroundTask
        response.background = BackgroundTask(_cleanup_single, tmp_dir, tmp_path)
        return response
    except Exception:
        _cleanup_single(tmp_dir, "")
        raise


def _cleanup_single(tmp_dir: str, keep_file: str) -> None:
    """清理临时目录"""
    try:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        if tmp_dir in _temp_dirs:
            _temp_dirs.remove(tmp_dir)
    except Exception:
        pass
```

---

## 5. 实施计划

### Phase 1: 紧急修复 — 消除循环引用崩溃 (0.5 天)

**优先级**: P0 🔴  
**目标**: 前端导出不再因循环引用崩溃

| 任务 | 文件 | 说明 |
|------|------|------|
| 1.1 确认 fetch 通道独立 | `deviceApi.ts` | 确保 `exportModel()` 的 fetch 不经 axios 拦截器 |
| 1.2 临时文件清理 | `router.py` | 使用 `BackgroundTask` 清理临时目录 |
| 1.3 添加响应类型头 | `router.py` | 确认 `FileResponse` 有正确的 `Content-Type` |

**验证**: 导出 1000+ DO 模型不再出现循环引用错误

### Phase 2: 数据模型重构 (1 天)

**优先级**: P0 🔴  
**目标**: 消除 `_model_to_dict()` 巨型转换函数，每个模型类自带序列化

| 任务 | 文件 | 说明 |
|------|------|------|
| 2.1 DAInfo/DOInfo/LNInfo/LDInfo/ServerModel 改为 `frozen=True, slots=True` | `__init__.py` | 不可变 + 低内存 |
| 2.2 `list` 改 `tuple` | `__init__.py` | 子元素不可变 |
| 2.3 各类添加 `to_dict()` | `__init__.py` | 替代 `_model_to_dict()` |
| 2.4 `_model_to_dict()` 重构为调用 `model.to_dict()` | `__init__.py` | 向后兼容过渡 |
| 2.5 `_discover_sub_das()` 添加 `max_depth` 参数 | `__init__.py` | 防止无限递归 |
| 2.6 `discover()` 添加 `on_error` 策略 | `__init__.py` | 增量容错 |

**验证**: 所有导出格式输出不变，`to_dict()` 结果与原 `_model_to_dict()` 一致

### Phase 3: 流式导出 (1-2 天)

**优先级**: P1 🟡  
**目标**: JSON/CSV/ICD 导出内存占用降至 O(1)

| 任务 | 文件 | 说明 |
|------|------|------|
| 3.1 实现 `JsonStreamWriter` | 新文件 `stream_writer.py` | 流式 JSON 写入器 |
| 3.2 实现 `export_json_streaming()` | `__init__.py` | 替代 `export_json()` |
| 3.3 实现 `export_csv_incremental()` | `__init__.py` | 替代 `export_csv()` |
| 3.4 引入 `lxml` 依赖 | `pyproject.toml` | 替代 `xmltodict` 实现 ICD 流式导出 |
| 3.5 实现 `export_icd_streaming()` | `__init__.py` | 使用 `lxml.xmlfile` 增量序列化 |

**验证**: 5000 DO 模型导出峰值内存 < 200MB

### Phase 4: 异步导出 + 进度反馈 (1 天)

**优先级**: P1 🟡  
**目标**: 大模型导出不再阻塞，前端可显示进度

| 任务 | 文件 | 说明 |
|------|------|------|
| 4.1 定义 `ExportTask` 数据类 | `router.py` | 异步任务状态 |
| 4.2 实现 `/export-model` 双模式（流式/异步） | `router.py` | 小模型流式，大模型异步 |
| 4.3 实现 `/export-model-progress` 端点 | `router.py` | 查询导出进度 |
| 4.4 实现 `/export-model-download` 端点 | `router.py` | 下载异步导出结果 |
| 4.5 前端 `ModelExportDialog.vue` 添加进度条 | `ModelExportDialog.vue` | 轮询进度 |
| 4.6 前端 `deviceApi.ts` 添加异步导出 API | `deviceApi.ts` | 对接异步接口 |

**验证**: 大模型导出时前端可正常操作，进度实时更新

### Phase 5: 模型缓存 (0.5 天)

**优先级**: P2 🟢  
**目标**: 重复导出无需重新发现

| 任务 | 文件 | 说明 |
|------|------|------|
| 5.1 实现 `ModelCache` 类 | 新文件 `cache.py` | 基于 JSON 文件的缓存 |
| 5.2 `discover()` 集成缓存 | `__init__.py` | 先查缓存，过期则重新发现 |
| 5.3 添加缓存失效 API | `router.py` | 手动清除缓存 |
| 5.4 缓存目录清理策略 | `cache.py` | LRU 或 TTL 自动清理 |

**验证**: 二次导出同一设备，发现阶段耗时 < 1s

---

## 6. 设计模式应用

| 模式 | 应用位置 | 说明 |
|------|----------|------|
| **Builder** | `InMemoryModelBuilder` / `StreamingModelBuilder` | 分离模型构建与表示，支持流式构建 |
| **Strategy** | `JsonStreamWriter` / `CsvStreamWriter` / `XmlStreamWriter` | 导出策略可替换 |
| **Frozen Dataclass** | `DAInfo`, `DOInfo`, `LNInfo`, `ServerModel` | 值对象不可变，线程安全 |
| **Generator** | `export_json_streaming()` | 惰性求值，内存 O(1) |
| **Cache-Aside** | `ModelCache` | 读取时查缓存，未命中则加载 |
| **Error Guard** | `_error_guard()` 上下文管理器 | 统一容错策略 |
| **Background Task** | `_cleanup_single()` | 资源延迟清理 |
| **Two-Phase** | 小模型同步/大模型异步 | 按规模选择策略 |

---

## 7. 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| `pyiec61850` 非线程安全 | 高 | 并发发现可能崩溃 | 使用连接池或串行化锁 |
| `frozen dataclass` 兼容性 | 低 | 构建阶段需可变对象 | Builder 构建完成后 `freeze` |
| `lxml` 新依赖引入 | 低 | 增加部署复杂度 | 提供 `xmltodict` 回退路径 |
| 流式导出格式差异 | 中 | JSON/ICD 输出可能微小差异 | 对比测试保证语义一致 |
| 缓存一致性问题 | 低 | IED 模型变更后缓存过期 | TTL + 手动失效 API |
| 前端异步轮询开销 | 低 | 频繁请求后端 | WebSocket 推送或 SSE 替代 |

---

## 8. 验收标准

- [ ] 前端导出不再出现 `Converting circular structure to JSON` 错误
- [ ] 5000 DO 模型导出成功率 > 95%
- [ ] 5000 DO 模型导出耗时 < 15s（首次）/ < 2s（缓存命中）
- [ ] 导出期间前端 UI 不阻塞，可显示进度
- [ ] JSON 导出峰值内存 < 200MB
- [ ] ICD 导出峰值内存 < 300MB
- [ ] 临时文件在导出完成后自动清理
- [ ] 递归深度超过 10 层时优雅降级而非崩溃
- [ ] 单个 LD/LN 发现失败不影响其他节点导出
- [ ] 所有导出格式输出与优化前语义一致
