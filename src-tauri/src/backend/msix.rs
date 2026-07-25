use std::fs::File;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

use tauri::AppHandle;
use tauri::Manager;

// ── 全局状态 ──

static MSIX_PORT: Mutex<u16> = Mutex::new(0);
static MSIX_HANDLE: Mutex<Option<Child>> = Mutex::new(None);
static MSIX_READY: Mutex<bool> = Mutex::new(false);
static HEALTH_FAILURES: Mutex<u8> = Mutex::new(0);

// ── 工具函数 ──

fn new_detached_cmd(program: &str) -> Command {
    let mut cmd = Command::new(program);
    #[cfg(target_os = "windows")]
    cmd.creation_flags(0x08000000); // CREATE_NO_WINDOW — 不分配控制台，进程静默后台运行
    cmd
}

fn health_url(port: u16) -> String {
    format!("http://127.0.0.1:{port}/api/health")
}

fn backend_base_url(port: u16) -> String {
    format!("http://127.0.0.1:{port}")
}

fn is_process_alive() -> bool {
    MSIX_HANDLE
        .lock()
        .map(|mut child| {
            child
                .as_mut()
                .is_some_and(|process| matches!(process.try_wait(), Ok(None)))
        })
        .unwrap_or(false)
}

fn find_sidecar() -> Option<PathBuf> {
    let binary_name = "ems_simulate_backend";

    let exe_path = std::env::current_exe().ok()?;
    let exe_dir = exe_path.parent()?;

    let base_dir = if exe_dir.ends_with("deps") {
        exe_dir.parent().unwrap_or(exe_dir)
    } else {
        exe_dir
    };

    // 1) <exe_dir>/<name>.exe
    let mut primary = base_dir.join(binary_name);
    #[cfg(target_os = "windows")]
    {
        let already_exe = primary.extension().is_some_and(|ext| ext == "exe");
        if !already_exe {
            primary.as_mut_os_string().push(".exe");
        }
    }
    if primary.is_file() {
        eprintln!("[EMS:msix] sidecar found at primary: {}", primary.display());
        return Some(primary);
    }

    // 2) <exe_dir>/binaries/ 子目录
    let binaries_dir = base_dir.join("binaries");
    if let Some(found) = find_in_dir(&binaries_dir, binary_name) {
        eprintln!(
            "[EMS:msix] sidecar found in binaries dir: {}",
            found.display()
        );
        return Some(found);
    }

    // 3) <exe_dir>/ 下 target-triple 后缀
    if let Some(found) = find_in_dir(base_dir, binary_name) {
        eprintln!("[EMS:msix] sidecar found in exe dir: {}", found.display());
        return Some(found);
    }

    // 4) 开发模式
    if let Ok(manifest_dir) = std::env::var("CARGO_MANIFEST_DIR") {
        let dev_dir = PathBuf::from(&manifest_dir).join("binaries");
        if let Some(found) = find_in_dir(&dev_dir, binary_name) {
            eprintln!("[EMS:msix] sidecar found in dev dir: {}", found.display());
            return Some(found);
        }
    }

    eprintln!("[EMS:msix] sidecar not found");
    None
}

fn find_in_dir(dir: &std::path::Path, base_name: &str) -> Option<PathBuf> {
    let entries = std::fs::read_dir(dir).ok()?;
    for entry in entries.filter_map(|e| e.ok()) {
        let name = entry.file_name();
        let name_str = name.to_string_lossy();
        if name_str.starts_with(base_name) {
            let path = entry.path();
            if path.is_file() {
                return Some(path);
            }
        }
    }
    None
}

fn try_spawn(data_dir: &str, selected_port: u16) -> Result<Child, String> {
    let binary_path = find_sidecar().ok_or_else(|| "未找到后端 sidecar 可执行文件".to_string())?;
    let port = selected_port.to_string();

    let log_dir = std::path::Path::new(data_dir).join("log");
    let _ = std::fs::create_dir_all(&log_dir);

    let stdout_file = File::create(log_dir.join("backend_stdout.log")).ok();
    let stderr_file = File::create(log_dir.join("backend_stderr.log")).ok();

    eprintln!(
        "[EMS:msix] spawning: {} --port {port}",
        binary_path.display()
    );
    eprintln!("[EMS:msix] data_dir={data_dir}");

    let mut cmd = new_detached_cmd(&binary_path.to_string_lossy());
    cmd.args(["--port", &port]).env("EMS_ROOT_DIR", data_dir);

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
        .map_err(|e| format!("后端 sidecar 启动失败: {e}"))?;

    eprintln!("[EMS:msix] spawned, pid={:?}", child.id());
    Ok(child)
}

// ── 公开 API ──

