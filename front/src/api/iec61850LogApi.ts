import { requestApi } from "./http";
import { IEC61850_LOG_API } from "@/constants/api";

export interface LogTriggerOptions {
  dchg: boolean;
  qchg: boolean;
  dupd: boolean;
  period: boolean;
  gi: boolean;
}

export interface LogControl {
  name: string;
  ref: string;
  ld: string;
  ln: string;
  enabled: boolean;
  log_ref: string;
  data_set_ref: string;
  trg_ops: LogTriggerOptions;
  intg_period: number;
}

export interface Iec61850LogEntry {
  entry_id: string;
  timestamp: string;
  timestamp_ms: number;
  level: string;
  service: string;
  object_ref: string;
  message: string;
  source: string;
  fields: Record<string, unknown>;
}

export interface Iec61850LogQuery {
  logRef: string;
  startTimeMs: number;
  endTimeMs: number;
  page?: number;
  pageSize?: number;
  keyword?: string;
  level?: string;
  service?: string;
}

export interface Iec61850LogResult {
  entries: Iec61850LogEntry[];
  total: number;
  page: number;
  page_size: number;
  more_follows: boolean;
}

export async function listLogControls(
  channelId: number,
): Promise<LogControl[]> {
  const result = await requestApi(IEC61850_LOG_API.CONTROLS, "post", {
    channel_id: channelId,
  });
  return result?.items || [];
}

export async function setLogControlEnabled(
  channelId: number,
  lcbRef: string,
  enabled: boolean,
): Promise<boolean> {
  const result = await requestApi(IEC61850_LOG_API.ENABLE, "post", {
    channel_id: channelId,
    lcb_ref: lcbRef,
    enabled,
  });
  return result?.success === true;
}

export async function queryIec61850Logs(
  channelId: number,
  query: Iec61850LogQuery,
): Promise<Iec61850LogResult> {
  const result = await requestApi(IEC61850_LOG_API.QUERY, "post", {
    channel_id: channelId,
    log_ref: query.logRef,
    start_time_ms: query.startTimeMs,
    end_time_ms: query.endTimeMs,
    page: query.page ?? 1,
    page_size: query.pageSize ?? 50,
    keyword: query.keyword ?? "",
    level: query.level ?? "",
    service: query.service ?? "",
  });
  return (
    result || {
      entries: [],
      total: 0,
      page: 1,
      page_size: query.pageSize ?? 50,
      more_follows: false,
    }
  );
}
