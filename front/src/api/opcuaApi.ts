import { instance, requestApi } from "./http";
import type { OpcUaScalarType } from "@/utils/opcuaValue";

export interface OpcUaPoint {
  id: number;
  point_type: number;
  point_code: string;
  point_name: string;
  node_id: string;
  namespace_uri: string;
  data_type: string;
  sampling_interval_ms: number;
  initial_value: boolean | number;
  related_code: string | null;
}

export interface OpcUaImportIssue {
  sheet: string;
  row: number;
  field: string;
  message?: string;
  value?: string;
}

export interface OpcUaImportPreview {
  sha256: string;
  total: number;
  counts: Record<string, number>;
  errors: OpcUaImportIssue[];
  conflicts: OpcUaImportIssue[];
  role: "client" | "server";
}

export interface OpcUaConfig {
  channel_id: number;
  role: "client" | "server";
  endpoint_url: string;
  endpoint_path: string;
  namespace_uri: string;
}

export interface OpcUaVariable {
  node_id: string;
  browse_name: string;
  data_type: OpcUaScalarType;
  initial_value: unknown;
  writable: boolean;
  point_code?: string | null;
  namespace_uri?: string;
}

export interface OpcUaObjectNode {
  node_id: string;
  browse_name: string;
  display_name?: string | null;
  node_class: string;
}

export interface OpcUaNodeDetails extends OpcUaObjectNode {
  description: string | null;
  namespace_uri: string;
  data_type: string | null;
  value_rank: number | null;
  array_dimensions: number[] | null;
  writable: boolean;
  references: (OpcUaObjectNode & {
    reference_type: string;
    forward: boolean;
  })[];
  type_definition: string | null;
  references_truncated: boolean;
}

export const browseOpcUaServer = (
  channel_id: number,
  node_id = "i=85",
  offset = 0,
): Promise<{
  nodes: OpcUaObjectNode[];
  total: number;
  offset: number;
  has_more: boolean;
}> =>
  requestApi("/api/opcua/server/browse", "post", {
    channel_id,
    node_id,
    offset,
    limit: 50,
  });

export const inspectOpcUaServerNode = (
  channel_id: number,
  node_id: string,
): Promise<OpcUaNodeDetails> =>
  requestApi("/api/opcua/server/inspect", "post", { channel_id, node_id });

export const readOpcUaServerValues = (
  channel_id: number,
  node_ids: string[],
): Promise<{
  values: OpcUaValueSnapshot[];
  errors: { node_id: string; message: string }[];
}> => requestApi("/api/opcua/server/values", "post", { channel_id, node_ids });

export const writeOpcUaServerValue = (
  channel_id: number,
  node_id: string,
  value: unknown,
): Promise<OpcUaValueSnapshot> =>
  requestApi("/api/opcua/server/write", "post", { channel_id, node_id, value });

export interface OpcUaModelPreview {
  sha256: string;
  namespace_uri: string;
  total: number;
  errors: { node_id: string; message: string }[];
  conflicts: { node_id: string; message: string }[];
}

export interface OpcUaCapability {
  name: string;
  enabled: boolean;
  running: boolean;
  reason: string | null;
  details?: Record<string, unknown>;
}

export interface OpcUaStatus {
  running: boolean;
  endpoint_url: string | null;
  error: string | null;
  node_count?: number | null;
}

export interface OpcUaValueSnapshot {
  node_id: string;
  value: unknown;
  status_code: string;
  variant_type: string | null;
  source_timestamp: string | null;
  server_timestamp: string | null;
}

export const readOpcUaPoint = (
  channel_id: number,
  point_code: string,
): Promise<OpcUaValueSnapshot> =>
  requestApi("/api/opcua/points/read", "post", { channel_id, point_code });

export const getOpcUaStatus = (channel_id: number): Promise<OpcUaStatus> =>
  requestApi("/api/opcua/status", "post", { channel_id });

export const getOpcUaCapabilities = (
  channel_id: number,
): Promise<{ capabilities: OpcUaCapability[] }> =>
  requestApi("/api/opcua/capabilities", "post", { channel_id });

