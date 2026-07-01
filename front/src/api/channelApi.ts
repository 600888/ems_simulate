/**
 * 通道管理 API
 */

import { instance, requestApi } from './http';
import { CHANNEL_API } from '@/constants';
import type {
  ChannelCreateRequest,
  ChannelInfo,
  PointImportResult,
  ProtocolConfigResponse,
} from '@/types/channel';

// ===== 类型定义 =====

export interface CopyDeviceResult {
  channel_id: number;
  device_id: number;
  name: string;
  code: string;
  ip: string;
}

export interface CopyDeviceResponse {
  copied_count: number;
  devices: CopyDeviceResult[];
}

export interface CopyDeviceRequest {
  channel_id: number;
  count: number;
  prefix?: string;
  suffix?: string;
  ip_start_offset: number;
  port_offset?: number;
}

export interface IEC61850DataSetInfo {
  ref: string;
  name: string;
  ld: string;
  member_count: number;
}

export interface IEC61850DataSetMember {
  ref: string;
  fc: string;
  iec_type: string;
  index?: number;
  value?: any;
}

export interface IEC61850DataSetDetail {
  ref: string;
  name: string;
  ld: string;
  member_count: number;
  members: IEC61850DataSetMember[];
}

export interface IEC61850DataSetTreeItem extends IEC61850DataSetInfo {
  ln?: string;
}

export interface IEC61850DataSetLnItem {
  name: string;
  datasets: IEC61850DataSetTreeItem[];
}

export interface IEC61850DataSetLdItem {
  name: string;
  children: IEC61850DataSetLnItem[];
}

export interface IEC61850DataModelItem {
  name: string;
  children: string[];
}

export interface IEC61850Structure {
  GOOSE: string[];
  Reports: string[];
  SettingGroups: string[];
  Files: string[];
  DataSets: IEC61850DataSetLdItem[];
  DataModel: IEC61850DataModelItem[];
}

export interface IEC61850TableDataResponse {
  total: number;
  head_data: string[];
  table_data: any[][];
  category: string;
  item: string;
}

export interface IEC61850DoItem {
  name: string;
  frame_type: number | null;
}

export interface IEC61850DaItem {
  name: string;
  path: string;
  fc: string;
  type: string;
  mms_type?: string;
}

// ===== IEC 61850 树形数据类型 =====

export interface IEC61850BdaItem {
  bda_name: string;
  bda_path: string;
  fc: string;
  point_code: string;
  mms_type?: string;
  value: string;
  status: string;
  read_time?: string;
}

export interface IEC61850DaNode {
  da_name: string;
  da_path: string;
  fc: string;
  is_struct: boolean;
  point_code: string;
  mms_type?: string;
  point_name: string;
  value: string;
  status: string;
  read_time?: string;
  children: IEC61850BdaItem[];
}

export interface IEC61850DoNode {
  do_name: string;
  do_ref: string;
  ld: string;
  ln: string;
  du_name: string;
  fc: string;
  frame_type: number;
  mms_type?: string;
  value?: string;
  status?: string;
  children: IEC61850DaNode[];
}

export interface IEC61850TreeDataResponse {
  items: IEC61850DoNode[];
  total: number;
}

// ===== API 函数 =====

export async function getProtocolConfig(): Promise<ProtocolConfigResponse> {
  try {
    return await requestApi(CHANNEL_API.PROTOCOLS, 'post', null);
  } catch (error) {
    console.error('Error fetching protocol config:', error);
    throw error;
  }
}

export async function getSerialPorts(): Promise<Array<{ device: string; description: string }>> {
  try {
    return await requestApi(CHANNEL_API.SERIAL_PORTS, 'post', null);
  } catch (error) {
    console.error('Error fetching serial ports:', error);
    throw error;
  }
}

export async function createChannel(channel: ChannelCreateRequest): Promise<{ channel_id: number }> {
  try {
    return await requestApi(CHANNEL_API.CREATE, 'post', channel, 30000);
  } catch (error) {
    console.error('Error creating channel:', error);
    throw error;
  }
}

