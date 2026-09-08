# IEC61850 批读回退与索引性能修复

日期：2026-09-09

## 排查证据

现场日志 `log/iec61850.log` 的 2026-09-09 07:10:13 批读记录：

```text
requested=4542, datasets=34, covered=4055, fallback=487,
failed=19, requests=521, elapsed=21251.56ms
```

DataSet 优先读取仍在执行。用当天的 `127.0.0.1:3782` 缓存模型和
`data/device/IEC61850-SVR/KG_BAMS.icd` 启动独立临时端口服务，复现了完全相同的 487 个缺失点：

- 425 个 DataSet 成员报 `projection mismatch: model=1, values=3`。
  在线发现把状态对象的 `q/t` 固定推断为 MX，而主值 `stVal` 属于 ST。
  按 ST 投影时只剩主值，实际响应包含主值、品质和时标三个字段，整个成员被拒绝。
- 62 个系统状态测点未配置在 DataSet 中，例如 LLN0 的 Health/Mod，必须兼容补读。
- 旧目录构建对每个 FCDA 扫描全部模型叶子。本地离线测量构建耗时 9.47 秒，规划另耗时 0.34 秒。
- 隔离服务上，34 个 DataSet 的原生读取及解码合计约 0.43 秒。

进一步核对主值发现：名称目录返回 `q/stVal/t` 字母序，而实际结构返回 `stVal/q/t`。
仅修正 FC 会使主值和品质错位，不能作为完整修复。

## 实现

1. 在线 DA 目录优先使用 `getDataDirectoryFC`，保留设备返回的真实 FC。
2. 按 LN/FC 查询并缓存变量规格，恢复 DA/BDA 原始字段顺序和实际 MMS 类型。
   查询不按测点重复，缓存不持有原生指针；规格使用后统一释放。
3. 规格不可用的在线 DO 标记 `unverifiedFCs` 并持久化，禁止猜测结构成员顺序；
   精确标量成员仍可批读，结构成员保留单点兼容回退。
4. 一次遍历建立叶子与祖先引用索引，成员投影改为查表；规划改用候选覆盖集合求交。
5. 批读日志增加 planning、dataset_read、fallback_read 耗时及 uncovered、covered_but_failed 分类。
   DataSet 成员错误改为 WARNING，默认文件日志可见。

## 验证

同一 ICD 的隔离服务，重新在线发现后读取 4542 个遥测/遥信点：

| 指标 | 首次读取 | 索引缓存命中 |
|---|---:|---:|
| 总耗时 | 471.74 ms | 380.21 ms |
| 规划（含索引） | 96.06 ms | 3.39 ms |
| DataSet 读取 | 367.09 ms | 368.06 ms |
| 补读 | 8.50 ms | 8.67 ms |
| DataSet 数 | 34 | 34 |
| 批读覆盖 | 4480 | 4480 |
| 补读点数 | 62 | 62 |
| 失败点数 | 0 | 0 |
| MMS 读值请求 | 96 | 96 |

425 个异常回退全部消除。11 个代表性告警、整型状态和模拟量主值与单点读取逐一对比通过。
现场原进程的 21.25 秒和隔离服务的测量不是同进程严格 A/B，不能把全部耗时差都归因于单一因素。

回归验证：

```text
python -m pytest tests/protocols/iec61850/datasets tests/protocols/iec61850/model tests/protocols/iec61850/mms/test_read.py -q
161 passed, 25 skipped
ruff check <修改的 Python 文件>
All checks passed
```

## 生效方式

更新后重启后端，并对客户端执行“重新发现”，替换旧缓存的 FC 和字段顺序。
单纯复用旧模型缓存不能修正历史元数据。本次排查没有重启或修改正在使用的服务实例，
实测使用独立临时端口，完成后已销毁临时服务。
