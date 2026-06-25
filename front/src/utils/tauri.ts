/**
 * Tauri 桌面客户端集成工具
 * 检测是否在 Tauri 环境中运行，并提供原生能力接口
 */

/** 是否运行在 Tauri 桌面客户端中 */
export function isTauri(): boolean {
  return !!(window as any).__TAURI_INTERNALS__
}

/** 获取 Tauri API 模块（仅 Tauri 环境可用） */
export async function getTauriApi() {
  if (!isTauri()) return null
  try {
    return await import('@tauri-apps/api')
  } catch {
    return null
  }
}

/** 调用 Rust 后端命令 */
export async function invoke<T = any>(cmd: string, args?: Record<string, unknown>): Promise<T> {
  if (!isTauri()) {
    throw new Error('不在 Tauri 环境中运行')
  }
  const { invoke: tauriInvoke } = await import('@tauri-apps/api/core')
  return tauriInvoke<T>(cmd, args)
}

/** 检查后端服务状态 */
export async function checkBackendStatus(backendUrl?: string): Promise<boolean> {
  if (!isTauri()) {
    // 浏览器环境：直接 HTTP 请求健康检查
    try {
      const resp = await fetch(`${backendUrl || 'http://127.0.0.1:8991'}/api/health`)
      return resp.ok
    } catch {
      return false
    }
  }
  try {
    return await invoke<boolean>('check_backend_status', {
      backendUrl: backendUrl || 'http://127.0.0.1:8991'
    })
  } catch {
    return false
  }
}

/** 获取应用配置 */
export async function getAppConfig() {
  if (!isTauri()) {
    return {
      backend_url: 'http://127.0.0.1:8991',
      api_docs: 'http://127.0.0.1:8991/docs',
      version: '1.0.0'
    }
  }
  try {
    return await invoke('get_app_config')
  } catch {
    return null
  }
}

/** 重启后端服务 */
export async function restartBackend(): Promise<string> {
  if (!isTauri()) {
    throw new Error('不在 Tauri 环境中运行')
  }
  const { invoke } = await import('@tauri-apps/api/core')
  return invoke<string>('restart_backend')
}

/** 打开外部 URL（使用系统默认浏览器） */
export async function openExternal(url: string) {
  if (!isTauri()) {
    window.open(url, '_blank')
    return
  }
  try {
    const { open } = await import('@tauri-apps/plugin-shell')
    await open(url)
  } catch (e) {
    console.error('打开外部链接失败:', e)
    window.open(url, '_blank')
  }
}

/** Tauri 环境初始化（在 main.ts 中调用） */
export async function initTauri() {
  if (!isTauri()) {
    console.log('[Tauri] 浏览器模式')
    return
  }

  console.log('[Tauri] 桌面客户端模式已激活')

  // 监听窗口事件（可选）
  try {
    const { getCurrentWindow } = await import('@tauri-apps/api/window')
    const appWindow = getCurrentWindow()

    // 窗口获得焦点
    await appWindow.onFocusChanged(({ payload: focused }: { payload: boolean }) => {
      console.log(`[Tauri] 窗口焦点: ${focused}`)
    })
  } catch (e) {
    console.warn('[Tauri] 窗口事件监听失败:', e)
  }
}

/** 监听 Tauri 关闭请求事件（窗口 X 按钮点击时触发） */
export async function onCloseRequested(callback: () => void) {
  if (!isTauri()) return
  try {
    const { getCurrentWindow } = await import('@tauri-apps/api/window')
    const appWindow = getCurrentWindow()
    await appWindow.listen('close-requested', () => {
      callback()
    })
  } catch (e) {
    console.warn('[Tauri] 监听关闭请求失败:', e)
  }
}
