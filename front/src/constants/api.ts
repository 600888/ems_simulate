/**
 * API 路径常量
 * 集中管理所有后端 API 路径，避免在各处硬编码
 * 所有接口均使用 POST 方法
 */

// ===== 通道相关 =====
export const CHANNEL_API = {
  PROTOCOLS: "/api/channels/protocols",
  SERIAL_PORTS: "/api/channels/serial-ports",
  CREATE: "/api/channels/create",
  DELETE: "/api/channels/delete",
  LIST: "/api/channels/list",
  DETAIL: "/api/channels/detail",
  UPDATE: "/api/channels/update",
  SECURITY_UPLOAD: "/api/channels/security-upload",
  IMPORT_POINTS: "/api/channels/import-points",
  IMPORT_DLT645_STANDARD_POINTS: "/api/channels/import-dlt645-standard-points",
  IMPORT_ICD: "/api/channels/import-icd",
  PREVIEW_ICD: "/api/channels/preview-icd",
  CREATE_AND_START: "/api/channels/create-and-start",
  RESTART: "/api/channels/restart",
  RELOAD_CONFIG: "/api/channels/reload-config",
  COPY: "/api/channels/copy",
  IEC61850_STRUCTURE: "/api/channels/iec61850-structure",
  IEC61850_READ_POINTS: "/api/channels/iec61850-read-points",
  IEC61850_TABLE_DATA: "/api/channels/iec61850-table-data",
  IEC61850_DO_CHILDREN: "/api/channels/iec61850-do-children",
  IEC61850_DA_CHILDREN: "/api/channels/iec61850-da-children",
  IEC61850_TREE_DATA: "/api/channels/iec61850-tree-data",
  IEC61850_READ_POINT: "/api/channels/iec61850-read-point",
  IEC61850_WRITE_POINT: "/api/channels/iec61850-write-point",
  IEC61850_READ_METADATA: "/api/channels/iec61850-read-metadata",
  IEC61850_DATASET_DETAIL: "/api/channels/iec61850-dataset-detail",
  IEC61850_FILE_DIRECTORY: "/api/channels/iec61850-file-directory",
  IEC61850_FILE_DIRECTORY_TREE: "/api/channels/iec61850-file-directory-tree",
  IEC61850_FILE_DOWNLOAD: "/api/channels/iec61850-file-download",
  IEC61850_FILE_UPLOAD: "/api/channels/iec61850-file-upload",
  IEC61850_FILE_DELETE: "/api/channels/iec61850-file-delete",
  IEC61850_FILE_CACHE_LIST: "/api/channels/iec61850-file-cache-list",
  IEC61850_FILE_CACHE_CLEAR: "/api/channels/iec61850-file-cache-clear",
} as const;

// ===== 设备相关 =====
export const DEVICE_API = {
  LIST: "/api/devices/list",
  INFO: "/api/devices/info",
  START_SIMULATION: "/api/devices/start-simulation",
  STOP_SIMULATION: "/api/devices/stop-simulation",
  START: "/api/devices/start",
  STOP: "/api/devices/stop",
  SLAVE_ID_LIST: "/api/devices/slave-id-list",
  TABLE: "/api/devices/table",
  AUTO_READ_STATUS: "/api/devices/auto-read-status",
  START_AUTO_READ: "/api/devices/start-auto-read",
  STOP_AUTO_READ: "/api/devices/stop-auto-read",
  MANUAL_READ: "/api/devices/manual-read",
  MESSAGES: "/api/devices/messages",
  MESSAGE_DETAIL: "/api/devices/message-detail",
  CLEAR_MESSAGES: "/api/devices/clear-messages",
  AVG_TIME: "/api/devices/avg-time",
  IEC61850_CONNECT_PROGRESS: "/api/devices/iec61850-connect-progress",
  IEC61850_LOAD_MODEL: "/api/devices/iec61850/load_model",
  IEC61850_IMPORT_MODEL: "/api/devices/iec61850/import_model",
  IEC61850_DISCOVER_MODEL: "/api/devices/iec61850/discover-model",
  IEC61850_MODEL_CACHE_STATUS: "/api/devices/iec61850/model-cache-status",
  IEC61850_LOAD_MODEL_FROM_CACHE: "/api/devices/iec61850/load-model-from-cache",
  EXPORT_MODEL: "/api/devices/export-model",
  ADD_SLAVE: "/api/devices/add-slave",
  DELETE_SLAVE: "/api/devices/delete-slave",
  EDIT_SLAVE: "/api/devices/edit-slave",
  IEC104_INTERROGATION: "/api/devices/iec104-interrogation",
  DLT645_COMMAND: "/api/devices/dlt645-command",
} as const;

