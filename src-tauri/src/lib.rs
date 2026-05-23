use std::sync::Mutex;
use tauri::{AppHandle, Emitter, Manager};

/// 后端子进程状态
pub struct BackendState {
    pub child: Mutex<Option<std::process::Child>>,
}

/// Sidecar 名称（与 tauri.conf.json 中 externalBin 配置一致）
const SIDECAR_NAME: &str = "ems_simulate_backend";

/// 日志文件路径（写入到用户可写数据目录）
static LOG_FILE_PATH: std::sync::OnceLock<String> = std::sync::OnceLock::new();

/// 编译期确定 Rust 目标三元组（替代不可用的 env!("TARGET")）
const fn target_triple() -> &'static str {
    if cfg!(target_arch = "x86_64") && cfg!(target_os = "windows") && cfg!(target_env = "msvc") {
        "x86_64-pc-windows-msvc"
    } else if cfg!(target_arch = "aarch64") && cfg!(target_os = "windows") {
        "aarch64-pc-windows-msvc"
    } else if cfg!(target_arch = "x86_64") && cfg!(target_os = "linux") && cfg!(target_env = "gnu") {
        "x86_64-unknown-linux-gnu"
    } else if cfg!(target_arch = "aarch64") && cfg!(target_os = "linux") && cfg!(target_env = "gnu") {
        "aarch64-unknown-linux-gnu"
    } else if cfg!(target_arch = "x86_64") && cfg!(target_os = "macos") {
        "x86_64-apple-darwin"
    } else if cfg!(target_arch = "aarch64") && cfg!(target_os = "macos") {
        "aarch64-apple-darwin"
    } else {
        "unknown-target"
    }
}

/// sidecar 二进制文件名（含目标三元组后缀）
fn sidecar_filename() -> String {
    let target = target_triple();
    if cfg!(target_os = "windows") {
        format!("{}-{}.exe", SIDECAR_NAME, target)
    } else {
        format!("{}-{}", SIDECAR_NAME, target)
    }
}

/// 简易文件日志器（MSIX 环境下 env_logger 无控制台，必须写文件）
struct FileLogger;

impl log::Log for FileLogger {
    fn enabled(&self, metadata: &log::Metadata) -> bool {
        metadata.level() <= log::Level::Info
    }

    fn log(&self, record: &log::Record) {
        if self.enabled(record.metadata()) {
            let timestamp = chrono_now();
            let line = format!("[{} {:5}] {}\n", timestamp, record.level(), record.args());

            if let Some(path) = LOG_FILE_PATH.get() {
                use std::io::Write;
                if let Ok(mut f) = std::fs::OpenOptions::new()
                    .create(true)
                    .append(true)
                    .open(path)
                {
                    let _ = f.write_all(line.as_bytes());
                }
            }

            #[cfg(debug_assertions)]
            eprint!("{}", line);
        }
    }

    fn flush(&self) {}
}

/// 简易时间戳
fn chrono_now() -> String {
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default();
    format!("{}", now.as_secs())
}

/// 初始化文件日志系统
fn init_file_logger(data_dir: &std::path::Path) {
    let log_dir = data_dir.join("log");
    let _ = std::fs::create_dir_all(&log_dir);
    let log_path = log_dir.join("tauri.log").to_string_lossy().to_string();

    // 截断旧日志（保留最近一次启动）
    let _ = std::fs::write(&log_path, "");

    LOG_FILE_PATH.set(log_path.clone()).ok();

    let logger = Box::leak(Box::new(FileLogger));
    let _ = log::set_logger(logger);
    log::set_max_level(log::LevelFilter::Info);

    log::info!("=== EMS Simulate 日志初始化完成 ===");
    log::info!("日志文件: {}", log_path);
}

/// 确保可写数据目录存在
fn ensure_data_dir() -> Result<std::path::PathBuf, String> {
    let local_app_data = std::env::var("LOCALAPPDATA")
        .map_err(|_| "无法获取 LOCALAPPDATA".to_string())?;
    let data_dir = std::path::Path::new(&local_app_data).join("ems_simulate");

    for sub in &["", "data", "log", "config", "upload", "plan"] {
        std::fs::create_dir_all(&data_dir.join(sub))
            .map_err(|e| format!("创建目录失败: {}", e))?;
    }

    log::info!("数据目录就绪: {}", data_dir.display());
    Ok(data_dir)
}

