import { ref, watch } from "vue";
import type { RouteLocationNormalized } from "vue-router";
import i18n from "@/i18n";

const STORAGE_KEY = "ems_visited_views";

export interface TagView extends Partial<RouteLocationNormalized> {
  title?: string;
}

function loadViews(): TagView[] {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      const parsed = JSON.parse(saved);
      // GOOSE 已改为设备内页面。过滤旧版本持久化的全局 GOOSE 标签，
      // 避免升级后仍显示已经取消的独立入口。
      return Array.isArray(parsed)
        ? parsed.filter(
            (view) => !normalizePath(view?.path).startsWith("/goose"),
          )
        : [];
    }
  } catch {
    // JSON 损坏，清除数据避免持续出错
    localStorage.removeItem(STORAGE_KEY);
  }
  return [];
}

// 规范化路径：统一解码，防止 URI 编码差异导致去重失败
export function normalizePath(p: string | undefined): string {
  if (!p) return "";
  try {
    return decodeURIComponent(p);
  } catch {
    return p;
  }
}

// 去重：以规范化 path 为唯一键，保留每个 key 的最后一次出现
function dedupByPath(views: TagView[]): TagView[] {
  const map = new Map<string, TagView>();
  for (const v of views) {
    const key = normalizePath(v.path);
    if (key) {
      map.set(key, v);
    }
  }
  return Array.from(map.values());
}

export const visitedViews = ref<TagView[]>(dedupByPath(loadViews()));

// 监听变化自动持久化
watch(
  visitedViews,
  (val) => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(val));
  },
  { deep: true },
);

export const addView = (view: RouteLocationNormalized) => {
  const path = view.path;
  const rawTitle = view.meta.title as string;
  const title =
    (rawTitle ? i18n.global.t(rawTitle) : "") ||
    (view.params.deviceName as string) ||
    (view.name as string) ||
    i18n.global.t("layout.tagsView.fallbackTitle");
  const tab: TagView = {
    path,
    query: view.query,
    params: view.params,
    fullPath: view.fullPath,
    name: view.name,
    meta: view.meta,
    title,
  };

  const normalizedPath = normalizePath(path);
  const idx = visitedViews.value.findIndex(
    (v) => normalizePath(v.path) === normalizedPath,
  );
  if (idx > -1) {
    // 已存在：原地更新，保持标签位置。用新数组引用确保 Vue 响应式可靠触发
    const newViews = [...visitedViews.value];
    newViews[idx] = tab;
    visitedViews.value = newViews;
    return;
  }
  // 未找到：新增
  visitedViews.value = [...visitedViews.value, tab];
};

export const delView = (view: TagView): Promise<TagView[]> => {
  return new Promise((resolve) => {
    const normalizedPath = normalizePath(view.path);
    const index = visitedViews.value.findIndex(
      (v) => normalizePath(v.path) === normalizedPath,
    );
    if (index > -1) {
      visitedViews.value.splice(index, 1);
    }
    resolve([...visitedViews.value]);
  });
};

export const delOthersViews = (view: TagView): Promise<TagView[]> => {
  return new Promise((resolve) => {
    const normalizedPath = normalizePath(view.path);
    visitedViews.value = visitedViews.value.filter(
      (v) => normalizePath(v.path) === normalizedPath,
    );
    resolve([...visitedViews.value]);
  });
};

export const delAllViews = (): Promise<void> => {
  return new Promise((resolve) => {
    visitedViews.value = [];
    resolve();
  });
};

// channelId -> deviceName 映射，用于 GOOSE/报告/文件页面高亮对应的设备标签
const channelIdDeviceMap = new Map<number, string>();

export function updateChannelIdDeviceMap(
  channelId: number,
  deviceName: string,
) {
  channelIdDeviceMap.set(channelId, deviceName);
}

export function getDeviceNameByChannelId(
  channelId: number,
): string | undefined {
  return channelIdDeviceMap.get(channelId);
}
