/**
 * GOOSE 管理 API
 * IEC 61850 GOOSE Publisher / Receiver / Subscriber 管理接口
 * 所有接口使用 POST 方法，参数放在 JSON body 中
 */

import { requestApi } from './http';
import { GOOSE_API } from '@/constants';

// ===== 类型定义 =====

/** GOOSE 数据集条目 */
export interface GooseDataSetEntry {
  index: number;
  name: string;
  value: boolean | number | string;
  iec_type: string;
}

/** GOOSE Publisher 状态 */
export interface GoosePublisherStatus {
  id: string;
  go_cb_ref: string;
  go_id: string;
  data_set_ref: string;
  app_id: number;
  conf_rev: number;
  st_num: number;
  sq_num: number;
  time_allowed_to_live: number;
  interface: string;
  simulation: boolean;
  is_running: boolean;
  dst_mac: string;
  vlan_id: number;
  vlan_prio: number;
  entry_count: number;
  entries: GooseDataSetEntry[];
}

/** GOOSE 订阅数据值 */
export interface GooseSubscriptionDataValue {
  index: number;
  type: string;
  value: boolean | number | string | null;
}

/** GOOSE 订阅状态 */
export interface GooseSubscriptionStatus {
  go_cb_ref: string;
  app_id: number | null;
  go_id: string;
  data_set_ref: string;
  conf_rev: number;
  st_num: number;
  sq_num: number;
  time_allowed_to_live: number;
  timestamp: number;
  state: 'init' | 'connected' | 'lost' | 'error';
  last_update: number;
  description: string;
  dst_mac: string;
  data_values: GooseSubscriptionDataValue[];
}

/** GOOSE Receiver 状态 */
export interface GooseReceiverStatus {
  id: string;
  interface: string;
  is_running: boolean;
  subscription_count: number;
  subscriptions: GooseSubscriptionStatus[];
}

/** 创建 Publisher 请求 */
export interface GoosePublisherCreateRequest {
  interface: string;
  go_cb_ref: string;
  go_id?: string;
  data_set_ref?: string;
  app_id?: number;
  conf_rev?: number;
  time_allowed_to_live?: number;
  dst_mac?: number[] | null;
  vlan_id?: number;
  vlan_prio?: number;
  simulation?: boolean;
  entries?: { name: string; value: boolean | number | string; iec_type: string }[];
}

/** 更新 Publisher 请求 */
export interface GoosePublisherUpdateRequest {
  go_id?: string;
  conf_rev?: number;
  time_allowed_to_live?: number;
  simulation?: boolean;
}

/** 创建数据集条目请求 */
export interface GooseEntryAddRequest {
  publisher_id: string;
  entry: { name: string; value: boolean | number | string; iec_type: string };
}

/** 创建 Receiver 请求 */
export interface GooseReceiverCreateRequest {
  interface: string;
  subscriptions?: {
    go_cb_ref: string;
    app_id?: number | null;
    dst_mac?: number[] | null;
    description?: string;
  }[];
}

/** 创建订阅请求 */
export interface GooseSubscriptionCreateRequest {
  go_cb_ref: string;
  app_id?: number | null;
  dst_mac?: number[] | null;
  description?: string;
}

/** 发现的远端 GOOSE 控制块 */
export interface DiscoveredGooseItem {
  go_cb_ref: string;
  go_id: string;
  app_id: number | null;
  data_set_ref: string;
  conf_rev: number;
  name: string;
  ld_inst: string;
}

/** 获取客户端发现的远端 GOOSE 控制块列表 */
export async function getDiscoveredGoose(channelId: number): Promise<DiscoveredGooseItem[]> {
  const data = await requestApi(GOOSE_API.DISCOVERED_LIST, 'post', { channel_id: channelId });
  return data?.items || [];
}

/** 将发现的远端 GOOSE 控制块导入为 Receiver 订阅 */
export async function importDiscoveredGoose(
  channelId: number,
  iface = 'eth0',
): Promise<{ imported: number; receiver: GooseReceiverStatus | null }> {
  const data = await requestApi(GOOSE_API.DISCOVERED_IMPORT, 'post', {
    channel_id: channelId,
    interface: iface,
  });
  return data || { imported: 0, receiver: null };
}

// ===== Publisher API =====

/** 获取所有 GOOSE Publisher 列表 */
export async function getGoosePublishers(): Promise<GoosePublisherStatus[]> {
  const data = await requestApi(GOOSE_API.PUBLISHERS_LIST, 'post', null);
  return data?.items || [];
}