/// 解析 sidecar 二进制路径（优先 resource_dir，回退到 exe 目录）
fn resolve_sidecar_path(app_handle: &AppHandle) -> Result<std::path::PathBuf, String> {
    let filename = sidecar_filename();
    log::info!("目标三元组: {}, sidecar 文件名: {}", target_triple(), filename);

    // 候选路径 1: Tauri resource_dir/binaries/
    if let Ok(resource_dir) = app_handle.path().resource_dir() {
        let p = resource_dir.join("binaries").join(&filename);
        log::info!("[路径] resource_dir 候选: {} (存在: {})", p.display(), p.exists());
        if p.exists() {
            log::info!("[路径] 使用 resource_dir 路径");
            return Ok(p);
        }
    } else {
        log::warn!("[路径] resource_dir 解析失败");
    }

    // 候选路径 2: exe 所在目录/binaries/
    if let Ok(exe_path) = std::env::current_exe() {
        if let Some(exe_dir) = exe_path.parent() {
            let p = exe_dir.join("binaries").join(&filename);
            log::info!("[路径] exe目录 候选: {} (存在: {})", p.display(), p.exists());
            if p.exists() {
                log::info!("[路径] 使用 exe 目录路径");
                return Ok(p);
            }

            // 候选路径 3: exe 目录直接放置（无 binaries 子目录）
            let p2 = exe_dir.join(&filename);
            log::info!("[路径] exe目录直接 候选: {} (存在: {})", p2.display(), p2.exists());
            if p2.exists() {
                log::info!("[路径] 使用 exe 目录直接路径");
                return Ok(p2);
            }
        }
    }

    // 所有候选路径都失败，输出详细诊断
    let diag = build_path_diagnostic(app_handle);
    Err(format!("未找到 sidecar 二进制文件 '{}'\n{}", filename, diag))
}

/// 构建路径诊断字符串
fn build_path_diagnostic(app_handle: &AppHandle) -> String {
    let mut parts = Vec::new();
    let filename = sidecar_filename();

    if let Ok(p) = app_handle.path().resource_dir() {
        parts.push(format!("resource_dir: {} (存在: {})", p.display(), p.exists()));
        let sidecar = p.join("binaries").join(&filename);
        parts.push(format!("  -> sidecar: {} (存在: {})", sidecar.display(), sidecar.exists()));
    } else {
        parts.push("resource_dir: 解析失败".to_string());
    }

    if let Ok(p) = std::env::current_exe() {
        parts.push(format!("current_exe: {}", p.display()));
        if let Some(dir) = p.parent() {
            let sidecar = dir.join("binaries").join(&filename);
            parts.push(format!("  -> sidecar: {} (存在: {})", sidecar.display(), sidecar.exists()));
        }
    }

    for var in &["LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)"] {
        if let Ok(v) = std::env::var(var) {
            parts.push(format!("env {}={}", var, v));
        }
    }

    parts.push(format!("TARGET={}", target_triple()));
    parts.join("\n")
}

/// 启动后端进程并监控输出
fn start_backend_process(
    app_handle: &AppHandle,
    data_dir: &std::path::Path,
) -> Result<std::process::Child, String> {
    log_path_diagnostics(app_handle);

    let sidecar_path = resolve_sidecar_path(app_handle)?;
    log::info!("[启动] sidecar 路径: {}", sidecar_path.display());

    let mut cmd = std::process::Command::new(&sidecar_path);
    cmd.env("EMS_ROOT_DIR", data_dir.to_string_lossy().to_string())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped());

    // Windows 下禁止子进程创建控制台窗口
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        const DETACHED_PROCESS: u32 = 0x00000008;
        cmd.creation_flags(CREATE_NO_WINDOW | DETACHED_PROCESS);
    }

    let mut child = cmd.spawn()
        .map_err(|e| format!("启动后端进程失败: {} (路径: {})", e, sidecar_path.display()))?;

    let pid = child.id();
    log::info!("[启动] 后端进程已启动, PID: {}", pid);

    // 消费 stdout
    if let Some(stdout) = child.stdout.take() {
        std::thread::spawn(move || {
            use std::io::{BufRead, BufReader};
            let reader = BufReader::new(stdout);
            for line in reader.lines().flatten() {
                log::info!("[backend:out] {}", line);
            }
        });
    }

    // 消费 stderr
    if let Some(stderr) = child.stderr.take() {
        std::thread::spawn(move || {
            use std::io::{BufRead, BufReader};
            let reader = BufReader::new(stderr);
            for line in reader.lines().flatten() {
                log::info!("[backend:err] {}", line);
            }
        });
    }

    Ok(child)
}

