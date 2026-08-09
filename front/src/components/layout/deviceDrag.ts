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
  const types = e.dataTransfer?.types;
  const typesArr = types ? Array.from(types) : [];
  if (typesArr.length > 0) {
    // types 可用时先校验 MIME：外部拖拽（文件/文本等）即使命中残留缓存也直接拒绝
    if (!typesArr.includes(DEVICE_DRAG_MIME)) return null;
    // 本应用拖拽：dragover 阶段部分浏览器（如 Firefox）getData 受限，优先使用缓存
    if (currentPayload) return currentPayload;
    try {
      const raw = e.dataTransfer?.getData(DEVICE_DRAG_MIME);
      return raw ? (JSON.parse(raw) as DeviceDragPayload) : null;
    } catch {
      return null;
    }
  }
  // types 为空（个别浏览器 dragover 场景）：信任带 TTL 的缓存
  if (currentPayload && Date.now() - payloadTimestamp < PAYLOAD_TTL_MS) {
    return currentPayload;
  }
  return null;
}

/** dragstart 时调用：写入 dataTransfer 并缓存 payload */
export function setDragPayload(e: DragEvent, payload: DeviceDragPayload): void {
  currentPayload = payload;
  payloadTimestamp = Date.now();
  e.dataTransfer?.setData(DEVICE_DRAG_MIME, JSON.stringify(payload));
  e.dataTransfer!.effectAllowed = "move";
}

/** dragend / drop 后调用：清空缓存 */
export function clearDragPayload(): void {
  currentPayload = null;
}
