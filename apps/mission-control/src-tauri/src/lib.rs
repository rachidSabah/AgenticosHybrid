use std::env::current_exe;
use std::fs::{create_dir_all, File, OpenOptions};
use std::io::{Read, Write};
use std::net::TcpStream;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use tauri::Manager;

struct BackendState {
    child: Mutex<Option<Child>>,
    log_path: PathBuf,
    startup_log: PathBuf,
}

#[cfg(target_os = "windows")]
fn configure_dll_directory(res_dir: &Path) {
    use std::os::windows::ffi::OsStrExt;
    let wide: Vec<u16> = res_dir
        .as_os_str()
        .encode_wide()
        .chain(std::iter::once(0))
        .collect();
    unsafe {
        windows_sys::Win32::System::LibraryLoader::SetDllDirectoryW(wide.as_ptr());
    }
}

#[cfg(not(target_os = "windows"))]
fn configure_dll_directory(_res_dir: &Path) {}

fn log_startup_event(log_path: &Path, message: &str) {
    if let Ok(mut file) = OpenOptions::new().create(true).append(true).open(log_path) {
        let timestamp = chrono::Local::now().format("%Y-%m-%d %H:%M:%S");
        let _ = writeln!(file, "[{}] {}", timestamp, message);
    }
}

fn get_log_directory(app: &tauri::AppHandle) -> PathBuf {
    app.path()
        .app_log_dir()
        .unwrap_or_else(|_| std::env::temp_dir().join("AgenticOS").join("logs"))
}

fn launch_backend(app: &tauri::AppHandle) -> (Option<Child>, PathBuf, PathBuf) {
    let log_dir = get_log_directory(app);
    let _ = create_dir_all(&log_dir);

    let startup_log = log_dir.join("startup.log");
    let backend_log_path = log_dir.join("backend.log");

    log_startup_event(&startup_log, "Desktop Runtime Starting...");

    let res_dir = match app.path().resource_dir() {
        Ok(dir) => dir,
        Err(e) => {
            log_startup_event(
                &startup_log,
                &format!("✗ Failed to resolve resource directory: {}", e),
            );
            return (None, backend_log_path, startup_log);
        }
    };

    log_startup_event(
        &startup_log,
        &format!("✓ Resource Directory: {}", res_dir.display()),
    );
    configure_dll_directory(&res_dir);

    let backend_dir = res_dir.join("backend");
    let candidates = [
        backend_dir.join("agentic_os.exe"),
        backend_dir.join("agentic-os.exe"),
    ];

    let current = current_exe().ok();

    let mut backend_path: Option<PathBuf> = None;
    for candidate in &candidates {
        if candidate.exists() {
            if let Some(ref curr) = current {
                if candidate == curr {
                    log_startup_event(
                        &startup_log,
                        &format!(
                            "✗ Candidate {} is the running executable — skipping to prevent self-launch",
                            candidate.display()
                        ),
                    );
                    continue;
                }
            }
            backend_path = Some(candidate.clone());
            break;
        }
    }

    // Fallback: search alongside the running EXE (portable mode)
    if backend_path.is_none() {
        if let Some(ref curr) = current {
            if let Some(exe_dir) = curr.parent() {
                let fallback_candidates = [
                    exe_dir.join("backend").join("agentic_os.exe"),
                    exe_dir.join("backend").join("agentic-os.exe"),
                    exe_dir.join("agentic_os.exe"),
                    exe_dir.join("agentic-os.exe"),
                ];
                for candidate in &fallback_candidates {
                    if candidate.exists() && candidate != curr {
                        log_startup_event(
                            &startup_log,
                            &format!(
                                "✓ Backend found alongside EXE (portable mode): {}",
                                candidate.display()
                            ),
                        );
                        backend_path = Some(candidate.clone());
                        break;
                    }
                }
                if backend_path.is_none() {
                    log_startup_event(
                        &startup_log,
                        "✗ No backend found alongside EXE either",
                    );
                }
            }
        }
    }

    let exe_path = match backend_path {
        Some(p) => {
            log_startup_event(
                &startup_log,
                &format!("✓ Launching Backend: {}", p.display()),
            );
            p
        }
        None => {
            log_startup_event(
                &startup_log,
                "✗ Backend binary not found in resources/backend/ or alongside EXE",
            );
            return (None, backend_log_path, startup_log);
        }
    };

    let out_file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&backend_log_path)
        .ok();
    let err_file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&backend_log_path)
        .ok();

    let mut cmd = Command::new(&exe_path);
    cmd.args(["serve", "--host", "127.0.0.1", "--port", "8000"]);

    if let Some(f) = out_file {
        cmd.stdout(Stdio::from(f));
    }
    if let Some(f) = err_file {
        cmd.stderr(Stdio::from(f));
    }

    match cmd.spawn() {
        Ok(child) => {
            log_startup_event(
                &startup_log,
                &format!(
                    "✓ Backend Process Spawned (PID: {}) on 127.0.0.1:8000",
                    child.id()
                ),
            );
            (Some(child), backend_log_path, startup_log)
        }
        Err(e) => {
            log_startup_event(
                &startup_log,
                &format!("✗ Failed to spawn backend process: {}", e),
            );
            (None, backend_log_path, startup_log)
        }
    }
}

