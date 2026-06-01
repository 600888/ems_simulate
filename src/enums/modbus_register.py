"""
Modbus 解析码模块
提供统一的数据类型解析配置
"""

from dataclasses import dataclass
from enum import Enum
import struct


@dataclass(frozen=True)
class DecodeInfo:
    """解析码配置数据类

    定义单个解析码的所有属性，作为单一数据源。

    Attributes:
        code: 解析码字符串，如 "0x41"
        name: 语义化名称，如 "INT32_BE"
        description: 中文描述
        register_cnt: 占用寄存器数量 (1=16位, 2=32位)
        is_signed: 是否有符号
        is_float: 是否浮点数
        is_big_endian: 是否大端字节序
        word_swap: 是否字内反序（ABCD <-> CDAB）
        pack_format: struct 模块打包格式
    """

    code: str
    name: str
    description: str
    register_cnt: int
    is_signed: bool
    is_float: bool
    is_big_endian: bool
    word_swap: bool
    pack_format: str

    @property
    def endian(self) -> str:
        """返回字节序标识符"""
        return ">" if self.is_big_endian else "<"

    @property
    def decode_type(self) -> "DecodeType":
        """返回解码类型枚举"""
        if self.is_float:
            return DecodeType.Float
        if self.register_cnt == 2:
            return DecodeType.SignedLong if self.is_signed else DecodeType.UnsignedLong
        return DecodeType.SignedInt if self.is_signed else DecodeType.UnsignedInt


class DecodeType(Enum):
    """解码数据类型"""

    SignedInt = 1  # 16位有符号整数
    UnsignedInt = 2  # 16位无符号整数
    SignedLong = 3  # 32位有符号整数
    UnsignedLong = 4  # 32位无符号整数
    Float = 5  # 32位浮点数


class DecodeCode(Enum):
    """解析码枚举 - 所有解析码的单一数据源

    命名规则: {类型}_{位数}_{字节序}[_SWAP]
    - 类型: UINT/INT/FLOAT/CHAR
    - 位数: 8/16/32
    - 字节序: BE(大端)/LE(小端)
    - SWAP: 字内反序
    """

    # ===== 8位字符类型 (使用16位寄存器存储) =====
    CHAR_8_BE = DecodeInfo("0x10", "CHAR_8_BE", "8位字符(大端)", 1, False, False, True, False, ">B")
    CHAR_8_BE_SIGNED = DecodeInfo("0x11", "CHAR_8_BE_SIGNED", "8位有符号字符(大端)", 1, True, False, True, False, ">b")

    # ===== 16位整数 - 大端 =====
    UINT16_BE = DecodeInfo("0x20", "UINT16_BE", "16位无符号整数(大端 ABCD)", 1, False, False, True, False, ">H")
    INT16_BE = DecodeInfo("0x21", "INT16_BE", "16位有符号整数(大端 ABCD)", 1, True, False, True, False, ">h")
    UINT16_BE_BYTE_SWAP = DecodeInfo(
        "0x22", "UINT16_BE_BYTE_SWAP", "16位无符号整数(大端字节交换 BADC)", 1, False, False, True, True, ">H"
    )

    # ===== 16位整数 - 大端字内反序 (0xB_) =====
    UINT16_BE_SWAP = DecodeInfo(
        "0xB0", "UINT16_BE_SWAP", "16位无符号整数(大端字交换 BADC)", 1, False, False, True, True, "=H"
    )
    INT16_BE_SWAP = DecodeInfo(
        "0xB1", "INT16_BE_SWAP", "16位有符号整数(大端字交换 BADC)", 1, True, False, True, True, "=h"
    )

    # ===== 32位整数/浮点 - 大端 (0x4_) =====
    UINT32_BE = DecodeInfo("0x40", "UINT32_BE", "32位无符号整数(大端 ABCD)", 2, False, False, True, False, ">I")
    INT32_BE = DecodeInfo("0x41", "INT32_BE", "32位有符号整数(大端 ABCD)", 2, True, False, True, False, ">i")
    FLOAT_BE = DecodeInfo("0x42", "FLOAT_BE", "32位浮点数(大端 ABCD)", 2, False, True, True, False, ">f")

    # ===== 32位整数/浮点 - 大端字内反序 =====
    UINT32_BE_SWAP = DecodeInfo(
        "0x43", "UINT32_BE_SWAP", "32位无符号整数(大端字交换 BADC)", 2, False, False, True, True, "=I"
    )
    INT32_BE_SWAP = DecodeInfo(
        "0x44", "INT32_BE_SWAP", "32位有符号整数(大端字交换 BADC)", 2, True, False, True, True, "=i"
    )
    FLOAT_BE_SWAP = DecodeInfo("0x45", "FLOAT_BE_SWAP", "32位浮点数(大端字交换 BADC)", 2, False, True, True, True, "=f")

    # ===== 16位整数 - 小端 (0xC_) =====
    UINT16_LE = DecodeInfo("0xC0", "UINT16_LE", "16位无符号整数(小端 DCBA)", 1, False, False, False, False, "<H")
    INT16_LE = DecodeInfo("0xC1", "INT16_LE", "16位有符号整数(小端 DCBA)", 1, True, False, False, False, "<h")

    # ===== 32位整数/浮点 - 小端 (0xD_) =====
    UINT32_LE = DecodeInfo("0xD0", "UINT32_LE", "32位无符号整数(小端 DCBA)", 2, False, False, False, False, "<I")
    INT32_LE = DecodeInfo("0xD1", "INT32_LE", "32位有符号整数(小端 DCBA)", 2, True, False, False, False, "<i")
    FLOAT_LE = DecodeInfo("0xD2", "FLOAT_LE", "32位浮点数(小端 DCBA)", 2, False, True, False, False, "<f")

    # ===== 32位整数/浮点 - 小端字内反序 =====
    FLOAT_LE_SWAP = DecodeInfo(
        "0xD3", "FLOAT_LE_SWAP", "32位浮点数(大端字交换 CDAB)", 2, False, True, True, True, ">f_"
    )
    UINT32_LE_SWAP = DecodeInfo(
        "0xD4", "UINT32_LE_SWAP", "32位无符号整数(大端字交换 CDAB)", 2, False, False, True, True, ">I_"
    )
    INT32_LE_SWAP = DecodeInfo(
        "0xD5", "INT32_LE_SWAP", "32位有符号整数(大端字交换 CDAB)", 2, True, False, True, True, ">i_"
    )

    # ===== 64位类型 (4个寄存器) =====
    UINT64_BE = DecodeInfo("0x60", "UINT64_BE", "64位无符号整数(大端)", 4, False, False, True, False, ">Q")
    INT64_BE = DecodeInfo("0x61", "INT64_BE", "64位有符号整数(大端)", 4, True, False, True, False, ">q")
    DOUBLE_BE = DecodeInfo("0x62", "DOUBLE_BE", "64位双精度浮点(大端)", 4, False, True, True, False, ">d")
    UINT64_LE = DecodeInfo("0xE0", "UINT64_LE", "64位无符号整数(小端)", 4, False, False, False, False, "<Q")
    INT64_LE = DecodeInfo("0xE1", "INT64_LE", "64位有符号整数(小端)", 4, True, False, False, False, "<q")
    DOUBLE_LE = DecodeInfo("0xE2", "DOUBLE_LE", "64位双精度浮点(小端)", 4, False, True, False, False, "<d")


