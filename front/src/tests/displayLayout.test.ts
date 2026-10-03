/// <reference types="jest" />
import {
  calculateFitZoom,
  getLayoutMode,
  normalizeResolutionMode,
  normalizeZoom,
  recommendResolution,
  RESOLUTION_PRESETS,
} from "@/utils/displayLayout";

describe("resolution fitting", () => {
  it.each([
    [1280, 720, 80],
    [1366, 768, 85],
    [960, 600, 60],
    [1536, 864, 96],
  ])(
    "fits a %i × %i window to a usable desktop layout at %i%%",
    (width, height, zoom) => {
      const preset = recommendResolution(width, height);
      expect(preset.id).toBe("1600x900");
      expect(calculateFitZoom(width, height, preset)).toBe(zoom);
      expect(width / (zoom / 100)).toBeGreaterThanOrEqual(preset.width);
      expect(height / (zoom / 100)).toBeGreaterThanOrEqual(preset.height);
    },
  );

  it("uses both dimensions and keeps native text size on large displays", () => {
    expect(recommendResolution(1920, 1080).id).toBe("1920x1080");
    expect(recommendResolution(2560, 1440).id).toBe("2560x1440");
    expect(recommendResolution(3840, 2160).id).toBe("3840x2160");
    expect(recommendResolution(2560, 800).id).toBe("1600x900");
    expect(calculateFitZoom(3840, 2160, RESOLUTION_PRESETS[6])).toBe(100);
  });

  it("allows a manual reference resolution and limits extreme shrinking", () => {
    expect(calculateFitZoom(1280, 720, RESOLUTION_PRESETS[4])).toBe(66);
    expect(calculateFitZoom(1280, 720, RESOLUTION_PRESETS[0])).toBe(100);
    expect(calculateFitZoom(600, 400, RESOLUTION_PRESETS[6])).toBe(50);
    expect(getLayoutMode(600 / 0.5)).toBe("medium");
    expect(getLayoutMode(599 / 0.5)).toBe("small");
  });

  it("recovers from invalid stored settings", () => {
    expect(normalizeResolutionMode("bogus")).toBe("auto");
    expect(normalizeResolutionMode(null)).toBe("auto");
    expect(normalizeResolutionMode("1920x1080")).toBe("1920x1080");
    expect(normalizeZoom(NaN)).toBe(100);
    expect(normalizeZoom(Infinity)).toBe(100);
    expect(normalizeZoom(-100)).toBe(100);
    expect(normalizeZoom(300)).toBe(150);
  });
});

