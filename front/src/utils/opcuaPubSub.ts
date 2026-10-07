import type { OpcUaDiscoveredVariable, OpcUaObjectNode } from "@/api/opcuaApi";

export type DataKind = "realtime" | "history" | "events";
export interface UaSelection extends OpcUaObjectNode {
  data_type?: string;
  history_read?: boolean;
  historizing?: boolean;
  event_notifier?: boolean;
}
export interface MonitorItem {
  node_id: string;
  namespace_uri?: string | null;
  sampling_interval_ms: number;
  queue_size: number;
  deadband: number;
  mode: "Disabled" | "Sampling" | "Reporting";
}
export interface UaSubscription {
  id: string;
  publishing_interval_ms: number;
  lifetime_count: number;
  keepalive_count: number;
  enabled: boolean;
  items: MonitorItem[];
}
export interface UaWriter {
  writer_id: number;
  name: string;
  kind: "variables" | "events";
  enabled: boolean;
  topic: string;
  metadata_topic: string;
  key_frame_count: number;
  fields: { node_id: string; alias: string }[];
  source_nodes: string[];
  event_fields: string[];
}
export interface UaPublisher {
  enabled: boolean;
  publisher_id: string;
  broker_url: string;
  writer_group_name: string;
  publishing_interval_ms: number;
  config_version: number;
  message_content: string[];
  field_content: string[];
  writers: UaWriter[];
}
export const EVENT_FIELDS = [
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
];
export const DRAG_MIME = "application/x-ems-opcua-nodes";
export const nodeKey = (id: string) => id.trim().replace(/^ns=0;/, "");
export function encodeUaDrag(channelId: number, nodes: UaSelection[]): string {
  return JSON.stringify({
    channelId,
    nodes: nodes.map(({ node_id, browse_name, node_class }) => ({
      node_id,
      browse_name,
      node_class,
    })),
  });
}
export function decodeUaDrag(raw: string, channelId: number): UaSelection[] {
  if (!raw || raw.length > 1024 * 1024) throw new Error("invalidDrag");
  const payload = JSON.parse(raw);
  if (payload.channelId !== channelId) throw new Error("crossChannelDrag");
  if (
    !Array.isArray(payload.nodes) ||
    !payload.nodes.length ||
    payload.nodes.length > 1000
  )
    throw new Error("invalidDrag");
  return payload.nodes.map((node: unknown) => {
    if (!node || typeof node !== "object") throw new Error("invalidDrag");
    const n = node as Record<string, unknown>;
    if (
      typeof n.node_id !== "string" ||
      !n.node_id.trim() ||
      n.node_id.length > 512 ||
      typeof n.browse_name !== "string" ||
      typeof n.node_class !== "string"
    )
      throw new Error("invalidDrag");
    return {
      node_id: nodeKey(n.node_id),
      browse_name: n.browse_name,
      node_class: n.node_class,
    };
  });
}
export function rejectionReason(
  node: UaSelection,
  kind: DataKind,
  role: "client" | "server",
): string | null {
  if (kind === "events")
    return node.node_class !== "Object" ||
      (role === "client" && !node.event_notifier)
      ? "requireEventSource"
      : null;
  if (node.node_class !== "Variable") return "requireVariable";
  if (kind === "history" && role === "client" && !node.history_read)
    return "requireHistory";
  return null;
}
export function uniqueSelections(
  existing: UaSelection[],
  incoming: UaSelection[],
): UaSelection[] {
  const map = new Map(existing.map((n) => [nodeKey(n.node_id), n]));
  incoming.forEach((n) => {
    if (!map.has(nodeKey(n.node_id)))
      map.set(nodeKey(n.node_id), { ...n, node_id: nodeKey(n.node_id) });
  });
  return [...map.values()];
}
export function defaultMonitor(nodeId: string): MonitorItem {
  return {
    node_id: nodeId,
    sampling_interval_ms: 500,
    queue_size: 10,
    deadband: 0,
    mode: "Reporting",
  };
}