class Decode:
    """解析码工具类

    提供向后兼容的静态方法接口，内部代理到 DecodeCode 枚举。
    """

    # 构建解析码映射表（启动时一次性构建）
    _CODE_MAP: dict[str, DecodeInfo] = {item.value.code: item.value for item in DecodeCode}

    # 默认解析码
    DEFAULT = DecodeCode.INT32_BE.value

    @classmethod
    def get_info(cls, decode: str) -> DecodeInfo:
        """获取解析码完整信息

        Args:
            decode: 解析码字符串，如 "0x41"

        Returns:
            DecodeInfo 对象，如未找到返回默认值
        """
        return cls._CODE_MAP.get(decode, cls.DEFAULT)

    @classmethod
    def get_all_codes(cls) -> list:
        """获取所有解析码列表（供前端使用）"""
        return [
            {
                "code": item.value.code,
                "name": item.value.name,
                "description": item.value.description,
                "register_cnt": item.value.register_cnt,
            }
            for item in DecodeCode
        ]

    @classmethod
    def get_decode_register_cnt(cls, decode: str) -> int:
        """获取解析码占用的寄存器数量"""
        return cls.get_info(decode).register_cnt

    @classmethod
    def get_endian(cls, decode: str) -> str:
        """获取字节序标识 ('>' 大端, '<' 小端)"""
        return cls.get_info(decode).endian

    @classmethod
    def is_decode_signed(cls, decode: str) -> bool:
        """判断是否有符号"""
        return cls.get_info(decode).is_signed

    @classmethod
    def get_decode_type(cls, decode: str) -> DecodeType:
        """获取解码数据类型"""
        return cls.get_info(decode).decode_type

    @classmethod
    def get_byteorder(cls, decode: str) -> str:
        """获取 struct 打包格式"""
        return cls.get_info(decode).pack_format

    @classmethod
    def get_limits_by_code(cls, decode: str, mul_coe: float = 1.0, add_coe: float = 0.0) -> tuple[float, float]:
        """根据解析码获取寄存器真实极值 (受乘法系数和加法系数影响)

        Args:
            decode: 解析码字符串
            mul_coe: 乘法系数
            add_coe: 加法系数

        Returns:
            (max_limit, min_limit)
        """
        decode_type = cls.get_decode_type(decode)

        if decode_type == DecodeType.SignedInt:
            raw_min, raw_max = -32768, 32767
        elif decode_type == DecodeType.UnsignedInt:
            raw_min, raw_max = 0, 65535
        elif decode_type == DecodeType.SignedLong:
            raw_min, raw_max = -2147483648, 2147483647
        elif decode_type == DecodeType.UnsignedLong:
            raw_min, raw_max = 0, 4294967295
        elif decode_type == DecodeType.Float:  # Include Float / Double as 32/64
            # 使用一个较大的合理浮点边界，因为完全使用 e38 前端表单可能不便
            raw_min, raw_max = -999999999.0, 999999999.0
        else:
            raw_min, raw_max = -9999999.0, 9999999.0  # fallback

        calc_min = raw_min * mul_coe + add_coe
        calc_max = raw_max * mul_coe + add_coe

        if mul_coe < 0:
            return (
                calc_min,
                calc_max,
            )  # calc_min(由raw_max得出) 是 max_limit, calc_max(由raw_min得出) 是 min_limit，已倒置

        return calc_max, calc_min

    @classmethod
    def pack_value(cls, byteorder: str, value) -> bytes:
        """将值打包为字节（支持字内反序）

        Args:
            byteorder: struct 格式字符串，如 ">f" 或 "<I_"（下划线表示字交换）
            value: 要打包的值

        Returns:
            打包后的字节串
        """
        if byteorder.endswith("_"):  # 处理字交换情况 (CDAB)
            fmt = byteorder[:-1]
            packed = struct.pack(fmt, float(value) if "f" in fmt or "d" in fmt else int(value))
            # 字交换逻辑：交换16位字的位置 (ABCD → CDAB)
            if len(packed) >= 4:
                words = [packed[i : i + 2] for i in range(0, len(packed), 2)]
                # 每4字节(2个word)为一组，交换word位置
                swapped_words = []
                for i in range(0, len(words), 2):
                    if i + 1 < len(words):
                        swapped_words.extend([words[i + 1], words[i]])
                    else:
                        swapped_words.append(words[i])
                return b"".join(swapped_words)
            return packed[::-1]
        return struct.pack(byteorder, float(value) if "f" in byteorder or "d" in byteorder else int(value))

    @classmethod
    def unpack_value(cls, byteorder: str, buffer: bytes):
        """将字节解包为值（支持字内反序）

        Args:
            byteorder: struct 格式字符串
            buffer: 要解包的字节串

        Returns:
            解包后的值
        """
        if byteorder.endswith("_"):  # 处理字交换情况 (CDAB)
            fmt = byteorder[:-1]
            if len(buffer) >= 4:
                words = [buffer[i : i + 2] for i in range(0, len(buffer), 2)]
                # 每4字节(2个word)为一组，交换word位置
                swapped_words = []
                for i in range(0, len(words), 2):
                    if i + 1 < len(words):
                        swapped_words.extend([words[i + 1], words[i]])
                    else:
                        swapped_words.append(words[i])
                swapped = b"".join(swapped_words)
            else:
                swapped = buffer[::-1]
            return struct.unpack(fmt, swapped)[0]
        return struct.unpack(byteorder, buffer)[0]


# ===== 向后兼容：保留 ByteOrder 枚举 =====
class ByteOrder(Enum):
    """字节序枚举（向后兼容，建议使用 DecodeCode）"""

    BigEndFloat = ">f"
    LittleEndFloat = "<f"
    WordSwappedFloat = "=f"
    LittleEndWordSwappedFloat = "<f_"
    BigEndSignedInt = ">i"
    LittleEndSignedInt = "<i"
    BigEndUnsignedInt = ">I"
    LittleEndUnsignedInt = "<I"
    BigEndSignedShort = ">h"
    LittleEndSignedShort = "<h"
    BigEndUnsignedShort = ">H"
    LittleEndUnsignedShort = "<H"
    BigEndWordSwappedSignedInt = "=i"
    BigEndWordSwappedUnsignedInt = "=I"
    BigEndWordSwappedSignedShort = "=h"
    BigEndWordSwappedUnsignedShort = "=H"
    LittleEndWordSwappedSignedInt = "<i_"
    LittleEndWordSwappedUnsignedInt = "<I_"
    LittleEndWordSwappedSignedShort = "<h_"
    LittleEndWordSwappedUnsignedShort = "<H_"
