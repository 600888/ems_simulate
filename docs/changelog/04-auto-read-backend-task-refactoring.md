# 自动读取后端任务化整改

> 版本：1.0
> 日期：2026-08-23
> 分类：自动读取 / 后台任务 / 协议 IO / 生命周期治理 / 前后端重构
> 状态：已实施

## 1. 问题背景

设备页面原有三套读取调度机制，任务归属和取消语义不一致：

| 场景                       | 整改前实现                                   | 主要问题                                                                        |
| -------------------------- | -------------------------------------------- | ------------------------------------------------------------------------------- |
| 批量自动读取               | `Device.data_update_thread` 使用固定周期线程 | 配置、状态、错误和停止语义不完整，前端选择的周期无法完整传递                    |
| 逐点自动读取               | 前端拉取全量点表，再逐点调用 `read-single`   | 页面生命周期决定任务生命周期；HTTP 请求数量随测点数量增长；停止只能终止前端循环 |
| IEC 61850 DataSet 自动读取 | 前端递归定时调用表格查询接口                 | 查询接口产生 MMS 读取副作用；页面切换、休眠会影响任务                           |
| 手动批量/逐点读取          | 前端请求或循环直接承担读取过程               | 无统一后台任务状态；取消、冲突和进度统计不一致                                  |

这套实现把“读取任务调度”和“页面状态刷新”混在一起。页面轮询不仅用于展示，还会真实触发协议 IO，因此存在以下风险：

1. 离开页面后任务中断，重新进入页面无法恢复任务状态；
2. 慢设备或网络抖动时，前端定时器可能产生请求叠加；
3. 逐点读取会产生大量 HTTP 请求，后端无法统一控制点间隔和取消边界；
4. 表格和 DataSet 查询不再是纯查询，普通刷新也可能访问远端设备；
5. 自动读取、手动读取可能同时访问同一个协议连接；
6. 停止操作不能准确表达 `running`、`stopping`、`failed` 等状态。

本次整改将自动读取、手动批量读取、手动逐点读取和手动 DataSet 读取统一迁移到后端任务管理器。前端仍可查询状态和缓存数据，但不再负责调度真实读取。

## 2. 目标架构

```text
Slave.vue / useAutoRead.ts
  ├─ start-auto-read         只提交一次自动读取配置
  ├─ stop-auto-read          显式请求停止
  ├─ auto-read-status        查询状态快照，不触发协议 IO
  ├─ manual-read             只提交一次手动读取任务
  ├─ manual-read-status      查询手动任务进度和计数
  └─ 表格 / DataSet 查询      只读取内存缓存
                         │
                         ▼
Device
  ├─ AutoReadTaskManager(repeat=True)
  ├─ AutoReadTaskManager(repeat=False)
  ├─ asyncio.Task + asyncio.Event
  ├─ 设备级 read_lock
  └─ batch / single / dataset runner
                         │
                         ▼
DataReader / PointOperator / ProtocolHandler
  └─ 协议连接仍由当前后端进程唯一持有
```

核心边界如下：

- 后端持有任务生命周期，页面切换不会停止自动读取；
- 每个设备最多运行一个自动读取任务，手动读取与自动读取互斥；
- 批量、逐点、DataSet 三种模式使用同一配置和状态模型；
- 停止使用协作式取消，在测点、分组、轮次和等待边界检查 stop event；
- 表格、树和状态查询只读缓存，不隐式触发协议 IO；
- 自动读取不在前端展示进度条；手动读取保留实时进度、成功数和失败数；
- 后端重启后任务不恢复，设备停止、替换或关闭时必须清理任务。

## 3. Celery 评估结论

本次没有引入 Celery，而是使用后端进程内、设备级的 `asyncio` 任务管理器。

| 评估项     | 当前项目特点                                             | 结论                                                       |
| ---------- | -------------------------------------------------------- | ---------------------------------------------------------- |
| 设备资源   | `Device`、串口、Socket、MMS 连接和原生句柄均在当前进程内 | Celery worker 无法安全直接复用                             |
| 部署形态   | Tauri + PyInstaller 单后端 sidecar                       | 增加 Redis/RabbitMQ 和 worker 会扩大安装、启动及退出复杂度 |
| 任务持久化 | 读取任务从属于当前设备连接会话                           | 不需要跨进程、跨重启持久化                                 |
| 横向扩展   | 单机桌面应用，协议连接要求单一所有者                     | 分布式调度收益很低，反而会产生设备所有权冲突               |
| 取消要求   | 停止后不能破坏正在使用的本地协议连接                     | `revoke/terminate` 不适合管理进程内原生连接                |