export async function importPoints(channelId: number, file: File): Promise<PointImportResult> {
  try {
    const formData = new FormData();
    formData.append('channel_id', channelId.toString());
    formData.append('file', file);
    const response = await instance.post(CHANNEL_API.IMPORT_POINTS, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data.data;
  } catch (error) {
    console.error('Error importing points:', error);
    throw error;
  }
}

/** 预览 ICD/SCD/CID 文件（只解析不保存） */
export async function previewIcd(
  file: File,
  interfaceName: string = 'eth0',
): Promise<PointImportResult> {
  try {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('interface', interfaceName);
    const response = await instance.post(CHANNEL_API.PREVIEW_ICD, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 60000,
    });
    return response.data.data;
  } catch (error) {
    console.error('Error previewing ICD file:', error);
    throw error;
  }
}

export async function importIcdPoints(
  channelId: number,
  file: File,
  interfaceName: string = 'eth0',
  autoCreateGoose: boolean = false,
): Promise<PointImportResult> {
  try {
    const formData = new FormData();
    formData.append('channel_id', channelId.toString());
    formData.append('file', file);
    formData.append('interface', interfaceName);
    formData.append('auto_create_goose', autoCreateGoose.toString());
    const response = await instance.post(CHANNEL_API.IMPORT_ICD, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 60000,
    });
    return response.data.data;
  } catch (error) {
    console.error('Error importing ICD file:', error);
    throw error;
  }
}

export async function createAndStartDevice(channelId: number): Promise<{ device_name: string }> {
  try {
    return await requestApi(CHANNEL_API.CREATE_AND_START, 'post', { channel_id: channelId }, 30000);
  } catch (error) {
    console.error('Error creating and starting device:', error);
    throw error;
  }
}

export async function deleteChannel(channelId: number): Promise<boolean> {
  try {
    return await requestApi(CHANNEL_API.DELETE, 'post', { channel_id: channelId });
  } catch (error) {
    console.error('Error deleting channel:', error);
    throw error;
  }
}

export async function getChannelList(): Promise<ChannelInfo[]> {
  try {
    return await requestApi(CHANNEL_API.LIST, 'post', null);
  } catch (error) {
    console.error('Error fetching channel list:', error);
    throw error;
  }
}

export async function getChannel(channelId: number): Promise<ChannelInfo> {
  try {
    return await requestApi(CHANNEL_API.DETAIL, 'post', { channel_id: channelId });
  } catch (error) {
    console.error('Error fetching channel:', error);
    throw error;
  }
}

export async function updateChannel(channelId: number, channel: Partial<ChannelCreateRequest>): Promise<boolean> {
  try {
    return await requestApi(CHANNEL_API.UPDATE, 'post', { channel_id: channelId, ...channel }, 30000);
  } catch (error) {
    console.error('Error updating channel:', error);
    throw error;
  }
}

export async function restartDevice(channelId: number): Promise<{ device_name: string }> {
  try {
    return await requestApi(CHANNEL_API.RESTART, 'post', { channel_id: channelId }, 30000);
  } catch (error) {
    console.error('Error restarting device:', error);
    throw error;
  }
}

export async function reloadDeviceConfig(channelId: number): Promise<{ device_name: string }> {
  try {
    return await requestApi(CHANNEL_API.RELOAD_CONFIG, 'post', { channel_id: channelId }, 30000);
  } catch (error) {
    console.error('Error reloading device config:', error);
    throw error;
  }
}

export async function copyDevice(request: CopyDeviceRequest): Promise<CopyDeviceResponse> {
  try {
    return await requestApi(CHANNEL_API.COPY, 'post', request);
  } catch (error) {
    console.error('Error copying device:', error);
    throw error;
  }
}

export async function getIEC61850Structure(channelId: number): Promise<IEC61850Structure> {
  try {
    return await requestApi(CHANNEL_API.IEC61850_STRUCTURE, 'post', { channel_id: channelId });
  } catch (error) {
    console.error('Error fetching IEC61850 structure:', error);
    throw error;
  }
}

export async function iec61850ReadPoints(
  channelId: number,
  category: string = '',
  item: string = '',
  intervalMs: number = 0,
): Promise<{ success: number; fail: number } | null> {
  try {
    return await requestApi(CHANNEL_API.IEC61850_READ_POINTS, 'post', {
      channel_id: channelId,
      category,
      item,
      interval_ms: intervalMs,
    });
  } catch (error) {
    console.error('Error reading IEC61850 points:', error);
    throw error;
  }
}

