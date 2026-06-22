use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

use tauri::AppHandle;
use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::CommandChild;

// ── 全局状态 ──

static BACKEND_PROCESS: Mutex<Option<ProcessHandle>> = Mutex::new(None);
static BACKEND_PORT: Mutex<u16> = Mutex::new(8991);
static BACKEND_READY: Mutex<bool> = Mutex::new(false);

// ── 进程句柄 ──

enum ProcessHandle {
    Sidecar(CommandChild),
    Direct(Child),
}

impl ProcessHandle {
    fn kill(self) -> std::io::Result<()> {
        match self {
            ProcessHandle::Sidecar(c) => c
                .kill()
                .map_err(|e| std::io::Error::new(std::io::ErrorKind::Other, e)),
            ProcessHandle::Direct(mut c) => {
                kill_process_tree(c.id());
                let _ = c.kill();
                let _ = c.wait();
                Ok(())
            }
        }
    }
}

// ── 工具函数 ──

fn new_detached_cmd(program: &str) -> Command {
    let mut cmd = Command::new(program);
    #[cfg(target_os = "windows")]
    cmd.creation_flags(0x08000000 | 0x00000008); // CREATE_NO_WINDOW | DETACHED_PROCESS
    cmd
}

fn kill_process_tree(pid: u32) {
    if pid == 0 {
        return;
    }
    #[cfg(target_os = "windows")]
    {
        let _ = new_detached_cmd("taskkill")
            .args(["/F", "/T", "/PID", &pid.to_string()])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
    }
    #[cfg(not(target_os = "windows"))]
    {
        let _ = new_detached_cmd("kill")
            .args(["-TERM", &format!("-{pid}")])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
    }
}

fn get_available_port(start: u16) -> u16 {
    let mut port = start;
    loop {
        if std::net::TcpListener::bind(format!("127.0.0.1:{port}")).is_ok() {
            return port;
        }
        port += 1;
    }
}

fn health_url(port: u16) -> String {
    format!("http://127.0.0.1:{port}/api/health")
}

fn backend_base_url(port: u16) -> String {
    format!("http://127.0.0.1:{port}")
}

fn ensure_data_dir(_app: &AppHandle) -> String {
    let dir = std::env::current_exe()
        .ok()
        .and_then(|exe| exe.parent().map(|parent| parent.to_path_buf()))
        .or_else(|| std::env::current_dir().ok())
        .unwrap_or_else(|| std::path::PathBuf::from("."));

    for sub in &["", "data", "config", "upload", "plan", "log"] {
        let _ = std::fs::create_dir_all(dir.join(sub));
    }

    dir.to_string_lossy().to_string()
}

fn find_project_root() -> Option<std::path::PathBuf> {
    if let Ok(manifest_dir) = std::env::var("CARGO_MANIFEST_DIR") {
        let root = std::path::PathBuf::from(&manifest_dir);
        if let Some(parent) = root.parent() {
            let parent = parent.to_path_buf();
            if parent.join("start_back_end.py").exists() {
                return Some(parent);
            }
        }
    }
    if let Ok(cwd) = std::env::current_dir() {
        if cwd.join("start_back_end.py").exists() {
            return Some(cwd);
        }
        if let Some(parent) = cwd.parent() {
            let parent = parent.to_path_buf();
            if parent.join("start_back_end.py").exists() {
                return Some(parent);
            }
        }
    }
    None
}

fn try_spawn_sidecar(app: &AppHandle, port: u16) -> Option<CommandChild> {
    let sidecar_cmd = app.shell().sidecar("ems_simulate_backend").ok()?;
    let data_dir = ensure_data_dir(app);

    let (_, child) = sidecar_cmd
        .args(["--port", &port.to_string()])
        .env("EMS_ROOT_DIR", &data_dir)
        .spawn()
        .inspect_err(|e| eprintln!("[EMS] sidecar spawn failed: {e}"))
        .ok()?;

    eprintln!("[EMS] sidecar started, port={port}, data={data_dir}");
    Some(child)
}

fn try_spawn_python_direct(port: u16) -> Option<Child> {
    let project_root = find_project_root()?;
    let data_dir = project_root.to_string_lossy().to_string();

    for sub in &["data", "log", "config", "upload", "plan"] {
        let _ = std::fs::create_dir_all(format!("{data_dir}/{sub}"));
    }

    let python_cmds = if cfg!(target_os = "windows") {
        vec!["python", "python3", "py"]
    } else {
        vec!["python3", "python"]
    };

    for py in &python_cmds {
        let mut cmd = new_detached_cmd(py);
        let child = cmd
            .args(["start_back_end.py", "--port", &port.to_string()])
            .env("EMS_ROOT_DIR", &data_dir)
            .current_dir(&project_root)
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .inspect(|c| {
                eprintln!(
                    "[EMS] direct python '{}' started, port={port}, root={data_dir}, pid={:?}",
                    py,
                    c.id()
                )
            })
            .ok()?;
        return Some(child);
    }

    eprintln!("[EMS] no Python executable found in PATH");
    None
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
                            eprintln!("[EMS] killing process {pid} on port {port}");
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

// ── 公开 API ──

pub fn spawn_backend(app: &AppHandle) -> String {
    let port = get_available_port(8991);
    *BACKEND_PORT.lock().unwrap() = port;
    *BACKEND_READY.lock().unwrap() = false;

    let url = health_url(port);

    let process = try_spawn_sidecar(app, port)
        .map(ProcessHandle::Sidecar)
        .or_else(|| try_spawn_python_direct(port).map(ProcessHandle::Direct));

    if let Some(handle) = process {
        *BACKEND_PROCESS.lock().unwrap() = Some(handle);
        eprintln!("[EMS] backend process spawned on port {port}");
    } else {
        eprintln!("[EMS] cannot start backend, check Python environment");
    }

    url
}

pub async fn wait_backend_ready(url: &str) {
    let client = reqwest::Client::new();
    let start = std::time::Instant::now();
    let timeout = Duration::from_secs(15);

    loop {
        if start.elapsed() > timeout {
            eprintln!("[EMS] backend startup timeout ({url})");
            return;
        }
        match client.get(url).send().await {
            Ok(resp) if resp.status().is_success() => {
                *BACKEND_READY.lock().unwrap() = true;
                eprintln!("[EMS] backend ready -> {url}");
                return;
            }
            _ => tokio::time::sleep(Duration::from_millis(500)).await,
        }
    }
}

pub async fn is_backend_ready() -> Result<bool, String> {
    if let Ok(g) = BACKEND_READY.lock() {
        if *g {
            return Ok(true);
        }
    }
    let port = *BACKEND_PORT.lock().map_err(|e| e.to_string())?;
    match reqwest::get(&health_url(port)).await {
        Ok(resp) if resp.status().is_success() => {
            if let Ok(mut g) = BACKEND_READY.lock() {
                *g = true;
            }
            Ok(true)
        }
        _ => Ok(false),
    }
}

pub fn get_backend_url() -> Result<String, String> {
    let port = BACKEND_PORT.lock().map_err(|e| e.to_string())?;
    Ok(backend_base_url(*port))
}

pub fn cleanup() {
    let handle = { BACKEND_PROCESS.lock().unwrap().take() };
    if let Some(h) = handle {
        eprintln!("[EMS] killing managed process handle");
        let _ = h.kill();
    }
}

pub fn stop() {
    cleanup();

    let port = *BACKEND_PORT.lock().unwrap();
    if port > 0 {
        kill_processes_on_port(port);
    }

    *BACKEND_READY.lock().unwrap() = false;
}
