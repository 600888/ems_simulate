"""IEC 61850 GOOSE Pydantic 数据模型

用于 GOOSE 相关 Web API 的请求/响应数据验证。
采用现代 Pydantic V2 风格设计，JSON 传参。
"""

from typing import Any

from pydantic import BaseModel, Field, field_validator

# ===== GOOSE Publisher 相关 =====


class GooseDataSetEntryCreate(BaseModel):
    """创建数据集条目"""

    name: str = Field(..., description="数据集条目名称", min_length=1, max_length=128)
    value: bool | int | float | str = Field(False, description="初始值")
    iec_type: str = Field("boolean", description="IEC 数据类型: boolean/integer/float/string/bitstring/timestamp")

    @field_validator("iec_type")
    @classmethod
    def validate_iec_type(cls, v: str) -> str:
        allowed = {"boolean", "integer", "float", "string", "bitstring", "timestamp"}
        if v not in allowed:
            raise ValueError(f"iec_type 必须是 {allowed} 之一, 收到: {v}")
        return v


class GooseDataSetEntryUpdate(BaseModel):
    """更新数据集条目值"""

    value: bool | int | float | str = Field(..., description="新值")


class GoosePublisherCreate(BaseModel):
    """创建 GOOSE Publisher"""

    interface: str = Field("eth0", description="网络接口名称", min_length=1)
    go_cb_ref: str = Field(..., description="GOOSE 控制块引用 (MMS格式, 如 LD0/LLN0$GO$gcb1)", min_length=1)
    go_id: str = Field("", description="GOOSE 标识符")
    data_set_ref: str = Field("", description="数据集引用 (如 LD0/LLN0$dsGOOSE1)")
    app_id: int = Field(0x0001, description="APPID", ge=0, le=0xFFFF)
    conf_rev: int = Field(1, description="配置修订号", ge=1)
    time_allowed_to_live: int = Field(1000, description="报文存活时间(ms)", ge=100, le=60000)
    dst_mac: list[int] | None = Field(None, description="目标MAC地址 (6字节)", max_length=6)
    vlan_id: int = Field(0, description="VLAN ID", ge=0, le=4095)
    vlan_prio: int = Field(4, description="VLAN 优先级", ge=0, le=7)
    simulation: bool = Field(True, description="是否为仿真模式")
    entries: list[GooseDataSetEntryCreate] = Field(default_factory=list, description="数据集条目列表")
    channel_id: int | None = Field(None, description="关联的通道ID (提供后持久化到数据库)", ge=1)

    @field_validator("dst_mac")
    @classmethod
    def validate_dst_mac(cls, v: list[int] | None) -> list[int] | None:
        if v is not None:
            if len(v) != 6:
                raise ValueError("dst_mac 必须包含 6 个字节")
            for b in v:
                if not 0 <= b <= 255:
                    raise ValueError(f"MAC 地址字节必须在 0-255 之间, 收到: {b}")
        return v


class GoosePublisherIdRequest(BaseModel):
    """GOOSE Publisher ID 请求"""

    publisher_id: str = Field(..., description="Publisher 标识 (go_cb_ref)")
    channel_id: int | None = Field(None, ge=1)


class GooseChannelRequest(BaseModel):
    """GOOSE 通道查询请求 (用于按通道获取发现的远端控制块)"""

    channel_id: int = Field(..., description="关联的通道ID", ge=1)


class GooseImportDiscoveredRequest(BaseModel):
    """将发现的远端 GOOSE 控制块导入为订阅"""

    channel_id: int = Field(..., description="关联的通道ID", ge=1)
    interface: str = Field("eth0", description="GOOSE 接收使用的网络接口", min_length=1)
    go_cb_refs: list[str] = Field(default_factory=list, description="要添加的控制块引用；为空时兼容导入全部")


class GoosePublisherUpdate(BaseModel):
    """更新 GOOSE Publisher 配置"""

    publisher_id: str = Field(..., description="Publisher 标识 (go_cb_ref)")
    channel_id: int | None = Field(None, ge=1)
    interface: str | None = Field(None, min_length=1)
    go_cb_ref: str | None = Field(None, min_length=1)
    go_id: str | None = Field(None, description="GOOSE 标识符")
    data_set_ref: str | None = None
    app_id: int | None = Field(None, ge=0, le=0xFFFF)
    conf_rev: int | None = Field(None, description="配置修订号", ge=1)
    time_allowed_to_live: int | None = Field(None, description="报文存活时间(ms)", ge=100, le=60000)
    simulation: bool | None = Field(None, description="是否为仿真模式")
    dst_mac: list[int] | None = Field(None, min_length=6, max_length=6)
    vlan_id: int | None = Field(None, ge=0, le=4095)
    vlan_prio: int | None = Field(None, ge=0, le=7)