只有当产品演进为多实例服务端部署、设备连接被拆分成独立代理服务、任务输入完全可序列化并且已有可靠 broker 时，才需要重新评估 Celery。即使在该阶段，Celery 也更适合文件导入、模型生成等离线任务，不应直接取得实时协议连接的所有权。

## 4. 后端整改

### 4.1 统一任务配置和状态模型

新增 `src/device/auto_read/` 模块，统一定义读取模式、任务状态、配置快照、轮次结果和 DataSet 快照。

关键代码：

```python
class AutoReadMode(StrEnum):
    BATCH = "batch"
    SINGLE = "single"
    DATASET = "dataset"


class AutoReadState(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    STOPPING = "stopping"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class AutoReadConfig:
    mode: AutoReadMode = AutoReadMode.BATCH
    cycle_interval_ms: int = 1000
    request_interval_ms: int = 0
    slave_id: int | None = None
    channel_id: int | None = None
    category: str = ""
    item: str = ""
    point_types: tuple[int, ...] = ()
    dlt645_prefix: int | None = None
    dlt645_settlement: int | None = None
```

`cycle_interval_ms` 表示一轮结束到下一轮开始的间隔；`request_interval_ms` 表示逐点或分组请求之间的限速间隔，不再复用一个含糊的 `interval` 表达两种含义。

状态快照包含：

```json
{
  "state": "idle | running | stopping | failed",
  "task_id": "uuid",
  "mode": "batch | single | dataset",
  "config": {},
  "started_at": "ISO-8601 or null",
  "last_cycle_at": "ISO-8601 or null",
  "cycle_count": 0,
  "current": 0,
  "total": 0,
  "success": 0,
  "fail": 0,
  "last_error": null
}
```

### 4.2 设备级后台任务管理器

`AutoReadTaskManager` 使用 `asyncio.Task` 托管循环，使用 `asyncio.Event` 传递停止信号，并通过任务 ID 防止旧任务结果覆盖新状态。

自动读取使用重复任务，手动读取使用相同管理器的单轮模式：

```python
self.auto_read_manager = AutoReadTaskManager(self._run_auto_read_cycle)
self.manual_read_manager = AutoReadTaskManager(
    self._run_auto_read_cycle,
    repeat=False,
)
```

任务循环的关键实现：

```python
async def _run(self, task_id, config, stop_event):
    try:
        while not stop_event.is_set():
            self._update_progress(task_id, 0, 0, 0, 0)
            result = await self._runner(
                config,
                stop_event,
                lambda current, total, success, fail: self._update_progress(
                    task_id, current, total, success, fail
                ),
            )
            if self._status.task_id != task_id:
                return

            self._status.cycle_count += 1
            self._status.success = result.success
            self._status.fail = result.fail

            if not self._repeat or stop_event.is_set():
                break

            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=config.cycle_interval_ms / 1000.0,
                )
            except TimeoutError:
                pass
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        if self._status.task_id == task_id:
            self._status.state = AutoReadState.FAILED
            self._status.last_error = str(exc)
    finally:
        if (
            self._status.task_id == task_id
            and self._status.state != AutoReadState.FAILED
        ):
            self._set_idle()
```

实际实现对普通异常、`CancelledError`、循环等待和最终状态收口分别处理，避免取消被误记为失败。

### 4.3 协作式停止与真实 `stopping` 状态

停止操作不会强杀正在执行 `asyncio.to_thread()` 的原生调用。强行取消 Python await 并不能终止底层线程，反而可能提前报告 `idle`，让第二个任务并发使用同一连接。

关键代码：

```python
async def stop(self, timeout: float = 1.0) -> dict[str, Any]:
    task = self._task
    if task is None or task.done():
        self._set_idle()
        return self.status()

    self._status.state = AutoReadState.STOPPING
    if self._stop_event is not None:
        self._stop_event.set()

    with suppress(TimeoutError):
        await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
    return self.status()
```

停止语义调整为：

1. 立即阻止开始新的测点、分组和下一轮；
2. 可中断的点间隔和轮次等待立即响应；
3. 已进入的同步原生 IO 在自身超时内返回，期间保持 `stopping`；
4. 旧任务完全退出前拒绝启动冲突任务；
5. 设备停止时执行更长的有界等待，最终关闭协议资源。

