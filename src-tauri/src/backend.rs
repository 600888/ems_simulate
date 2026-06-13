use std::fs::File;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

use tauri::AppHandle;
use tauri::Manager;

/// 创建一个不会弹出控制台窗口的命令
/// Windows 上使用 CREATE_NO_WINDOW | DETACHED_PROCESS 彻底阻止控制台闪现
fn new_detached_cmd(program: &str) -> Command {
    let mut cmd = Command::new(program);
    #[cfg(target_os = "windows")]
    cmd.creation_flags(0x08000000 | 0x00000008); // CREATE_NO_WINDOW | DETACHED_PROCESS
    cmd
}

// ── 状态管理（全局静态变量，避免 Tauri managed state 的复杂查找） ──

/// 后端进程句柄
static BACKEND_HANDLE: Mutex<Option<Child>> = Mutex::new(None);
static BACKEND_READY: Mutex<bool> = Mutex::new(false);

// ── 端口 ──

const DEFAULT_PORT: u16 = 8991;
const HEALTH_PATH: &str = "/api/health";

fn health_url() -> String {
    format!("http://127.0.0.1:{DEFAULT_PORT}{HEALTH_PATH}")
}

/// 向后端返回后端 URL
#[tauri::command]
pub fn get_backend_url() -> Result<String, String> {
    Ok(backend_base_url())
}

/// 获取后端基础 URL（非 command，供内部使用）
pub fn backend_base_url() -> String {
    format!("http://127.0.0.1:{DEFAULT_PORT}")
}

/// 检查后端是否已就绪（带兜底直连健康检查，应对 wait_backend_ready 超时后后端才就绪的场景）
#[tauri::command]
pub async fn is_backend_ready() -> Result<bool, String> {
    // 快速路径：Rust 侧轮询已确认就绪
    if let Ok(guard) = BACKEND_READY.lock() {
        if *guard {
            return Ok(true);
        }
    }

    // 慢速路径：直接探测健康检查端点（应对 wait_backend_ready 超时等情况）
    match reqwest::get(&health_url()).await {
        Ok(resp) if resp.status().is_success() => {
            // 更新全局状态
            if let Ok(mut guard) = BACKEND_READY.lock() {
                *guard = true;
            }
            eprintln!("[EMS] backend ready (detected via fallback health check)");
            Ok(true)
        }
        _ => Ok(false),
    }
}

// ── 确保数据目录 ──

fn ensure_data_dir(app: &AppHandle) -> String {
    // 优先使用 Tauri 提供的 app_local_data_dir
    if let Ok(dir) = app.path().app_local_data_dir() {
        for sub in &["", "data", "config", "upload", "plan", "logs"] {
            let _ = std::fs::create_dir_all(dir.join(sub));
        }
        return dir.to_string_lossy().to_string();
    }
    // 回退到 exe 目录
    if let Ok(exe) = std::env::current_exe() {
        if let Some(parent) = exe.parent() {
            return parent.to_string_lossy().to_string();
        }
    }
    ".".to_string()
}

// ── 后端进程启动 ──

/// 同步启动后端进程（在 setup 中调用，确保窗口打开前已注册句柄）
pub fn spawn_backend(app: &AppHandle) {
    *BACKEND_READY.lock().unwrap() = false;
    let data_dir = ensure_data_dir(app);

    if let Some(child) = try_spawn_backend_process(&data_dir) {
        *BACKEND_HANDLE.lock().unwrap() = Some(child);
        eprintln!("[EMS] backend process spawned (no console window)");
    } else {
        eprintln!("[EMS] cannot start backend binary");
    }
}

/// 查找 sidecar 二进制文件路径
///
/// 与 Tauri shell plugin 的 `relative_command_path` 保持一致的解析逻辑：
/// 优先在 exe 同级目录查找，再回退到 binaries/ 子目录和开发模式路径。
fn find_sidecar_binary() -> Option<std::path::PathBuf> {
    let binary_name = "ems_simulate_backend";

    let exe_path = std::env::current_exe().ok()?;
    let exe_dir = exe_path.parent()?;

    // 处理 deps 目录（测试场景），与 Tauri 行为一致
    let base_dir = if exe_dir.ends_with("deps") {
        exe_dir.parent().unwrap_or(exe_dir)
    } else {
        exe_dir
    };

    // 1) 与 Tauri 行为一致：`<exe_dir>/<name>.exe`（生产安装路径）
    let mut primary = base_dir.join(binary_name);
    #[cfg(target_os = "windows")]
    {
        let already_exe = primary.extension().is_some_and(|ext| ext == "exe");
        if !already_exe {
            primary.as_mut_os_string().push(".exe");
        }
    }
    if primary.is_file() {
        eprintln!("[EMS] sidecar found at primary path: {}", primary.display());
        return Some(primary);
    }

    // 2) 回退：`<exe_dir>/binaries/` 子目录（MSI 备选路径，支持 target-triple 后缀）
    let binaries_dir = base_dir.join("binaries");
    if let Some(found) = find_in_dir(&binaries_dir, binary_name) {
        eprintln!("[EMS] sidecar found in binaries dir: {}", found.display());
        return Some(found);
    }

    // 3) 回退：`<exe_dir>/` 目录下 target-triple 后缀的文件
    if let Some(found) = find_in_dir(base_dir, binary_name) {
        eprintln!("[EMS] sidecar found in exe dir: {}", found.display());
        return Some(found);
    }

    // 4) 开发模式：`<CARGO_MANIFEST_DIR>/binaries/` 下的匹配文件
    if let Ok(manifest_dir) = std::env::var("CARGO_MANIFEST_DIR") {
        let dev_dir = std::path::PathBuf::from(&manifest_dir).join("binaries");
        if let Some(found) = find_in_dir(&dev_dir, binary_name) {
            eprintln!("[EMS] sidecar found in dev dir: {}", found.display());
            return Some(found);
        }
    }

    eprintln!(
        "[EMS] sidecar binary not found. Searched: primary={}, binaries={}, dev binaries",
        primary.display(),
        binaries_dir.display()
    );
    None
}