class GoosePublisherEntryAdd(BaseModel):
    """向 Publisher 添加数据集条目"""

    publisher_id: str = Field(..., description="Publisher 标识 (go_cb_ref)")
    entry: GooseDataSetEntryCreate = Field(..., description="数据集条目")


class GoosePublisherEntryUpdate(BaseModel):
    """更新 Publisher 数据集条目"""

    publisher_id: str = Field(..., description="Publisher 标识 (go_cb_ref)")
    index: int = Field(..., description="条目索引", ge=0)
    value: bool | int | float | str = Field(..., description="新值")


class GoosePublisherEntryRemove(BaseModel):
    """移除 Publisher 数据集条目"""

    publisher_id: str = Field(..., description="Publisher 标识 (go_cb_ref)")
    index: int = Field(..., description="条目索引", ge=0)


class GoosePublisherEntriesReplace(BaseModel):
    publisher_id: str
    channel_id: int = Field(..., ge=1)
    entries: list[GooseDataSetEntryCreate] = Field(default_factory=list)


# ===== GOOSE Subscriber 相关 =====


class GooseSubscriptionCreate(BaseModel):
    """创建 GOOSE 订阅"""

    receiver_id: str = Field("", description="Receiver 标识（新建时可选）")
    go_cb_ref: str = Field(..., description="GOOSE 控制块引用 (MMS格式)", min_length=1)
    app_id: int | None = Field(None, description="APPID 过滤", ge=0, le=0xFFFF)
    dst_mac: list[int] | None = Field(None, description="目标MAC地址过滤 (6字节)", max_length=6)
    description: str = Field("", description="描述")
    data_set_ref: str = ""
    conf_rev: int = Field(0, ge=0)
    enabled: bool = False
    ied_name: str = Field("", max_length=128)
    ld_inst: str = Field("", max_length=128)
    ln_name: str = Field("LLN0", max_length=128)
    dataset_entries: list[dict[str, Any]] = Field(default_factory=list)
    go_id: str = Field("", description="GOOSE 标识符")

    @field_validator("dst_mac")
    @classmethod
    def validate_dst_mac(cls, v: list[int] | None) -> list[int] | None:
        if v is not None:
            if len(v) != 6:
                raise ValueError("dst_mac 必须包含 6 个字节")
            for b in v:
                if not 0 <= b <= 255:
                    raise ValueError(f"MAC 地址字节必须在 0-255 之间, 收到: {b}")
        return v


class GooseSubscriptionRemove(BaseModel):
    """移除 GOOSE 订阅"""

    receiver_id: str = Field(..., description="Receiver 标识")
    go_cb_ref: str = Field(..., description="GOOSE 控制块引用", min_length=1)


class GooseSubscriptionUpdate(BaseModel):
    channel_id: int = Field(..., ge=1)
    receiver_id: str = Field(..., min_length=1)
    go_cb_ref: str = Field(..., min_length=1)
    new_go_cb_ref: str | None = Field(None, min_length=1)
    app_id: int | None = Field(None, ge=0, le=0xFFFF)
    dst_mac: list[int] | None = Field(None, max_length=6)
    description: str = Field("", max_length=512)
    data_set_ref: str = ""
    conf_rev: int = Field(0, ge=0)
    enabled: bool = False
    ied_name: str = Field("", max_length=128)
    ld_inst: str = Field("", max_length=128)
    ln_name: str = Field("LLN0", max_length=128)
    dataset_entries: list[dict[str, Any]] = Field(default_factory=list)
    go_id: str = Field("", description="GOOSE 标识符")


class GooseSubscriptionHistoryRequest(BaseModel):
    channel_id: int = Field(..., ge=1)
    receiver_id: str = Field(..., min_length=1)
    go_cb_ref: str = Field(..., min_length=1)
    limit: int = Field(100, ge=1, le=200)


class GooseReceiverCreate(BaseModel):
    """创建 GOOSE Receiver"""

    interface: str = Field("eth0", description="网络接口名称", min_length=1)
    channel_id: int = Field(..., ge=1)
    name: str = Field("default", min_length=1, max_length=128)
    description: str = Field("", max_length=512)
    auto_start: bool = False
    subscriptions: list[GooseSubscriptionCreate] = Field(default_factory=list, description="初始订阅列表")


