use std::sync::Mutex;
use tauri::{AppHandle, Manager};
use tauri_plugin_opener::OpenerExt;

/// 后端进程状态
pub struct BackendState {
    /// 存储后端子进程，用于优雅关闭
    pub child: Mutex<Option<tokio::process::Child>>,
}

/// 获取后端可执行文件路径
/// - 开发模式: 返回 None，需手动启动后端
/// - 生产模式: 返回 PyInstaller 打包的可执行文件路径
fn find_backend_binary(app_handle: &AppHandle) -> Option<std::path::PathBuf> {
    // 1. 检查环境变量 EMS_BACKEND_BIN
    if let Ok(path) = std::env::var("EMS_BACKEND_BIN") {
        let p = std::path::PathBuf::from(&path);
        if p.exists() {
            log::info!("使用环境变量指定的后端: {}", p.display());
            return Some(p);
        }
    }

    #[cfg(target_os = "windows")]
    let bin_names = ["ems_simulate_backend.exe", "ems_simulate.exe"];
    #[cfg(not(target_os = "windows"))]
    let bin_names = ["ems_simulate_backend", "ems_simulate"];

    // 2. 检查 exe 同级目录（打包后 ems_simulate_backend/ 放在 exe 旁边）
    if let Ok(exe_path) = std::env::current_exe() {
        if let Some(exe_dir) = exe_path.parent() {
            for name in &bin_names {
                let candidate = exe_dir.join("ems_simulate_backend").join(name);
                if candidate.exists() {
                    log::info!("找到后端可执行文件 (exe同级): {}", candidate.display());
                    return Some(candidate);
                }
            }
        }
    }

    // 3. 检查资源目录中的 PyInstaller 产物
    let resource_dir = app_handle
        .path()
        .resource_dir()
        .unwrap_or_default();

    for name in &bin_names {
        let candidate = resource_dir.join("ems_simulate_backend").join(name);
        if candidate.exists() {
            log::info!("找到后端可执行文件: {}", candidate.display());
            return Some(candidate);
        }
    }

    // 4. 开发模式：尝试从项目根目录找到 Python 入口
    let dev_candidates = [
        resource_dir.join("..").join("start_back_end.py"),
        std::path::PathBuf::from("start_back_end.py"),
    ];
    for candidate in &dev_candidates {
        if candidate.exists() {
            log::info!("开发模式 - 检测到 Python 入口: {}", candidate.display());
            // 开发模式返回 None，由外部管理
            break;
        }
    }

    log::warn!("未找到后端可执行文件，请确保已通过 PyInstaller 打包并放置在资源目录中");
    None
}

/// 启动 Python 后端进程（生产模式）
async fn start_backend_process(binary_path: &std::path::Path) -> Result<tokio::process::Child, String> {
    let mut cmd = tokio::process::Command::new(binary_path);

    // 设置工作目录为可执行文件所在目录
    if let Some(parent) = binary_path.parent() {
        cmd.current_dir(parent);
    }

    #[cfg(target_os = "windows")]
    {
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }

    cmd.stdout(std::process::Stdio::piped());
    cmd.stderr(std::process::Stdio::piped());

    let child = cmd
        .spawn()
        .map_err(|e| format!("启动后端进程失败: {}", e))?;

    log::info!("后端进程已启动 (PID: {})", child.id().unwrap_or(0));
    Ok(child)
}

