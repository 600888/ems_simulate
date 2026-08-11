/**
 * 侧边栏设备组树 / 未分组区域的拖拽工具
 *
 * 拖拽内容分为两类：
 *  - device：设备节点，可拖入某个分组（移入分组）或未分组区域（移出分组）
 *  - group：分组节点，可拖到其他分组下（调整层级）或未分组区域（提升为顶级分组）
 */

export const DEVICE_DRAG_MIME = "application/x-ems-device-drag";

export interface DeviceDragPayload {
  type: "device" | "group";
  id: number;
  name?: string;
  /** 设备当前所在分组 id（type=device 时有效），null 表示未分组 */
  groupId?: number | null;
}

/** 最近一次 dragstart 写入的 payload，供 dragover/drop 读取（部分浏览器 dragover 中 getData 受限） */
let currentPayload: DeviceDragPayload | null = null;
let payloadTimestamp = 0;
/** 缓存兜底过期时间：拖拽会话应很快结束（dragend 时清除），TTL 仅防御异常情况下残留 */
const PAYLOAD_TTL_MS = 60_000;

/** 从拖拽事件读取 payload；非本应用发起的拖拽返回 null */
export function readDragPayload(e: DragEvent): DeviceDragPayload | null {
  // 在 TTL 窗口内无条件信任 dragstart 写入的缓存：
  //  - Tauri WebView2 的 dragover 阶段 dataTransfer.types 为空或不可靠，
  //    按 types 校验会误判为外部拖拽，导致 preventDefault 不执行、显示禁用光标；
  //  - 缓存仅在 dragstart 时写入，dragend/drop 时清除，残留概率极低，
  //    外部拖拽（文件等）时缓存必然为 null，不会误触发。
  if (currentPayload && Date.now() - payloadTimestamp < PAYLOAD_TTL_MS) {
    return currentPayload;
  }
  // 缓存过期后的兜底：尝试从 dataTransfer 直接读取
  try {
    const raw = e.dataTransfer?.getData(DEVICE_DRAG_MIME);
    return raw ? (JSON.parse(raw) as DeviceDragPayload) : null;
  } catch {
    return null;
  }
}

/** dragstart 时调用：写入 dataTransfer 并缓存 payload */
export function setDragPayload(e: DragEvent, payload: DeviceDragPayload): void {
  if (!e.dataTransfer) return;
  currentPayload = payload;
  payloadTimestamp = Date.now();
  e.dataTransfer.setData(DEVICE_DRAG_MIME, JSON.stringify(payload));
  e.dataTransfer.effectAllowed = "move";
}

/** dragend / drop 后调用：清空缓存 */
export function clearDragPayload(): void {
  currentPayload = null;
}
