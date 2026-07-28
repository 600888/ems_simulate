/**
 * Tauri 桌面客户端集成工具
 * 检测是否在 Tauri 环境中运行，并提供原生能力接口
 */

/** 是否运行在 Tauri 桌面客户端中 */
export function isTauri(): boolean {
  return !!(window as any).__TAURI_INTERNALS__;
}

/** 在独立原生窗口中打开指定设备的报文查看器；同一设备只保留一个窗口。 */
export async function openMessageWindow(deviceName: string): Promise<void> {
  if (!isTauri()) throw new Error("不在 Tauri 环境中运行");

  const { WebviewWindow } = await import("@tauri-apps/api/webviewWindow");
  let hash = 2166136261;
  for (const char of deviceName) {
    hash ^= char.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  const label = `message-${(hash >>> 0).toString(16)}`;
  const existing = await WebviewWindow.getByLabel(label);
  if (existing) {
    await existing.show();
    await existing.unminimize();
    await existing.setFocus();
    return;
  }

  const baseUrl = `${window.location.origin}${window.location.pathname}`;
  const messageWindow = new WebviewWindow(label, {
    url: `${baseUrl}#/message-view/${encodeURIComponent(deviceName)}`,
    title: `查看报文 - ${deviceName}`,
    width: 1100,
    height: 650,
    minWidth: 820,
    minHeight: 480,
    center: true,
    resizable: true,
    decorations: true,
    focus: true,
  });

  await new Promise<void>((resolve, reject) => {
    messageWindow.once("tauri://created", () => resolve());
    messageWindow.once("tauri://error", ({ payload }) => reject(payload));
  });
}

/** 获取 Tauri API 模块（仅 Tauri 环境可用） */
export async function getTauriApi() {
  if (!isTauri()) return null;
  try {
    return await import("@tauri-apps/api");
  } catch {
    return null;
  }
}

/** 调用 Rust 后端命令 */
export async function invoke<T = any>(
  cmd: string,
  args?: Record<string, unknown>,
): Promise<T> {
  if (!isTauri()) {
    throw new Error("不在 Tauri 环境中运行");
  }
  const { invoke: tauriInvoke } = await import("@tauri-apps/api/core");
  return tauriInvoke<T>(cmd, args);
}

/**
 * Save generated content through the native picker in Tauri and use the
 * browser download mechanism on the web.
 *
 * Returns false when the native picker is cancelled.
 */
export async function saveDownload(
  blob: Blob,
  filename: string,
): Promise<boolean> {
  if (isTauri()) {
    const { save } = await import("@tauri-apps/plugin-dialog");
    const destination = await save({ defaultPath: filename });
    if (!destination) return false;

    const contents = Array.from(new Uint8Array(await blob.arrayBuffer()));
    await invoke("save_file", { path: destination, contents });
    return true;
  }

  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
  return true;
}

/** 检查后端服务状态 */
export async function checkBackendStatus(
  backendUrl?: string,
): Promise<boolean> {
  // 页面由后端自身提供时，当前 origin 才是实际端口（普通 MSI 可能因
  // 8991 被占用而使用动态端口）。健康接口成功是服务运行的权威信号。
  const isLocalHttpPage =
    ["http:", "https:"].includes(window.location.protocol) &&
    ["127.0.0.1", "localhost", "::1"].includes(window.location.hostname);
  const baseUrl =
    backendUrl?.replace(/\/+$/, "") ||
    (isLocalHttpPage ? window.location.origin : "http://127.0.0.1:8991");

  const probeHealth = async (): Promise<boolean> => {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 2000);
    try {
      const resp = await fetch(`${baseUrl}/api/health`, {
        cache: "no-store",
        signal: controller.signal,
      });
      return resp.ok;
    } catch {
      return false;
    } finally {
      window.clearTimeout(timeout);
    }
  };

  if (!isTauri()) return probeHealth();

  // 桌面端同时参考 HTTP 健康接口和 Rust 进程状态。任一确认服务正常
  // 即显示运行中，避免过期进程句柄造成误报；连续失败保护仍由 Rust 负责。
  const [healthOk, managedProcessOk] = await Promise.all([
    probeHealth(),
    invoke<boolean>("is_backend_ready").catch(() => false),
  ]);
  return healthOk || managedProcessOk;
}

/** 获取应用配置 */
export async function getAppConfig() {
  if (!isTauri()) {
    return {
      backend_url: "http://127.0.0.1:8991",
      api_docs: "http://127.0.0.1:8991/docs",
      version: "1.0.0",
    };
  }
  try {
    return await invoke("get_app_config");
  } catch {
    return null;
  }
}

/** 重启后端服务 */
export async function restartBackend(): Promise<string> {
  if (!isTauri()) {
    throw new Error("不在 Tauri 环境中运行");
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<string>("restart_backend");
}

/** 打开外部 URL（使用系统默认浏览器） */
export async function openExternal(url: string) {
  if (!isTauri()) {
    window.open(url, "_blank");
    return;
  }
  try {
    const { open } = await import("@tauri-apps/plugin-shell");
    await open(url);
  } catch (e) {
    console.error("打开外部链接失败:", e);
    window.open(url, "_blank");
  }
}

/** Tauri 环境初始化（在 main.ts 中调用） */
export async function initTauri() {
  if (!isTauri()) {
    console.log("[Tauri] 浏览器模式");
    return;
  }

  console.log("[Tauri] 桌面客户端模式已激活");

  // 监听窗口事件（可选）
  try {
    const { getCurrentWindow } = await import("@tauri-apps/api/window");
    const appWindow = getCurrentWindow();

    // 窗口获得焦点
    await appWindow.onFocusChanged(
      ({ payload: focused }: { payload: boolean }) => {
        console.log(`[Tauri] 窗口焦点: ${focused}`);
      },
    );
  } catch (e) {
    console.warn("[Tauri] 窗口事件监听失败:", e);
  }
}

/** 监听 Tauri 关闭请求事件（窗口 X 按钮点击时触发） */
export async function onCloseRequested(callback: () => void) {
  if (!isTauri()) return;
  try {
    const { getCurrentWindow } = await import("@tauri-apps/api/window");
    const appWindow = getCurrentWindow();
    await appWindow.listen("close-requested", () => {
      callback();
    });
  } catch (e) {
    console.warn("[Tauri] 监听关闭请求失败:", e);
  }
}
