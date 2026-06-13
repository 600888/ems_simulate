use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

use tauri::AppHandle;
use tauri::Manager;
use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::CommandChild;

// ── 无控制台命令创建 ──

/// 创建一个不会弹出控制台窗口的命令
/// Windows: CREATE_NO_WINDOW | DETACHED_PROCESS
fn new_detached_cmd(program: &str) -> Command {
    let mut cmd = Command::new(program);
    #[cfg(target_os = "windows")]
    cmd.creation_flags(0x08000000 | 0x00000008); // CREATE_NO_WINDOW | DETACHED_PROCESS
    cmd
}

// ── 统一进程句柄 ──

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

// ── 进程树清理 ──

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

// ── 全局状态 ──

static BACKEND_PROCESS: Mutex<Option<ProcessHandle>> = Mutex::new(None);
static BACKEND_PORT: Mutex<u16> = Mutex::new(8991);
static BACKEND_READY: Mutex<bool> = Mutex::new(false);

// ── 动态端口 ──

fn get_available_port(start: u16) -> u16 {
    let mut port = start;
    loop {
        if std::net::TcpListener::bind(format!("127.0.0.1:{port}")).is_ok() {
            return port;
        }
        port += 1;
    }
}

// ── 健康检查 ──

fn health_url(port: u16) -> String {
    format!("http://127.0.0.1:{port}/api/health")
}

fn backend_base_url(port: u16) -> String {
    format!("http://127.0.0.1:{port}")
}

// ── Tauri commands ──

/// 向前端返回后端 URL
#[tauri::command]
pub fn get_backend_url() -> Result<String, String> {
    let port = BACKEND_PORT.lock().map_err(|e| e.to_string())?;
    Ok(backend_base_url(*port))
}

/// 检查后端是否已就绪（带兜底直连健康检查）
#[tauri::command]
pub async fn is_backend_ready() -> Result<bool, String> {
    // 快速路径
    if let Ok(g) = BACKEND_READY.lock() {
        if *g {
            return Ok(true);
        }
    }
    // 慢速路径：直连探测
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

// ── 数据目录 ──

fn ensure_data_dir(app: &AppHandle) -> String {
    if let Ok(dir) = app.path().app_local_data_dir() {
        for sub in &["", "data", "config", "upload", "plan", "logs"] {
            let _ = std::fs::create_dir_all(dir.join(sub));
        }
        return dir.to_string_lossy().to_string();
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(parent) = exe.parent() {
            return parent.to_string_lossy().to_string();
        }
    }
    ".".to_string()
}

/// 查找项目根目录（开发模式直连 python 时使用）
fn find_project_root() -> Option<std::path::PathBuf> {
    // CARGO_MANIFEST_DIR = src-tauri, 项目根 = 上一级
    if let Ok(manifest_dir) = std::env::var("CARGO_MANIFEST_DIR") {
        let root = std::path::PathBuf::from(&manifest_dir);
        if let Some(parent) = root.parent() {
            let parent = parent.to_path_buf();
            if parent.join("start_back_end.py").exists() {
                return Some(parent);
            }
        }
    }
    // 回退：当前目录或上级
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

// ── 后端进程启动 ──

/// 同步启动后端进程并注册到静态变量，返回健康检查 URL
pub fn spawn_backend(app: &AppHandle) -> String {
    let port = get_available_port(8991);
    *BACKEND_PORT.lock().unwrap() = port;
    *BACKEND_READY.lock().unwrap() = false;

    let url = health_url(port);

    // 优先 sidecar（打包后），否则直接启动 Python（开发模式）
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

/// 通过 Tauri shell 插件启动 sidecar（生产模式）
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

/// 开发模式下直接启动 Python 后端
fn try_spawn_python_direct(port: u16) -> Option<Child> {
    let project_root = find_project_root()?;
    let data_dir = project_root.to_string_lossy().to_string();

    // 确保数据目录存在
    for sub in &["data", "logs", "config", "upload", "plan"] {
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

// ── 健康检查轮询 ──

/// 异步轮询等待后端就绪
pub async fn wait_backend_ready(url: &str) {
    let client = reqwest::Client::new();
    let start = std::time::Instant::now();
    let timeout = Duration::from_secs(10);

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

// ── 进程清理 ──

/// 轻量清理：仅杀死已管理的进程句柄（CloseRequested 时调用，不阻塞 GUI）
pub fn cleanup_managed_process() {
    let handle = { BACKEND_PROCESS.lock().unwrap().take() };
    if let Some(h) = handle {
        eprintln!("[EMS] killing managed process handle");
        let _ = h.kill();
    }
}

/// 完整清理：杀死进程树 + 端口清扫（Exit 事件时调用）
pub fn stop_backend() {
    cleanup_managed_process();

    let port = *BACKEND_PORT.lock().unwrap();
    if port > 0 {
        kill_processes_on_port(port);
    }

    *BACKEND_READY.lock().unwrap() = false;
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
