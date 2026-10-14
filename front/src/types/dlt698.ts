/** Proposed DL/T 698 HTTP contract. Integers cross JSON as decimal strings. */
export type Dlt698Role = "client" | "server";
export const DLT698_DATA_TYPES = [
  "Null",
  "Boolean",
  "Int8",
  "UInt8",
  "Int16",
  "UInt16",
  "Int32",
  "UInt32",
  "Int64",
  "UInt64",
  "Enum",
  "Float32",
  "Float64",
  "OctetString",
  "VisibleString",
  "Utf8String",
  "BitString",
  "Date",
  "Time",
  "DateTime",
  "DateTimeS",
  "Array",
  "Structure",
] as const;
export type Dlt698DataType = (typeof DLT698_DATA_TYPES)[number];
export interface Dlt698Data {
  type: Dlt698DataType;
  value: string | boolean | null | Dlt698Data[];
}
export type Dlt698ResultKind =
  | "data"
  | "dar"
  | "transport_error"
  | "validation_error"
  | "unknown"
  | "pending";
export interface Dlt698Result {
  index: number;
  oad: string;
  kind: Dlt698ResultKind;
  data?: Dlt698Data;
  dar?: number;
  message?: string;
  updated_at?: string;
  tsa?: string;
  children?: Dlt698Result[];
  md5?: string;
}
export interface Dlt698Point {
  code: string;
  name: string;
  oad: string;
  category: "energy" | "demand" | "variable" | "harmonic" | "parameter";
  data_type: Dlt698DataType;
  unit: string;
  scaler: number;
  standard: boolean;
  writable: boolean;
  initial_value: Dlt698Data;
  last_good?: Dlt698Data;
  last_good_at?: string;
  result?: Dlt698Result;
}
export interface Dlt698Config {
  role: Dlt698Role;
  server_address: string;
  logical_address: number;
  client_address: number;
  association: "public" | "preestablished";
  request_timeout_ms: number;
  heartbeat_interval_s: number;
  protocol_version: number;
  send_frame_max: number;
  receive_frame_max: number;
  receive_window: number;
  apdu_max: number;
  association_timeout_s: number;
  wiring: "three_phase_four_wire" | "three_phase_three_wire" | "single_phase";
  tariff_count: number;
  harmonic_order: number;
}
export type Dlt698Feature =
  | "points"
  | "get"
  | "set"
  | "action"
  | "records"
  | "reports"
  | "proxy"
  | "routes"
  | "local_values"
  | "auto_read"
  | "mapping"
  | "simulation"
  | "history"
  | "import"
  | "config"
  | "md5"
  | "then_get";
export interface Dlt698Status {
  available: boolean;
  state:
    | "stopped"
    | "listening"
    | "associating"
    | "associated"
    | "requesting"
    | "timeout"
    | "rejected"
    | "cancelled"
    | "lost";
  features: Partial<
    Record<Dlt698Feature, { supported: boolean; reason?: string }>
  >;
  sessions: { id: string; address: string; associated: boolean }[];
  negotiated?: Partial<Dlt698Config>;
  auto_read?: { running: boolean; interval_ms: number; codes: string[] };
  security_backend: boolean;
}
export interface Dlt698RecordQuery {
  template: "daily" | "monthly" | "power_loss" | "initialization";
  oad: string;
  selector: "all" | "at" | "between" | "sequences" | "latest";
  start: string;
  end: string;
  latest: number;
  columns: string[];
}
export interface Dlt698RecordResult {
  columns: { oad: string; name: string }[];
  rows: Dlt698Data[][];
  dar?: number;
  blocks: number | null;
}
export interface Dlt698Report {
  id: string;
  time: string;
  session_id: string;
  kind: string;
  piid_acd: string;
  oad?: string;
  data?: Dlt698Data;
  items?: { oad: string; data?: Dlt698Data; dar?: number }[];
  record?: Dlt698RecordResult;
  port?: string;
  frames?: string[];
  follow_report?: unknown;
  acd?: boolean;
  acknowledgement: string;
}
export interface Dlt698Route {
  tsa: string;
  session_id: string;
  bridge: "connected" | "unavailable";
}
export interface Dlt698Operation {
  service:
    "set" | "action" | "local_values" | "proxy" | "md5" | "then_get" | "report";
  items: {
    oad?: string;
    omd?: string;
    data?: Dlt698Data;
    tsa?: string;
    get_oad?: string;
    delay_s?: number;
  }[];
  session_id?: string;
  proxy_service?: string;
  /** Service-specific record, transparent transport, report and ThenGet options. */
  options?: Record<string, unknown>;
}
