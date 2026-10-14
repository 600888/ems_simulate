import axios from "axios";
import { instance } from "./http";
import type {
  Dlt698Config,
  Dlt698Operation,
  Dlt698Point,
  Dlt698RecordQuery,
  Dlt698RecordResult,
  Dlt698Report,
  Dlt698Result,
  Dlt698Route,
  Dlt698Status,
} from "@/types/dlt698";

// An absent planned endpoint is a workspace state, not a global error toast.
const http = axios.create({
  baseURL: instance.defaults.baseURL,
  // Protocol timeouts and cancellation belong to dlt698; large reads may span requests.
  timeout: 0,
});
async function request<T>(
  channelId: number,
  path: string,
  method = "GET",
  data?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const response = await http.request({
    url: `/api/dlt698/channels/${channelId}/${path}`,
    method,
    data,
    signal,
  });
  const body = response.data;
  if (body.code !== 0 && body.code !== 200)
    throw new Error(body.message || "DL/T 698 request failed");
  return body.data as T;
}
export const dlt698Api = {
  status: (id: number) => request<Dlt698Status>(id, "status"),
  config: (id: number) => request<Dlt698Config>(id, "config"),
  saveConfig: (id: number, config: Dlt698Config) =>
    request<Dlt698Config>(id, "config", "PUT", config),
  points: (id: number) => request<Dlt698Point[]>(id, "points"),
  savePoint: (id: number, point: Dlt698Point, originalCode?: string) => {
    const {
      result: _result,
      last_good: _lastGood,
      last_good_at: _lastGoodAt,
      ...definition
    } = point;
    return request<Dlt698Point>(
      id,
      `points${originalCode ? `/${encodeURIComponent(originalCode)}` : ""}`,
      originalCode ? "PUT" : "POST",
      definition,
    );
  },
  deletePoint: (id: number, code: string) =>
    request<void>(id, `points/${encodeURIComponent(code)}`, "DELETE"),
  catalog: (
    id: number,
    layout: Pick<Dlt698Config, "wiring" | "tariff_count" | "harmonic_order">,
  ) => request<Dlt698Point[]>(id, "catalog", "POST", layout),
  read: (id: number, codes: string[], signal?: AbortSignal) =>
    request<Dlt698Result[]>(id, "read", "POST", { codes }, signal),
  probe: (id: number, oads: string[], signal?: AbortSignal) =>
    request<Dlt698Result[]>(id, "probe", "POST", { oads }, signal),
  operation: (id: number, operation: Dlt698Operation) =>
    request<Dlt698Result[]>(id, "operations", "POST", operation),
  records: (id: number, query: Dlt698RecordQuery, signal?: AbortSignal) =>
    request<Dlt698RecordResult>(id, "records/query", "POST", query, signal),
  appendRecord: (id: number, query: Dlt698RecordQuery, row: unknown) =>
    request<void>(id, "records/rows", "POST", { query, row }),
  reports: (id: number) => request<Dlt698Report[]>(id, "reports"),
  routes: (id: number) => request<Dlt698Route[]>(id, "routes"),
  saveRoute: (id: number, route: Dlt698Route) =>
    request<void>(id, "routes", "POST", route),
  autoRead: (
    id: number,
    running: boolean,
    interval_ms: number,
    codes: string[],
  ) => request<void>(id, "auto-read", "PUT", { running, interval_ms, codes }),
  importStandardPoints: (id: number) =>
    request<{ count: number }>(id, "points/standard", "POST"),
  importPoints: async (id: number, file: File) => {
    const data = new FormData();
    data.append("file", file);
    return request<{ count: number }>(id, "points/import", "POST", data);
  },
};
