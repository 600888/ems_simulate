import { ref, watch } from "vue";
import type { LocaleType } from "@/i18n";

const ZOOM_KEY = "app-zoom";
const LOCALE_KEY = "app-locale";

// 缩放范围：50% ~ 150%，步长 5%
export const ZOOM_MIN = 50;
export const ZOOM_MAX = 150;
export const ZOOM_STEP = 5;
export const ZOOM_DEFAULT = 100;

export const zoomLevel = ref<number>(
  Number(localStorage.getItem(ZOOM_KEY)) || ZOOM_DEFAULT,
);

export const currentLocale = ref<LocaleType>(
  (localStorage.getItem(LOCALE_KEY) as LocaleType) || "zh-CN",
);

export type LayoutMode = "small" | "medium" | "large";
export const effectiveViewportWidth = ref(window.innerWidth);
export const layoutMode = ref<LayoutMode>("large");

function updateResponsiveLayout(factor: number) {
  const width = window.innerWidth / factor;
  effectiveViewportWidth.value = width;
  layoutMode.value = width < 1200 ? "small" : width < 1400 ? "medium" : "large";

  document.body.classList.remove(
    "layout-small",
    "layout-medium",
    "layout-large",
  );
  document.body.classList.add(`layout-${layoutMode.value}`);

  const rootStyle = document.documentElement.style;
  if (layoutMode.value === "small") {
    rootStyle.setProperty("--header-height", "40px");
    rootStyle.setProperty("--sidebar-width", "64px");
    rootStyle.setProperty("--tags-height", "30px");
    rootStyle.setProperty("--footer-height", "24px");
  } else if (layoutMode.value === "medium") {
    rootStyle.setProperty("--header-height", "44px");
    rootStyle.setProperty("--sidebar-width", "260px");
    rootStyle.setProperty("--tags-height", "32px");
    rootStyle.setProperty("--footer-height", "28px");
  } else {
    rootStyle.setProperty("--header-height", "48px");
    rootStyle.setProperty("--sidebar-width", "280px");
    rootStyle.setProperty("--tags-height", "34px");
    rootStyle.setProperty("--footer-height", "32px");
  }
}

/** 设置缩放级别并持久化 */
export function setZoom(val: number) {
  zoomLevel.value = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, val));
  localStorage.setItem(ZOOM_KEY, String(zoomLevel.value));
}

/** 设置语言并持久化 */
export function setLocale(locale: LocaleType) {
  currentLocale.value = locale;
  localStorage.setItem(LOCALE_KEY, locale);
}

/** 应用缩放：transform scale + 尺寸补偿，始终保持内容填满视口，不溢出不留空 */
function applyZoom(val: number) {
  const factor = val / 100;
  updateResponsiveLayout(factor);
  const wrapper = document.querySelector(
    ".theme-wrapper",
  ) as HTMLElement | null;
  if (!wrapper) return;

  if (factor === 1) {
    // 正常
    wrapper.style.transform = "none";
    wrapper.style.width = "";
    wrapper.style.height = "";
    return;
  }

  // 缩小或放大：用 transform scale + 反比例补偿容器尺寸
  // 使得缩放后的内容始终精确填满 100vw x 100vh 视口
  wrapper.style.transformOrigin = "top left";
  wrapper.style.transform = `scale(${factor})`;
  wrapper.style.width = `${100 / factor}vw`;
  wrapper.style.height = `${100 / factor}vh`;
}

export function refreshZoomLayout() {
  applyZoom(zoomLevel.value);
}

/** 监听缩放变化 */
watch(zoomLevel, applyZoom, { immediate: true });
window.addEventListener("resize", refreshZoomLayout);

export function useAppSettings() {
  return {
    zoomLevel,
    currentLocale,
    setZoom,
    setLocale,
    ZOOM_MIN,
    ZOOM_MAX,
    ZOOM_STEP,
    ZOOM_DEFAULT,
  };
}
