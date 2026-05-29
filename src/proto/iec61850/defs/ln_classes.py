"""IEC 61850 逻辑节点 (LN) 分类表和数据对象 (DO) 名称集合

供 IEC61850Client / IEC61850Server / ModelExporter 共用。
"""

# ========== LN class 分类表 (按 lnClass 名称) ==========

YC_LN_CLASSES = frozenset({
    # 测量类 (Measurement)
    "MMXU", "MMTR", "MSQI", "MSTU", "MVGC",
    "MHAN", "MDIF", "MFLK", "MSEQ", "MFUL",
    "MHAI", "MHAV", "MHI", "MPMG", "MSQ",
    "MSTA", "MENV", "MLLN",
    # 温度/环境/传感器监视类
    "STMP",   # 温度监视 (Temperature supervision)
    "SIMG",   # 绝缘监视 (Insulation supervision)
    "SIML",   # 绝缘水平监视 (Insulation level supervision)
    "SVCB",   # 电容器组监视 (Supervision of capacitor bank)
    "SFCL",   # 滤波器监视 (Supervision of filter)
    "SLTC",   # 有载分接开关监视 (Supervision of load tap changer)
    "SMBP",   # 电机保护监视 (Supervision of motor protection)
    "MMXN",   # 中性点测量 (Measurement for neutral)
})

YX_LN_CLASSES = frozenset({
    # 通用 I/O
    "GGIO",
    # 物理设备 (Physical Device)
    "LPHD",
    # 保护类 (Protection)
    "PTRC", "PSCH", "PTOC", "PDIS", "PTTR", "PTEF",
    "PTUV", "PTOV", "PPRF", "PUPF", "PVOC", "POPF",
    "PTOF", "PHAR", "PDIF", "PDIR", "PDOP", "PPAM",
    "PQUM", "PSDE", "PTUC", "PFRC", "PARC", "PFRQ",
    "PMSS", "PMHI", "PMHO", "PNVI", "PPVE", "PSLF",
    "PSPV", "PTAF", "PUMV", "PZOM", "PAFD",
    # 断路器 / 开关
    "XCBR", "XSWI",
    # 逻辑 / 同期
    "LGOS", "LPOW", "LSYN", "LTMS",
    # 故障录波 / 扰动记录
    "RBRF", "RDRE", "RADF", "RATV",
    "RBDR", "RDIR", "RDST", "RESV", "RFSQ",
    "RINC", "RITR", "RLSB", "RPTR", "RRST",
    "RSRS", "RTRO", "RTRV",
    # 互感器
    "TCTR", "TVTR", "TANG",
    # 告警
    "CALH",
    # 其他
    "SAR",
    # 监视/状态类
    "STUB",   # 管路监视 (Supervision of tubing)
    "YEFN",   # 接地故障 (Earth fault supervision)
    "ZBTC",   # 电池温度 (Battery cell temperature)
    "ZBGL",   # 电池等级 (Battery level)
    "ZBXN",   # 电池中性点 (Battery neutral)
})

YK_LN_CLASSES = frozenset({
    "CSWI", "CILO", "CCGR", "CPOW", "CSLS",
})

YT_LN_CLASSES = frozenset({
    "APC", "DPC", "SPC", "VYY", "ZCEC", "ZCVL",
    "ZGNN", "ZIXL", "ZRCE", "ZRCT", "ZSCD", "ZSEQ",
})

ALL_LN_CLASSES = YC_LN_CLASSES | YX_LN_CLASSES | YK_LN_CLASSES | YT_LN_CLASSES

# ========== DO 名称集合 ==========

# 系统 DO 名称 - 跳过 (IEC 61850 标准中每个 LN 都有的状态/描述信息,
# CDC 类型为 ENC(枚举), stVal 是整型而非布尔, 无法用 readBooleanValue 读取)
SKIP_SYSTEM_DOS = frozenset({
    "Mod",      # 模式 (ENC)
    "Beh",      # 行为 (ENC)
    "Health",   # 健康 (ENC)
    "NamPlt",   # 铭牌 (LPL)
    "PhyHealth",# 物理设备健康 (ENC, 同 Health)
    "Proxy",    # 代理状态 (SPS)
    "PhyNam",   # 物理设备铭牌 (LPL)
})

# 信号 DO 名称 - 可映射为遥信 (CDC 类型为 ACT/SPS, stVal 是布尔值)
SIGNAL_DOS = frozenset({
    "Op",       # 保护动作 (ACT)
    "OpDs",     # 动作方向 (ACD)
    "Str",      # 启动 (ACT)
    "Tr",       # 跳闸 (ACT)
    "TrBlk",    # 闭锁 (SPS)
    "OpCnt",    # 动作计数 (INC)
    "Aut",      # 自动 (SPS)
    "AutRs",    # 自动复位 (SPS)
    "Es",       # 紧急 (SPS)
    "Gn",       # 通用 (SPS)
})
