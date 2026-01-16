from enum import Enum
import struct


class DecodeType(Enum):
    SignedInt = 1
    UnsignedInt = 2
    SignedLong = 3
    UnsignedLong = 4
    Float = 5


class ByteOrder(Enum):
    # 标准字节序
    BigEndFloat = ">f"  # 大端float（高字节在前）
    LittleEndFloat = "<f"  # 小端float（低字节在前）
    WordSwappedFloat = "=f"  # 字内反序float（2字节为单位交换）
    LittleEndWordSwappedFloat = "<f_"  # 小端字内反序float（先小端再2字节交换）

    BigEndSignedInt = ">i"  # 大端int
    LittleEndSignedInt = "<i"  # 小端int
    BigEndUnsignedInt = ">I"  # 大端无符号int
    LittleEndUnsignedInt = "<I"  # 小端无符号int
    BigEndSignedShort = ">h"  # 大端short
    LittleEndSignedShort = "<h"  # 小端short
    BigEndUnsignedShort = ">H"  # 大端无符号short
    LittleEndUnsignedShort = "<H"  # 小端无符号short

    # 大端字内反序版本
    BigEndWordSwappedSignedInt = "=i"  # 字内反序int
    BigEndWordSwappedUnsignedInt = "=I"  # 字内反序无符号int
    BigEndWordSwappedSignedShort = "=h"  # 字内反序short
    BigEndWordSwappedUnsignedShort = "=H"  # 字内反序无符号short

    # 小端字内反序版本
    LittleEndWordSwappedSignedInt = "<i_"
    LittleEndWordSwappedUnsignedInt = "<I_"
    LittleEndWordSwappedSignedShort = "<h_"
    LittleEndWordSwappedUnsignedShort = "<H_"


class Decode:
    decode_register_cnt_map = {
        "0x10": 1,
        "0x20": 1,
        "0x21": 1,
        "0x22": 1,
        "0xB0": 1,
        "0xB1": 1,
        "0x40": 2,
        "0x41": 2,
        "0x42": 2,
        "0x43": 2,
        "0x44": 2,
        "0x45": 2,
        "0xD0": 2,
        "0xD1": 2,
        "0xD2": 2,
        "0xD3": 2,
        "0xD4": 2,
        "0xD5": 2,
    }
    # 定义大端序的解码标识集合
    big_endian_codes = {
        "0x10",
        "0x20",
        "0x21",
        "0xB0",
        "0xB1",
        "0x40",
        "0x41",
        "0x42",
        "0x43",
        "0x44",
        "0x45",
    }
    signed_code_list = ["0x11", "0x21", "0xB1", "0x41", "0x44", "0xD1", "0xD5"]
    unsigned_code_list = ["0x10", "0x20", "0xB0", "0x40", "0x43", "0xD0", "0xD4"]
    float_code_list = ["0x42", "0x45", "0xD2", "0xD3"]

    def __init__(self):
        pass

    @classmethod
    def get_decode_register_cnt(cls, decode: str) -> int:
        return cls.decode_register_cnt_map.get(decode, 1)  # 默认返回1个寄存器

    @classmethod
    def get_endian(cls, decode: str) -> str:
        """根据解码标识返回字节序

        Args:
            decode: 解码标识字符串

        Returns:
            ">" 表示大端序，"<" 表示小端序
        """
        return ">" if decode in cls.big_endian_codes else "<"

    @classmethod
    def is_decode_signed(cls, decode: str) -> bool:
        if decode in cls.signed_code_list:
            return True
        else:
            return False

    @classmethod
    def get_decode_type(cls, decode: str) -> DecodeType:
        if decode == "0x11" or decode == "0x21" or decode == "0xB1":
            return DecodeType.SignedInt
        elif decode == "0x10" or decode == "0x20" or decode == "0xB0":
            return DecodeType.UnsignedInt
        elif decode == "0x40" or decode == "0x43" or decode == "0xD0":
            return DecodeType.UnsignedLong
        elif (
            decode == "0x41" or decode == "0x44" or decode == "0xD1" or decode == "0xD5"
        ):
            return DecodeType.SignedLong
        elif decode in cls.float_code_list:
            return DecodeType.Float
        else:
            return DecodeType.SignedInt  # 默认返回有符号整数

    @classmethod
    def get_byteorder(cls, decode: str) -> str:
        if decode == "0x10" or decode == "0x11":  # char默认当成始为无符号short处理
            return ByteOrder.BigEndUnsignedShort.value
        elif decode == "0x20":
            return ByteOrder.BigEndUnsignedShort.value
        elif decode == "0x21":
            return ByteOrder.BigEndSignedShort.value
        elif decode == "0xB0":
            return ByteOrder.BigEndWordSwappedUnsignedShort.value
        elif decode == "0xB1":
            return ByteOrder.BigEndWordSwappedSignedShort.value
        elif decode == "0x40":
            return ByteOrder.BigEndUnsignedInt.value
        elif decode == "0x41":
            return ByteOrder.BigEndSignedInt.value
        elif decode == "0x42":
            return ByteOrder.BigEndFloat.value
        elif decode == "0x43":
            return ByteOrder.BigEndWordSwappedUnsignedInt.value
        elif decode == "0x44":
            return ByteOrder.BigEndWordSwappedSignedInt.value
        elif decode == "0x45":
            return ByteOrder.WordSwappedFloat.value
        elif decode == "0xD0":
            return ByteOrder.LittleEndUnsignedInt.value
        elif decode == "0xD1":
            return ByteOrder.LittleEndSignedInt.value
        elif decode == "0xD2":
            return ByteOrder.LittleEndFloat.value
        elif decode == "0xD3":
            return ByteOrder.LittleEndWordSwappedFloat.value
        elif decode == "0xD4":
            return ByteOrder.LittleEndWordSwappedUnsignedInt.value
        elif decode == "0xD5":
            return ByteOrder.LittleEndWordSwappedSignedInt.value
        else:  # 默认当大端有符号整数处理
            return ByteOrder.BigEndSignedShort.value

    @staticmethod
    def pack_value(byteorder: str, value) -> bytes:
        """
        支持整数和浮点数字节序打包（含字交换）
        """
        if byteorder.endswith("_"):  # 处理所有字交换情况
            fmt = byteorder[:-1]
            packed = struct.pack(fmt, float(value) if "f" in fmt else int(value))
            # 通用字交换逻辑（2字节为单位）
            if len(packed) >= 4:  # 4字节及以上数据
                return b"".join(
                    packed[i : i + 2][::-1] for i in range(0, len(packed), 2)
                )
            return packed[::-1]  # 小于4字节的数据整体反转
        return struct.pack(byteorder, float(value) if "f" in byteorder else int(value))

    @staticmethod
    def unpack_value(byteorder: str, buffer: bytes):
        """支持整数和浮点数字节序解包（含字交换）"""
        if byteorder.endswith("_"):  # 处理所有字交换情况
            fmt = byteorder[:-1]
            # 反向字交换
            if len(buffer) >= 4:
                swapped = b"".join(
                    buffer[i : i + 2][::-1] for i in range(0, len(buffer), 2)
                )
            else:
                swapped = buffer[::-1]
            return struct.unpack(fmt, swapped)[0]
        return struct.unpack(byteorder, buffer)[0]