export const listOpcUaVariables = (
  channel_id: number,
): Promise<{ nodes: OpcUaVariable[] }> =>
  requestApi("/api/opcua/nodes/variables", "post", { channel_id });

export const saveOpcUaVariable = (
  channel_id: number,
  variable: OpcUaVariable,
) => requestApi("/api/opcua/nodes/upsert", "post", { channel_id, ...variable });

export const deleteOpcUaVariable = (channel_id: number, node_id: string) =>
  requestApi("/api/opcua/nodes/delete", "post", { channel_id, node_id });

export async function exportOpcUaModel(channel_id: number): Promise<Blob> {
  return (
    await instance.post(
      "/api/opcua/model/export",
      { channel_id },
      { responseType: "blob" },
    )
  ).data;
}

export async function exportOpcUaPoints(channel_id: number): Promise<Blob> {
  return (
    await instance.post(
      "/api/opcua/points/export",
      { channel_id },
      { responseType: "blob" },
    )
  ).data;
}

export const getOpcUaConfig = (channel_id: number): Promise<OpcUaConfig> =>
  requestApi("/api/opcua/config", "post", { channel_id });

export const listOpcUaPoints = (
  channel_id: number,
  search = "",
  point_type: number | null = null,
  offset = 0,
  limit = 100,
): Promise<{ points: OpcUaPoint[]; total: number }> =>
  requestApi("/api/opcua/points/list", "post", {
    channel_id,
    search,
    point_type,
    offset,
    limit,
  });

export const deleteOpcUaPoint = (channel_id: number, point_code: string) =>
  requestApi("/api/opcua/points/delete", "post", { channel_id, point_code });

export const clearOpcUaPoints = (
  channel_id: number,
): Promise<{ deleted: number }> =>
  requestApi("/api/opcua/points/clear", "post", { channel_id });

export const resetOpcUaVariables = (
  channel_id: number,
): Promise<{ reset: number }> =>
  requestApi("/api/opcua/nodes/reset", "post", { channel_id });

function workbookForm(channelId: number, file: File): FormData {
  const form = new FormData();
  form.append("channel_id", String(channelId));
  form.append("file", file);
  return form;
}

export async function previewOpcUaPoints(
  channelId: number,
  file: File,
): Promise<OpcUaImportPreview> {
  const response = await instance.post(
    "/api/opcua/points/import/preview",
    workbookForm(channelId, file),
    {
      headers: { "Content-Type": "multipart/form-data" },
    },
  );
  return response.data.data;
}