/// 打印 Tauri 路径诊断信息
fn log_path_diagnostics(app_handle: &AppHandle) {
    log::info!("=== 路径诊断 ===");

    if let Ok(p) = app_handle.path().resource_dir() {
        log::info!("resource_dir: {} (存在: {})", p.display(), p.exists());
    } else {
        log::error!("resource_dir 解析失败");
    }

    if let Ok(p) = app_handle.path().app_data_dir() {
        log::info!("app_data_dir: {} (存在: {})", p.display(), p.exists());
    } else {
        log::error!("app_data_dir 解析失败");
    }

    if let Ok(p) = app_handle.path().app_local_data_dir() {
        log::info!("app_local_data_dir: {} (存在: {})", p.display(), p.exists());
    } else {
        log::error!("app_local_data_dir 解析失败");
    }

    if let Ok(p) = std::env::current_exe() {
        log::info!("current_exe: {} (存在: {})", p.display(), p.exists());
    } else {
        log::error!("current_exe 获取失败");
    }

    for var in &["LOCALAPPDATA", "APPDATA", "PROGRAMFILES", "EMS_ROOT_DIR", "EMS_BACKEND_URL"] {
        match std::env::var(var) {
            Ok(v) => log::info!("env {}={}", var, v),
            Err(_) => log::info!("env {}=(未设置)", var),
        }
    }

    log::info!("Rust TARGET: {}", target_triple());

    // 列出 exe 目录下的内容
    if let Ok(exe_path) = std::env::current_exe() {
        if let Some(exe_dir) = exe_path.parent() {
            log::info!("exe 目录内容:");
            if let Ok(entries) = std::fs::read_dir(exe_dir) {
                for entry in entries.flatten() {
                    let name = entry.file_name().to_string_lossy().to_string();
                    let is_dir = entry.file_type().map(|t| t.is_dir()).unwrap_or(false);
                    log::info!("  {}{}", name, if is_dir { "/" } else { "" });
                }
            }
            // 检查 binaries 子目录
            let binaries_dir = exe_dir.join("binaries");
            if binaries_dir.exists() {
                log::info!("binaries/ 目录内容:");
                if let Ok(entries) = std::fs::read_dir(&binaries_dir) {
                    for entry in entries.flatten() {
                        let name = entry.file_name().to_string_lossy().to_string();
                        log::info!("  {}", name);
                    }
                }
            } else {
                log::info!("binaries/ 目录不存在");
            }
        }
    }

    log::info!("=== 路径诊断结束 ===");
}

/// 等待后端就绪（TCP 端口检测）
/// 每 100ms 尝试连接后端端口，连接成功即表示服务已启动
async fn wait_for_backend_ready(url: &str, timeout_secs: u64) -> Result<(), String> {
    // 从 URL 解析端口号 (http://127.0.0.1:8991 -> 8991)
    let port = url::Url::parse(url)
        .ok()
        .and_then(|u| u.port())
        .unwrap_or(8991);
    let addr = format!("127.0.0.1:{}", port);
    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(timeout_secs);

    loop {
        // TCP 连接成功 = 端口已监听 = 服务就绪
        match tokio::net::TcpStream::connect(&addr).await {
            Ok(_) => {
                log::info!("后端端口 {} 已就绪", port);
                return Ok(());
            }
            Err(_) => {
                if std::time::Instant::now() >= deadline {
                    return Err(format!("后端在 {}s 内未就绪 (端口: {})", timeout_secs, addr));
                }
                tokio::time::sleep(std::time::Duration::from_millis(100)).await;
            }
        }
    }
}

