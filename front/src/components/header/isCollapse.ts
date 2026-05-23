import { ref } from "vue";

export const isCollapse = ref(false);

// small 断点 (< 1200px) 下侧边栏 overlay 弹出模式
export const sidebarOverlayMode = ref(false);

// 关闭 overlay 模式（点击遮罩或导航后调用）
export function closeSidebarOverlay() {
  sidebarOverlayMode.value = false;
}