export function mergeDiscoveredMonitors(
  existing: MonitorItem[],
  incoming: OpcUaDiscoveredVariable[],
  limit = 1000,
): {
  items: MonitorItem[];
  added: OpcUaDiscoveredVariable[];
  overflow: boolean;
} {
  const items = [...existing],
    added: OpcUaDiscoveredVariable[] = [];
  const logicalKey = (item: {
    node_id: string;
    namespace_uri?: string | null;
  }) =>
    item.namespace_uri
      ? JSON.stringify([
          item.namespace_uri,
          nodeKey(item.node_id).replace(/^ns=\d+;/, ""),
        ])
      : nodeKey(item.node_id);
  const keys = new Set(existing.map(logicalKey));
  const rawKeys = new Set(
    existing
      .filter((item) => !item.namespace_uri)
      .map((item) => nodeKey(item.node_id)),
  );
  let overflow = false;
  for (const node of incoming) {
    if (!node.readable || node.node_class !== "Variable") continue;
    const key = logicalKey(node);
    if (keys.has(key) || rawKeys.has(nodeKey(node.node_id))) continue;
    if (items.length >= limit) {
      overflow = true;
      continue;
    }
    keys.add(key);
    items.push({
      ...defaultMonitor(node.node_id),
      namespace_uri: node.namespace_uri,
    });
    added.push(node);
  }
  return { items, added, overflow };
}
export function defaultSubscription(id = "Subscription1"): UaSubscription {
  return {
    id,
    publishing_interval_ms: 500,
    lifetime_count: 10000,
    keepalive_count: 10,
    enabled: false,
    items: [],
  };
}
export function defaultWriter(id: number, kind: UaWriter["kind"]): UaWriter {
  const topic = `opcua/ems/WriterGroup1/${id}`;
  return {
    writer_id: id,
    name: kind === "variables" ? `DataSet${id}` : `Events${id}`,
    kind,
    enabled: true,
    topic: `${topic}/data`,
    metadata_topic: `${topic}/metadata`,
    key_frame_count: 1,
    fields: [],
    source_nodes: [],
    event_fields: [
      "EventId",
      "SourceNode",
      "SourceName",
      "Time",
      "Severity",
      "Message",
    ],
  };
}
export function defaultPublisher(channelId: number): UaPublisher {
  return {
    enabled: false,
    publisher_id: `ems-${channelId}`,
    broker_url: "mqtt://127.0.0.1:1883",
    writer_group_name: "WriterGroup1",
    publishing_interval_ms: 500,
    config_version: 1,
    message_content: [
      "publisher_id",
      "writer_group_name",
      "sequence_number",
      "timestamp",
      "status",
      "metadata_version",
    ],
    field_content: ["status_code", "source_timestamp", "server_timestamp"],
    writers: [defaultWriter(1, "variables"), defaultWriter(2, "events")],
  };
}
export function csvText(headers: string[], rows: unknown[][]): string {
  const cell = (value: unknown) => {
    let text =
      typeof value === "object" && value !== null
        ? JSON.stringify(value)
        : String(value ?? "");
    if (typeof value === "string" && /^[=+\-@\t\r]/.test(text))
      text = `'${text}`;
    return `"${text.replace(/"/g, '""')}"`;
  };
  return (
    "\uFEFF" +
    [headers, ...rows].map((row) => row.map(cell).join(",")).join("\r\n")
  );
}
export function downloadCsv(
  filename: string,
  headers: string[],
  rows: unknown[][],
): void {
  const url = URL.createObjectURL(
    new Blob([csvText(headers, rows)], { type: "text/csv;charset=utf-8" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
export const displayUaValue = (value: unknown) =>
  typeof value === "object" && value !== null
    ? JSON.stringify(value)
    : String(value ?? "—");
