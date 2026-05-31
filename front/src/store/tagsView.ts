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

// 去重：以 fullPath（含 query）为唯一键，保留每个 key 的最后一次出现
function dedupByPath(views: TagView[]): TagView[] {
    const map = new Map<string, TagView>();
    for (const v of views) {
        const key = v.fullPath || v.path;
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
    // 同时检查 path 和 fullPath，提高匹配可靠性
    const key = view.fullPath || view.path;
    if (visitedViews.value.some(v => (v.fullPath || v.path) === key)) return;
    visitedViews.value.push(
        Object.assign({}, view, {
            title: (view.meta.title as string) || (view.params.deviceName as string) || (view.name as string) || '标签页'
        })
    );
};

export const delView = (view: TagView): Promise<TagView[]> => {
    return new Promise(resolve => {
        const index = visitedViews.value.findIndex(v => (v.fullPath || v.path) === (view.fullPath || view.path));
        if (index > -1) {
            visitedViews.value.splice(index, 1);
        }
        resolve([...visitedViews.value]);
    });
};

export const delOthersViews = (view: TagView): Promise<TagView[]> => {
    return new Promise(resolve => {
        visitedViews.value = visitedViews.value.filter(v => (v.fullPath || v.path) === (view.fullPath || view.path));
        resolve([...visitedViews.value]);
    });
};

export const delAllViews = (): Promise<void> => {
    return new Promise(resolve => {
        visitedViews.value = [];
        resolve();
    });
};
