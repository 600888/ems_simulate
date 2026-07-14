/**
 * IEC 61850 Reports API 调用层
 */

import { requestApi } from "./http";
import { REPORT_API } from "@/constants/api";
import { HTTP_TIMEOUT_IEC61850_REPORT_BATCH } from "@/constants/app";

// ===== 类型定义 =====

export interface TrgOps {
  dchg: boolean;
  qchg: boolean;
  dupd: boolean;
  period: boolean;
  gi: boolean;
}

export interface OptFields {
  seq_num: boolean;
  time_stamp: boolean;
  data_set: boolean;
  reason_code: boolean;
  data_ref: boolean;
  entry_id: boolean;
  config_ref: boolean;
  buf_ovfl: boolean;
}

export interface RcbInfo {
  name: string;
  ref: string;
  rcb_type: string;
  ld: string;
  ln: string;
  rpt_id: string;
  rpt_ena: boolean;
  data_set_ref: string;
  conf_rev: number;
  buf_time: number;
  intg_period: number;
  sq_num: number;
  purge_buf: boolean;
  entry_id: string | null;
  time_of_entry: string | number | null;
  owner: string;
  resv: boolean;
  resv_tms: number;
  reserved: boolean;
  locked: boolean;
  trg_ops: TrgOps;
  opt_fields: OptFields;
  active: boolean;
}

export interface ReportDataEntry {
  seq_num: number;
  time_stamp: string;
  reason_codes: Record<string, string>;
  data_values: Record<string, any>;
  entry_id: string | null;
  conf_rev: number;
  data_set: string;
  rpt_id: string;
  received_at: string;
  uid: number;
}

export interface ReportDataResponse {
  data: ReportDataEntry[];
  total: number;
  latest_uid: number | null;
  unchanged: boolean;
}

export interface ReportStateResponse {
  total: number;
  latest_uid: number | null;
}

export interface ReportEntrySummary {
  entry_key: string;
  index: number;
  seq_num: number | null;
  time_stamp: string;
  received_at: string;
  data_set: string;
  rpt_id: string;
  conf_rev: number | null;
  entry_id: string | null;
  value_count: number;
}

export interface ReportTreeNode {
  id: string;
  label: string;
  node_type: "ld" | "ln" | "do" | "da" | "bda" | "group" | "value" | string;
  fc?: string | null;
  reason?: string | null;
  value?: any;
  raw_ref?: string | null;
  children?: ReportTreeNode[];
}

export interface ReportDataTreeResponse {
  rcb_ref: string;
  entry: ReportEntrySummary | null;
  tree_items: ReportTreeNode[];
}

export interface LatestReportResponse extends ReportDataTreeResponse {
  latest_uid: number | null;
  unchanged: boolean;
}

export interface ReportHistoryResponse {
  entries: ReportEntrySummary[];
  total: number;
  latest_uid: number | null;
  unchanged: boolean;
}

export interface ActiveReport {
  rcb_ref: string;
  enabled_since: string;
  cache_size: number;
}

export interface RcbListResponse {
  rcbs: RcbInfo[];
}

export interface ReportDataTreeOptions {
  entryKey?: string | null;
  latest?: boolean;
}

// ===== API 函数 =====

export async function listRcbs(channelId: number): Promise<RcbInfo[]> {
  try {
    const result = await requestApi(REPORT_API.LIST, "post", {
      channel_id: channelId,
    });
    return result?.rcbs || [];
  } catch (error) {
    console.error("Error listing RCBs:", error);
    return [];
  }
}

export async function applyConfig(
  channelId: number,
  rcbRef: string,
  rptEna: boolean,
  trgOps?: Partial<TrgOps>,
  optFields?: Partial<OptFields>
): Promise<{ success: boolean; rcb?: RcbInfo }> {
  const result = await requestApi(REPORT_API.APPLY, "post", {
    channel_id: channelId,
    rcb_ref: rcbRef,
    rpt_ena: rptEna,
    trg_ops: trgOps,
    opt_fields: optFields,
  });
  return { success: result?.success === true, rcb: result?.rcb };
}

export interface BatchApplyResult {
  success: boolean;
  success_count: number;
  fail_count: number;
  fail_details: { rcb_ref: string; reason: string }[];
}

export async function batchApplyConfig(
  channelId: number,
  rcbRefs: string[],
  rptEna: boolean,
  trgOps?: Partial<TrgOps>,
  optFields?: Partial<OptFields>
): Promise<BatchApplyResult> {
  const result = await requestApi(
    REPORT_API.BATCH_APPLY,
    "post",
    {
      channel_id: channelId,
      items: rcbRefs.map((ref) => ({ rcb_ref: ref })),
      rpt_ena: rptEna,
      trg_ops: trgOps,
      opt_fields: optFields,
    },
    HTTP_TIMEOUT_IEC61850_REPORT_BATCH,
  );
  return {
    success: result?.success === true,
    success_count: result?.success_count ?? 0,
    fail_count: result?.fail_count ?? 0,
    fail_details: result?.fail_details ?? [],
  };
}