/// PID 文件名
const PID_FILENAME: &str = "backend.pid";

/// 读取并清理上一次残留的后端进程
fn cleanup_stale_backend(data_dir: &std::path::Path) {
    let pid_path = data_dir.join(PID_FILENAME);
    if !pid_path.exists() {
        return;
    }
    if let Ok(pid_str) = std::fs::read_to_string(&pid_path) {
        if let Ok(pid) = pid_str.trim().parse::<u32>() {
            log::info!("发现残留后端进程 PID: {}, 尝试清理", pid);
            kill_pid(pid);
        }
    }
    let _ = std::fs::remove_file(&pid_path);
}

/// 通过 PID 杀进程（Windows: taskkill /F /T; 其他: kill）
fn kill_pid(pid: u32) {
    #[cfg(target_os = "windows")]
    {
        let _ = std::process::Command::new("taskkill")
            .args(["/F", "/T", "/PID", &pid.to_string()])
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .status();
    }

    #[cfg(not(target_os = "windows"))]
    {
        unsafe {
            libc::kill(pid as i32, libc::SIGTERM);
        }
    }
}

/// 保存后端 PID 到文件，用于异常退出时清理
fn save_backend_pid(data_dir: &std::path::Path, pid: u32) {
    let pid_path = data_dir.join(PID_FILENAME);
    if let Err(e) = std::fs::write(&pid_path, pid.to_string()) {
        log::warn!("保存 PID 文件失败: {}", e);
    }
}

/// 删除 PID 文件（正常退出时调用）
fn remove_backend_pid(data_dir: &std::path::Path) {
    let pid_path = data_dir.join(PID_FILENAME);
    let _ = std::fs::remove_file(&pid_path);
}

/// 关闭后端进程（Windows 下使用 taskkill 杀进程树，即时终止）
fn shutdown_backend(child: &mut std::process::Child, data_dir: &std::path::Path) {
    let pid = child.id();
    log::info!("正在关闭后端进程 (PID: {})...", pid);

    #[cfg(target_os = "windows")]
    {
        // taskkill /F /T 强制杀掉整个进程树，是即时终止，无需后续等待
        let kill_result = std::process::Command::new("taskkill")
            .args(["/F", "/T", "/PID", &pid.to_string()])
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .status();
        match kill_result {
            Ok(s) => log::info!("taskkill 完成 (exit: {})", s.code().unwrap_or(-1)),
            Err(e) => {
                log::warn!("taskkill 失败: {}, 回退到 child.kill()", e);
                let _ = child.kill();
            }
        }
    }

    #[cfg(not(target_os = "windows"))]
    {
        let _ = child.kill();
    }

    remove_backend_pid(data_dir);
    log::info!("后端进程已关闭");
}

/// Tauri 命令: 检查后端状态
#[tauri::command]
async fn check_backend_status(backend_url: String) -> Result<bool, String> {
    match reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(2))
        .connect_timeout(std::time::Duration::from_millis(500))
        .build()
        .unwrap_or_else(|_| reqwest::Client::new())
        .get(&format!("{}/api/health", backend_url))
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

/// Tauri 命令: 获取诊断信息
#[tauri::command]
fn get_diagnostic_info(app_handle: AppHandle) -> serde_json::Value {
    let mut info = serde_json::Map::new();

    info.insert("paths".into(), serde_json::json!({
        "resource_dir": app_handle.path().resource_dir().map(|p| p.display().to_string()).ok(),
        "app_data_dir": app_handle.path().app_data_dir().map(|p| p.display().to_string()).ok(),
        "app_local_data_dir": app_handle.path().app_local_data_dir().map(|p| p.display().to_string()).ok(),
        "current_exe": std::env::current_exe().map(|p| p.display().to_string()).ok(),
    }));

    info.insert("env".into(), serde_json::json!({
        "LOCALAPPDATA": std::env::var("LOCALAPPDATA").ok(),
        "EMS_ROOT_DIR": std::env::var("EMS_ROOT_DIR").ok(),
    }));

    info.insert("target".into(), serde_json::Value::String(target_triple().to_string()));

    // 读取日志文件最后 30 行
    if let Some(log_path) = LOG_FILE_PATH.get() {
        if let Ok(content) = std::fs::read_to_string(log_path) {
            let lines: Vec<&str> = content.lines().rev().take(30).collect();
            let log_preview = lines.into_iter().rev().collect::<Vec<_>>().join("\n");
            info.insert("log_tail".into(), serde_json::Value::String(log_preview));
        }
    }

    serde_json::Value::Object(info)
}