/** 获取指定 GOOSE Publisher 状态 */
export async function getGoosePublisher(publisherId: string): Promise<GoosePublisherStatus | null> {
  return await requestApi(GOOSE_API.PUBLISHER_DETAIL, 'post', { publisher_id: publisherId });
}

/** 创建 GOOSE Publisher */
export async function createGoosePublisher(req: GoosePublisherCreateRequest): Promise<GoosePublisherStatus | null> {
  return await requestApi(GOOSE_API.PUBLISHERS, 'post', req);
}

/** 更新 GOOSE Publisher */
export async function updateGoosePublisher(
  publisherId: string,
  req: GoosePublisherUpdateRequest,
): Promise<GoosePublisherStatus | null> {
  return await requestApi(GOOSE_API.PUBLISHER_UPDATE, 'post', { publisher_id: publisherId, ...req });
}

/** 删除 GOOSE Publisher */
export async function deleteGoosePublisher(publisherId: string): Promise<boolean> {
  const data = await requestApi(GOOSE_API.PUBLISHER_DELETE, 'post', { publisher_id: publisherId });
  return data !== null;
}

/** 启动 GOOSE Publisher */
export async function startGoosePublisher(publisherId: string): Promise<boolean> {
  const data = await requestApi(GOOSE_API.PUBLISHER_START, 'post', { publisher_id: publisherId });
  return data !== null;
}

/** 停止 GOOSE Publisher */
export async function stopGoosePublisher(publisherId: string): Promise<boolean> {
  const data = await requestApi(GOOSE_API.PUBLISHER_STOP, 'post', { publisher_id: publisherId });
  return data !== null;
}

/** 立即发布 GOOSE 报文 */
export async function publishGooseNow(publisherId: string): Promise<boolean> {
  const data = await requestApi(GOOSE_API.PUBLISHER_PUBLISH, 'post', { publisher_id: publisherId });
  return data !== null;
}

// ===== Publisher Entry API =====

/** 添加数据集条目 */
export async function addGoosePublisherEntry(
  publisherId: string,
  name: string,
  value: boolean | number | string,
  iec_type: string,
): Promise<any> {
  return await requestApi(GOOSE_API.PUBLISHER_ENTRIES_ADD, 'post', {
    publisher_id: publisherId,
    entry: { name, value, iec_type },
  });
}

/** 更新数据集条目 */
export async function updateGoosePublisherEntry(
  publisherId: string,
  entryIndex: number,
  value: boolean | number | string,
): Promise<any> {
  return await requestApi(GOOSE_API.PUBLISHER_ENTRIES_UPDATE, 'post', {
    publisher_id: publisherId,
    index: entryIndex,
    value,
  });
}

/** 删除数据集条目 */
export async function deleteGoosePublisherEntry(
  publisherId: string,
  entryIndex: number,
): Promise<boolean> {
  const data = await requestApi(GOOSE_API.PUBLISHER_ENTRIES_REMOVE, 'post', { publisher_id: publisherId, index: entryIndex });
  return data !== null;
}

// ===== Receiver API =====

/** 获取所有 GOOSE Receiver 列表 */
export async function getGooseReceivers(): Promise<GooseReceiverStatus[]> {
  const data = await requestApi(GOOSE_API.RECEIVERS_LIST, 'post', null);
  return data?.items || [];
}

/** 获取指定 GOOSE Receiver 状态 */
export async function getGooseReceiver(receiverId: string): Promise<GooseReceiverStatus | null> {
  return await requestApi(GOOSE_API.RECEIVER_DETAIL, 'post', { receiver_id: receiverId });
}

/** 创建 GOOSE Receiver */
export async function createGooseReceiver(req: GooseReceiverCreateRequest): Promise<GooseReceiverStatus | null> {
  return await requestApi(GOOSE_API.RECEIVERS, 'post', req);
}

/** 删除 GOOSE Receiver */
export async function deleteGooseReceiver(receiverId: string): Promise<boolean> {
  const data = await requestApi(GOOSE_API.RECEIVER_DELETE, 'post', { receiver_id: receiverId });
  return data !== null;
}

/** 启动 GOOSE Receiver */
export async function startGooseReceiver(receiverId: string): Promise<boolean> {
  const data = await requestApi(GOOSE_API.RECEIVER_START, 'post', { receiver_id: receiverId });
  return data !== null;
}