export async function getIEC61850TableData(
  channelId: number,
  category: string = '',
  item: string = '',
  pointName: string | null = null,
  pageIndex: number = 1,
  pageSize: number = 10,
  pointTypes: number[] = [],
): Promise<Map<string, any>> {
  try {
    const data = await requestApi(CHANNEL_API.IEC61850_TABLE_DATA, 'post', {
      channel_id: channelId,
      category,
      item,
      point_name: pointName,
      page_index: pageIndex,
      page_size: pageSize,
      point_types: pointTypes.length > 0 ? pointTypes.join(',') : '',
    });
    return new Map<string, any>(Object.entries(data));
  } catch (error) {
    console.error('Error fetching IEC61850 table data:', error);
    throw error;
  }
}

export async function getIEC61850DoChildren(
  channelId: number,
  ld: string,
  ln: string,
): Promise<IEC61850DoItem[]> {
  try {
    const data = await requestApi(CHANNEL_API.IEC61850_DO_CHILDREN, 'post', {
      channel_id: channelId, ld, ln,
    });
    return data?.items || [];
  } catch (error) {
    console.error('Error fetching IEC61850 DO children:', error);
    return [];
  }
}

export async function getIEC61850DaChildren(
  channelId: number,
  ld: string,
  ln: string,
  doName: string,
): Promise<IEC61850DaItem[]> {
  try {
    const data = await requestApi(CHANNEL_API.IEC61850_DA_CHILDREN, 'post', {
      channel_id: channelId, ld, ln, do_name: doName,
    });
    return data?.items || [];
  } catch (error) {
    console.error('Error fetching IEC61850 DA children:', error);
    return [];
  }
}

export async function getIEC61850TreeData(
  channelId: number,
  category: string = '',
  item: string = '',
  pointName: string | null = null,
  pointTypes: number[] = [],
  pageIndex: number = 1,
  pageSize: number = 10,
): Promise<IEC61850TreeDataResponse | null> {
  try {
    const data = await requestApi(CHANNEL_API.IEC61850_TREE_DATA, 'post', {
      channel_id: channelId,
      category,
      item,
      point_name: pointName,
      point_types: pointTypes.length > 0 ? pointTypes.join(',') : '',
      page_index: pageIndex,
      page_size: pageSize,
    });
    return data;
  } catch (error) {
    console.error('Error fetching IEC61850 tree data:', error);
    return null;
  }
}

export async function iec61850ReadPoint(
  channelId: number,
  pointCode: string,
): Promise<{ value: number | null; point_code: string; mms_type: string } | null> {
  try {
    return await requestApi(CHANNEL_API.IEC61850_READ_POINT, 'post', {
      channel_id: channelId,
      point_code: pointCode,
    });
  } catch (error) {
    console.error('Error reading IEC61850 point:', error);
    throw error;
  }
}

export interface Iec61850MetadataResponse {
  point_code: string
  quality: {
    validity: number | null
    detailQuality: number | null
    source: number | null
    operatorBlocked: boolean | null
    test: boolean | null
  }
  timestamp: {
    seconds: number | null
    fraction: number | null
    timeAccuracy: number | null
    leapSecondsKnown: boolean | null
    clockFailure: boolean | null
    clockNotSynchronized: boolean | null
    unixTimestampMs: number | null
  }
}

export async function iec61850ReadPointMetadata(
  channelId: number,
  pointCode: string,
): Promise<Iec61850MetadataResponse | null> {
  try {
    return await requestApi(CHANNEL_API.IEC61850_READ_METADATA, 'post', {
      channel_id: channelId,
      point_code: pointCode,
    });
  } catch (error) {
    console.error('Error reading IEC61850 point metadata:', error);
    throw error;
  }
}

export async function iec61850WritePoint(
  channelId: number,
  pointCode: string,
  pointValue: number | string,
): Promise<{ point_code: string; value: number | string } | null> {
  try {
    return await requestApi(CHANNEL_API.IEC61850_WRITE_POINT, 'post', {
      channel_id: channelId,
      point_code: pointCode,
      point_value: pointValue,
    });
  } catch (error) {
    console.error('Error writing IEC61850 point:', error);
    throw error;
  }
}