/// 显示错误页面（含诊断信息）
fn show_error(window: &tauri::WebviewWindow, error: &str, diag: &str, log_path: Option<&str>) {
    let log_hint = log_path
        .map(|p| format!("<p style='color:#666;font-size:12px;margin-top:8px'>日志: {}</p>", p))
        .unwrap_or_default();

    let html = format!(
        "<html><body style='display:flex;align-items:center;justify-content:center;height:100vh;\
         font-family:sans-serif;background:#1a1a2e;color:#e94560;margin:0'>\
         <div style='text-align:center;max-width:700px;padding:20px'>\
         <h1>后端启动失败</h1>\
         <p style='color:#eee;word-break:break-all'>{}</p>\
         <div style='margin-top:16px;padding:12px;background:#111;border-radius:6px;\
         text-align:left;font-size:12px;color:#888;max-width:600px;word-break:break-all'>\
         <b style='color:#aaa'>诊断信息:</b><br/><pre style='margin:4px 0 0;color:#666;white-space:pre-wrap'>{}</pre></div>\
         {}</div></body></html>",
        error.replace('&', "&amp;").replace('<', "&lt;").replace('>', "&gt;"),
        diag.replace('&', "&amp;").replace('<', "&lt;").replace('>', "&gt;"),
        log_hint,
    );
    let _ = window.eval(&format!("document.documentElement.innerHTML = `{}`", html));
    let _ = window.show();
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // 先确保数据目录存在（用于日志输出）
    let early_data_dir = ensure_data_dir().ok();

    // 初始化文件日志（替代 env_logger，MSIX 无控制台）
    if let Some(ref data_dir) = early_data_dir {
        init_file_logger(data_dir);
    } else {
        let _ = env_logger::try_init();
        log::warn!("无法创建数据目录，文件日志不可用");
    }

    let backend_url = std::env::var("EMS_BACKEND_URL")
        .unwrap_or_else(|_| "http://127.0.0.1:8991".to_string());

    log::info!("EMS Simulate 桌面客户端启动中...");
    log::info!("后端 URL: {}", backend_url);

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_process::init())
        .manage(BackendState { child: Mutex::new(None) })
        .setup(move |app| {
            let app_handle = app.handle().clone();
            let url = backend_url.clone();

            // 开发模式：直接连接后端（后端已在外部运行）
            if cfg!(debug_assertions) {
                log::info!("开发模式: 连接到 {}", url);
                let _window = tauri::WebviewWindowBuilder::new(
                    &app_handle, "main", tauri::WebviewUrl::External(url::Url::parse(&url).unwrap())
                )
                .title("EMS Simulate")
                .inner_size(1280.0, 800.0)
                .min_inner_size(960.0, 600.0)
                .center()
                .resizable(true)
                .decorations(true)
                .build()
                .expect("创建主窗口失败");
                return Ok(());
            }

            // 生产模式：先创建 loading 窗口显示启动状态
            let _window = tauri::WebviewWindowBuilder::new(&app_handle, "main", tauri::WebviewUrl::App("index.html".into()))
                .title("EMS Simulate")
                .inner_size(1280.0, 800.0)
                .min_inner_size(960.0, 600.0)
                .center()
                .resizable(true)
                .decorations(true)
                .visible(true)
                .background_color(tauri::window::Color(0x0f, 0x0c, 0x29, 0xff))
                .build()
                .expect("创建主窗口失败");

            let app_clone = app_handle.clone();
            let url_health = url.clone();
            let url_nav = url.clone();

            tauri::async_runtime::spawn(async move {
                // 1. 确保可写数据目录
                let data_dir = match ensure_data_dir() {
                    Ok(d) => d,
                    Err(e) => {
                        log::error!("初始化数据目录失败: {}", e);
                        if let Some(win) = app_clone.get_webview_window("main") {
                            let diag = build_path_diagnostic(&app_clone);
                            show_error(&win, &format!("初始化数据目录失败: {}", e), &diag, LOG_FILE_PATH.get().map(|s| s.as_str()));
                        }
                        return;
                    }
                };

                // 2. 清理上次残留的后端进程（异常退出时 PID 文件可能仍存在）
                cleanup_stale_backend(&data_dir);

                // 3. 启动后端
                let child = match start_backend_process(&app_clone, &data_dir) {
                    Ok(c) => c,
                    Err(e) => {
                        log::error!("后端启动失败: {}", e);
                        if let Some(win) = app_clone.get_webview_window("main") {
                            let diag = build_path_diagnostic(&app_clone);
                            show_error(&win, &e, &diag, LOG_FILE_PATH.get().map(|s| s.as_str()));
                        }
                        return;
                    }
                };

                // 存储子进程句柄并保存 PID（用于异常退出时清理残留进程）
                let pid = child.id();
                if let Some(state) = app_clone.try_state::<BackendState>() {
                    if let Ok(mut guard) = state.child.lock() {
                        *guard = Some(child);
                    }
                }
                save_backend_pid(&data_dir, pid);

                // 4. 等待后端就绪（TCP 端口检测，每 100ms 一次）
                match wait_for_backend_ready(&url_health, 60).await {
                    Ok(()) => {
                        log::info!("后端服务已就绪，导航到 {}", url_nav);
                        // 直接导航现有窗口到后端 URL（避免销毁重建导致 Tauri 无窗口退出）
                        if let Some(win) = app_clone.get_webview_window("main") {
                            match url::Url::parse(&url_nav) {
                                Ok(parsed_url) => {
                                    let _ = win.navigate(parsed_url);
                                    log::info!("窗口导航完成");
                                }
                                Err(e) => {
                                    log::error!("解析后端 URL 失败: {}", e);
                                }
                            }
                        }
                    }
                    Err(e) => {
                        log::error!("{}", e);
                        if let Some(win) = app_clone.get_webview_window("main") {
                            let diag = build_path_diagnostic(&app_clone);
                            show_error(&win, &e, &diag, LOG_FILE_PATH.get().map(|s| s.as_str()));
                        }
                    }
                }
            });

            Ok(())
        })
        .on_window_event(move |window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                // 阻止默认关闭行为
                api.prevent_close();
                // 通知前端显示关闭动画
                let _ = window.emit("close-requested", ());

                // 延迟 100ms 让关闭动画开始，然后关闭后端并退出
                let app_handle = window.app_handle().clone();
                tauri::async_runtime::spawn(async move {
                    tokio::time::sleep(std::time::Duration::from_millis(100)).await;

                    // 关闭后端进程
                    let data_dir = ensure_data_dir().ok();
                    if let Some(state) = app_handle.try_state::<BackendState>() {
                        if let Ok(mut guard) = state.child.lock() {
                            if let Some(ref mut child) = guard.take() {
                                let dir = data_dir.as_deref().unwrap_or(std::path::Path::new("."));
                                shutdown_backend(child, dir);
                            }
                        }
                    }
                    // 如果 child 句柄已丢失，尝试通过 PID 文件清理
                    if let Some(ref dir) = data_dir {
                        cleanup_stale_backend(dir);
                    }

                    log::info!("后端已关闭，退出应用");
                    // 先关闭窗口，再退出进程，避免 WebView2 窗口类注销报错
                    if let Some(win) = app_handle.get_webview_window("main") {
                        let _ = win.destroy();
                    }
                    std::process::exit(0);
                });
            }
        })
        .invoke_handler(tauri::generate_handler![check_backend_status, get_app_config, get_diagnostic_info])
        .run(tauri::generate_context!())
        .expect("启动 EMS Simulate 桌面客户端失败");
}
