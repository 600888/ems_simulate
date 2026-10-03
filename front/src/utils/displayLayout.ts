export const RESOLUTION_PRESETS = [
  { id: "1280x720", width: 1280, height: 720 },
  { id: "1366x768", width: 1366, height: 768 },
  { id: "1440x900", width: 1440, height: 900 },
  { id: "1600x900", width: 1600, height: 900 },
  { id: "1920x1080", width: 1920, height: 1080 },
  { id: "2560x1440", width: 2560, height: 1440 },
  { id: "3840x2160", width: 3840, height: 2160 },
] as const;

export type ResolutionPreset = (typeof RESOLUTION_PRESETS)[number];
export type ResolutionMode = "auto" | "custom" | ResolutionPreset["id"];
export type LayoutMode = "small" | "medium" | "large";

export const ZOOM_MIN = 50;
export const ZOOM_MAX = 150;
export const ZOOM_STEP = 5;
export const ZOOM_DEFAULT = 100;

export function normalizeZoom(value: number): number {
  return Number.isFinite(value) && value > 0
    ? Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, Math.round(value)))
    : ZOOM_DEFAULT;
}

export function normalizeResolutionMode(value: string | null): ResolutionMode {
  if (value === "custom" || RESOLUTION_PRESETS.some(({ id }) => id === value)) {
    return value as ResolutionMode;
  }
  return "auto";
}

/** 保留至少 1600 × 900 的布局空间，小屏按比例缩小，大屏保持自然字号。 */
export function recommendResolution(
  width: number,
  height: number,
): ResolutionPreset {
  let recommended: ResolutionPreset = RESOLUTION_PRESETS[3];
  for (const preset of RESOLUTION_PRESETS.slice(4)) {
    if (preset.width <= width && preset.height <= height) recommended = preset;
  }
  return recommended;
}

export function calculateFitZoom(
  width: number,
  height: number,
  resolution: ResolutionPreset,
): number {
  // 向下取整，避免舍入后超出所选参考尺寸；50% 以下交给响应式布局处理。
  return normalizeZoom(
    Math.max(
      ZOOM_MIN,
      Math.floor(
        Math.min(1, width / resolution.width, height / resolution.height) * 100,
      ),
    ),
  );
}

export function getLayoutMode(width: number): LayoutMode {
  return width < 1200 ? "small" : width < 1400 ? "medium" : "large";
}
