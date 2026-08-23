import { DEVICE_API } from "@/constants";

import { requestApi } from "./http";

export type ConnectionState =
  "connecting" | "established" | "active" | "idle" | "closed" | "abnormal";

export type DisconnectReason =
  | "remote_closed"
  | "network_reset"
  | "idle_timeout"
  | "protocol_error"
  | "tls_handshake_failed"
  | "authentication_failed"
  | "server_stopped"
  | "connection_replaced"
  | "max_connections_rejected"
  | "process_terminated"
  | "unknown";

export interface ConnectionRecord {
  session_id: string;
  channel_id: number;
  protocol_type: string;
  server_instance_id: string;
  state: ConnectionState;
  remote_ip: string | null;
  remote_port: number | null;
  local_ip: string | null;
  local_port: number | null;
  transport_connected_at: string;
  established_at: string | null;
  last_activity_at: string;
  disconnected_at: string | null;
  duration_ms: number;
  disconnect_reason: DisconnectReason | null;
  disconnect_initiator: string | null;
  close_detail: string | null;
  client_identity: Record<string, unknown>;
  security: Record<string, unknown>;
  rx_bytes: number;
  tx_bytes: number;
  rx_messages: number;
  tx_messages: number;
  error_count: number;
  end_time_accuracy: "exact" | "estimated";
}

export interface ConnectionSummary {
  supported: boolean;
  unsupported_reason?: string;
  server_running: boolean;
  current_count: number;
  active_count: number;
  idle_count: number;
  history_count: number;
  abnormal_disconnects_today: number;
  updated_at?: string;
}

export interface CurrentConnectionsResult {
  supported: boolean;
  unsupported_reason?: string;
  items: ConnectionRecord[];
}

export interface ConnectionHistoryQuery {
  page?: number;
  page_size?: number;
  disconnect_reason?: DisconnectReason | null;
  remote_ip?: string | null;
}

export interface ConnectionHistoryResult {
  supported: boolean;
  unsupported_reason?: string;
  page?: number;
  page_size?: number;
  total: number;
  retention_limit: number;
  items: ConnectionRecord[];
}

export async function getConnectionSummary(
  deviceName: string,
): Promise<ConnectionSummary> {
  return await requestApi(DEVICE_API.CONNECTION_SUMMARY, "post", {
    device_name: deviceName,
  });
}

export async function getCurrentConnections(
  deviceName: string,
): Promise<CurrentConnectionsResult> {
  return await requestApi(DEVICE_API.CURRENT_CONNECTIONS, "post", {
    device_name: deviceName,
  });
}

export async function getConnectionHistory(
  deviceName: string,
  query: ConnectionHistoryQuery = {},
): Promise<ConnectionHistoryResult> {
  return await requestApi(DEVICE_API.CONNECTION_HISTORY, "post", {
    device_name: deviceName,
    page: query.page ?? 1,
    page_size: query.page_size ?? 20,
    disconnect_reason: query.disconnect_reason ?? null,
    remote_ip: query.remote_ip?.trim() || null,
  });
}

export async function getConnectionDetail(
  deviceName: string,
  sessionId: string,
): Promise<ConnectionRecord> {
  return await requestApi(DEVICE_API.CONNECTION_DETAIL, "post", {
    device_name: deviceName,
    session_id: sessionId,
  });
}
