"""IEC 61850 DA 路径映射和模式定义

包含 DA 路径到帧类型/iec_type 的映射、
附加 DA 信息、ENC 类型覆盖、BDA 类型映射等。

从 iec61850_client.py 提取，供 Client/Server/ModelExporter 共用。
"""

from .constants import (
    IEC_TYPE_BOOLEAN,
    IEC_TYPE_FLOAT,
    IEC_TYPE_INTEGER,
    IEC_TYPE_STRING,
    IEC_TYPE_TIMESTAMP,
    IEC_TYPE_UNKNOWN,
)

# DA 路径 -> (frame_type, iec_type) 映射 (用于模型发现时推断测点类型)
# frame_type 仍保留用于数据库分类（遥测/遥信/遥控/遥调），但读写不再依赖它
DA_PATH_TO_FRAME_TYPE = {
    "mag.f": (0, IEC_TYPE_FLOAT),  # 遥测
    "cVal.mag.f": (0, IEC_TYPE_FLOAT),  # 遥测 (CMV)
    "instMag.f": (0, IEC_TYPE_FLOAT),  # 遥测 (SAV)
    "stVal": (1, IEC_TYPE_BOOLEAN),  # 遥信
    "ctlVal": (2, IEC_TYPE_BOOLEAN),  # 遥控 (布尔型)
    "Oper.ctlVal": (2, IEC_TYPE_BOOLEAN),  # 遥控
    "setVal": (3, IEC_TYPE_FLOAT),  # 遥调
}

# DA 第一层名称 -> (完整 DA 路径, frame_type, iec_type) 映射
# 用于从服务器模型发现 DA 结构时，根据 getDataDirectory 返回的 DA 名称
# 推断测点类型和完整 DA 路径，避免猜测导致的测点遗漏
DA_PATTERNS = {
    # 遥测 (YC) - 测量值类 DA
    "mag": ("mag.f", 0, IEC_TYPE_FLOAT),  # MV/SAV CDC: 浮点测量值
    "cVal": ("cVal.mag.f", 0, IEC_TYPE_FLOAT),  # CMV CDC: 复数测量值
    "instMag": ("instMag.f", 0, IEC_TYPE_FLOAT),  # SAV CDC: 瞬时测量值
    "mxVal": ("mxVal.f", 0, IEC_TYPE_FLOAT),  # 某些实现的测量值
    "fCVal": ("fCVal.mag.f", 0, IEC_TYPE_FLOAT),  # 复数浮点测量值
    # 遥信 (YX) - 状态值类 DA
    "stVal": ("stVal", 1, IEC_TYPE_BOOLEAN),  # SPS/ACT/ACD/SEC CDC: 状态值
    # 遥控 (YK) - 控制值类 DA
    "ctlVal": ("ctlVal", 2, IEC_TYPE_BOOLEAN),  # SPC/DPC CDC: 控制值
    "Oper": ("Oper.ctlVal", 2, IEC_TYPE_BOOLEAN),  # SPC/DPC CDC: 安全操作控制
    # 遥调 (YT) - 设定值类 DA
    "setVal": ("setVal", 3, IEC_TYPE_FLOAT),  # APC/BSC/ISC CDC: 设定值
    "wVal": ("wVal.f", 3, IEC_TYPE_FLOAT),  # 某些实现的设定值
}

# ENC/DPC 类型 DO 的 stVal 类型覆盖
# Mod/Beh/Health/PhyHealth 的 stVal 是枚举整型; Pos(DPC) 的 stVal 是 DbPos 整型
# 格式: DO名 -> {DA名: iec_type}
ENC_DO_DA_TYPE_OVERRIDE = {
    "Mod": {"stVal": IEC_TYPE_INTEGER, "ctlVal": IEC_TYPE_INTEGER},
    "Beh": {"stVal": IEC_TYPE_INTEGER},
    "Health": {"stVal": IEC_TYPE_INTEGER},
    "PhyHealth": {"stVal": IEC_TYPE_INTEGER},
    "Pos": {"stVal": IEC_TYPE_INTEGER},
}

