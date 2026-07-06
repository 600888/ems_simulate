/**
 * 日志查看 API
 */

import { requestApi } from "./http";

export interface LogEntry {
  time: string;
  level: string;
  content: string;
}

export interface LogQueryResponse {
  total: number;
  offset: number;
  limit: number;
  logs: LogEntry[];
}

export interface LogModulesResponse {
  modules: string[];
}

export interface LogDevicesResponse {
  devices: string[];
}

export interface LogErrorCountResponse {
  error_count: number;
}

/**
 * 获取日志模块列表
 */
export async function getLogModules(): Promise<LogModulesResponse> {
  return requestApi("/api/logs/modules", "GET", null);
}

/**
 * 获取有独立日志的设备列表
 */
export async function getLogDevices(): Promise<LogDevicesResponse> {
  return requestApi("/api/logs/devices", "GET", null);
}

/**
 * 查询日志内容
 */
export async function queryLogs(params: {
  module?: string;
  device?: string;
  level?: string;
  offset?: number;
  limit?: number;
  keyword?: string;
}): Promise<LogQueryResponse> {
  const query = new URLSearchParams();
  if (params.module) query.set("module", params.module);
  if (params.device) query.set("device", params.device);
  if (params.level) query.set("level", params.level);
  if (params.offset !== undefined) query.set("offset", String(params.offset));
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  if (params.keyword) query.set("keyword", params.keyword);
  return requestApi(`/api/logs/query?${query.toString()}`, "GET", null);
}

/**
 * 获取错误日志数量
 */
export async function getLogErrorCount(): Promise<LogErrorCountResponse> {
  return requestApi("/api/logs/error-count", "GET", null);
}

/**
 * 重置错误计数（将统计起点设为当前时间）
 */
export async function resetLogErrorCount(): Promise<void> {
  await requestApi("/api/logs/reset-error-count", "POST", null);
}
