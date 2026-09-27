# 解析码系统

解析码格式为 `类型位数_字节顺序`。字母表示数值按大端表示时的字节；后缀表示这些字节在 Modbus 寄存器中的实际顺序。例如 `INT32_CDAB` 把数值的 `AB CD` 两个寄存器按 `CD AB` 存储。8 位值存放在一个 16 位寄存器中，`AB` 取低字节，`BA` 取高字节。

## 可用类型

| 类型 | 字节顺序 | 寄存器数 |
|---|---|---:|
| `UINT8`、`INT8` | `AB`、`BA` | 1 |
| `UINT16`、`INT16` | `AB`、`BA` | 1 |
| `UINT32`、`INT32`、`FLOAT32` | `ABCD`、`BADC`、`CDAB`、`DCBA` | 2 |
| `UINT64`、`INT64` | `ABCDEFGH`、`GHEFCDAB` | 4 |
| `DOUBLE` | `ABCDEFGH`、`BADCFEHG`、`GHEFCDAB`、`HGFEDCBA` | 4 |

`DOUBLE` 是 IEEE 754 64 位双精度浮点数。所有新配置均保存语义化解析码；读取旧配置或导入旧点表时仍接受下面的十六进制码。升级数据库时旧码按此表迁移。同义旧码会归并。

## 旧码迁移表

| 旧码 | 新解析码 |
|---|---|
| `0x10` | `UINT8_AB` |
| `0x11` | `INT8_AB` |
| `0x20` | `UINT16_AB` |
| `0x21` | `INT16_AB` |
| `0x22` | `UINT16_AB` |
| `0xB0` | `UINT16_AB` |
| `0xB1` | `INT16_AB` |
| `0xC0` | `UINT16_BA` |
| `0xC1` | `INT16_BA` |
| `0x40` | `UINT32_ABCD` |
| `0x41` | `INT32_ABCD` |
| `0x42` | `FLOAT32_ABCD` |
| `0x43` | `UINT32_DCBA` |
| `0x44` | `INT32_DCBA` |
| `0x45` | `FLOAT32_DCBA` |
| `0xD0` | `UINT32_CDAB` |
| `0xD1` | `INT32_CDAB` |
| `0xD2` | `FLOAT32_CDAB` |
| `0xD3` | `FLOAT32_CDAB` |
| `0xD4` | `UINT32_CDAB` |
| `0xD5` | `INT32_CDAB` |
| `0x60` | `UINT64_ABCDEFGH` |
| `0x61` | `INT64_ABCDEFGH` |
| `0x62` | `DOUBLE_ABCDEFGH` |
| `0xE0` | `UINT64_GHEFCDAB` |
| `0xE1` | `INT64_GHEFCDAB` |
| `0xE2` | `DOUBLE_GHEFCDAB` |

这张表依据旧版 Modbus 客户端和服务端的实际寄存器读写顺序。部分旧版界面文字与实际行为不符，尤其是 `0x22`、`0x43`、`0xD0` 和 `0xE2`。`0x10`、`0x11` 的旧版 8 位范围处理不一致，升级后按真实 8 位数值处理。

## 代码示例

```python
from src.enums.modbus_register import Decode

registers = Decode.encode_registers("DOUBLE_HGFEDCBA", 1234.5)
value = Decode.decode_registers("DOUBLE_HGFEDCBA", registers)
assert value == 1234.5

# 旧码仍可作为输入，但 normalize 返回应保存的新名称。
assert Decode.normalize("0xE2") == "DOUBLE_GHEFCDAB"
```

遥测和遥调的工程值仍按 `工程值 = 寄存器值 × 乘法系数 + 加法系数` 计算。