/** 停止 GOOSE Receiver */
export async function stopGooseReceiver(receiverId: string): Promise<boolean> {
  const data = await requestApi(GOOSE_API.RECEIVER_STOP, 'post', { receiver_id: receiverId });
  return data !== null;
}

// ===== Receiver Subscription API =====

/** 添加订阅 */
export async function addGooseSubscription(
  receiverId: string,
  req: GooseSubscriptionCreateRequest,
): Promise<GooseSubscriptionStatus | null> {
  return await requestApi(GOOSE_API.RECEIVER_SUBSCRIPTIONS_ADD, 'post', { receiver_id: receiverId, ...req });
}

/** 移除订阅 */
export async function removeGooseSubscription(
  receiverId: string,
  goCbRef: string,
): Promise<boolean> {
  const data = await requestApi(GOOSE_API.RECEIVER_SUBSCRIPTIONS_REMOVE, 'post', { receiver_id: receiverId, go_cb_ref: goCbRef });
  return data !== null;
}



// ===== ICD 导入 =====
// ICD 文件统一导入在 /import-icd (channelApi.ts)，含 MMS 测点 + GOOSE 配置
// 创建/编辑 IEC61850 设备时通过 AddDeviceDialog 的 ICD 上传功能导入

// ===== GOOSE 报文抓包类型定义 =====

/** GOOSE 捕获的数据值 */
export interface GooseCapturedDataValue {
  type: string;
  value: boolean | number | string | null;
}

/** GOOSE 捕获的报文 */
export interface GooseCapturedPacket {
  src_mac: string;
  dst_mac: string;
  timestamp: number;
  time: string;
  length: number;
  app_id: number;
  app_id_hex: string;
  go_cb_ref: string;
  go_id: string;
  data_set_ref: string;
  st_num: number;
  sq_num: number;
  time_allowed_to_live: number;
  conf_rev: number;
  simulation: boolean;
  nds_com: boolean;
  num_dat_set_entries: number;
  vlan_id: number;
  vlan_prio: number;
  has_vlan: boolean;
  data_values: GooseCapturedDataValue[];
  hex_data: string;
  hex_string: string;
}

/** GOOSE 捕获统计 */
export interface GooseCaptureStatistics {
  is_running: boolean;
  total_captured: number;
  buffer_size: number;
  max_buffer_size: number;
  interface: string;
  app_ids: { app_id: number; app_id_hex: string; count: number }[];
  go_cb_refs: { go_cb_ref: string; count: number }[];
}

/** GOOSE 捕获状态 */
export interface GooseCaptureStatus {
  interface: string;
  is_running: boolean;
  max_packets: number;
  packet_count: number;
  filter_app_id: number | null;
  filter_go_cb_ref: string;
}

/** 启动抓包请求 */
export interface GooseCaptureStartRequest {
  interface?: string;
  max_packets?: number;
  filter_app_id?: number | null;
}

// ===== GOOSE 报文抓包 API =====

/** 启动 GOOSE 报文抓包 */
export async function startGooseCapture(req: GooseCaptureStartRequest): Promise<boolean> {
  const data = await requestApi(GOOSE_API.CAPTURE_START, 'post', req);
  return data !== null;
}

/** 停止 GOOSE 报文抓包 */
export async function stopGooseCapture(): Promise<boolean> {
  const data = await requestApi(GOOSE_API.CAPTURE_STOP, 'post', {});
  return data !== null;
}

/** 获取捕获的 GOOSE 报文列表 */
export async function getGooseCapturedPackets(
  count?: number,
  filterAppId?: number | null,
): Promise<{
  packets: GooseCapturedPacket[];
  statistics: GooseCaptureStatistics;
  status: GooseCaptureStatus;
}> {
  const data = await requestApi(GOOSE_API.CAPTURE_LIST, 'post', {
    count: count || 0,
    filter_app_id: filterAppId ?? null,
  });
  return data || { packets: [], statistics: {} as GooseCaptureStatistics, status: {} as GooseCaptureStatus };
}

/** 清空捕获的报文 */
export async function clearGooseCapturedPackets(): Promise<boolean> {
  const data = await requestApi(GOOSE_API.CAPTURE_CLEAR, 'post', {});
  return data !== null;
}

/** 获取抓包状态 */
export async function getGooseCaptureStatus(): Promise<{ captures: GooseCaptureStatus[] }> {
  const data = await requestApi(GOOSE_API.CAPTURE_STATUS, 'post', {});
  return data || { captures: [] };
}
