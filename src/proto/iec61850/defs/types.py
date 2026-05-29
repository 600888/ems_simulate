"""IEC 61850 数据模型类型定义

包含所有共享的数据类 (dataclass)，
供 Client/Server/ModelExporter 共用。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .constants import IecType, FrameType


@dataclass
class PointRef:
    """测点引用信息"""
    address: str           # 原始地址
    mms_ref: str           # MMS 引用路径
    fc: str                # 功能约束
    iec_type: str          # 数据类型 (兼容旧字符串格式)
    frame_type: int = 0    # 帧类型
    code: str = ""         # 短编码
    name: str = ""         # 测点名称


@dataclass
class DAInfo:
    """数据属性 (DA) 信息"""
    name: str = ""
    path: str = ""
    fc: str = ""
    iec_type: str = ""
    sub_das: List['DAInfo'] = field(default_factory=list)


@dataclass
class DOInfo:
    """数据对象 (DO) 信息"""
    name: str = ""
    ref: str = ""
    frame_type: int = -1
    das: List[DAInfo] = field(default_factory=list)


@dataclass
class DataSetInfo:
    """数据集 (DataSet) 信息"""
    name: str = ""
    ref: str = ""
    is_deletable: bool = False
    members: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class RCBInfo:
    """报告控制块 (RCB) 信息"""
    name: str = ""
    ref: str = ""
    rcb_type: str = ""


@dataclass
class GoCBInfo:
    """GOOSE 控制块信息"""
    name: str = ""
    ref: str = ""
    go_cb_ref: str = ""
    go_id: str = ""
    app_id: Optional[int] = None
    data_set_ref: str = ""
    conf_rev: int = 0


@dataclass
class LNInfo:
    """逻辑节点 (LN) 信息"""
    name: str = ""
    ln_class: str = ""
    ref: str = ""
    dos: List[DOInfo] = field(default_factory=list)
    datasets: List[DataSetInfo] = field(default_factory=list)
    rcb_list: List[RCBInfo] = field(default_factory=list)
    gocb_list: List[GoCBInfo] = field(default_factory=list)


@dataclass
class LDInfo:
    """逻辑设备 (LD) 信息"""
    name: str = ""
    inst: str = ""
    lns: List[LNInfo] = field(default_factory=list)


@dataclass
class ServerModel:
    """服务端完整模型"""
    host: str = ""
    port: int = 102
    discover_time: str = ""
    lds: List[LDInfo] = field(default_factory=list)
