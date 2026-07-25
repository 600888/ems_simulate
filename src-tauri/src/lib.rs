mod backend;

use std::path::PathBuf;
use tauri::Manager;
use tauri_plugin_opener::OpenerExt;

fn resolve_directory(path: &str) -> Result<PathBuf, String> {
    let path = path.trim();
    if path.is_empty() {
        return Err("目录不能为空".to_string());
    }

    let directory = PathBuf::from(path)
        .canonicalize()
        .map_err(|error| format!("目录不存在或不可访问: {path} ({error})"))?;
    if !directory.is_dir() {
        return Err(format!("路径不是目录: {}", directory.display()));
    }

    Ok(directory)
}

#[tauri::command]
fn open_directory(app: tauri::AppHandle, path: String) -> Result<(), String> {
    let directory = resolve_directory(&path)?;

    app.opener()
        .open_path(directory.to_string_lossy(), None::<&str>)
        .map_err(|error| format!("打开目录失败: {error}"))
}

#[cfg(test)]
mod tests {
    use super::resolve_directory;

    #[test]
    fn directory_path_must_not_be_empty() {
        assert!(resolve_directory("   ").is_err());
    }

    #[test]
    fn existing_directory_is_canonicalized() {
        let current = std::env::current_dir().unwrap();
        assert_eq!(
            resolve_directory(current.to_str().unwrap()).unwrap(),
            current.canonicalize().unwrap()
        );
    }

    #[test]
    fn existing_file_is_rejected() {
        let executable = std::env::current_exe().unwrap();
        assert!(resolve_directory(executable.to_str().unwrap()).is_err());
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        // 必须最先注册：第二次启动在 setup 之前退出，避免重复拉起共享数据后端。
        .plugin(tauri_plugin_single_instance::init(
            |app, _args, _working_directory| {
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.unminimize();
                    let _ = window.show();
                    let _ = window.set_focus();
                }
            },
        ))
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_process::init())
        .setup(|app| {
            let handle = app.handle().clone();

            // 同步启动后端进程，返回健康检查 URL（生产=sidecar，开发=直连 Python）
            let health_url = backend::spawn_backend(&handle);

            // 异步等待后端就绪（loading 页面 JS 同时通过 invoke 轮询 is_backend_ready）
            tauri::async_runtime::spawn(async move {
                let _ = backend::wait_backend_ready(&health_url).await;
            });

            // 后端异常退出时及时刷新 Rust 侧状态，重启命令不再被旧 READY 状态误导。
            tauri::async_runtime::spawn(backend::monitor_backend());

            // 窗口由 tauri.conf.json 自动创建（visible=false + backgroundColor 消除白屏），
            // 延迟 show() 等 CSS 渲染完成后再显示，消除纯色→渐变的视觉跳跃
            let window = app
                .get_webview_window("main")
                .expect("main 窗口未找到，请检查 tauri.conf.json 的 windows 配置");

            let w = window.clone();
            tauri::async_runtime::spawn(async move {
                tokio::time::sleep(std::time::Duration::from_millis(50)).await;
                let _ = w.show();
            });

            let app_handle = app.handle().clone();
            window.on_window_event(move |event| {
                if let tauri::WindowEvent::CloseRequested { .. } = event {
                    eprintln!("[EMS] window close requested, fast cleanup");
                    backend::cleanup_managed_process();
                    // 独立报文窗口存在时，关闭主窗口也应退出整个应用。
                    app_handle.exit(0);
                }
            });

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            backend::get_backend_url,
            backend::is_backend_ready,
            backend::restart_backend,
            open_directory,
        ])
        .build(tauri::generate_context!())
        .expect("启动 EMS Simulate 失败");

    // 应用退出时确保后端进程被终止
    app.run(|_app_handle, event| match event {
        tauri::RunEvent::ExitRequested { .. } => {
            eprintln!("[EMS] ExitRequested, stopping backend");
            backend::stop_backend();
        }
        tauri::RunEvent::Exit => {
            eprintln!("[EMS] Exit, final cleanup");
            backend::stop_backend();
        }
        _ => {}
    });
}