# 附加 DA (元数据类) - 这些不是主值, 但需要在树形表格中显示
# 映射格式: DA名 -> (完整DA路径, FC, iec_type)
EXTRA_DA_INFO = {
    "q": ("q", "MX", IEC_TYPE_INTEGER),  # 品质 (Quality struct - Pack32 / BitString)
    "t": ("t", "MX", IEC_TYPE_TIMESTAMP),  # 时标 (Timestamp struct)
    "du": ("du", "DC", IEC_TYPE_STRING),  # 描述 (Description string) - 小写兼容
    "dU": ("dU", "DC", IEC_TYPE_STRING),  # 描述 (Description string) - IEC 61850 标准名
    "subVal": ("subVal", "SV", IEC_TYPE_UNKNOWN),  # 替代值
    "subEna": ("subEna", "SV", IEC_TYPE_BOOLEAN),  # 替代使能
    "blkEna": ("blkEna", "BL", IEC_TYPE_BOOLEAN),  # 闭锁使能
    "origin": ("origin", "OR", IEC_TYPE_INTEGER),  # 来源 (Origin struct - orCat=INT, orIdent=Octet)
    "ctlNum": ("ctlNum", "CO", IEC_TYPE_INTEGER),  # 控制序号
    "SBO": ("SBO", "CO", IEC_TYPE_UNKNOWN),  # SBO 参考
    "SBOw": ("SBOw.ctlVal", "CO", IEC_TYPE_BOOLEAN),  # SBO 写入
    "Cancel": ("Cancel.ctlVal", "CO", IEC_TYPE_BOOLEAN),  # 取消
    "Oper": ("Oper.ctlVal", "CO", IEC_TYPE_BOOLEAN),  # 操作 (已在 DA_PATTERNS 中, 但这里补充 FC)
    "frVal": ("frVal", "ST", IEC_TYPE_INTEGER),  # 冻结值
    "frTm": ("frTm", "ST", IEC_TYPE_TIMESTAMP),  # 冻结时间
    "actVal": ("actVal", "ST", IEC_TYPE_INTEGER),  # BCR 实际值
    "frValSec": ("frValSec", "ST", IEC_TYPE_INTEGER),  # BCR 冻结秒值
    "valWTr": ("valWTr", "CO", IEC_TYPE_BOOLEAN),  # 值带瞬变
    # NamPlt (铭牌) 相关 DA - LPL CDC, FC=DC
    "vendor": ("vendor", "DC", IEC_TYPE_STRING),  # 厂商
    "swRev": ("swRev", "DC", IEC_TYPE_STRING),  # 软件版本
    "configRev": ("configRev", "DC", IEC_TYPE_STRING),  # 配置版本
    "d": ("d", "DC", IEC_TYPE_STRING),  # 描述 (短名称, 某些 NamPlt 实现)
    "lnNs": ("lnNs", "DC", IEC_TYPE_STRING),  # LN 命名空间
    "AddCause": ("AddCause", "CO", IEC_TYPE_INTEGER),  # 附加原因
    # 替代/结构元数据 (不作为测点)
    "subQ": ("subQ", "SV", IEC_TYPE_INTEGER),  # 替代品质 (Quality struct)
    "subID": ("subID", "SV", IEC_TYPE_STRING),  # 替代标识 (Octet string)
    "dataNs": ("dataNs", "DC", IEC_TYPE_STRING),  # 数据命名空间
}

# 不作为测点创建的元数据 DA (在 EXTRA_DA_INFO 中定义但不生成测点)
SKIP_DA_NAMES = frozenset(
    {
        "q",
        "t",  # 品质/时标, IEC61850 固有属性
        "subQ",
        "subID",  # 替代品质/标识
        "subVal",
        "subEna",  # 替代值/使能, 结构元数据
        "setMag",  # 设定值幅值, 结构体 DA 服务端不支持直接读取
        "dataNs",  # 数据命名空间
        "ctlModel",  # 控制模型配置
        "sboTimeout",  # SBO 超时配置
        "sboClass",  # SBO 类别配置
        # NamPlt/PhyNam 铭牌字符串 DA, 大部分服务器不支持 MMS 读取
        "vendor",
        "swRev",
        "configRev",
        "d",
        "dU",
        "lnNs",
    }
)

# BDA 子节点 -> iec_type 映射（用于推断 struct 内部 BDA 的数据类型）
BDA_TYPE_MAP = {
    # Quality (q) 的 BDA
    "validity": IEC_TYPE_INTEGER,
    "detailQuality": IEC_TYPE_INTEGER,
    "source": IEC_TYPE_INTEGER,
    "operatorBlocked": IEC_TYPE_BOOLEAN,
    "test": IEC_TYPE_BOOLEAN,
    # Timestamp (t) 的 BDA
    "seconds": IEC_TYPE_INTEGER,
    "fraction": IEC_TYPE_INTEGER,
    "LeapSecondsKnown": IEC_TYPE_BOOLEAN,
    "ClockedFailure": IEC_TYPE_BOOLEAN,
    "ClockNotSynchronized": IEC_TYPE_BOOLEAN,
    "TimeAccuracy": IEC_TYPE_INTEGER,
    # Origin 的 BDA
    "orCat": IEC_TYPE_INTEGER,
    "orIdent": IEC_TYPE_UNKNOWN,  # Octet string
}

# 需要递归展开子 BDA 的 struct DA 名称
# q 和 t 展开为子测点 (如 q.validity, t.seconds 等), origin 展开为测点
STRUCT_DA_EXPAND_ONLINE = {"origin", "q", "t"}

# 已知 struct DA 的硬编码 BDA 子节点 (当在线发现子 DA 失败时使用)
KNOWN_BDA_FALLBACK_ONLINE = {
    "origin": ["orCat", "orIdent"],
    # Quality (q) 的 BDA 子节点
    "q": ["validity", "detailQuality", "source", "operatorBlocked", "test"],
    # Timestamp (t) 的 BDA 子节点
    "t": ["seconds", "fraction", "TimeAccuracy"],
}