/// 等待后端就绪（轮询健康检查）
async fn wait_for_backend_ready(url: &str, max_retries: u32, delay_ms: u64) -> Result<(), String> {
    let client = reqwest::Client::new();
    let health_url = format!("{}/api/health", url);

    for i in 0..max_retries {
        match client.get(&health_url).timeout(std::time::Duration::from_secs(3)).send().await {
            Ok(resp) if resp.status().is_success() => {
                log::info!("后端就绪 (尝试 {}/{})", i + 1, max_retries);
                return Ok(());
            }
            Ok(resp) => {
                log::debug!(
                    "后端响应但状态异常: {} (尝试 {}/{})",
                    resp.status(),
                    i + 1,
                    max_retries
                );
            }
            Err(e) => {
                log::debug!(
                    "后端未就绪: {} (尝试 {}/{})",
                    e,
                    i + 1,
                    max_retries
                );
            }
        }
        tokio::time::sleep(std::time::Duration::from_millis(delay_ms)).await;
    }

    Err(format!("后端在 {} 次尝试后仍未就绪", max_retries))
}

/// 优雅关闭后端进程
async fn shutdown_backend(mut child: tokio::process::Child) {
    log::info!("正在关闭后端进程...");

    #[cfg(target_os = "windows")]
    {
        // Windows: 发送 Ctrl+C 信号
        let _ = child.kill().await;
        let _ = tokio::time::timeout(std::time::Duration::from_secs(5), child.wait()).await;
    }

    #[cfg(not(target_os = "windows"))]
    {
        // Unix: 先发 SIGTERM，等待 5 秒，再发 SIGKILL
        use tokio::signal::unix::{signal, SignalKind};
        // 使用 kill 发送 SIGTERM
        if let Some(id) = child.id() {
            unsafe {
                libc::kill(id as i32, libc::SIGTERM);
            }
        }
        match tokio::time::timeout(std::time::Duration::from_secs(5), child.wait()).await {
            Ok(_) => log::info!("后端进程已正常退出"),
            Err(_) => {
                log::warn!("后端进程超时未响应，强制终止");
                let _ = child.kill().await;
            }
        }
    }

    log::info!("后端进程已关闭");
}

/// Tauri 命令: 检查后端状态
#[tauri::command]
async fn check_backend_status(backend_url: String) -> Result<bool, String> {
    let client = reqwest::Client::new();
    let health_url = format!("{}/api/health", backend_url);

    match client
        .get(&health_url)
        .timeout(std::time::Duration::from_secs(3))
        .send()
        .await
    {
        Ok(resp) => Ok(resp.status().is_success()),
        Err(_) => Ok(false),
    }
}

/// Tauri 命令: 获取应用配置
#[tauri::command]
fn get_app_config() -> serde_json::Value {
    serde_json::json!({
        "backend_url": "http://127.0.0.1:8991",
        "api_docs": "http://127.0.0.1:8991/docs",
        "version": "1.0.0"
    })
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    env_logger::init();

    let backend_url = std::env::var("EMS_BACKEND_URL")
        .unwrap_or_else(|_| "http://127.0.0.1:8991".to_string());
    let backend_url_clone = backend_url.clone();

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_process::init())
        .manage(BackendState {
            child: Mutex::new(None),
        })
        .setup(move |app| {
            log::info!("EMS Simulate 桌面客户端启动中...");

            let app_handle = app.handle().clone();
            let url = backend_url_clone.clone();
            let url_for_nav = url.clone();

            // 获取主窗口引用（初始不可见）
            let window = app_handle
                .get_webview_window("main")
                .expect("主窗口未找到");

            // 尝试查找并启动后端
            if let Some(binary_path) = find_backend_binary(&app_handle) {
                log::info!("生产模式: 启动内嵌后端进程");

                let url_for_health = url.clone();
                let app_handle_clone = app_handle.clone();

                tauri::async_runtime::spawn(async move {
                    match start_backend_process(&binary_path).await {
                        Ok(child) => {
                            // 存储子进程句柄到状态管理
                            if let Some(state) = app_handle_clone.try_state::<BackendState>() {
                                if let Ok(mut guard) = state.child.lock() {
                                    *guard = Some(child);
                                }
                            }

                            // 等待后端就绪
                            match wait_for_backend_ready(&url_for_health, 30, 500).await {
                                Ok(()) => {
                                    log::info!("后端服务已就绪");
                                    // 导航到后端 URL 并显示窗口
                                    if let Some(win) = app_handle_clone.get_webview_window("main") {
                                        let backend_url_parsed = url::Url::parse(&url_for_nav).unwrap();
                                        let _ = win.navigate(backend_url_parsed);
                                        let _ = win.show();
                                        let _ = win.set_focus();
                                    }
                                }
                                Err(e) => {
                                    log::error!("{}", e);
                                    // 显示错误信息在窗口中
                                    if let Some(win) = app_handle_clone.get_webview_window("main") {
                                        let _ = win.show();
                                    }
                                }
                            }
                        }
                        Err(e) => {
                            log::error!("{}", e);
                            if let Some(win) = app_handle_clone.get_webview_window("main") {
                                let _ = win.show();
                            }
                        }
                    }
                });
            } else {
                log::info!("开发模式: 直接连接到 {}", url);
                // 开发模式：后端已在运行，直接导航并显示
                let backend_url_parsed = url::Url::parse(&url_for_nav).unwrap();
                let _ = window.navigate(backend_url_parsed);
                let _ = window.show();
                let _ = window.set_focus();
            }

            // 设置系统托盘
            setup_tray(&app_handle, url)?;

            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                // 默认隐藏到托盘而不是关闭
                let _ = window.hide();
                api.prevent_close();
            }
        })
        .invoke_handler(tauri::generate_handler![
            check_backend_status,
            get_app_config,
        ])
        .run(tauri::generate_context!())
        .expect("启动 EMS Simulate 桌面客户端失败");
}

