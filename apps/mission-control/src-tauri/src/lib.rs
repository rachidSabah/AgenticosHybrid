use std::env::current_exe;
use std::fs::{create_dir_all, File, OpenOptions};
use std::io::{Read, Write};
use std::net::TcpStream;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use tauri::Manager;


#[allow(dead_code)]
struct BackendState {
    /// Held to keep the backend process alive for the application lifetime.
    child: Mutex<Option<Child>>,
    log_path: PathBuf,
    startup_log: PathBuf,
}

impl Drop for BackendState {
    fn drop(&mut self) {
        if let Ok(mut guard) = self.child.lock() {
            if let Some(mut child) = guard.take() {
                let _ = child.kill();
                let _ = child.wait();
            }
        }
    }
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

fn wait_for_backend_health(timeout_secs: u64, startup_log: &Path) -> bool {
    let start = std::time::Instant::now();
    while start.elapsed().as_secs() < timeout_secs {
        if TcpStream::connect("127.0.0.1:8000").is_ok() {
            log_startup_event(startup_log, "✓ Backend health check passed (port 8000 open)");
            return true;
        }
        std::thread::sleep(std::time::Duration::from_millis(500));
    }
    log_startup_event(
        startup_log,
        &format!(
            "✗ Backend health check timed out after {}s (port 8000 never opened)",
            timeout_secs
        ),
    );
    false
}

fn launch_backend(app: &tauri::AppHandle) -> (Option<Child>, PathBuf, PathBuf) {
    let log_dir = get_log_directory(app);
    let _ = create_dir_all(&log_dir);

    let startup_log = log_dir.join("startup.log");
    let backend_log_path = log_dir.join("backend.log");

    // Clear previous startup log
    let _ = OpenOptions::new()
        .create(true)
        .write(true)
        .truncate(true)
        .open(&startup_log);

    log_startup_event(&startup_log, "Desktop Runtime Starting...");

    let current = current_exe().ok();
    let exe_dir = current.as_ref().and_then(|c| c.parent().map(|p| p.to_path_buf()));

    // Log where we are running from
    if let Some(ref dir) = exe_dir {
        log_startup_event(&startup_log, &format!("✓ Running from: {}", dir.display()));
    } else {
        log_startup_event(&startup_log, "✗ Could not determine exe directory");
    }

    // Strategy 1: Try uv run with bundled backend source (most portable, avoids
    // PyInstaller binary extraction issues with Windows Defender)
    let mut launch_method: Option<String> = None;
    if let Some(ref dir) = exe_dir {
        let pyproject_path = dir.join("backend").join("pyproject.toml");
        let src_path = dir.join("backend").join("src");
        if pyproject_path.exists() || src_path.exists() {
            log_startup_event(
                &startup_log,
                &format!("✓ Bundled backend source found — pyproject: {}", pyproject_path.exists()),
            );
            // Check if uv is available
            let uv_check = Command::new("uv")
                .arg("--version")
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .spawn();
            if let Ok(mut child) = uv_check {
                if let Ok(status) = child.wait() {
                    if status.success() {
                        log_startup_event(&startup_log, "✓ STRATEGY 1: Spawning via uv run --project backend");
                        launch_method = Some("uv".to_string());
                    } else {
                        log_startup_event(&startup_log, "  uv check: installed but returned non-zero");
                    }
                }
            } else {
                log_startup_event(&startup_log, "  uv check: failed to spawn");
            }
        } else {
            log_startup_event(&startup_log, &format!(
                "  No bundled source — pyproject exists: {}, src exists: {}",
                pyproject_path.exists(), src_path.exists()
            ));
        }
    }

    // Strategy 2: Try PyInstaller binary alongside EXE (portable ZIP mode)
    if launch_method.is_none() {
        if let Some(ref dir) = exe_dir {
            let portable_candidates = [
                dir.join("backend").join("agentic_os.exe"),
                dir.join("backend").join("agentic-os.exe"),
                dir.join("agentic_os.exe"),
                dir.join("agentic-os.exe"),
            ];
            for candidate in &portable_candidates {
                log_startup_event(
                    &startup_log,
                    &format!("  Checking portable candidate: {} (exists: {})", candidate.display(), candidate.exists()),
                );
                if candidate.exists() {
                    if let Some(ref curr) = current {
                        if candidate == curr {
                            log_startup_event(&startup_log, "    Same as running EXE — skipping");
                            continue;
                        }
                    }
                    log_startup_event(
                        &startup_log,
                        &format!("✓ STRATEGY 2: PyInstaller binary alongside EXE: {}", candidate.display()),
                    );
                    launch_method = Some(candidate.to_string_lossy().to_string());
                    break;
                }
            }
        }
    }

    // Strategy 3: Try PyInstaller binary from Tauri resource dir (installed mode)
    if launch_method.is_none() {
        match app.path().resource_dir() {
            Ok(res_dir) => {
                log_startup_event(&startup_log, &format!("✓ Resource directory: {}", res_dir.display()));
                configure_dll_directory(&res_dir);
                let resource_candidates = [
                    res_dir.join("backend").join("agentic_os.exe"),
                    res_dir.join("backend").join("agentic-os.exe"),
                ];
                for candidate in &resource_candidates {
                    log_startup_event(
                        &startup_log,
                        &format!("  Checking resource candidate: {} (exists: {})", candidate.display(), candidate.exists()),
                    );
                    if candidate.exists() {
                        if let Some(ref curr) = current {
                            if candidate == curr {
                                log_startup_event(&startup_log, "    Same as running EXE — skipping");
                                continue;
                            }
                        }
                        log_startup_event(
                            &startup_log,
                            &format!("✓ STRATEGY 3: PyInstaller binary from resources: {}", candidate.display()),
                        );
                        launch_method = Some(candidate.to_string_lossy().to_string());
                        break;
                    }
                }
            }
            Err(e) => {
                log_startup_event(&startup_log, &format!("✗ Failed to resolve resource directory: {}", e));
            }
        }
    }

    // Strategy 3b: Try uv from resource dir (installed mode, Python source)
    if launch_method.is_none() {
        match app.path().resource_dir() {
            Ok(res_dir) => {
                let pyproject = res_dir.join("backend").join("pyproject.toml");
                if pyproject.exists() {
                    let uv_check = Command::new("uv")
                        .arg("--version")
                        .stdout(Stdio::null())
                        .stderr(Stdio::null())
                        .spawn();
                    if let Ok(mut child) = uv_check {
                        if let Ok(status) = child.wait() {
                            if status.success() {
                                log_startup_event(
                                    &startup_log,
                                    "✓ STRATEGY 3b: uv + backend source from resource dir",
                                );
                                launch_method = Some(format!("uv::{}", res_dir.join("backend").to_string_lossy()));
                            }
                        }
                    }
                }
            }
            Err(_) => {}
        }
    }

    // Strategy 4: Try system python -m agentic_os serve
    if launch_method.is_none() {
        for python_cmd in &["python", "python3"] {
            let check = Command::new(python_cmd)
                .args(["-c", "import agentic_os; print('ok')"])
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .spawn();
            if let Ok(mut child) = check {
                if let Ok(status) = child.wait() {
                    if status.success() {
                        log_startup_event(
                            &startup_log,
                            &format!("✓ STRATEGY 4: agentic_os importable via '{}'", python_cmd),
                        );
                        launch_method = Some(python_cmd.to_string());
                        break;
                    }
                }
            }
            log_startup_event(&startup_log, &format!("  python check '{}': not importable", python_cmd));
        }
    }

    let launch_method = match launch_method {
        Some(m) => {
            log_startup_event(&startup_log, &format!("✓ Launch method: {}", m));
            m
        }
        None => {
            log_startup_event(
                &startup_log,
                "✗ All launch strategies exhausted — cannot start backend",
            );
            return (None, backend_log_path, startup_log);
        }
    };

    let exe_dir = current.as_ref().and_then(|c| c.parent().map(|p| p.to_path_buf()));

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

    let mut cmd = if launch_method.starts_with("uv::") {
        let backend_dir = &launch_method[4..];
        let mut c = Command::new("uv");
        c.args(["--project", backend_dir, "run", "python", "-m", "agentic_os", "serve", "--host", "127.0.0.1", "--port", "8000"]);
        c.current_dir(backend_dir);
        c
    } else {
        match launch_method.as_str() {
            "uv" => {
                let mut c = Command::new("uv");
                c.args(["--project", "backend", "run", "python", "-m", "agentic_os", "serve", "--host", "127.0.0.1", "--port", "8000"]);
                if let Some(ref dir) = exe_dir {
                    c.current_dir(dir);
                }
                c
            }
            "python" | "python3" => {
                let mut c = Command::new(&launch_method);
                c.args(["-m", "agentic_os", "serve", "--host", "127.0.0.1", "--port", "8000"]);
                if let Some(ref dir) = exe_dir {
                    c.current_dir(dir);
                }
                c
            }
            _ => {
                // Binary path (PyInstaller or other EXE)
                let exe_path = PathBuf::from(&launch_method);
                let mut c = Command::new(&exe_path);
                c.args(["serve", "--host", "127.0.0.1", "--port", "8000"]);
                if let Some(ref dir) = exe_dir {
                    c.current_dir(dir);
                }
                c
            }
        }
    };

    if let Some(f) = out_file {
        cmd.stdout(Stdio::from(f));
    }
    if let Some(f) = err_file {
        cmd.stderr(Stdio::from(f));
    }

    log_startup_event(
        &startup_log,
        &format!("Spawning: {:?} with args: {:?} in dir: {:?}", cmd.get_program(), cmd.get_args(), cmd.get_current_dir()),
    );

    let mut child = match cmd.spawn() {
        Ok(child) => {
            let pid = child.id();
            log_startup_event(
                &startup_log,
                &format!("✓ Backend Process Spawned (PID: {}) on 127.0.0.1:8000", pid),
            );
            child
        }
        Err(e) => {
            log_startup_event(
                &startup_log,
                &format!("✗ Failed to spawn backend process: {}", e),
            );
            return (None, backend_log_path, startup_log);
        }
    };

    // Wait for backend to become healthy (up to 30 seconds)
    let healthy = wait_for_backend_health(30, &startup_log);

    if !healthy {
        // Check if process exited early — capture any startup log content
        match child.try_wait() {
            Ok(Some(exit_status)) => {
                log_startup_event(
                    &startup_log,
                    &format!(
                        "✗ Backend process exited prematurely with status: {}",
                        exit_status
                    ),
                );
                // Read last 20 lines of backend log for diagnostics
                if let Ok(contents) = std::fs::read_to_string(&backend_log_path) {
                    let lines: Vec<&str> = contents.lines().collect();
                    let tail = if lines.len() > 20 {
                        &lines[lines.len() - 20..]
                    } else {
                        &lines[..]
                    };
                    for line in tail {
                        log_startup_event(&startup_log, &format!("  ┊ {}", line));
                    }
                }
                return (None, backend_log_path, startup_log);
            }
            Ok(None) => {
                // Process still running but port not open — might be slow startup
                log_startup_event(&startup_log, "⚠ Backend process is running but port 8000 is not yet open. It may still be initializing.");
            }
            Err(e) => {
                log_startup_event(
                    &startup_log,
                    &format!("✗ Error checking backend process status: {}", e),
                );
            }
        }
    }

    (Some(child), backend_log_path, startup_log)
}

#[tauri::command]
fn get_app_version() -> String {
    env!("CARGO_PKG_VERSION").to_string()
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

fn cleanup_child(app_handle: &tauri::AppHandle) {
    if let Some(state) = app_handle.try_state::<BackendState>() {
        if let Ok(mut guard) = state.child.lock() {
            if let Some(mut child) = guard.take() {
                let _ = child.kill();
                let _ = child.wait();
            }
        }
    }
}

pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_window_state::Builder::default().build())
        .setup(|app| {
            let (child, backend_log_path, startup_log) = launch_backend(app.handle());

            // launch_backend() already waits up to 30 s for the backend port.
            // Log the final outcome so the startup log is complete.
            if child.is_some() {
                log_startup_event(&startup_log, "✓ Desktop Runtime Ready — opening Mission Control");
            } else {
                log_startup_event(
                    &startup_log,
                    "⚠ No backend process — UI will open in offline mode.",
                );
            }

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
        .build(tauri::generate_context!())
        .unwrap_or_else(|e| {
            eprintln!("AgenticOS Desktop Runtime failed to start: {e}");
            std::process::exit(1);
        });

    app.run(|app_handle, event| {
        if let tauri::RunEvent::ExitRequested { .. } = event {
            cleanup_child(app_handle);
        }
    });
}