#[tauri::command]
fn get_app_version() -> String {
    "1.0.0-rc1 (build 1)".to_string()
}

#[derive(serde::Serialize)]
struct BackendStatusResponse {
    connected: bool,
    details: String,
    log_path: String,
    startup_log_path: String,
}

#[tauri::command]
fn get_backend_status(app: tauri::AppHandle) -> BackendStatusResponse {
    let state = app.state::<BackendState>();
    let connected = TcpStream::connect("127.0.0.1:8000").is_ok();
    let details = if connected {
        "Embedded backend operational on port 8000".to_string()
    } else {
        "Backend port 127.0.0.1:8000 unreachable. Check startup logs for details.".to_string()
    };

    BackendStatusResponse {
        connected,
        details,
        log_path: state.log_path.to_string_lossy().to_string(),
        startup_log_path: state.startup_log.to_string_lossy().to_string(),
    }
}

#[derive(serde::Serialize)]
struct DiagnosticReport {
    startup_log: String,
    backend_log: String,
    status: BackendStatusResponse,
}

#[tauri::command]
fn get_startup_diagnostics(app: tauri::AppHandle) -> DiagnosticReport {
    let state = app.state::<BackendState>();
    let status = get_backend_status(app.clone());

    let startup_log = std::fs::read_to_string(&state.startup_log)
        .unwrap_or_else(|_| "No startup log available.".to_string());

    let backend_log = if state.log_path.exists() {
        let mut f = File::open(&state.log_path).ok();
        let mut contents = String::new();
        if let Some(ref mut file) = f {
            let _ = file.read_to_string(&mut contents);
        }
        if contents.len() > 10000 {
            contents.split_off(contents.len() - 10000)
        } else {
            contents
        }
    } else {
        "No backend log found.".to_string()
    };

    DiagnosticReport {
        startup_log,
        backend_log,
        status,
    }
}

pub fn run() {
    if let Err(e) = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_window_state::Builder::default().build())
        .setup(|app| {
            let (child, backend_log_path, startup_log) = launch_backend(app.handle());
            app.manage(BackendState {
                child: Mutex::new(child),
                log_path: backend_log_path,
                startup_log,
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_app_version,
            get_backend_status,
            get_startup_diagnostics,
        ])
        .run(tauri::generate_context!())
    {
        // Log the error and exit gracefully instead of panicking.
        // This prevents a crash-restart loop on Windows.
        eprintln!("AgenticOS Desktop Runtime failed to start: {e}");
        std::process::exit(1);
    }
}
