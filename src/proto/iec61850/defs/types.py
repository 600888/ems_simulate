"""IEC 61850 数据模型类型定义

包含所有共享的数据类 (dataclass)，
供 Client/Server/Reports 共用。
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PointRef:
    """测点引用信息"""

    address: str  # 原始地址
    mms_ref: str  # MMS 引用路径
    fc: str  # 功能约束
    iec_type: str  # 数据类型 (兼容旧字符串格式)
    frame_type: int = 0  # 帧类型
    code: str = ""  # 短编码
    name: str = ""  # 测点名称
    mms_type: str = "MMS_UNKNOWN"  # 原生 MMS 类型


@dataclass
class TrgOps:
    """触发选项 (Trigger Options)

    IEC 61850-7-2 定义的报告触发选项:
    - dchg: 数据值变化触发 (data-change)
    - qchg: 品质变化触发 (quality-change)
    - dupd: 数据更新触发 (data-update)
    - period: 周期触发 (integrity period)
    - gi: 通用查询触发 (general interrogation)
    """

    dchg: bool = True
    qchg: bool = False
    dupd: bool = False
    period: bool = False
    gi: bool = True


@dataclass
class OptFields:
    """可选字段 (Optional Fields)

    报告报文中可选包含的字段:
    - seq_num: 序号 (sequence number)
    - time_stamp: 时标 (timestamp)
    - data_set: 数据集引用 (data set reference)
    - reason_code: 变化原因码 (reason code)
    - data_ref: 数据引用 (data reference)
    - entry_id: 入口 ID (entry ID, 仅 BRCB)
    - config_ref: 配置版本引用 (configuration revision)
    - buf_ovfl: 缓冲溢出标志 (buffer overflow, 仅 BRCB)
    """

    seq_num: bool = True
    time_stamp: bool = True
    data_set: bool = True
    reason_code: bool = True
    data_ref: bool = False
    entry_id: bool = True
    config_ref: bool = False
    buf_ovfl: bool = False


@dataclass
class RCBInfo:
    """报告控制块 (RCB) 信息"""

    name: str = ""
    ref: str = ""
    rcb_type: str = ""  # "BRCB" 或 "URCB"
    ld: str = ""
    ln: str = ""
    rpt_id: str = ""
    rpt_ena: bool = False
    data_set_ref: str = ""
    conf_rev: int = 1
    buf_time: int = 0  # 缓冲时间 (ms)
    intg_period: int = 0  # 完整性周期 (ms), 仅 URCB
    purge_buf: bool = False  # 清除缓冲, 仅 BRCB
    entry_id: bytes | None = None  # 入口 ID, 仅 BRCB
    time_of_entry: str = ""  # 入口时间 (格式化字符串), 仅 BRCB
    sq_num: int = 0  # 顺序号 (Sequence Number)
    owner: str = ""  # 当前预留客户端 (Owner)
    resv: bool = False  # 保留状态 (Resv), 仅 URCB
    resv_tms: int = 0  # BRCB 保留时间 (ResvTms)，0 表示未保留
    trg_ops: TrgOps = field(default_factory=TrgOps)
    opt_fields: OptFields = field(default_factory=OptFields)


@dataclass
class ReportDataEntry:
    """单条报告数据条目

    从服务器推送的报告数据解析后的结构化表示。
    """

    seq_num: int = 0
    time_stamp: str = ""
    reason_codes: dict[str, str] = field(default_factory=dict)
    data_values: dict[str, Any] = field(default_factory=dict)
    entry_id: bytes | None = None
    conf_rev: int = 1
    data_set: str = ""
    rpt_id: str = ""
    received_at: str = ""
    uid: int = 0  # 全局唯一递增 ID，用作环状缓冲区稳定标识
