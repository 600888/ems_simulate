import { computed, ref, watch } from "vue";
import type { LocaleType } from "@/i18n";
import {
  RESOLUTION_PRESETS,
  ZOOM_DEFAULT,
  ZOOM_MAX,
  ZOOM_MIN,
  ZOOM_STEP,
  calculateFitZoom,
  getLayoutMode,
  normalizeResolutionMode,
  normalizeZoom,
  recommendResolution,
  type LayoutMode,
  type ResolutionMode,
} from "@/utils/displayLayout";

export { RESOLUTION_PRESETS, ZOOM_DEFAULT, ZOOM_MAX, ZOOM_MIN, ZOOM_STEP };
export type { LayoutMode, ResolutionMode };

const ZOOM_KEY = "app-zoom";
const LOCALE_KEY = "app-locale";
const RESOLUTION_KEY = "app-resolution";

function readSetting(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function saveSetting(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* 禁用存储时仍可使用设置。 */
  }
}

const customZoom = ref(normalizeZoom(Number(readSetting(ZOOM_KEY))));
// 首次升级默认启用自动适配；旧缩放值保留供“自定义”模式使用。
export const resolutionMode = ref<ResolutionMode>(
  normalizeResolutionMode(readSetting(RESOLUTION_KEY)),
);
export const currentLocale = ref<LocaleType>(
  readSetting(LOCALE_KEY) === "en-US" ? "en-US" : "zh-CN",
);

function readBrowserDisplay() {
  const pixelRatio = window.devicePixelRatio || 1;
  return {
    screenWidth: window.screen.width || window.innerWidth,
    screenHeight: window.screen.height || window.innerHeight,
    availableWidth: window.screen.availWidth || window.innerWidth,
    availableHeight: window.screen.availHeight || window.innerHeight,
    physicalWidth: Math.round(
      (window.screen.width || window.innerWidth) * pixelRatio,
    ),
    physicalHeight: Math.round(
      (window.screen.height || window.innerHeight) * pixelRatio,
    ),
    viewportWidth: window.innerWidth,
    viewportHeight: window.innerHeight,
    pixelRatio,
    native: false,
  };
}

export const displayInfo = ref(readBrowserDisplay());
export const recommendedResolution = computed(() =>
  recommendResolution(
    Math.min(displayInfo.value.availableWidth, displayInfo.value.viewportWidth),
    Math.min(
      displayInfo.value.availableHeight,
      displayInfo.value.viewportHeight,
    ),
  ),
);
export const activeResolution = computed(
  () =>
    RESOLUTION_PRESETS.find(({ id }) => id === resolutionMode.value) ??
    recommendedResolution.value,
);
export const zoomLevel = computed(() =>
  resolutionMode.value === "custom"
    ? customZoom.value
    : calculateFitZoom(
        displayInfo.value.viewportWidth,
        displayInfo.value.viewportHeight,
        activeResolution.value,
      ),
);
export const effectiveViewportWidth = computed(
  () => displayInfo.value.viewportWidth / (zoomLevel.value / 100),
);
export const effectiveViewportHeight = computed(
  () => displayInfo.value.viewportHeight / (zoomLevel.value / 100),
);
export const layoutMode = computed<LayoutMode>(() =>
  getLayoutMode(effectiveViewportWidth.value),
);

export function setResolutionMode(value: ResolutionMode) {
  resolutionMode.value = normalizeResolutionMode(value);
  saveSetting(RESOLUTION_KEY, resolutionMode.value);
}

/** 手动调整缩放时切换为自定义，保留手动设置，不被窗口变化覆盖。 */
export function setZoom(value: number | number[]) {
  if (typeof value !== "number") return;
  customZoom.value = normalizeZoom(value);
  saveSetting(ZOOM_KEY, String(customZoom.value));
  setResolutionMode("custom");
}

export function setLocale(locale: LocaleType) {
  currentLocale.value = locale;
  saveSetting(LOCALE_KEY, locale);
}

function applyZoom() {
  const rootStyle = document.documentElement.style;
  const factor = zoomLevel.value / 100;
  // 在根节点统一缩放，teleport 到 body 的弹窗、下拉框与主界面使用同一坐标系。
  rootStyle.setProperty("zoom", String(factor));
  rootStyle.setProperty(
    "--app-viewport-width",
    `${effectiveViewportWidth.value}px`,
  );
  rootStyle.setProperty(
    "--app-viewport-height",
    `${effectiveViewportHeight.value}px`,
  );
  rootStyle.width = `${effectiveViewportWidth.value}px`;
  rootStyle.height = `${effectiveViewportHeight.value}px`;
  document.body.classList.remove(
    "layout-small",
    "layout-medium",
    "layout-large",
  );
  document.body.classList.add(`layout-${layoutMode.value}`);
  const sizes =
    layoutMode.value === "small"
      ? [40, 64, 30, 24]
      : layoutMode.value === "medium"
        ? [44, 260, 32, 28]
        : [48, 280, 34, 32];
  [
    "--header-height",
    "--sidebar-width",
    "--tags-height",
    "--footer-height",
  ].forEach((key, index) => rootStyle.setProperty(key, `${sizes[index]}px`));
}