/// 设置系统托盘图标和菜单
fn setup_tray(app_handle: &AppHandle, backend_url: String) -> Result<(), Box<dyn std::error::Error>> {
    use tauri::{
        menu::{MenuBuilder, MenuItemBuilder},
        tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    };

    let show_item = MenuItemBuilder::with_id("show", "显示主窗口").build(app_handle)?;
    let hide_item = MenuItemBuilder::with_id("hide", "隐藏主窗口").build(app_handle)?;
    let docs_item = MenuItemBuilder::with_id("docs", "API 文档").build(app_handle)?;
    let separator = tauri::menu::PredefinedMenuItem::separator(app_handle)?;
    let quit_item = MenuItemBuilder::with_id("quit", "退出").build(app_handle)?;

    let menu = MenuBuilder::new(app_handle)
        .items(&[&show_item, &hide_item, &docs_item, &separator, &quit_item])
        .build()?;

    let _tray = TrayIconBuilder::new()
        .icon(app_handle.default_window_icon().unwrap().clone())
        .tooltip("EMS Simulate")
        .menu(&menu)
        .on_menu_event(move |app, event| {
            let id = event.id().as_ref();
            match id {
                "show" => {
                    if let Some(window) = app.get_webview_window("main") {
                        let _ = window.show();
                        let _ = window.set_focus();
                    }
                }
                "hide" => {
                    if let Some(window) = app.get_webview_window("main") {
                        let _ = window.hide();
                    }
                }
                "docs" => {
                    let url = format!("{}/docs", backend_url);
                    let _ = app.opener().open_url(&url, None::<&str>);
                }
                "quit" => {
                    // 优雅关闭后端子进程
                    if let Some(state) = app.try_state::<BackendState>() {
                        if let Ok(mut guard) = state.child.lock() {
                            if let Some(child) = guard.take() {
                                tauri::async_runtime::spawn(async move {
                                    shutdown_backend(child).await;
                                });
                            }
                        }
                    }
                    app.exit(0);
                }
                _ => {}
            }
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                // 左键点击显示/隐藏窗口
                if let Some(window) = tray.app_handle().get_webview_window("main") {
                    if window.is_visible().unwrap_or(false) {
                        let _ = window.hide();
                    } else {
                        let _ = window.show();
                        let _ = window.set_focus();
                    }
                }
            }
        })
        .build(app_handle)?;

    Ok(())
}
