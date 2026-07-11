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
  channel_id: number;
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
  name?: string;
  fc?: string;
  description?: string;
  previous_value?: boolean | number | string | null;
  changed?: boolean;
  changed_at?: number;
}

export interface GooseDataSetMember {
  name: string;
  fc?: string;
  type?: string;
  description?: string;
}

/** GOOSE 订阅状态 */
export interface GooseSubscriptionStatus {
  go_cb_ref: string;
  app_id: number | null;
  go_id: string;
  data_set_ref: string;
  conf_rev: number;
  received_conf_rev: number;
  config_mismatch: boolean;
  st_num: number;
  sq_num: number;
  time_allowed_to_live: number;
  timestamp: number;
  state: 'init' | 'connected' | 'lost' | 'error';
  last_update: number;
  description: string;
  dst_mac: string;
  data_values: GooseSubscriptionDataValue[];
  enabled: boolean;
  ied_name: string;
  ld_inst: string;
  ln_name: string;
  dataset_entries: GooseDataSetMember[];
  message_count: number;
  last_change: number;
}

export interface GooseMessageHistoryItem {
  received_at: number;
  timestamp: number;
  st_num: number;
  sq_num: number;
  conf_rev: number;
  data_set_ref: string;
  value_count: number;
  changed_count: number;
  data_values: GooseSubscriptionDataValue[];
}

/** GOOSE Receiver 状态 */
export interface GooseReceiverStatus {
  id: string;
  channel_id: number;
  name: string;
  description: string;
  auto_start: boolean;
  interface: string;
  is_running: boolean;
  subscription_count: number;
  subscriptions: GooseSubscriptionStatus[];
}

/** 创建 Publisher 请求 */
export interface GoosePublisherCreateRequest {
  channel_id: number;
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
  channel_id: number;
  interface?: string;
  go_cb_ref?: string;
  go_id?: string;
  data_set_ref?: string;
  app_id?: number;
  conf_rev?: number;
  time_allowed_to_live?: number;
  simulation?: boolean;
  dst_mac?: number[] | null;
  vlan_id?: number;
  vlan_prio?: number;
}

/** 创建数据集条目请求 */
export interface GooseEntryAddRequest {
  publisher_id: string;
  entry: { name: string; value: boolean | number | string; iec_type: string };
}

/** 创建 Receiver 请求 */
export interface GooseReceiverCreateRequest {
  channel_id: number;
  interface: string;
  name?: string;
  description?: string;
  auto_start?: boolean;
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
  data_set_ref?: string;
  conf_rev?: number;
  enabled?: boolean;
  ied_name?: string;
  ld_inst?: string;
  ln_name?: string;
  dataset_entries?: GooseDataSetMember[];
}

export interface GooseSubscriptionUpdateRequest extends Omit<GooseSubscriptionCreateRequest, 'go_cb_ref'> {
  new_go_cb_ref?: string;
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
  detail_status?: 'complete' | 'partial';
  discovery_error_code?: number | null;
  discovery_error?: string;
  attempted_refs?: string[];
}

export interface NetworkInterfaceInfo {
  id: string;
  name: string;
  display_name: string;
  mac: string;
  ipv4: string[];
  is_up: boolean;
  is_loopback: boolean;
  supports_raw_ethernet: boolean;
}

export async function getGooseNetworkInterfaces(): Promise<NetworkInterfaceInfo[]> {
  const data = await requestApi(GOOSE_API.NETWORK_INTERFACES, 'get', null);
  return data?.items || [];
}

