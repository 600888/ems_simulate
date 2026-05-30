/**
 * IEC 61850 Reports API 调用层
 */

import { requestApi } from './http';
import { REPORT_API } from '@/constants/api';

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
  rcb_type: string;        // "BRCB" | "URCB"
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
  time_of_entry: number | null;
  owner: string;
  resv: boolean;
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
}

export interface ReportDataResponse {
  data: ReportDataEntry[];
  total: number;
}

export interface ActiveReport {
  rcb_ref: string;
  enabled_since: string;
  cache_size: number;
}

export interface RcbListResponse {
  rcbs: RcbInfo[];
}

// ===== API 函数 =====

export async function listRcbs(channelId: number): Promise<RcbInfo[]> {
  try {
    const result = await requestApi(REPORT_API.LIST, 'post', {
      channel_id: channelId,
    });
    return result?.rcbs || [];
  } catch (error) {
    console.error('Error listing RCBs:', error);
    return [];
  }
}

export async function enableReport(
  channelId: number,
  rcbRef: string,
  gi: boolean = true,
  trgOps?: Partial<TrgOps>,
  optFields?: Partial<OptFields>,
): Promise<boolean> {
  try {
    const result = await requestApi(REPORT_API.ENABLE, 'post', {
      channel_id: channelId,
      rcb_ref: rcbRef,
      gi,
      trg_ops: trgOps,
      opt_fields: optFields,
    });
    return result?.success === true;
  } catch (error) {
    console.error('Error enabling report:', error);
    return false;
  }
}

export async function disableReport(channelId: number, rcbRef: string): Promise<boolean> {
  try {
    const result = await requestApi(REPORT_API.DISABLE, 'post', {
      channel_id: channelId,
      rcb_ref: rcbRef,
    });
    return result?.success === true;
  } catch (error) {
    console.error('Error disabling report:', error);
    return false;
  }
}

export async function triggerGi(channelId: number, rcbRef: string): Promise<boolean> {
  try {
    const result = await requestApi(REPORT_API.GI, 'post', {
      channel_id: channelId,
      rcb_ref: rcbRef,
    });
    return result?.success === true;
  } catch (error) {
    console.error('Error triggering GI:', error);
    return false;
  }
}

export async function getReportData(
  channelId: number,
  rcbRef: string,
  limit: number = 100,
): Promise<ReportDataResponse> {
  try {
    const result = await requestApi(REPORT_API.DATA, 'post', {
      channel_id: channelId,
      rcb_ref: rcbRef,
      limit,
    });
    return result || { data: [], total: 0 };
  } catch (error) {
    console.error('Error fetching report data:', error);
    return { data: [], total: 0 };
  }
}

export async function getRcbDetail(channelId: number, rcbRef: string): Promise<RcbInfo | null> {
  try {
    return await requestApi(REPORT_API.DETAIL, 'post', {
      channel_id: channelId,
      rcb_ref: rcbRef,
    });
  } catch (error) {
    console.error('Error fetching RCB detail:', error);
    return null;
  }
}

export async function listActiveReports(channelId: number): Promise<ActiveReport[]> {
  try {
    const result = await requestApi(REPORT_API.ACTIVE, 'post', {
      channel_id: channelId,
    });
    return result?.active_reports || [];
  } catch (error) {
    console.error('Error listing active reports:', error);
    return [];
  }
}
