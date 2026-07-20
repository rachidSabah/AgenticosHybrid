use tauri::Manager;

/// Launch the backend server as a sidecar subprocess.
fn launch_backend(app: &tauri::AppHandle) -> Option<std::process::Child> {
    let backend_path = app
        .path()
        .resource_dir()
        .ok()?
        .join("backend")
        .join("agentic_os.exe");

    if !backend_path.exists() {
        return None;
    }

    std::process::Command::new(&backend_path)
        .args(["serve", "--port", "8000"])
        .spawn()
        .ok()
}

#[tauri::command]
fn get_app_version() -> String {
    "1.0.0-rc1 (build 1)".to_string()
}

#[tauri::command]
fn get_backend_status(_app: tauri::AppHandle) -> Result<(), String> {
    std::net::TcpStream::connect("127.0.0.1:8000")
        .map(|_| ())
        .map_err(|e| format!("Backend unreachable: {}", e))
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_window_state::Builder::default().build())
        .setup(|app| {
            // Auto-launch backend if embedded binary exists
            let _backend = launch_backend(app.handle());
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_app_version,
            get_backend_status,
        ])
        .run(tauri::generate_context!())
        .expect("error while running AgenticOS Desktop Runtime");
}