### 4.4 批量、逐点和 DataSet 使用同一轮次执行器

`Device._run_auto_read_cycle()` 根据不可变配置快照选择执行方式。

逐点模式不再由前端获取点表和循环请求，而是在后端筛选测点并依次读取：

```python
if config.mode == AutoReadMode.SINGLE:
    for index, point in enumerate(points, start=1):
        if stop_event.is_set():
            break

        value = await self.point_operator.read_single_point_async(
            point.code,
            slave_id=point.rtu_addr,
        )
        if value is None:
            fail += 1
        else:
            success += 1

        progress(index, total, success, fail)

        if config.request_interval_ms > 0 and index < total:
            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=config.request_interval_ms / 1000.0,
                )
            except TimeoutError:
                pass
```

批量读取继续使用 Modbus 连续地址合并和 IEC 61850 分组批读能力，但 `DataReader` 现在接收 stop event 与进度回调，在每个测点或分组完成后上报累计结果。

### 4.5 实时成功/失败计数

整改后的第一版状态只实时更新 `current/total`，导致手动读取界面在任务运行时持续显示“成功 0、失败 0”，直到整轮结束才写入最终计数。

进度回调已扩展为四个字段：

```python
ProgressCallback = Callable[[int, int, int, int], None]

def _update_progress(
    self,
    task_id: str,
    current: int,
    total: int,
    success: int,
    fail: int,
) -> None:
    if self._status.task_id != task_id:
        return
    self._status.current = current
    self._status.total = total
    self._status.success = success
    self._status.fail = fail
```

现在逐点读取每完成一个测点、批量读取每完成一个分组，状态接口都能返回当前累计成功数和失败数。

### 4.6 设备级读取互斥和生命周期清理

自动读取管理器持有设备级 `read_lock`。自动读取、手动读取、单点读取和 DataSet 读取使用同一把锁，避免同一协议连接上的并发访问。

同时增加以下生命周期约束：

- 自动读取运行时拒绝启动手动读取；
- 手动读取运行时拒绝启动自动读取；
- 设备 `stop()` 先关闭自动读取和手动读取任务，再停止协议处理器；
- 删除、重建、重载和点表导入替换设备前，先停止旧设备任务；
- 重建设备时保存正在运行的自动读取配置，新实例成功启动后显式恢复任务；
- 同配置重复启动自动读取时幂等返回当前状态，不创建重复任务；
- 不同配置冲突时返回 HTTP 409。

### 4.7 DataSet 查询去除协议读取副作用

IEC 61850 DataSet 的真实读取只允许由显式手动读取或后台自动任务触发，结果写入设备级 `DatasetSnapshot`：

```python
@dataclass(slots=True)
class DatasetSnapshot:
    values: dict[str, Any] = field(default_factory=dict)
    updated_at: datetime | None = None
    last_error: str | None = None
```

`iec61850-tree-data` 和 `iec61850-dataset-detail` 改为只读取快照，并返回：

- `last_updated_at`：最近一次成功读取时间；
- `stale`：是否尚未读取或最近一次读取失败；
- `last_error`：最近一次读取错误；
- `values`：最近一次成功值。

查询接口不再调用 `read_dataset_values()`，因此普通表格刷新不会隐式产生 MMS 请求。

## 5. API 变更

### 5.1 自动读取接口

| 接口                                 | 行为                                                   |
| ------------------------------------ | ------------------------------------------------------ |
| `POST /api/devices/start-auto-read`  | 接收完整模式、周期、点间隔和筛选配置；立即返回任务状态 |
| `POST /api/devices/auto-read-status` | 返回结构化状态快照，不触发协议读取                     |
| `POST /api/devices/stop-auto-read`   | 设置 stop event，并返回 `stopping` 或 `idle` 状态      |

启动请求支持：

```python
class AutoReadStartRequest(BaseModel):
    device_name: str
    mode: Literal["batch", "single", "dataset"] = "batch"
    cycle_interval_ms: int = Field(1000, ge=100, le=3_600_000)
    request_interval_ms: int = Field(0, ge=0, le=3_600_000)
    slave_id: int | None = None
    channel_id: int | None = None
    category: str = ""
    item: str = ""
    point_types: list[int] = Field(default_factory=list)
```

### 5.2 手动读取接口

