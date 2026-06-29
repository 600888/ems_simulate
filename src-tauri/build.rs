fn main() {
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&[
            "get_backend_url",
            "is_backend_ready",
            "restart_backend",
        ]),
    ))
    .expect("failed to build Tauri application manifest")
}