export async function triggerGi(channelId: number, rcbRef: string): Promise<boolean> {
  const result = await requestApi(REPORT_API.GI, "post", {
    channel_id: channelId,
    rcb_ref: rcbRef,
  });
  return result?.success === true;
}

export async function getReportData(
  channelId: number,
  rcbRef: string,
  limit: number = 100,
  knownLatestUid: number | null = null,
): Promise<ReportDataResponse> {
  try {
    const result = await requestApi(REPORT_API.DATA, "post", {
      channel_id: channelId,
      rcb_ref: rcbRef,
      limit,
      known_latest_uid: knownLatestUid,
    });
    return result || { data: [], total: 0, latest_uid: null, unchanged: false };
  } catch (error) {
    console.error("Error fetching report data:", error);
    return { data: [], total: 0, latest_uid: null, unchanged: false };
  }
}

export async function getReportState(
  channelId: number,
  rcbRef: string,
): Promise<ReportStateResponse> {
  try {
    const result = await requestApi(REPORT_API.STATE, "post", {
      channel_id: channelId,
      rcb_ref: rcbRef,
    });
    return result || { total: 0, latest_uid: null };
  } catch (error) {
    console.error("Error fetching report state:", error);
    return { total: 0, latest_uid: null };
  }
}

export async function getReportDataTree(
  channelId: number,
  rcbRef: string,
  options: ReportDataTreeOptions = {}
): Promise<ReportDataTreeResponse> {
  try {
    const result = await requestApi(REPORT_API.DATA_TREE, "post", {
      channel_id: channelId,
      rcb_ref: rcbRef,
      entry_key: options.entryKey || null,
      latest: options.latest ?? true,
    });
    return result || { rcb_ref: rcbRef, entry: null, tree_items: [] };
  } catch (error) {
    console.error("Error fetching report data tree:", error);
    return { rcb_ref: rcbRef, entry: null, tree_items: [] };
  }
}

export async function getLatestReport(
  channelId: number,
  rcbRef: string,
  knownLatestUid: number | null = null,
): Promise<LatestReportResponse> {
  try {
    const result = await requestApi(REPORT_API.LATEST, "post", {
      channel_id: channelId,
      rcb_ref: rcbRef,
      latest: true,
      known_latest_uid: knownLatestUid,
    });
    return result || {
      rcb_ref: rcbRef,
      entry: null,
      tree_items: [],
      latest_uid: null,
      unchanged: false,
    };
  } catch (error) {
    console.error("Error fetching latest report:", error);
    return {
      rcb_ref: rcbRef,
      entry: null,
      tree_items: [],
      latest_uid: null,
      unchanged: false,
    };
  }
}

export async function getReportHistory(
  channelId: number,
  rcbRef: string,
  limit: number = 100,
  knownLatestUid: number | null = null,
): Promise<ReportHistoryResponse> {
  try {
    const result = await requestApi(REPORT_API.HISTORY, "post", {
      channel_id: channelId,
      rcb_ref: rcbRef,
      limit,
      known_latest_uid: knownLatestUid,
    });
    return result || { entries: [], total: 0, latest_uid: null, unchanged: false };
  } catch (error) {
    console.error("Error fetching report history:", error);
    return { entries: [], total: 0, latest_uid: null, unchanged: false };
  }
}

export async function getRcbDetail(
  channelId: number,
  rcbRef: string
): Promise<RcbInfo | null> {
  try {
    return await requestApi(REPORT_API.DETAIL, "post", {
      channel_id: channelId,
      rcb_ref: rcbRef,
    });
  } catch (error) {
    console.error("Error fetching RCB detail:", error);
    return null;
  }
}

export async function refreshRcb(
  channelId: number,
  rcbRef: string
): Promise<RcbInfo | null> {
  try {
    return await requestApi(REPORT_API.REFRESH, "post", {
      channel_id: channelId,
      rcb_ref: rcbRef,
    });
  } catch (error) {
    console.error("Error refreshing RCB:", error);
    return null;
  }
}

export async function listActiveReports(channelId: number): Promise<ActiveReport[]> {
  try {
    const result = await requestApi(REPORT_API.ACTIVE, "post", {
      channel_id: channelId,
    });
    return result?.active_reports || [];
  } catch (error) {
    console.error("Error listing active reports:", error);
    return [];
  }
}