export async function applyOpcUaPoints(
  channelId: number,
  file: File,
  sha256: string,
  mode: "add" | "overwrite",
): Promise<{ created: number; updated: number; total: number }> {
  const form = workbookForm(channelId, file);
  form.append("expected_sha256", sha256);
  form.append("mode", mode);
  const response = await instance.post("/api/opcua/points/import/apply", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data.data;
}

export async function previewOpcUaModel(
  channelId: number,
  file: File,
): Promise<OpcUaModelPreview> {
  const response = await instance.post(
    "/api/opcua/model/import/preview",
    workbookForm(channelId, file),
    {
      headers: { "Content-Type": "multipart/form-data" },
    },
  );
  return response.data.data;
}

export async function applyOpcUaModel(
  channelId: number,
  file: File,
  sha256: string,
  mode: "add" | "overwrite",
): Promise<{ created: number; updated: number }> {
  const form = workbookForm(channelId, file);
  form.append("expected_sha256", sha256);
  form.append("mode", mode);
  return (
    await instance.post("/api/opcua/model/import/apply", form, {
      headers: { "Content-Type": "multipart/form-data" },
    })
  ).data.data;
}

export const browseOpcUaNodes = (
  channel_id: number,
  node_id: string,
  offset = 0,
) =>
  requestApi("/api/opcua/nodes/browse", "post", {
    channel_id,
    node_id,
    limit: 100,
    offset,
  }) as Promise<{
    nodes: { node_id: string; browse_name: string; node_class: string }[];
    total: number;
    offset: number;
    has_more: boolean;
  }>;

export const readOpcUaNode = (
  channel_id: number,
  node_id: string,
): Promise<OpcUaValueSnapshot> =>
  requestApi("/api/opcua/nodes/read", "post", { channel_id, node_id });

export const writeOpcUaNode = (
  channel_id: number,
  node_id: string,
  value: unknown,
): Promise<OpcUaValueSnapshot> =>
  requestApi("/api/opcua/nodes/write", "post", { channel_id, node_id, value });

export const saveOpcUaClientEndpoint = (
  channel_id: number,
  endpoint_url: string,
) =>
  requestApi("/api/opcua/config/client-endpoint", "post", {
    channel_id,
    endpoint_url,
  });

export const saveOpcUaServerModel = (
  channel_id: number,
  endpoint_path: string,
  namespace_uri: string,
) =>
  requestApi("/api/opcua/config/server-model", "post", {
    channel_id,
    endpoint_path,
    namespace_uri,
  });

export const getOpcUaFeatures = (
  channel_id: number,
): Promise<Record<string, any>> =>
  requestApi("/api/opcua/features/config", "post", { channel_id });

export const saveOpcUaFeature = (
  channel_id: number,
  name: string,
  config: unknown,
) =>
  requestApi("/api/opcua/features/save", "post", { channel_id, name, config });

export interface OpcUaStreamEvent extends Partial<OpcUaValueSnapshot> {
  sequence: number;
  timestamp: string;
  kind: string;
  state?: string;
  subscription?: string;
  Message?: string;
  Severity?: number;
  SourceName?: string;
  EventId?: unknown;
}

export const readOpcUaStream = (
  channel_id: number,
  after: number,
): Promise<{
  events: OpcUaStreamEvent[];
  gap: boolean;
  latest_sequence: number;
}> => requestApi("/api/opcua/stream/read", "post", { channel_id, after });

export const readOpcUaHistory = (
  channel_id: number,
  node_id: string,
  start: string,
  end: string,
  continuation: string | null = null,
): Promise<{
  values: OpcUaValueSnapshot[];
  continuation: string | null;
}> =>
  requestApi("/api/opcua/history/read", "post", {
    channel_id,
    node_id,
    start,
    end,
    continuation,
    limit: 100,
  });

export const getOpcUaDiagnostics = (
  channel_id: number,
): Promise<{
  calls: Record<string, unknown>[];
  sessions: Record<string, unknown>[];
}> => requestApi("/api/opcua/diagnostics", "post", { channel_id });

export const discoverOpcUaEndpoints = (
  channel_id: number,
  endpoint_url: string,
): Promise<{
  endpoints: Record<string, any>[];
}> =>
  requestApi("/api/opcua/endpoints/discover", "post", {
    channel_id,
    endpoint_url,
  });

export const generateOpcUaCertificate = (
  channel_id: number,
  application_uri: string,
  host: string,
) =>
  requestApi("/api/opcua/certificates/generate", "post", {
    channel_id,
    application_uri,
    host,
  });

export const trustOpcUaCertificate = (
  channel_id: number,
  fingerprint: string,
  trusted: boolean,
) =>
  requestApi("/api/opcua/certificates/trust", "post", {
    channel_id,
    fingerprint,
    trusted,
  });

export const saveOpcUaPassword = (channel_id: number, password: string) =>
  requestApi("/api/opcua/credentials/client", "post", { channel_id, password });

export const saveOpcUaUser = (
  channel_id: number,
  username: string,
  role: string,
  password: string | null,
) =>
  requestApi("/api/opcua/users/save", "post", {
    channel_id,
    username,
    role,
    password,
  });

export const emitOpcUaEvent = (
  channel_id: number,
  message: string,
  severity: number,
) =>
  requestApi("/api/opcua/events/emit", "post", {
    channel_id,
    message,
    severity,
  });

export const pauseOpcUaSimulation = (channel_id: number, paused: boolean) =>
  requestApi("/api/opcua/simulation/pause", "post", { channel_id, paused });