// ===== 设备组相关 =====
export const DEVICE_GROUP_API = {
  TREE: "/api/device-groups/tree",
  LIST: "/api/device-groups/list",
  ROOT: "/api/device-groups/root",
  UNGROUPED: "/api/device-groups/ungrouped",
  DETAIL: "/api/device-groups/detail",
  DEVICES_IN_GROUP: "/api/device-groups/devices",
  CHILDREN: "/api/device-groups/children",
  CREATE: "/api/device-groups/create",
  UPDATE: "/api/device-groups/update",
  DELETE: "/api/device-groups/delete",
  UPDATE_STATUS: "/api/device-groups/update-status",
  ADD_DEVICE: "/api/device-groups/add-device",
  REMOVE_DEVICE: "/api/device-groups/remove-device",
  MOVE_DEVICES: "/api/device-groups/move-devices",
  BATCH_OPERATION: "/api/device-groups/batch-operation",
} as const;

// ===== 测点相关 =====
export const POINT_API = {
  EDIT_DATA: "/api/points/edit-data",
  EDIT_LIMIT: "/api/points/edit-limit",
  GET_LIMIT: "/api/points/get-limit",
  INFO: "/api/points/info",
  SET_SIMULATE_METHOD: "/api/points/set-simulate-method",
  SET_SIMULATE_STEP: "/api/points/set-simulate-step",
  SET_SIMULATION_RANGE: "/api/points/set-simulation-range",
  EDIT_METADATA: "/api/points/edit-metadata",
  EDIT_IEC104_METADATA: "/api/points/edit-iec104-metadata",
  READ_SINGLE: "/api/points/read-single",
  ADD: "/api/points/add",
  ADD_BATCH: "/api/points/add-batch",
  DELETE: "/api/points/delete",
  CHANGE_HISTORY: "/api/points/change-history",
  SET_CHANGE_TRACKING: "/api/points/set-change-tracking",
  CLEAR_CHANGE_HISTORY: "/api/points/clear-change-history",
  CLEAR_BY_SLAVE: "/api/points/clear-by-slave",
  RESET_DATA: "/api/points/reset-data",
} as const;

// ===== 测点映射相关 =====
export const POINT_MAPPING_API = {
  BASE: "/api/point-mappings",
  LIST: "/api/point-mappings/list",
  CREATE: "/api/point-mappings/create",
  UPDATE: "/api/point-mappings/update",
  DELETE: "/api/point-mappings/delete",
} as const;

// ===== 测点树相关 =====
export const POINT_TREE_API = {
  BASE: "/api/point-tree",
  TREE: "/api/point-tree/tree",
} as const;