class GooseReceiverIdRequest(BaseModel):
    """GOOSE Receiver ID 请求"""

    receiver_id: str = Field(..., description="Receiver 标识")
    channel_id: int | None = Field(None, ge=1)


class GooseReceiverUpdate(BaseModel):
    receiver_id: str
    channel_id: int = Field(..., ge=1)
    interface: str = Field(..., min_length=1)
    name: str = Field("default", min_length=1, max_length=128)
    description: str = Field("", max_length=512)
    auto_start: bool = False


class GooseReceiverSubscriptionsReplace(BaseModel):
    receiver_id: str
    channel_id: int = Field(..., ge=1)
    subscriptions: list[GooseSubscriptionCreate] = Field(default_factory=list)


# ===== 通用查询 =====


class GooseChannelQuery(BaseModel):
    """按通道查询 GOOSE 配置"""

    channel_id: int = Field(..., description="通道ID", ge=1)


class GoosePublishNow(BaseModel):
    """立即发布 GOOSE 报文"""

    channel_id: int = Field(..., description="通道ID", ge=1)
    publisher_id: str = Field(..., description="Publisher 标识 (go_cb_ref)")


# ===== 响应模型 =====


class GoosePublisherStatus(BaseModel):
    """GOOSE Publisher 状态"""

    go_cb_ref: str
    go_id: str = ""
    data_set_ref: str = ""
    app_id: int = 0
    conf_rev: int = 1
    st_num: int = 1
    sq_num: int = 0
    time_allowed_to_live: int = 1000
    interface: str = ""
    simulation: bool = True
    is_running: bool = False
    dst_mac: str = ""
    vlan_id: int = 0
    vlan_prio: int = 4
    entry_count: int = 0
    entries: list[dict[str, Any]] = Field(default_factory=list)


class GooseSubscriptionStatus(BaseModel):
    """GOOSE 订阅状态"""

    go_cb_ref: str
    app_id: int | None = None
    go_id: str = ""
    data_set_ref: str = ""
    conf_rev: int = 0
    st_num: int = 0
    sq_num: int = 0
    time_allowed_to_live: int = 0
    timestamp: int = 0
    state: str = "init"
    last_update: float = 0.0
    description: str = ""
    dst_mac: str = ""
    data_values: list[dict[str, Any]] = Field(default_factory=list)


class GooseReceiverStatus(BaseModel):
    """GOOSE Receiver 状态"""

    interface: str = ""
    is_running: bool = False
    subscription_count: int = 0
    subscriptions: list[GooseSubscriptionStatus] = Field(default_factory=list)


# ===== GOOSE 报文抓包相关 =====


class GooseCaptureStartRequest(BaseModel):
    """启动 GOOSE 报文抓包"""

    interface: str = Field("", description="网络接口名称 (为空则自动选择)")
    channel_id: int = Field(..., ge=1)
    max_packets: int = Field(500, description="最大缓存报文数", ge=50, le=10000)
    filter_app_id: int | None = Field(None, description="APPID 过滤", ge=0, le=0xFFFF)


class GooseCaptureStopRequest(BaseModel):
    """停止 GOOSE 报文抓包"""

    channel_id: int = Field(..., ge=1)
    interface: str = ""


class GooseCaptureListRequest(BaseModel):
    """获取捕获的 GOOSE 报文"""

    count: int = Field(0, description="获取最近 N 条 (0=全部)", ge=0)
    channel_id: int = Field(..., ge=1)
    interface: str = ""
    filter_app_id: int | None = Field(None, description="APPID 过滤", ge=0, le=0xFFFF)


class GooseCaptureStatusResponse(BaseModel):
    """GOOSE 报文抓包状态"""

    is_running: bool = False
    interface: str = ""
    total_captured: int = 0
    buffer_size: int = 0
    max_buffer_size: int = 500
    filter_app_id: int | None = None
    filter_go_cb_ref: str = ""


# ===== GOOSE ICD 导入相关 =====


class GooseIcdImportResult(BaseModel):
    """ICD 文件 GOOSE 导入结果"""

    publishers: list[dict[str, Any]] = Field(default_factory=list, description="可创建的 Publisher 配置列表")
    subscriptions: list[dict[str, Any]] = Field(default_factory=list, description="可创建的 Subscription 配置列表")
    summary: dict[str, Any] = Field(default_factory=dict, description="解析摘要")
