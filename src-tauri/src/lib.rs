mod backend;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_process::init())
        .setup(|app| {
            let handle = app.handle().clone();

            // 同步启动后端进程（立即注册到静态变量，窗口关闭时可立刻清理）
            backend::spawn_backend(&handle);

            // 异步等待后端就绪（loading 页面 JavaScript 通过 invoke 轮询 is_backend_ready）
            tauri::async_runtime::spawn(async move {
                backend::wait_backend_ready().await;
            });

            // 创建主窗口
            // 生产模式：先显示 loading 动画页面（由页面 JS 轮询后端就绪后自动跳转）
            // 开发模式：直接加载后端地址
            let url = if cfg!(debug_assertions) {
                tauri::WebviewUrl::External(
                    url::Url::parse("http://localhost:8991").unwrap(),
                )
            } else {
                tauri::WebviewUrl::App("index.html".into())
            };
            let window = tauri::WebviewWindowBuilder::new(
                app.handle(),
                "main",
                url,
            )
            .title("EMS Simulate")
            .inner_size(1280.0, 800.0)
            .min_inner_size(960.0, 600.0)
            .center()
            .resizable(true)
            .decorations(true)
            .build()
            .expect("创建主窗口失败");

            // 窗口关闭时：轻量清理
            window.on_window_event(move |event| {
                if let tauri::WindowEvent::CloseRequested { .. } = event {
                    eprintln!("[EMS] window close requested, fast cleanup");
                    backend::cleanup_managed_process();
                }
            });

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            backend::get_backend_url,
            backend::is_backend_ready,
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
