"""Bounded, typed feature requests with no SDK dependencies."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    node_id: str = Field(min_length=1, max_length=512)
    kind: Literal["fixed", "random", "sine", "step"] = "sine"
    minimum: float = 0
    maximum: float = 100
    period_s: float = Field(default=10, gt=0, le=86400)
    offset_s: float = Field(default=0, ge=-86400, le=86400)
    interval_ms: int = Field(default=500, ge=50, le=3600000)
    value: Any = 0
    step: float = 1
    write_policy: Literal["pause", "overwrite", "reject"] = "pause"
    enabled: bool = True

    @model_validator(mode="after")
    def bounds(self):
        if self.minimum > self.maximum:
            raise ValueError("模拟下限不能大于上限")
        return self


class SimulationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rules: list[Rule] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="after")
    def unique(self):
        if len({item.node_id for item in self.rules}) != len(self.rules):
            raise ValueError("每个节点只能绑定一条模拟规则")
        return self


class MonitoredItem(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    node_id: str = Field(min_length=1, max_length=512)
    namespace_uri: str | None = Field(default=None, max_length=255)
    sampling_interval_ms: float = Field(default=500, ge=0, le=3600000)
    queue_size: int = Field(default=10, ge=1, le=10000)
    deadband: float = Field(default=0, ge=0)
    mode: Literal["Disabled", "Sampling", "Reporting"] = "Reporting"


class SubscriptionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=64)
    publishing_interval_ms: float = Field(default=500, ge=50, le=3600000)
    lifetime_count: int = Field(default=10000, ge=3, le=100000)
    keepalive_count: int = Field(default=10, ge=1, le=10000)
    enabled: bool = True
    items: list[MonitoredItem] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="after")
    def bounds(self):
        if self.lifetime_count < self.keepalive_count * 3:
            raise ValueError("生命周期计数须至少为保活计数的三倍")
        keys = {(item.namespace_uri, item.node_id) for item in self.items}
        if len(keys) != len(self.items):
            raise ValueError("同一订阅中监控项不能重复")
        return self


class SubscriptionsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subscriptions: list[SubscriptionConfig] = Field(default_factory=list, max_length=100)
    reconnect: bool = True
    retry_min_s: float = Field(default=1, ge=0.1, le=60)
    retry_max_s: float = Field(default=30, ge=1, le=300)

    @model_validator(mode="after")
    def unique(self):
        if len({item.id for item in self.subscriptions}) != len(self.subscriptions):
            raise ValueError("订阅名称不能重复")
        if self.retry_min_s > self.retry_max_s:
            raise ValueError("最小重连间隔不能大于最大间隔")
        return self


class SecurityConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["None", "Sign", "SignAndEncrypt"] = "None"
    application_uri: str = Field(default="urn:ems-simulate:application", min_length=1, max_length=255)
    advertised_host: str | None = Field(default=None, max_length=255)
    identity: Literal["anonymous", "username"] = "anonymous"
    username: str = Field(default="", max_length=128)
    allow_anonymous: bool = False
    certificate: str | None = Field(default=None, max_length=32768)
    trusted: list[str] = Field(default_factory=list, max_length=100)
    users: list[dict[str, str]] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_identity(self):
        if self.identity == "username" and (not self.username or self.mode != "SignAndEncrypt"):
            raise ValueError("用户名身份需要用户名和 SignAndEncrypt")
        if any(
            set(user) != {"username", "role"}
            or user["role"] not in {"viewer", "operator"}
            or not 1 <= len(user["username"]) <= 64
            for user in self.users
        ):
            raise ValueError("用户角色只能为 viewer 或 operator")
        if len({user["username"] for user in self.users}) != len(self.users):
            raise ValueError("用户名重复")
        if self.mode != "None" and not self.certificate:
            raise ValueError("请先生成应用证书")
        return self


class HistoryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    nodes: list[str] = Field(default_factory=list, max_length=1000)
    retention_days: int = Field(default=7, ge=1, le=3650)
    max_values: int = Field(default=100000, ge=1, le=10000000)

    @model_validator(mode="after")
    def unique_nodes(self):
        if len(set(self.nodes)) != len(self.nodes):
            raise ValueError("历史节点不能重复")
        return self


class EventsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    source_node: str = Field(default="i=2253", min_length=1, max_length=512)
    event_type: str = Field(default="i=2041", min_length=1, max_length=512)
    minimum_severity: int = Field(default=0, ge=0, le=1000)
    source_nodes: list[str] = Field(default_factory=list, max_length=100)
    message_filter: str = Field(default="", max_length=256)
    returned_fields: list[str] = Field(
        default_factory=lambda: ["EventId", "EventType", "SourceNode", "SourceName", "Time", "Severity", "Message"],
        max_length=32,
    )

    @model_validator(mode="after")
    def validate_sources(self):
        if len(set(self.source_nodes)) != len(self.source_nodes) or any(
            not 1 <= len(s) <= 512 for s in self.source_nodes
        ):
            raise ValueError("事件源重复或 NodeId 长度无效")
        allowed = {
            "EventId",
            "EventType",
            "SourceNode",
            "SourceName",
            "Time",
            "ReceiveTime",
            "Severity",
            "Message",
            "ConditionId",
            "AckedState",
            "Retain",
        }
        if (
            not self.returned_fields
            or len(set(self.returned_fields)) != len(self.returned_fields)
            or not set(self.returned_fields) <= allowed
        ):
            raise ValueError("事件返回字段无效")
        return self


class DataSetField(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_id: str = Field(min_length=1, max_length=512)
    alias: str = Field(min_length=1, max_length=128)


class DataSetWriterConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    writer_id: int = Field(ge=1, le=65535)
    name: str = Field(min_length=1, max_length=128)
    kind: Literal["variables", "events"] = "variables"
    enabled: bool = True
    topic: str = Field(min_length=1, max_length=1024)
    metadata_topic: str = Field(min_length=1, max_length=1024)
    key_frame_count: int = Field(default=1, ge=1, le=1000)
    fields: list[DataSetField] = Field(default_factory=list, max_length=1000)
    source_nodes: list[str] = Field(default_factory=list, max_length=100)
    event_fields: list[str] = Field(
        default_factory=lambda: ["EventId", "SourceNode", "SourceName", "Time", "Severity", "Message"], max_length=32
    )

    @model_validator(mode="after")
    def unique_fields(self):
        if any(c in topic for topic in (self.topic, self.metadata_topic) for c in ("#", "+", "\x00")):
            raise ValueError("发布主题不能包含 MQTT 通配符或空字符")
        if self.topic == self.metadata_topic:
            raise ValueError("数据主题与元数据主题不能相同")
        if len({f.node_id for f in self.fields}) != len(self.fields) or len({f.alias for f in self.fields}) != len(
            self.fields
        ):
            raise ValueError("数据集 NodeId 和字段别名不能重复")
        if len(set(self.source_nodes)) != len(self.source_nodes) or any(
            not 1 <= len(s) <= 512 for s in self.source_nodes
        ):
            raise ValueError("事件源无效")
        EventsConfig(returned_fields=self.event_fields)
        return self


class PubSubConfig(BaseModel):
    """MQTT 3.1.1 / JSON, QoS 0 with reversible Variant fields."""

    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    publisher_id: str = Field(default="ems-simulate", min_length=1, max_length=128)
    broker_url: str = Field(default="mqtt://127.0.0.1:1883", max_length=1024)
    writer_group_name: str = Field(default="WriterGroup1", min_length=1, max_length=128)
    publishing_interval_ms: int = Field(default=500, ge=50, le=3600000)
    config_version: int = Field(default=1, ge=1, le=4294967295)
    message_content: list[
        Literal["publisher_id", "writer_group_name", "sequence_number", "timestamp", "status", "metadata_version"]
    ] = Field(
        default_factory=lambda: [
            "publisher_id",
            "writer_group_name",
            "sequence_number",
            "timestamp",
            "status",
            "metadata_version",
        ],
        max_length=6,
    )
    field_content: list[Literal["status_code", "source_timestamp", "server_timestamp"]] = Field(
        default_factory=lambda: ["status_code", "source_timestamp", "server_timestamp"], max_length=3
    )
    writers: list[DataSetWriterConfig] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_writers(self):
        from urllib.parse import urlsplit

        parsed = urlsplit(self.broker_url)
        if (
            parsed.scheme not in {"mqtt", "mqtts"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Broker 地址应为 mqtt://host:port 或 mqtts://host:port")
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            raise ValueError("MQTT 端口无效")
        if len({w.writer_id for w in self.writers}) != len(self.writers):
            raise ValueError("DataSetWriterId 不能重复")
        metadata_topics = [w.metadata_topic for w in self.writers]
        if len(set(metadata_topics)) != len(metadata_topics) or set(metadata_topics) & {w.topic for w in self.writers}:
            raise ValueError("各数据集的元数据主题必须独立于数据主题")
        if self.enabled and not any(
            w.enabled and (w.fields if w.kind == "variables" else w.source_nodes) for w in self.writers
        ):
            raise ValueError("至少配置一个有节点的已启用数据集")
        return self