| 接口                                   | 行为                                     |
| -------------------------------------- | ---------------------------------------- |
| `POST /api/devices/manual-read`        | 提交一次后台 `batch/single/dataset` 任务 |
| `POST /api/devices/manual-read-status` | 查询手动任务实时进度、成功数和失败数     |
| `POST /api/devices/stop-manual-read`   | 请求取消当前手动读取任务                 |

逐点手动读取只提交一次 `mode: single`。测点筛选、DL/T 645 地址过滤、点间限速和协议读取全部由后端完成，前端不再为每个测点调用一次 `read-single`。

## 6. 前端整改

### 6.1 自动读取只提交一次任务

自动读取开关打开时仅调用一次 `startAutoRead()`，关闭时调用一次 `stopAutoRead()`。页面保留低频 single-flight 状态查询，用于恢复开关、模式和错误状态；状态查询不会触发协议 IO。

组件失活或卸载时只清理前端状态刷新 timer，不停止后端任务。重新进入页面后通过后端状态恢复当前任务配置。

### 6.2 删除前端真实读取循环

从 `useAutoRead.ts` 删除：

- `singlePointAutoReadTimer`；
- `datasetAutoReadTimer`；
- `doSinglePointReadCycle()`；
- `scheduleDatasetAutoRead()`；
- 逐点读取前拉取最多 10000 个测点的逻辑；
- 循环调用 `readSinglePoint()` 的逻辑；
- 通过 DataSet 表格刷新触发 MMS 读取的逻辑。

保留的轮询仅用于状态和缓存展示，不再承担读取调度。

### 6.3 手动读取统一提交后台任务

手动批量、逐点和 DataSet 读取共用同一个前端控制函数：

```ts
const runBackgroundManualRead = async (config: AutoReadConfig) => {
  let status = await manualRead(routeName.value, config);

  while (status.state === "running" || status.state === "stopping") {
    if (cancelRead.value && status.state === "running") {
      status = await stopManualRead(routeName.value);
    } else {
      await new Promise((resolve) => setTimeout(resolve, 200));
      status = await getManualReadStatus(routeName.value);
    }

    successCount.value = status.success;
    failCount.value = status.fail;
    readProgress.value = status.total
      ? Math.floor((status.current / status.total) * 100)
      : 0;
  }

  return status;
};
```

这里的状态查询仅读取后台任务快照。真实协议读取已经在第一次 `manualRead()` 提交后由后端独立执行。

### 6.4 自动读取不显示进度条

自动读取状态不会写入手动读取的 `readProgress`、`successCount` 和 `failCount`。进度条区域仅由 `isReading` 或手动读取残留进度控制，因此打开自动读取时不再显示进度条。

手动读取仍展示：

- 当前百分比；
- 实时成功数；
- 实时失败数；
- 完成、取消或错误消息。

### 6.5 间隔文案和国际化

补充并修正以下中英文翻译：

- `slave.cycleInterval`：轮询周期 / Cycle Interval；
- `slave.pointInterval`：点间隔 / Point Interval。

DataSet 和批量自动读取展示轮询周期，逐点模式与 DL/T 645 展示点间隔，避免一个“间隔”字段表达不同含义。

## 7. 整改前后行为对比

| 行为               | 整改前                    | 整改后                                |
| ------------------ | ------------------------- | ------------------------------------- |
| 自动读取任务所有者 | 前端 timer 或后端固定线程 | 后端设备级 `asyncio.Task`             |
| 逐点读取 HTTP 数量 | 一个点一次请求            | 一次提交后台任务，状态查询不触发读取  |
| 页面切换           | 可能停止或丢失任务        | 后端任务继续，返回页面恢复状态        |
| 自动读取停止       | 清 timer 或线程 join      | stop event + `stopping/idle` 状态收口 |
| 手动读取取消       | 仅终止前端循环            | 后端停止事件阻止后续点、分组和轮次    |
| DataSet 表格刷新   | 可能触发 MMS 读取         | 只读取快照                            |
| 自动读取进度条     | 前端显示                  | 不显示                                |
| 手动成功/失败计数  | 运行中可能一直为 0/0      | 每个点或分组完成后实时更新            |
| 同设备并发读取     | 缺少统一约束              | 设备级读锁 + 自动/手动任务互斥        |
| 任务错误           | 分散在请求或控制台        | `failed` + `last_error` 状态快照      |

## 8. 主要变更文件