export function refreshZoomLayout() {
  const previous = displayInfo.value;
  const browser = readBrowserDisplay();
  displayInfo.value = previous.native
    ? {
        ...previous,
        viewportWidth: browser.viewportWidth,
        viewportHeight: browser.viewportHeight,
      }
    : browser;
  applyZoom();
}

watch([zoomLevel, effectiveViewportWidth, effectiveViewportHeight], applyZoom, {
  flush: "sync",
});

/** 跟随窗口、DPI 和所在显示器变化；卸载时清理全部事件监听。 */
export function initializeDisplaySettings(): () => void {
  let disposed = false;
  let requestId = 0;
  let resizeFrame = 0;
  const unlisteners: Array<() => void> = [];

  const refreshMonitor = async () => {
    if (
      !(window as Window & { __TAURI_INTERNALS__?: unknown })
        .__TAURI_INTERNALS__
    )
      return;
    const id = ++requestId;
    try {
      const { currentMonitor } = await import("@tauri-apps/api/window");
      const monitor = await currentMonitor();
      if (disposed || id !== requestId) return;
      if (!monitor) {
        displayInfo.value = readBrowserDisplay();
        applyZoom();
        return;
      }
      const ratio = monitor.scaleFactor || 1;
      displayInfo.value = {
        ...readBrowserDisplay(),
        screenWidth: Math.round(monitor.size.width / ratio),
        screenHeight: Math.round(monitor.size.height / ratio),
        availableWidth: Math.round(monitor.workArea.size.width / ratio),
        availableHeight: Math.round(monitor.workArea.size.height / ratio),
        physicalWidth: monitor.size.width,
        physicalHeight: monitor.size.height,
        pixelRatio: ratio,
        native: true,
      };
      applyZoom();
    } catch {
      // 浏览器模式或原生显示器接口不可用时使用浏览器信息。
      if (!disposed && id === requestId) {
        displayInfo.value = readBrowserDisplay();
        applyZoom();
      }
    }
  };

  const onResize = () => {
    cancelAnimationFrame(resizeFrame);
    resizeFrame = requestAnimationFrame(() => {
      refreshZoomLayout();
      void refreshMonitor();
    });
  };
  const onFocus = () => {
    refreshZoomLayout();
    void refreshMonitor();
  };
  window.addEventListener("resize", onResize);
  window.addEventListener("focus", onFocus);
  // DPR 改变有时不会触发 resize（尤其是切换同尺寸、不同缩放的显示器）。
  let dpiQuery: MediaQueryList | undefined;
  const onDpiChange = () => {
    dpiQuery?.removeEventListener("change", onDpiChange);
    dpiQuery = window.matchMedia(
      `(resolution: ${window.devicePixelRatio || 1}dppx)`,
    );
    dpiQuery.addEventListener("change", onDpiChange);
    onFocus();
  };
  onDpiChange();

  if (
    (window as Window & { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__
  ) {
    void import("@tauri-apps/api/window")
      .then(async ({ getCurrentWindow }) => {
        for (const subscribe of [
          () => getCurrentWindow().onMoved(onResize),
          () => getCurrentWindow().onScaleChanged(onFocus),
        ]) {
          try {
            const unlisten = await subscribe();
            if (disposed) unlisten();
            else unlisteners.push(unlisten);
          } catch {
            /* 浏览器检测仍然有效。 */
          }
        }
      })
      .catch(() => {});
  }

  return () => {
    disposed = true;
    ++requestId;
    cancelAnimationFrame(resizeFrame);
    window.removeEventListener("resize", onResize);
    window.removeEventListener("focus", onFocus);
    dpiQuery?.removeEventListener("change", onDpiChange);
    unlisteners.forEach((unlisten) => unlisten());
  };
}

export function useAppSettings() {
  return {
    zoomLevel,
    currentLocale,
    resolutionMode,
    displayInfo,
    recommendedResolution,
    setZoom,
    setLocale,
    setResolutionMode,
    ZOOM_MIN,
    ZOOM_MAX,
    ZOOM_STEP,
    ZOOM_DEFAULT,
    RESOLUTION_PRESETS,
  };
}