export async function getIEC61850DatasetDetail(
  channelId: number,
  datasetRef: string,
): Promise<IEC61850DataSetDetail | null> {
  try {
    return await requestApi(CHANNEL_API.IEC61850_DATASET_DETAIL, 'post', {
      channel_id: channelId,
      dataset_ref: datasetRef,
    });
  } catch (error) {
    console.error('Error fetching IEC61850 dataset detail:', error);
    throw error;
  }
}

// ===== IEC 61850 文件服务类型 =====

export interface FileEntry {
  name: string;
  type: 'file' | 'directory';
  size: number;
  size_human: string;
  last_modified: string | null;
  full_path: string;
}

export interface FileDownloadResult {
  filename: string;
  data: string;  // Base64 编码
  size: number;
  cached: boolean;
}

export interface FileCacheEntry {
  remote_path: string;
  local_path: string;
  file_size: number;
  remote_modified: string | null;
  download_time: string | null;
  checksum: string | null;
}

// ===== IEC 61850 文件服务 API =====

export async function getFileDirectory(
  channelId: number,
  directory: string = '',
): Promise<{ directory: string; entries: FileEntry[]; total: number } | null> {
  try {
    return await requestApi(CHANNEL_API.IEC61850_FILE_DIRECTORY, 'post', {
      channel_id: channelId,
      directory,
    });
  } catch (error) {
    console.error('Error fetching file directory:', error);
    return null;
  }
}

export async function getFileDirectoryTree(
  channelId: number,
  directory: string = '',
  maxDepth: number = 5,
): Promise<{ directory: string; entries: FileEntry[]; total: number } | null> {
  try {
    return await requestApi(CHANNEL_API.IEC61850_FILE_DIRECTORY_TREE, 'post', {
      channel_id: channelId,
      directory,
      max_depth: maxDepth,
    });
  } catch (error) {
    console.error('Error fetching file directory tree:', error);
    return null;
  }
}

export async function downloadRemoteFile(
  channelId: number,
  filename: string,
  useCache: boolean = true,
): Promise<FileDownloadResult | null> {
  try {
    return await requestApi(CHANNEL_API.IEC61850_FILE_DOWNLOAD, 'post', {
      channel_id: channelId,
      filename,
      use_cache: useCache,
      return_format: 'json',
    });
  } catch (error) {
    console.error('Error downloading remote file:', error);
    return null;
  }
}

export async function uploadRemoteFile(
  channelId: number,
  remoteFilename: string,
  fileData: string,  // Base64 编码
): Promise<boolean> {
  try {
    const result = await requestApi(CHANNEL_API.IEC61850_FILE_UPLOAD, 'post', {
      channel_id: channelId,
      remote_filename: remoteFilename,
      file_data: fileData,
    });
    return result !== null;
  } catch (error) {
    console.error('Error uploading remote file:', error);
    return false;
  }
}

export async function deleteRemoteFile(
  channelId: number,
  filename: string,
): Promise<boolean> {
  try {
    const result = await requestApi(CHANNEL_API.IEC61850_FILE_DELETE, 'post', {
      channel_id: channelId,
      filename,
    });
    return result !== null;
  } catch (error) {
    console.error('Error deleting remote file:', error);
    return false;
  }
}

export async function getFileCacheList(
  channelId: number,
): Promise<FileCacheEntry[]> {
  try {
    const data = await requestApi(CHANNEL_API.IEC61850_FILE_CACHE_LIST, 'post', {
      channel_id: channelId,
    });
    return data?.files || [];
  } catch (error) {
    console.error('Error fetching file cache list:', error);
    return [];
  }
}

export async function clearFileCache(
  channelId: number,
  remotePath: string = '',
): Promise<number> {
  try {
    const data = await requestApi(CHANNEL_API.IEC61850_FILE_CACHE_CLEAR, 'post', {
      channel_id: channelId,
      remote_path: remotePath,
    });
    return data?.cleared || 0;
  } catch (error) {
    console.error('Error clearing file cache:', error);
    return 0;
  }
}
