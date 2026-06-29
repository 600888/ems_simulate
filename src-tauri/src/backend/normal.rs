use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

use tauri::{AppHandle, Manager};
use tauri_plugin_shell::process::CommandChild;
use tauri_plugin_shell::ShellExt;

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

fn ensure_data_dir(app: &AppHandle) -> String {
    // MSI 通常安装在 Program Files，exe 所在目录不可写。运行数据统一放到
    // Tauri 的用户级应用数据目录，避免后端刚拉起就因无法创建数据库/日志退出。
    let dir = app
        .path()
        .app_local_data_dir()
        .ok()
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

fn try_spawn_sidecar(app: &AppHandle, port: u16) -> Result<CommandChild, String> {
    let sidecar_cmd = app
        .shell()
        .sidecar("ems_simulate_backend")
        .map_err(|e| format!("无法定位后端 sidecar: {e}"))?;
    let data_dir = ensure_data_dir(app);

    let (_, child) = sidecar_cmd
        .args(["--port", &port.to_string()])
        .env("EMS_ROOT_DIR", &data_dir)
        .spawn()
        .map_err(|e| format!("后端 sidecar 启动失败: {e}"))?;

    eprintln!("[EMS] sidecar started, port={port}, data={data_dir}");
    Ok(child)
}

fn try_spawn_python_direct(port: u16) -> Result<Child, String> {
    let project_root = find_project_root().ok_or_else(|| "未找到 start_back_end.py".to_string())?;
    let data_dir = project_root.to_string_lossy().to_string();

    for sub in &["data", "log", "config", "upload", "plan"] {
        let _ = std::fs::create_dir_all(format!("{data_dir}/{sub}"));
    }

    let python_cmds = if cfg!(target_os = "windows") {
        vec!["python", "python3", "py"]
    } else {
        vec!["python3", "python"]
    };

    let mut errors = Vec::new();
    for py in &python_cmds {
        let mut cmd = new_detached_cmd(py);
        match cmd
            .args(["start_back_end.py", "--port", &port.to_string()])
            .env("EMS_ROOT_DIR", &data_dir)
            .current_dir(&project_root)
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
        {
            Ok(child) => {
                eprintln!(
                    "[EMS] direct python '{}' started, port={port}, root={data_dir}, pid={:?}",
                    py,
                    child.id()
                );
                return Ok(child);
            }
            Err(e) => errors.push(format!("{py}: {e}")),
        }
    }

    Err(format!("没有可用的 Python 解释器 ({})", errors.join("; ")))
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

fn spawn_backend_checked(app: &AppHandle, port: u16) -> Result<String, String> {
    *BACKEND_PORT.lock().unwrap() = port;
    *BACKEND_READY.lock().unwrap() = false;

    let url = health_url(port);
    let process = match try_spawn_sidecar(app, port) {
        Ok(child) => ProcessHandle::Sidecar(child),
        Err(sidecar_error) => {
            eprintln!("[EMS] {sidecar_error}; trying direct Python");
            try_spawn_python_direct(port)
                .map(ProcessHandle::Direct)
                .map_err(|python_error| format!("{sidecar_error}; {python_error}"))?
        }
    };

    *BACKEND_PROCESS.lock().unwrap() = Some(process);
    eprintln!("[EMS] backend process spawned on port {port}");
    Ok(url)
}

pub fn spawn_backend(app: &AppHandle) -> String {
    let port = get_available_port(8991);
    match spawn_backend_checked(app, port) {
        Ok(url) => url,
        Err(error) => {
            eprintln!("[EMS] cannot start backend: {error}");
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
            eprintln!("[EMS] backend startup timeout ({url})");
            *BACKEND_READY.lock().unwrap() = false;
            return false;
        }
        match client.get(url).send().await {
            Ok(resp) if resp.status().is_success() => {
                *BACKEND_READY.lock().unwrap() = true;
                eprintln!("[EMS] backend ready -> {url}");
                return true;
            }
            _ => tokio::time::sleep(Duration::from_millis(500)).await,
        }
    }
}

pub async fn is_backend_ready() -> Result<bool, String> {
    let port = *BACKEND_PORT.lock().map_err(|e| e.to_string())?;
    let client = reqwest::Client::builder()
        .connect_timeout(Duration::from_secs(1))
        .timeout(Duration::from_secs(2))
        .build()
        .map_err(|e| e.to_string())?;
    let ready = matches!(
        client.get(health_url(port)).send().await,
        Ok(resp) if resp.status().is_success()
    );
    if let Ok(mut g) = BACKEND_READY.lock() {
        *g = ready;
    }
    match ready {
        true => Ok(true),
        false => Ok(false),
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

pub fn restart(app: &AppHandle) -> Result<String, String> {
    let port = *BACKEND_PORT.lock().map_err(|e| e.to_string())?;
    stop();
    std::thread::sleep(Duration::from_millis(800));
    // 重启尽量复用原端口：WebView 当前页面来自这个 origin，切换端口会让
    // 页面仍指向已经失效的旧服务。
    for _ in 0..20 {
        if std::net::TcpListener::bind(("127.0.0.1", port)).is_ok() {
            return spawn_backend_checked(app, port);
        }
        std::thread::sleep(Duration::from_millis(100));
    }
    Err(format!("后端端口 {port} 未能释放，无法重启"))
}
