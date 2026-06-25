mod msix;
mod normal;

use tauri::AppHandle;

/// 检测当前是否运行在 MSIX/AppX 环境中
///
/// MSIX 包使用 EntryPoint="Windows.FullTrustApplication"（完全信任模式），
/// 不会设置 PACKAGE_FAMILY_NAME 等环境变量。只能通过 exe 路径是否在
/// WindowsApps 目录下来判断。
fn is_msix_env() -> bool {
    #[cfg(target_os = "windows")]
    {
        if let Ok(exe) = std::env::current_exe() {
            if let Some(path) = exe.to_str() {
                return path.contains("WindowsApps");
            }
        }
        false
    }
    #[cfg(not(target_os = "windows"))]
    {
        false
    }
}

// ── Tauri commands（放在 mod.rs 中，让 #[tauri::command] 宏正确生成内部符号） ──

#[tauri::command]
pub async fn is_backend_ready() -> Result<bool, String> {
    if is_msix_env() {
        Ok(msix::is_backend_ready().await)
    } else {
        normal::is_backend_ready().await
    }
}

#[tauri::command]
pub fn get_backend_url() -> Result<String, String> {
    if is_msix_env() {
        Ok("http://127.0.0.1:8991".to_string())
    } else {
        normal::get_backend_url()
    }
}

#[tauri::command]
pub async fn restart_backend(app: tauri::AppHandle) -> Result<String, String> {
    let url = if is_msix_env() {
        msix::restart(&app)
    } else {
        normal::restart(&app)
    };
    // 异步等待后端就绪
    wait_backend_ready(&url).await;
    Ok(url)
}

// ── 统一入口：根据环境转发到对应模块 ──

pub fn spawn_backend(app: &AppHandle) -> String {
    if is_msix_env() {
        eprintln!("[EMS] detected MSIX environment, using msix backend module");
        msix::spawn_backend(app)
    } else {
        normal::spawn_backend(app)
    }
}

pub async fn wait_backend_ready(url: &str) {
    if is_msix_env() {
        msix::wait_backend_ready().await
    } else {
        normal::wait_backend_ready(url).await
    }
}

pub fn cleanup_managed_process() {
    if is_msix_env() {
        msix::cleanup()
    } else {
        normal::cleanup()
    }
}

pub fn stop_backend() {
    if is_msix_env() {
        msix::stop()
    } else {
        normal::stop()
    }
}