// ===== GOOSE 相关 =====
export const GOOSE_API = {
  NETWORK_INTERFACES: "/api/network-interfaces",
  // Publisher
  PUBLISHERS: "/api/channels/goose/publishers",
  PUBLISHERS_LIST: "/api/channels/goose/publishers/list",
  DISCOVERED_LIST: "/api/channels/goose/discovered/list",
  DISCOVERED_IMPORT: "/api/channels/goose/discovered/import",
  PUBLISHER_DETAIL: "/api/channels/goose/publishers/detail",
  PUBLISHER_UPDATE: "/api/channels/goose/publishers/update",
  PUBLISHER_DELETE: "/api/channels/goose/publishers/delete",
  PUBLISHER_START: "/api/channels/goose/publishers/start",
  PUBLISHER_STOP: "/api/channels/goose/publishers/stop",
  PUBLISHER_PUBLISH: "/api/channels/goose/publishers/publish",
  PUBLISHER_ENTRIES_ADD: "/api/channels/goose/publishers/entries/add",
  PUBLISHER_ENTRIES_UPDATE: "/api/channels/goose/publishers/entries/update",
  PUBLISHER_ENTRIES_REMOVE: "/api/channels/goose/publishers/entries/remove",
  PUBLISHER_ENTRIES_REPLACE: "/api/channels/goose/publishers/entries/replace",
  // Receiver
  RECEIVERS: "/api/channels/goose/receivers",
  RECEIVERS_LIST: "/api/channels/goose/receivers/list",
  RECEIVER_DETAIL: "/api/channels/goose/receivers/detail",
  RECEIVER_DELETE: "/api/channels/goose/receivers/delete",
  RECEIVER_UPDATE: "/api/channels/goose/receivers/update",
  RECEIVER_START: "/api/channels/goose/receivers/start",
  RECEIVER_STOP: "/api/channels/goose/receivers/stop",
  RECEIVER_SUBSCRIPTIONS_ADD: "/api/channels/goose/receivers/subscriptions/add",
  RECEIVER_SUBSCRIPTIONS_REMOVE:
    "/api/channels/goose/receivers/subscriptions/remove",
  RECEIVER_SUBSCRIPTIONS_REPLACE:
    "/api/channels/goose/receivers/subscriptions/replace",
  RECEIVER_SUBSCRIPTIONS_UPDATE:
    "/api/channels/goose/receivers/subscriptions/update",
  RECEIVER_SUBSCRIPTIONS_HISTORY:
    "/api/channels/goose/receivers/subscriptions/history",
  // ICD 统一导入使用 /import-icd (channelApi.ts)，含 MMS 测点 + GOOSE 配置
  // GOOSE 报文抓包
  CAPTURE_START: "/api/channels/goose/capture/start",
  CAPTURE_STOP: "/api/channels/goose/capture/stop",
  CAPTURE_LIST: "/api/channels/goose/capture/list",
  CAPTURE_CLEAR: "/api/channels/goose/capture/clear",
  CAPTURE_STATUS: "/api/channels/goose/capture/status",
} as const;

// ===== Reports 相关 =====
export const REPORT_API = {
  LIST: "/api/channels/iec61850/reports/list",
  APPLY: "/api/channels/iec61850/reports/apply",
  BATCH_APPLY: "/api/channels/iec61850/reports/batch-apply",
  GI: "/api/channels/iec61850/reports/gi",
  DATA: "/api/channels/iec61850/reports/data",
  STATE: "/api/channels/iec61850/reports/state",
  LATEST: "/api/channels/iec61850/reports/latest",
  HISTORY: "/api/channels/iec61850/reports/history",
  DATA_TREE: "/api/channels/iec61850/reports/data-tree",
  DETAIL: "/api/channels/iec61850/reports/detail",
  ACTIVE: "/api/channels/iec61850/reports/active",
  REFRESH: "/api/channels/iec61850/reports/refresh",
} as const;

// ===== SCL 文件管理相关 =====
// 后端 API 端点 (FastAPI, RESTful 风格)
export const SCL_API = {
  FILE_LIST: "/api/scl/list", // GET
  FILE_UPLOAD: "/api/scl/upload", // POST (multipart/form-data)
  FILE_DETAIL: "/api/scl/detail", // GET ?filename=
  FILE_DELETE: "/api/scl/delete", // DELETE ?filename=
  FILE_PREVIEW: "/api/scl/preview", // POST (上传临时文件)
  FILE_VALIDATE: "/api/scl/validate", // POST (filename in Form)
  FILE_PARSE: "/api/scl/parse", // POST (filename in Form)
  FILE_IMPORT_POINTS: "/api/scl/import-points", // POST
  FILE_IMPORT_GOOSE: "/api/scl/import-goose", // POST
  FILE_IMPORT_FULL: "/api/scl/import-full", // POST
  FILE_BROWSE_TREE: "/api/scl/browse-tree", // GET ?filename=
  FILE_CONTENT: "/api/scl/content", // GET ?filename=
  FILE_DIFF: "/api/scl/diff", // POST
  FILE_IED_LIST: "/api/scl/ied-list", // GET ?filename=
} as const;

// ===== IEC 61850 图形化建模 =====
export const MODELING_API = {
  PROJECTS: "/api/modeling/projects",
  NODE_KINDS: "/api/modeling/node-kinds",
} as const;
