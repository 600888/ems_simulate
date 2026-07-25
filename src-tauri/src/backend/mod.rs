mod msix;
mod normal;

use tauri::AppHandle;

const HEALTH_FAILURE_LIMIT: u8 = 3;
const DYNAMIC_PORT_MIN: u16 = 50_000;
const DYNAMIC_PORT_MAX: u16 = u16::MAX;

/// 从高位非特权端口范围的随机位置开始查找空闲回环端口。
///
/// 这里的 bind 只是快速探测，后端进程随后会立即执行实际绑定。
fn get_available_port() -> Result<u16, String> {
    use std::time::{SystemTime, UNIX_EPOCH};

    let port_count = u32::from(DYNAMIC_PORT_MAX) - u32::from(DYNAMIC_PORT_MIN) + 1;
    let time_seed = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos() as u64;
    let seed = time_seed ^ (u64::from(std::process::id()) << 32);
    let start_offset = (seed % u64::from(port_count)) as u32;

    find_available_port_from(start_offset)
}

fn find_available_port_from(start_offset: u32) -> Result<u16, String> {
    let port_count = u32::from(DYNAMIC_PORT_MAX) - u32::from(DYNAMIC_PORT_MIN) + 1;

    for scanned in 0..port_count {
        let offset = (start_offset + scanned) % port_count;
        let port = (u32::from(DYNAMIC_PORT_MIN) + offset) as u16;
        if std::net::TcpListener::bind(("127.0.0.1", port)).is_ok() {
            return Ok(port);
        }
    }

    Err(format!(
        "端口范围 {DYNAMIC_PORT_MIN}-{DYNAMIC_PORT_MAX} 内没有可用的回环端口"
    ))
}

/// 根据进程与健康检查结果计算服务状态。
///
/// 后端尚未完成首次启动时仍要求健康检查真实成功；一旦已经就绪，进程存活期间
/// 允许最多两次连续的瞬时探测失败，第三次失败才判定服务卡死。
fn evaluate_backend_status(
    process_alive: bool,
    health_ok: bool,
    was_ready: bool,
    consecutive_failures: u8,
) -> (bool, u8) {
    if health_ok {
        return (true, 0);
    }
    if !process_alive {
        return (false, 0);
    }
    if !was_ready {
        return (false, consecutive_failures);
    }

    let failures = consecutive_failures.saturating_add(1);
    (failures < HEALTH_FAILURE_LIMIT, failures)
}

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
        msix::get_backend_url()
    } else {
        normal::get_backend_url()
    }
}

#[tauri::command]
pub async fn restart_backend(app: tauri::AppHandle) -> Result<String, String> {
    let url = if is_msix_env() {
        msix::restart(&app)?
    } else {
        normal::restart(&app)?
    };
    if wait_backend_ready(&url).await {
        Ok(url.trim_end_matches("/api/health").to_string())
    } else {
        Err(format!("后端进程已启动，但健康检查超时: {url}"))
    }
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

pub async fn wait_backend_ready(url: &str) -> bool {
    if is_msix_env() {
        msix::wait_backend_ready(url).await
    } else {
        normal::wait_backend_ready(url).await
    }
}

/// Rust 侧持续检测后端进程是否存活。健康接口的连续失败次数只由状态栏探测累计，
/// 避免后台监控与前端轮询重复计数。
pub async fn monitor_backend() {
    loop {
        if is_msix_env() {
            msix::refresh_process_status();
        } else {
            normal::refresh_process_status();
        }
        tokio::time::sleep(std::time::Duration::from_secs(2)).await;
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

#[cfg(test)]
mod tests {
    use super::{evaluate_backend_status, get_available_port, DYNAMIC_PORT_MAX, DYNAMIC_PORT_MIN};

    #[test]
    fn dynamic_backend_port_is_in_high_port_range() {
        let port = get_available_port().unwrap();
        assert!((DYNAMIC_PORT_MIN..=DYNAMIC_PORT_MAX).contains(&port));
    }

    #[test]
    fn dynamic_backend_port_skips_an_occupied_port() {
        let _reservation = std::net::TcpListener::bind(("127.0.0.1", DYNAMIC_PORT_MIN)).ok();
        let port = super::find_available_port_from(0).unwrap();
        assert_ne!(port, DYNAMIC_PORT_MIN);
    }

    #[test]
    fn missing_process_is_immediately_unhealthy() {
        assert_eq!(evaluate_backend_status(false, false, true, 2), (false, 0));
    }

    #[test]
    fn running_process_tolerates_two_consecutive_health_failures() {
        let first = evaluate_backend_status(true, false, true, 0);
        let second = evaluate_backend_status(true, false, first.0, first.1);
        let third = evaluate_backend_status(true, false, second.0, second.1);

        assert_eq!(first, (true, 1));
        assert_eq!(second, (true, 2));
        assert_eq!(third, (false, 3));
    }

    #[test]
    fn successful_health_check_resets_failure_count() {
        assert_eq!(evaluate_backend_status(true, true, true, 2), (true, 0));
    }

    #[test]
    fn healthy_endpoint_is_authoritative_when_process_handle_is_stale() {
        assert_eq!(evaluate_backend_status(false, true, false, 0), (true, 0));
    }

    #[test]
    fn startup_still_requires_a_successful_health_check() {
        assert_eq!(evaluate_backend_status(true, false, false, 0), (false, 0));
    }
}