export async function replaceGooseSubscriptions(
  channelId: number,
  receiverId: string,
  subscriptions: GooseSubscriptionCreateRequest[],
): Promise<GooseReceiverStatus | null> {
  return await requestApi(GOOSE_API.RECEIVER_SUBSCRIPTIONS_REPLACE, 'post', {
    channel_id: channelId,
    receiver_id: receiverId,
    subscriptions,
  });
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
export async function getGoosePublishers(channelId: number): Promise<GoosePublisherStatus[]> {
  const data = await requestApi(GOOSE_API.PUBLISHERS_LIST, 'post', { channel_id: channelId });
  return data?.items || [];
}

/** 获取指定 GOOSE Publisher 状态 */
export async function getGoosePublisher(channelId: number, publisherId: string): Promise<GoosePublisherStatus | null> {
  return await requestApi(GOOSE_API.PUBLISHER_DETAIL, 'post', { channel_id: channelId, publisher_id: publisherId });
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
export async function deleteGoosePublisher(channelId: number, publisherId: string): Promise<boolean> {
  const data = await requestApi(GOOSE_API.PUBLISHER_DELETE, 'post', { channel_id: channelId, publisher_id: publisherId });
  return data !== null;
}

/** 启动 GOOSE Publisher */
export async function startGoosePublisher(channelId: number, publisherId: string): Promise<boolean> {
  const data = await requestApi(GOOSE_API.PUBLISHER_START, 'post', { channel_id: channelId, publisher_id: publisherId });
  return data !== null;
}

/** 停止 GOOSE Publisher */
export async function stopGoosePublisher(channelId: number, publisherId: string): Promise<boolean> {
  const data = await requestApi(GOOSE_API.PUBLISHER_STOP, 'post', { channel_id: channelId, publisher_id: publisherId });
  return data !== null;
}

/** 立即发布 GOOSE 报文 */
export async function publishGooseNow(channelId: number, publisherId: string): Promise<boolean> {
  const data = await requestApi(GOOSE_API.PUBLISHER_PUBLISH, 'post', { channel_id: channelId, publisher_id: publisherId });
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

export async function replaceGoosePublisherEntries(
  channelId: number,
  publisherId: string,
  entries: { name: string; value: boolean | number | string; iec_type: string }[],
): Promise<GoosePublisherStatus | null> {
  return await requestApi(GOOSE_API.PUBLISHER_ENTRIES_REPLACE, 'post', {
    channel_id: channelId,
    publisher_id: publisherId,
    entries,
  });
}

// ===== Receiver API =====

/** 获取所有 GOOSE Receiver 列表 */
export async function getGooseReceivers(channelId: number): Promise<GooseReceiverStatus[]> {
  const data = await requestApi(GOOSE_API.RECEIVERS_LIST, 'post', { channel_id: channelId });
  return data?.items || [];
}

/** 获取指定 GOOSE Receiver 状态 */
export async function getGooseReceiver(channelId: number, receiverId: string): Promise<GooseReceiverStatus | null> {
  return await requestApi(GOOSE_API.RECEIVER_DETAIL, 'post', { channel_id: channelId, receiver_id: receiverId });
}

/** 创建 GOOSE Receiver */
export async function createGooseReceiver(req: GooseReceiverCreateRequest): Promise<GooseReceiverStatus | null> {
  return await requestApi(GOOSE_API.RECEIVERS, 'post', req);
}

export async function updateGooseReceiver(
  channelId: number,
  receiverId: string,
  req: { interface: string; name: string; description: string; auto_start: boolean },
): Promise<GooseReceiverStatus | null> {
  return await requestApi(GOOSE_API.RECEIVER_UPDATE, 'post', {
    channel_id: channelId,
    receiver_id: receiverId,
    ...req,
  });
}

/** 删除 GOOSE Receiver */
export async function deleteGooseReceiver(channelId: number, receiverId: string): Promise<boolean> {
  const data = await requestApi(GOOSE_API.RECEIVER_DELETE, 'post', { channel_id: channelId, receiver_id: receiverId });
  return data !== null;
}

/** 启动 GOOSE Receiver */
export async function startGooseReceiver(channelId: number, receiverId: string): Promise<boolean> {
  const data = await requestApi(GOOSE_API.RECEIVER_START, 'post', { channel_id: channelId, receiver_id: receiverId });
  return data !== null;
}

/** 停止 GOOSE Receiver */
export async function stopGooseReceiver(channelId: number, receiverId: string): Promise<boolean> {
  const data = await requestApi(GOOSE_API.RECEIVER_STOP, 'post', { channel_id: channelId, receiver_id: receiverId });
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

export async function updateGooseSubscription(
  channelId: number,
  receiverId: string,
  goCbRef: string,
  req: GooseSubscriptionUpdateRequest,
): Promise<GooseReceiverStatus | null> {
  return await requestApi(GOOSE_API.RECEIVER_SUBSCRIPTIONS_UPDATE, 'post', {
    channel_id: channelId,
    receiver_id: receiverId,
    go_cb_ref: goCbRef,
    ...req,
  });
}

export async function getGooseSubscriptionHistory(
  channelId: number,
  receiverId: string,
  goCbRef: string,
  limit = 100,
): Promise<GooseMessageHistoryItem[]> {
  const data = await requestApi(GOOSE_API.RECEIVER_SUBSCRIPTIONS_HISTORY, 'post', {
    channel_id: channelId,
    receiver_id: receiverId,
    go_cb_ref: goCbRef,
    limit,
  });
  return data?.items || [];
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
  channel_id: number;
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
export async function stopGooseCapture(channelId: number): Promise<boolean> {
  const data = await requestApi(GOOSE_API.CAPTURE_STOP, 'post', { channel_id: channelId });
  return data !== null;
}

/** 获取捕获的 GOOSE 报文列表 */
export async function getGooseCapturedPackets(
  channelId: number,
  count?: number,
  filterAppId?: number | null,
): Promise<{
  packets: GooseCapturedPacket[];
  statistics: GooseCaptureStatistics;
  status: GooseCaptureStatus;
}> {
  const data = await requestApi(GOOSE_API.CAPTURE_LIST, 'post', {
    channel_id: channelId,
    count: count || 0,
    filter_app_id: filterAppId ?? null,
  });
  return data || { packets: [], statistics: {} as GooseCaptureStatistics, status: {} as GooseCaptureStatus };
}

/** 清空捕获的报文 */
export async function clearGooseCapturedPackets(channelId: number): Promise<boolean> {
  const data = await requestApi(GOOSE_API.CAPTURE_CLEAR, 'post', { channel_id: channelId });
  return data !== null;
}

/** 获取抓包状态 */
export async function getGooseCaptureStatus(channelId: number): Promise<{ captures: GooseCaptureStatus[] }> {
  const data = await requestApi(GOOSE_API.CAPTURE_STATUS, 'post', { channel_id: channelId });
  return data || { captures: [] };
}
