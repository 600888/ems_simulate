import { requestApi } from './http'

export type StoragePathKey =
  | 'data_directory'
  | 'point_table_cache_directory'
  | 'iec61850_model_cache_directory'
  | 'iec61850_file_cache_directory'
  | 'iec61850_temp_directory'

export type StoragePaths = Record<StoragePathKey, string>

export interface DirectoryStatus {
  exists: boolean
  writable: boolean
}

export interface StorageSettingsData {
  paths: StoragePaths
  defaults: StoragePaths
  status: Record<StoragePathKey, DirectoryStatus>
  changed_fields?: StoragePathKey[]
  restart_required?: boolean
}

const STORAGE_SETTINGS_URL = '/api/settings/storage'

export function getStorageSettings(): Promise<StorageSettingsData> {
  return requestApi(STORAGE_SETTINGS_URL, 'GET', null)
}

export function updateStorageSettings(paths: StoragePaths): Promise<StorageSettingsData> {
  return requestApi(STORAGE_SETTINGS_URL, 'PUT', paths)
}
