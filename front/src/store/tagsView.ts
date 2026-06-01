import { ref, watch } from 'vue';
import type { RouteLocationNormalized } from 'vue-router';

const STORAGE_KEY = 'ems_visited_views';

export interface TagView extends Partial<RouteLocationNormalized> {
    title?: string;
}

function loadViews(): TagView[] {
    try {
        const saved = localStorage.getItem(STORAGE_KEY);
        if (saved) {
            return JSON.parse(saved);
        }
    } catch {
        // ignore
    }
    return [];
}

// 去重：以 path 为唯一键（不含 query），保留每个 key 的最后一次出现
function dedupByPath(views: TagView[]): TagView[] {
    const map = new Map<string, TagView>();
    for (const v of views) {
        const key = v.path;
        if (key) {
            map.set(key, v);
        }
    }
    return Array.from(map.values());
}

export const visitedViews = ref<TagView[]>(dedupByPath(loadViews()));

// 监听变化自动持久化
watch(visitedViews, (val) => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(val));
}, { deep: true });

export const addView = (view: RouteLocationNormalized) => {
    // 以 path 作为唯一键去重，避免因 query 参数差异导致同一设备打开多个标签
    const key = view.path;
    if (visitedViews.value.some(v => v.path === key)) return;
    visitedViews.value.push(
        Object.assign({}, view, {
            title: (view.meta.title as string) || (view.params.deviceName as string) || (view.name as string) || '标签页'
        })
    );
};

export const delView = (view: TagView): Promise<TagView[]> => {
    return new Promise(resolve => {
        const index = visitedViews.value.findIndex(v => v.path === view.path);
        if (index > -1) {
            visitedViews.value.splice(index, 1);
        }
        resolve([...visitedViews.value]);
    });
};

export const delOthersViews = (view: TagView): Promise<TagView[]> => {
    return new Promise(resolve => {
        visitedViews.value = visitedViews.value.filter(v => v.path === view.path);
        resolve([...visitedViews.value]);
    });
};

export const delAllViews = (): Promise<void> => {
    return new Promise(resolve => {
        visitedViews.value = [];
        resolve();
    });
};

// channelId -> deviceName 映射，用于报告/文件页面高亮对应的设备标签
const channelIdDeviceMap = new Map<number, string>();

export function updateChannelIdDeviceMap(channelId: number, deviceName: string) {
    channelIdDeviceMap.set(channelId, deviceName);
}

export function getDeviceNameByChannelId(channelId: number): string | undefined {
    return channelIdDeviceMap.get(channelId);
}