fn spawn_backend_checked(app: &AppHandle, port: u16) -> Result<String, String> {
    *MSIX_PORT.lock().unwrap() = port;
    *MSIX_READY.lock().unwrap() = false;
    *HEALTH_FAILURES.lock().unwrap() = 0;

    let data_dir = if let Ok(dir) = app.path().app_local_data_dir() {
        for sub in &["", "data", "config", "upload", "plan", "log"] {
            let _ = std::fs::create_dir_all(dir.join(sub));
        }
        dir.to_string_lossy().to_string()
    } else if let Ok(exe) = std::env::current_exe() {
        if let Some(parent) = exe.parent() {
            parent.to_string_lossy().to_string()
        } else {
            ".".to_string()
        }
    } else {
        ".".to_string()
    };

    let child = try_spawn(&data_dir, port)?;
    *MSIX_HANDLE.lock().unwrap() = Some(child);
    eprintln!("[EMS:msix] backend process spawned");

    Ok(health_url(port))
}

pub fn spawn_backend(app: &AppHandle) -> String {
    let port = match super::get_available_port() {
        Ok(port) => port,
        Err(error) => {
            eprintln!("[EMS:msix] cannot allocate backend port: {error}");
            return health_url(0);
        }
    };
    match spawn_backend_checked(app, port) {
        Ok(url) => url,
        Err(error) => {
            eprintln!("[EMS:msix] cannot start backend binary: {error}");
            health_url(port)
        }
    }
}

pub async fn wait_backend_ready(url: &str) -> bool {
    let client = reqwest::Client::builder()
        .connect_timeout(Duration::from_secs(1))
        .timeout(Duration::from_secs(2))
        .build()
        .unwrap_or_else(|_| reqwest::Client::new());
    let start = std::time::Instant::now();
    let timeout = Duration::from_secs(15);

    loop {
        if start.elapsed() > timeout {
            eprintln!("[EMS:msix] backend startup timeout ({url})");
            *MSIX_READY.lock().unwrap() = false;
            return false;
        }
        match client.get(url).send().await {
            Ok(resp) if resp.status().is_success() => {
                *MSIX_READY.lock().unwrap() = true;
                *HEALTH_FAILURES.lock().unwrap() = 0;
                eprintln!("[EMS:msix] backend ready");
                return true;
            }
            _ => tokio::time::sleep(Duration::from_millis(500)).await,
        }
    }
}

pub async fn is_backend_ready() -> bool {
    let process_alive = is_process_alive();
    let port = *MSIX_PORT.lock().unwrap();
    let client = reqwest::Client::builder()
        .connect_timeout(Duration::from_secs(1))
        .timeout(Duration::from_secs(2))
        .build()
        .unwrap_or_else(|_| reqwest::Client::new());
    let health_ok = matches!(
        client.get(health_url(port)).send().await,
        Ok(resp) if resp.status().is_success()
    );
    let was_ready = *MSIX_READY.lock().unwrap();
    let failures = *HEALTH_FAILURES.lock().unwrap();
    let (ready, next_failures) =
        super::evaluate_backend_status(process_alive, health_ok, was_ready, failures);

    *MSIX_READY.lock().unwrap() = ready;
    *HEALTH_FAILURES.lock().unwrap() = next_failures;
    ready
}

pub fn refresh_process_status() {
    if !is_process_alive() {
        *MSIX_READY.lock().unwrap() = false;
        *HEALTH_FAILURES.lock().unwrap() = 0;
    }
}

pub fn cleanup() {
    if let Some(mut child) = MSIX_HANDLE.lock().unwrap().take() {
        let _ = child.kill();
        let _ = child.wait();
        eprintln!("[EMS:msix] managed process killed");
    }
}

pub fn stop() {
    cleanup();
    *MSIX_READY.lock().unwrap() = false;
    *HEALTH_FAILURES.lock().unwrap() = 0;
}

pub fn restart(app: &AppHandle) -> Result<String, String> {
    let port = *MSIX_PORT.lock().map_err(|e| e.to_string())?;
    stop();
    std::thread::sleep(Duration::from_millis(800));
    for _ in 0..20 {
        if std::net::TcpListener::bind(("127.0.0.1", port)).is_ok() {
            return spawn_backend_checked(app, port);
        }
        std::thread::sleep(Duration::from_millis(100));
    }
    Err(format!("后端端口 {port} 未能释放，无法重启"))
}

pub fn get_backend_url() -> Result<String, String> {
    let port = *MSIX_PORT.lock().map_err(|e| e.to_string())?;
    if port == 0 {
        return Err("后端端口尚未分配".to_string());
    }
    Ok(backend_base_url(port))
}