| 文件                                    | 变更摘要                                               |
| --------------------------------------- | ------------------------------------------------------ |
| `src/device/auto_read/models.py`        | 任务模式、配置、状态、轮次结果和 DataSet 快照          |
| `src/device/auto_read/task_manager.py`  | 后台任务生命周期、协作式停止、实时计数和读锁           |
| `src/device/core/device.py`             | 自动/手动任务入口、三种读取 runner、冲突与生命周期清理 |
| `src/device/core/data/data_reader.py`   | stop event、分组取消检查、四字段进度回调               |
| `src/web/api/schemas/device.py`         | 自动读取和手动读取请求模型                             |
| `src/web/api/device/router.py`          | 自动/手动任务启动、状态、停止接口                      |
| `src/web/api/channel/iec61850.py`       | DataSet 显式读取和纯快照查询                           |
| `src/web/api/channel/device_manage.py`  | 设备删除、重启和复制相关生命周期适配                   |
| `src/web/api/channel/helpers.py`        | 设备重建清理及自动读取配置恢复                         |
| `src/web/api/channel/import_points.py`  | 导入替换设备前停止读取任务                             |
| `front/src/api/deviceApi.ts`            | 统一任务类型和 API 调用                                |
| `front/src/constants/api.ts`            | 手动读取状态与停止接口常量                             |
| `front/src/composables/useAutoRead.ts`  | 删除真实读取循环，改为任务提交与状态展示               |
| `front/src/components/device/Slave.vue` | 自动读取隐藏进度条、间隔文案调整                       |
| `front/src/i18n/locales/zh-CN.ts`       | 中文周期和点间隔翻译                                   |
| `front/src/i18n/locales/en-US.ts`       | 英文周期和点间隔翻译                                   |

`src/device/data_update/data_update_thread.py` 仍被设备控制器的数据同步线程使用，但不再承担 `Device` 的自动读取调度。

## 9. 测试与验证

新增和补充的测试覆盖：

- 同配置重复启动幂等，不同配置启动冲突；
- 停止可中断轮次等待；
- 原生不可取消 IO 返回前保持 `stopping`；
- 单轮手动任务只执行一次；
- 后台逐点任务按后端筛选结果依次读取；
- 运行中的任务实时暴露 `current/total/success/fail`；
- 自动和手动读取 API 正确映射配置；
- DataSet 查询不触发 `read_dataset_values()`；
- DataSet 引用的点号和美元符号形式可命中同一快照；
- 设备重建测试适配异步停止语义。

最终验证结果：

| 验证项              | 结果                     |
| ------------------- | ------------------------ |
| 后端完整 Pytest     | `762 passed, 25 skipped` |
| 自动读取定向测试    | `13 passed`              |
| Ruff 全量静态检查   | 通过                     |
| Vue TypeScript 检查 | 通过                     |
| Vite 生产构建       | 通过                     |
| 前端 Prettier 检查  | 通过                     |
| `git diff --check`  | 通过                     |

## 10. 边界与后续建议

1. 状态查询轮询与读取调度是两件事。当前保留的状态轮询只读取内存快照，不会触发协议 IO；如后续需要减少状态请求，可迁移到 SSE 或 WebSocket，但不是本次正确性的前置条件。
2. Python 无法安全强杀已经进入原生库的同步调用。此时任务会保持 `stopping`，直到调用超时返回；不能为了界面立即变为 `idle` 而提前释放设备连接所有权。
3. 自动读取任务只保存在当前后端进程内，不跨应用重启恢复。设备重新连接后需由用户重新启用。
4. DataSet 最近一次成功值会在读取失败时保留，同时通过 `stale` 和 `last_error` 标记其新鲜度，调用方不能把旧快照误认为本轮成功结果。
5. 如未来增加新的协议读取模式，应接入同一任务管理器、设备级读锁和状态模型，不应重新在前端创建真实读取循环。

## 11. 总结

本次整改把读取任务的所有权从页面迁回设备后端：批量、逐点和 DataSet 自动读取统一由后端循环执行；手动读取统一为单轮后台任务；停止、冲突、错误、进度和生命周期均通过结构化状态管理。前端只负责提交配置、请求停止、查询状态和展示缓存，不再通过定时器或逐点 HTTP 调用调度协议读取。

在当前单进程桌面部署和进程内协议连接模型下，`asyncio` 设备级任务管理器比 Celery 更符合资源所有权与取消要求，同时避免引入额外 broker、worker 和跨进程协调成本。
