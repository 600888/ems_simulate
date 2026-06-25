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

const MSIX_PORT: u16 = 8991;
static MSIX_HANDLE: Mutex<Option<Child>> = Mutex::new(None);
static MSIX_READY: Mutex<bool> = Mutex::new(false);

// ── 工具函数 ──

fn new_detached_cmd(program: &str) -> Command {
    let mut cmd = Command::new(program);
    #[cfg(target_os = "windows")]
    cmd.creation_flags(0x08000000); // CREATE_NO_WINDOW — 不分配控制台，进程静默后台运行
    cmd
}

fn health_url() -> String {
    format!("http://127.0.0.1:{MSIX_PORT}/api/health")
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

fn try_spawn(data_dir: &str) -> Option<Child> {
    let binary_path = find_sidecar()?;
    let port = MSIX_PORT.to_string();

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
        .inspect_err(|e| eprintln!("[EMS:msix] spawn failed: {e}"))
        .ok()?;

    eprintln!("[EMS:msix] spawned, pid={:?}", child.id());
    Some(child)
}

// ── 公开 API ──

pub fn spawn_backend(app: &AppHandle) -> String {
    *MSIX_READY.lock().unwrap() = false;

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

    if let Some(child) = try_spawn(&data_dir) {
        *MSIX_HANDLE.lock().unwrap() = Some(child);
        eprintln!("[EMS:msix] backend process spawned");
    } else {
        eprintln!("[EMS:msix] cannot start backend binary");
    }

    health_url()
}

pub async fn wait_backend_ready() {
    let client = reqwest::Client::new();
    let url = health_url();
    let start = std::time::Instant::now();
    let timeout = Duration::from_secs(15);

    loop {
        if start.elapsed() > timeout {
            eprintln!("[EMS:msix] backend startup timeout ({url})");
            return;
        }
        match client.get(&url).send().await {
            Ok(resp) if resp.status().is_success() => {
                *MSIX_READY.lock().unwrap() = true;
                eprintln!("[EMS:msix] backend ready");
                return;
            }
            _ => tokio::time::sleep(Duration::from_millis(500)).await,
        }
    }
}

pub async fn is_backend_ready() -> bool {
    if let Ok(guard) = MSIX_READY.lock() {
        if *guard {
            return true;
        }
    }

    match reqwest::get(&health_url()).await {
        Ok(resp) if resp.status().is_success() => {
            if let Ok(mut guard) = MSIX_READY.lock() {
                *guard = true;
            }
            eprintln!("[EMS:msix] backend ready (fallback health check)");
            true
        }
        _ => false,
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
    kill_processes_on_port(MSIX_PORT);
    *MSIX_READY.lock().unwrap() = false;
}

pub fn restart(app: &AppHandle) -> String {
    stop();
    std::thread::sleep(Duration::from_millis(800));
    spawn_backend(app)
}

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