/// 在目录中查找以 `base_name` 开头的可执行文件
fn find_in_dir(dir: &std::path::Path, base_name: &str) -> Option<std::path::PathBuf> {
    let entries = std::fs::read_dir(dir).ok()?;
    for entry in entries.filter_map(|e| e.ok()) {
        let name = entry.file_name();
        let name_str = name.to_string_lossy();
        if name_str.starts_with(base_name) {
            let path = entry.path();
            // 跳过非文件（如目录）
            if path.is_file() {
                return Some(path);
            }
        }
    }
    None
}

/// 使用 new_detached_cmd 启动后端，避免 Windows 上弹出控制台窗口
/// stdout/stderr 重定向到日志文件，便于排查启动失败原因
fn try_spawn_backend_process(data_dir: &str) -> Option<Child> {
    let binary_path = find_sidecar_binary()?;
    let port = DEFAULT_PORT.to_string();

    // 确保 logs 目录存在
    let log_dir = std::path::Path::new(data_dir).join("logs");
    let _ = std::fs::create_dir_all(&log_dir);

    let stdout_file = File::create(log_dir.join("backend_stdout.log")).ok();
    let stderr_file = File::create(log_dir.join("backend_stderr.log")).ok();

    eprintln!(
        "[EMS] spawning backend: {} --port {port}",
        binary_path.display()
    );
    eprintln!("[EMS] data_dir={data_dir}, logs at {}", log_dir.display());

    let mut cmd = new_detached_cmd(&binary_path.to_string_lossy());
    cmd.args(["--port", &port]).env("EMS_ROOT_DIR", data_dir);

    // 重定向到日志文件（而非 null），便于排查
    if let Some(f) = stdout_file {
        cmd.stdout(f);
    } else {
        cmd.stdout(Stdio::null());
    }
    if let Some(f) = stderr_file {
        cmd.stderr(f);
    } else {
        cmd.stderr(Stdio::null());
    }

    let child = cmd
        .spawn()
        .inspect_err(|e| eprintln!("[EMS] failed to spawn backend: {e}"))
        .ok()?;

    eprintln!("[EMS] backend process spawned, pid={:?}", child.id());
    Some(child)
}

// ── 健康检查 ──

/// 异步轮询等待后端就绪（10s 与前端一致，避免后端启动慢时过早放弃）
pub async fn wait_backend_ready() {
    let client = reqwest::Client::new();
    let url = health_url();
    let start = std::time::Instant::now();
    let timeout = Duration::from_secs(10);

    loop {
        if start.elapsed() > timeout {
            eprintln!("[EMS] backend startup timeout ({url})");
            return;
        }
        match client.get(&url).send().await {
            Ok(resp) if resp.status().is_success() => {
                *BACKEND_READY.lock().unwrap() = true;
                eprintln!("[EMS] backend ready");
                return;
            }
            _ => tokio::time::sleep(Duration::from_millis(500)).await,
        }
    }
}

// ── 进程清理 ──

/// 轻量清理：仅杀死已管理的进程句柄（窗口 CloseRequested 时调用，不阻塞 GUI）
pub fn cleanup_managed_process() {
    if let Some(mut child) = BACKEND_HANDLE.lock().unwrap().take() {
        let _ = child.kill();
        let _ = child.wait();
        eprintln!("[EMS] managed process killed");
    }
}

/// 完整清理：杀死进程 + 端口清扫（Exit 事件时调用）
pub fn stop_backend() {
    cleanup_managed_process();
    kill_processes_on_port(DEFAULT_PORT);
    *BACKEND_READY.lock().unwrap() = false;
}

/// 强制杀死占用指定端口的全部进程
fn kill_processes_on_port(port: u16) {
    #[cfg(target_os = "windows")]
    {
        let output = new_detached_cmd("netstat")
            .args(["-ano"])
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .output()
            .ok();
        if let Some(out) = output {
            let stdout = String::from_utf8_lossy(&out.stdout);
            let port_str = format!(":{port}");
            for line in stdout.lines() {
                if line.contains(&port_str) && line.contains("LISTENING") {
                    if let Some(pid_str) = line.split_whitespace().last() {
                        if let Ok(pid) = pid_str.parse::<u32>() {
                            let _ = new_detached_cmd("taskkill")
                                .args(["/F", "/PID", &pid.to_string()])
                                .stdout(Stdio::null())
                                .stderr(Stdio::null())
                                .status();
                        }
                    }
                }
            }
        }
    }
    #[cfg(not(target_os = "windows"))]
    {
        let _ = new_detached_cmd("fuser")
            .args(["-k", &format!("{port}/tcp")])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
    }
}
