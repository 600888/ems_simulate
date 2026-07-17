/**
 * 应用通用常量
 */

// 数据刷新间隔（毫秒）
export const TABLE_REFRESH_INTERVAL = 1000;

// HTTP 请求超时时间（毫秒）
export const HTTP_TIMEOUT = 5000;
// IEC61850 DataSet 批量读取前端接口等待时间
export const HTTP_TIMEOUT_IEC61850_DATASET_READ = 10000;
// IEC61850 报告批量操作前端接口等待时间。大型模型可能包含数百个 RCB，
// 每个都需要独立的 MMS 读写与订阅注册，不能沿用 30 秒短超时。
export const HTTP_TIMEOUT_IEC61850_REPORT_BATCH = 120000;
// 文件上传/ICD解析等耗时操作单独设置超时
export const HTTP_TIMEOUT_LONG = 60000;
// 后端发现任务默认上限为 10 分钟，额外预留 10 秒用于响应编码与传输。
export const HTTP_TIMEOUT_MODEL_DISCOVERY = 610000;

// 错误消息去重间隔（毫秒）
export const ERROR_DEBOUNCE_MS = 3000;

// 默认分页大小
export const DEFAULT_PAGE_SIZE = 10;

// 从机地址范围
export const SLAVE_ADDR_MIN = 0;
export const SLAVE_ADDR_MAX = 255;

// 端口范围
export const PORT_MIN = 1;
export const PORT_MAX = 65535;

// ========================================
// 断点常量（用于 JS 侧判断当前窗口尺寸）
// 与 breakpoints.scss 保持同步
// ========================================
export const BREAKPOINTS = {
  small: 960,
  medium: 1200,
  large: 1400,
} as const;

// 侧边栏宽度（CSS 变量驱动，此处仅作参考常量）
// 实际渲染值由 --sidebar-width CSS 变量在不同断点下动态覆盖
// large: 280px / medium: 260px / small: 64px (自动折叠 overlay 模式)
export const SIDEBAR_WIDTH = "280px";
export const SIDEBAR_COLLAPSED_WIDTH = "64px";
export const SIDEBAR_MEDIUM_WIDTH = "260px";

// 侧边栏本地存储 Key
export const LS_KEY_COLLAPSE = "isCollapse";
export const LS_KEY_ACTIVE_ROUTE = "activeRoute";
export const LS_KEY_THEME = "sidebar-theme";

// 报文捕获默认限制
export const MESSAGE_DEFAULT_LIMIT = 100;

// 读取进度相关
export const READ_PROGRESS_DELAY = 1500; // 读取完成后延迟清除进度
export const SINGLE_READ_PROGRESS_DELAY = 2000;

// WebSocket 重连间隔（毫秒）
export const WS_RECONNECT_INTERVAL = 3000;