describe("display settings integration", () => {
  let storage: Map<string, string>;
  let screenWindow: Record<string, any>;
  let styles: Map<string, string>;
  let listeners: Map<string, () => void>;

  beforeEach(() => {
    jest.resetModules();
    jest.dontMock("@tauri-apps/api/window");
    storage = new Map();
    styles = new Map();
    listeners = new Map();
    screenWindow = {
      innerWidth: 1280,
      innerHeight: 720,
      devicePixelRatio: 2,
      screen: {
        width: 1920,
        height: 1080,
        availWidth: 1920,
        availHeight: 1040,
      },
      addEventListener: jest.fn((event, callback) =>
        listeners.set(event, callback),
      ),
      removeEventListener: jest.fn((event) => listeners.delete(event)),
      matchMedia: jest.fn(() => ({
        addEventListener: jest.fn(),
        removeEventListener: jest.fn(),
      })),
    };
    Object.assign(globalThis, {
      window: screenWindow,
      localStorage: {
        getItem: (key: string) => storage.get(key) ?? null,
        setItem: (key: string, value: string) => storage.set(key, value),
      },
      document: {
        createElement: () => ({}),
        documentElement: {
          style: {
            setProperty: (key: string, value: string) => styles.set(key, value),
          },
        },
        body: { classList: { remove: jest.fn(), add: jest.fn() } },
      },
      requestAnimationFrame: (callback: () => void) => {
        callback();
        return 1;
      },
      cancelAnimationFrame: jest.fn(),
    });
  });

  function settings(): typeof import("@/composables/useAppSettings") {
    return jest.requireActual("@/composables/useAppSettings");
  }

  it("distinguishes high DPI pixel resolution from window layout space", () => {
    const app = settings();
    const stop = app.initializeDisplaySettings();
    expect(app.displayInfo.value.physicalWidth).toBe(3840);
    expect(app.displayInfo.value.pixelRatio).toBe(2);
    expect(app.zoomLevel.value).toBe(80);
    expect(styles.get("--app-viewport-width")).toBe("1600px");
    expect(styles.get("zoom")).toBe("0.8");
    stop();
    expect(listeners.size).toBe(0);
  });

  it("updates auto fitting on resize and preserves custom zoom", () => {
    const app = settings();
    const stop = app.initializeDisplaySettings();
    screenWindow.innerWidth = 960;
    screenWindow.innerHeight = 600;
    listeners.get("resize")?.();
    expect(app.zoomLevel.value).toBe(60);
    app.setZoom(110);
    expect(storage.get("app-resolution")).toBe("custom");
    expect(storage.get("app-zoom")).toBe("110");
    screenWindow.innerWidth = 1366;
    listeners.get("resize")?.();
    expect(app.zoomLevel.value).toBe(110);
    app.setResolutionMode("auto");
    expect(app.zoomLevel.value).toBe(66);
    stop();
  });

  it("restores a selected resolution and falls back when storage is blocked", () => {
    storage.set("app-resolution", "1920x1080");
    const app = settings();
    expect(app.resolutionMode.value).toBe("1920x1080");
    expect(app.zoomLevel.value).toBe(66);
    Object.assign(globalThis, {
      localStorage: {
        getItem: () => {
          throw Error("blocked");
        },
        setItem: () => {
          throw Error("blocked");
        },
      },
    });
    jest.resetModules();
    const blocked = settings();
    expect(blocked.resolutionMode.value).toBe("auto");
    expect(() => blocked.setZoom(90)).not.toThrow();
  });

  it("reads native monitor pixels and follows moves to another DPI", async () => {
    screenWindow.__TAURI_INTERNALS__ = {};
    let moved: (() => void) | undefined;
    const unlisten = jest.fn();
    const currentMonitor = jest.fn().mockResolvedValue({
      size: { width: 3840, height: 2160 },
      workArea: { size: { width: 3840, height: 2080 } },
      scaleFactor: 2,
    });
    jest.doMock("@tauri-apps/api/window", () => ({
      currentMonitor,
      getCurrentWindow: () => ({
        onMoved: async (callback: () => void) => {
          moved = callback;
          return unlisten;
        },
        onScaleChanged: async () => unlisten,
      }),
    }));
    const flush = async () => {
      for (let i = 0; i < 10; i++) await Promise.resolve();
    };
    const app = settings();
    const stop = app.initializeDisplaySettings();
    await flush();
    expect(app.displayInfo.value.native).toBe(true);
    expect(app.displayInfo.value.physicalWidth).toBe(3840);
    expect(app.displayInfo.value.availableWidth).toBe(1920);
    expect(app.zoomLevel.value).toBe(80);

    currentMonitor.mockResolvedValue({
      size: { width: 1920, height: 1080 },
      workArea: { size: { width: 1920, height: 1040 } },
      scaleFactor: 1,
    });
    moved?.();
    await flush();
    expect(app.displayInfo.value.physicalWidth).toBe(1920);
    expect(app.displayInfo.value.pixelRatio).toBe(1);
    currentMonitor.mockResolvedValue(null);
    moved?.();
    await flush();
    expect(app.displayInfo.value.native).toBe(false);
    stop();
    expect(unlisten).toHaveBeenCalledTimes(2);
  });
});
