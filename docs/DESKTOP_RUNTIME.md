# Desktop Runtime — v1.0.0-rc1

The Desktop Runtime is a **native desktop shell** for the AgenticOS platform. Built on Tauri v2, it provides a multi-window graphical environment where users interact with AI agents, manage workspaces, monitor system health, and control every aspect of the platform — all from the desktop, with full offline capability.

---

## 1. Architecture

The runtime is composed of 30+ subsystems assembled by the `DesktopRuntimeManager` (composition root at `src/agentic_os/core/desktop/manager.py`). Each subsystem is an independent module with a well-defined interface, wired together at startup.

```
DesktopRuntimeManager
├── Core Services
│   ├── NativeWindowManager
│   ├── WorkspaceManager
│   ├── NativeNotificationService
│   ├── NativeFileIntegration
│   ├── NativeClipboardService
│   ├── NativeTerminalIntegration
│   ├── NativeProcessManager
│   ├── NativeMenuManager
│   └── NativeDragDropService
├── Persistence
│   └── LocalDatabaseManager
├── Phase 4 M6 Part 2
│   ├── RuntimeDiscoveryManager
│   ├── AutoUpdateManager
│   ├── DesktopInstallerManager
│   ├── FirstRunWizard
│   ├── ChannelManager
│   ├── RollbackManager
│   ├── PortableRuntimeManager
│   ├── OfflineRuntimeManager
│   ├── BackupManager
│   ├── DeltaUpdateEngine
│   ├── SignatureVerification
│   └── WindowsPlatformIntegration
├── Phase 4 M6 Part 3
│   └── DesktopHardeningManager
├── Infrastructure
│   ├── DesktopLogging
│   ├── DesktopConfigurationManager
│   ├── DesktopDiagnosticsManager
│   ├── DesktopPerformanceMonitor
│   └── DesktopEventPublisher
└── Keyboard Shortcut Registry
```

---

## 2. Subsystems

### 2.1 NativeWindowManager
Manages native desktop windows (create, close, focus, minimize, maximize, restore, fullscreen, hide/show). Each window has a label, title, URL, dimensions, position, and state. Windows are tracked by ID and events are published to the EventBus on open/close. (**`src/agentic_os/core/desktop/window.py`**)

### 2.2 WorkspaceManager
Provides virtual workspace isolation — create, switch, edit, and delete workspaces. Each workspace has tabs (ordered by position) and panels (arranged in a `WorkspaceLayout`). Active workspace tracking enables context-aware UI. Events: workspace created, switched, layout changed. (**`src/agentic_os/core/desktop/workspace.py`**)

### 2.3 NativeNotificationService
Sends and manages desktop notifications with levels (info, success, warning, error, critical). Supports dismiss, click tracking, and unread count. Integrates with Tauri for native OS notifications when available. (**`src/agentic_os/core/desktop/notification.py`**)

### 2.4 NativeFileIntegration
File dialog and filesystem operations — open file, save file, select folder dialogs; read/write files; check existence; get file info; ensure directories. Tauri-backed for native dialogs. (**`src/agentic_os/core/desktop/file_integration.py`**)

### 2.5 NativeClipboardService
Read/write system clipboard content (text, HTML, images, files). Cross-platform through Tauri clipboard API. (**`src/agentic_os/core/desktop/clipboard.py`**)

### 2.6 NativeTerminalIntegration
Embedded terminal management — open, close, list, and interact with integrated terminal sessions. Supports custom shell paths, working directories, environment variables. (**`src/agentic_os/core/desktop/terminal.py`**)

### 2.7 NativeProcessManager
Manages child processes spawned by the runtime — list, terminate, monitor. Used for running AI agent subprocesses, MCP servers, and user tasks. (**`src/agentic_os/core/desktop/process.py`**)

### 2.8 NativeMenuManager
Application menu bar management — creates default menus (File, Edit, View, Window, Help) and custom menus. Each menu contains items (action, checkbox, radio, separator, submenu). (**`src/agentic_os/core/desktop/menu.py`**)

### 2.9 NativeDragDropService
Handles drag-and-drop payloads from the OS (files, text, URLs). Validates dropped content and emits events to subscribers. (**`src/agentic_os/core/desktop/dragdrop.py`**)

### 2.10 LocalDatabaseManager
Persistent local database for workspace state, configuration, and offline queue. Uses SQLite under the hood. Provides initialization, info, and close lifecycle. (**`src/agentic_os/core/desktop/database.py`**)

---

## 3. Runtime Discovery

The `RuntimeDiscoveryManager` (at `src/agentic_os/core/desktop/runtime_discovery.py`) automatically detects installed runtimes on the host system. It scans PATH and known installation directories for well-known binaries, extracts version strings, and builds a capability profile for each discovered runtime.

**Discoverable runtimes:**

| Runtime       | Binary names                          | Capabilities                            |
|---------------|---------------------------------------|------------------------------------------|
| Python        | `python`, `python3`, `py`            | execution, scripting, package_management |
| Node.js       | `node`, `nodejs`                     | execution, package_management            |
| Docker        | `docker`                              | containerization, image_management       |
| Git           | `git`                                 | version_control, clone, commit           |
| Claude Code   | `claude`, `claude-code`              | ai_assistant, code_generation            |
| OpenCode      | `opencode`                           | ai_coding, agentic                       |
| Gemini CLI    | `gemini`                              | ai_assistant                             |
| Codex CLI     | `codex`                               | ai_assistant                             |
| Ollama        | `ollama`                              | local_llm, model_serving                 |
| LM Studio     | `lm-studio`                           | local_llm                                |
| SQLite        | `sqlite3`, `sqlite`                  | database, sql                            |

The discovery process:
1. Iterates each provider definition
2. Uses `shutil.which()` to locate the binary on PATH
3. Runs `<binary> --version` to extract version
4. Assigns capabilities from a static mapping
5. Returns a `RuntimeDiscoveryResult` with all found runtimes

Results are cached and accessible via the REST API at `/api/desktop/runtimes`.

---

## 4. Auto-Update Framework

The `AutoUpdateManager` (at `src/agentic_os/core/desktop/update.py`) handles checking for, downloading, verifying, and installing updates.

### 4.1 Update Checking
Queries the GitHub Releases API (`https://api.github.com/repos/rachidSabah/AgenticOS/releases`) on the configured channel. Returns a sorted list of `ReleaseInfo` objects with version, tag, URL, release notes, and asset details.

### 4.2 Download & SHA256 Verification
Downloads the update package to a temporary directory. After download, computes the SHA256 hash of the file and compares it against the expected checksum in the manifest. If they mismatch, the download is marked as failed.

### 4.3 Rollback
The `RollbackManager` (at `src/agentic_os/core/desktop/rollback.py`) maintains a version history and supports rolling back to any previous version. Returns an `UpdateResult` with the rollback outcome.

### 4.4 Update Channels
The `ChannelManager` (at `src/agentic_os/core/desktop/channel.py`) manages three release channels:
- **stable** — Production releases
- **beta** — Pre-release candidates
- **nightly** — Daily development builds

Users can switch channels at runtime via the API.

### 4.5 Update Lifecycle
```
check_for_updates → download_update (verifies SHA256) → install_update → completed/failed
                                              │
                                         rollback (optional)
```

---

## 5. Offline Mode

The `OfflineRuntimeManager` (at `src/agentic_os/core/desktop/offline.py`) provides full offline capability.

**States:** `ONLINE → OFFLINE → SYNCHRONIZING → ONLINE`

**Features:**
- Event queuing — all events are queued when offline (`queue_event`)
- Sync on reconnect — when returning online, queued events are replayed automatically (`sync_queued_events`)
- Queue monitoring — inspect queue size and contents at any time
- Configurable — offline mode settings are adjustable (`OfflineConfig`)

---

## 6. Backup & Restore

The `BackupManager` (at `src/agentic_os/core/desktop/backup.py`) creates and manages application backups.

**Backup scopes (from `BackupScope` enum):**
- **config** — Desktop and application configuration
- **workspaces** — Workspace layouts, tabs, and panels
- **database** — Local SQLite database
- **full** — All of the above

**Operations:**
- `create_backup(config)` — Creates a ZIP archive with a timestamp
- `list_backups()` — Lists all available backups
- `get_backup_info(path)` — Details about a specific backup
- `delete_backup(path)` — Removes a backup
- `restore(config)` — Restores from a backup archive
- `verify_backup(path)` — Checks backup file integrity
- `get_available_restore_points()` — Lists all valid restore targets

Backups are stored in `~/.agentic_os/backups/` by default.

---

## 7. Installer Generation

The `DesktopInstallerManager` (at `src/agentic_os/core/desktop/installer.py`) generates production installers for all target platforms.

**Supported installer types:**

| InstallerType | Platform    | Extension |
|---------------|-------------|-----------|
| MSI           | Windows     | `.msi`    |
| EXE           | Windows     | `.exe`    |
| PORTABLE_ZIP  | All         | `.zip`    |
| AppImage      | Linux       | `.AppImage` |
| DEB           | Linux (Debian/Ubuntu) | `.deb` |
| RPM           | Linux (Fedora/RHEL)   | `.rpm` |
| DMG           | macOS       | `.dmg`    |
| PKG           | macOS       | `.pkg`    |

**Operations:**
- `generate_installer(config)` — Generates a single installer with SHA256 checksum
- `generate_all(config)` — Generates all installers supported on the current OS
- `validate_installer(path)` — Validates an existing installer file
- `get_supported_types()` — Returns supported types for the current platform

---

## 8. First Run Wizard

The `FirstRunWizard` (at `src/agentic_os/core/desktop/first_run.py`) provides a 9-step guided setup for new users.

**Steps:**

| # | Step                   | Description                                  |
|---|------------------------|----------------------------------------------|
| 1 | `welcome`              | Welcome screen, EULA acceptance              |
| 2 | `workspace`            | Create initial default workspace             |
| 3 | `config`               | Basic configuration (language, theme, etc.)  |
| 4 | `runtime_discovery`    | Scan for installed runtimes                  |
| 5 | `provider`             | Configure AI provider (API keys, endpoints)  |
| 6 | `plugin`               | Initialize and enable plugins                |
| 7 | `database`             | Set up local database                        |
| 8 | `health`               | Verify system health                         |
| 9 | `complete`             | Finish setup, start desktop runtime          |

Each step can be skipped or re-run. The wizard state is persisted and can be queried via the API.

---

## 9. Delta Updates

The `DeltaUpdateEngine` (at `src/agentic_os/core/desktop/delta_update.py`) computes and applies incremental (delta) patches between versions.

- `compute_delta(from_version, to_version, source_path, target_path)` — Creates a delta patch
- `apply_delta(delta, target_path)` — Applies an existing delta patch to the target
- `get_available_delta(from_version, to_version)` — Retrieves a pre-computed delta

Delta patches reduce download size by only transmitting changed bytes between consecutive versions.

---

## 10. Signature Verification

The `SignatureVerification` (at `src/agentic_os/core/desktop/signature.py`) verifies the cryptographic integrity of downloaded files and installer packages.

- `verify_sha256(file_path, expected_hash)` — Compares a file's SHA256 hash against an expected value
- `verify_signature(data, signature, public_key)` — Cryptographic signature verification (GPG/Windows Authenticode)
- `get_checksum(file_path, algorithm)` — Computes a hash for any file (supports sha256, sha512, md5)

---

## 11. Platform Integration

The `WindowsPlatformIntegration` (at `src/agentic_os/core/desktop/windows_platform.py`) handles Windows-specific OS integration.

**Capabilities:**
- **Shortcuts** — Start Menu and Desktop shortcut creation
- **File Associations** — Register `.agentic` and other file extensions
- **Auto-Start** — Register for automatic launch on user login
- **Taskbar Pinning** — Pin to Windows taskbar
- **Quick Launch** — Add to quick launch toolbar
- **System Tray** — System tray icon with status
- **Toast Notifications** — Windows native toast notifications

Similar platform integration modules for Linux and macOS follow the same interface pattern.

---

## 12. Production Hardening

The `DesktopHardeningManager` (at `src/agentic_os/core/desktop/hardening.py`) provides comprehensive production hardening for the desktop runtime.

### 12.1 Startup Validation
At boot, the hardening manager checks:
- Python version meets requirements
- Configuration file exists (or falls back to defaults)
- Workspace directory is accessible
- Database directory is accessible
- Required ports are available

### 12.2 Integrity Checks
Verifies that all core modules can be imported successfully (desktop manager, domain models, ports, etc.). Monitors memory usage and flags high consumption.

### 12.3 Self Diagnostics
Full diagnostic scan of all service modules, disk space, and system health. Produces recommendations for configuration changes.

### 12.4 Memory Leak Detection
Tracks baseline memory usage and monitors growth over time. If memory exceeds the configurable threshold (`memory_leak_threshold_mb`), it reports a potential leak and suggests recovery actions.

### 12.5 Thread Monitoring
Enumerates all Python threads, counts active/blocked/deadlocked threads, and alerts if the count exceeds the configured `thread_count_threshold`.

### 12.6 Resource Cleanup
Periodically cleans temporary files (`agentic_os_*` in temp directory) and cache directories. Tracks cleanup history.

### 12.7 Recovery Mode
Activates a recovery mode that:
1. Enters safe mode
2. Runs automatic repair on workspace, config, cache, and database targets
3. Cleans up resources
4. Exits recovery mode

### 12.8 Graceful Shutdown
Planned shutdown executes in order: save workspaces → stop monitoring → close database → cleanup resources → publish shutdown event → stop services. Honor the `graceful_shutdown_timeout_seconds` configuration.

---

## 13. REST API Reference

All endpoints are served under the FastAPI application at the configured port (default `8000`). The desktop runtime endpoints are available only when `settings.desktop_enabled` is `True`.

### 13.1 Runtime State

| Method | Path                    | Description                        |
|--------|-------------------------|------------------------------------|
| GET    | `/api/desktop/state`    | Full desktop runtime state         |
| GET    | `/api/desktop/status`   | Runtime status (running/stopped)   |
| POST   | `/api/desktop/restart`  | Restart the desktop runtime        |

### 13.2 Windows

| Method | Path                                          | Description               |
|--------|-----------------------------------------------|---------------------------|
| GET    | `/api/desktop/windows`                        | List all windows          |
| GET    | `/api/desktop/windows/{id}`                   | Get window by ID          |
| POST   | `/api/desktop/windows`                        | Create a window           |
| DELETE | `/api/desktop/windows/{id}`                   | Close a window            |
| POST   | `/api/desktop/windows/{id}/focus`             | Focus a window            |
| POST   | `/api/desktop/windows/{id}/minimize`          | Minimize a window         |
| POST   | `/api/desktop/windows/{id}/maximize`          | Maximize a window         |
| POST   | `/api/desktop/windows/{id}/restore`           | Restore a window          |
| POST   | `/api/desktop/windows/{id}/fullscreen`        | Enter fullscreen          |

### 13.3 Workspaces

| Method | Path                                                        | Description                |
|--------|-------------------------------------------------------------|----------------------------|
| GET    | `/api/desktop/workspaces`                                   | List all workspaces        |
| GET    | `/api/desktop/workspaces/active`                            | Get active workspace       |
| GET    | `/api/desktop/workspaces/{id}`                              | Get workspace by ID        |
| POST   | `/api/desktop/workspaces`                                   | Create workspace           |
| PUT    | `/api/desktop/workspaces/{id}`                              | Update workspace           |
| DELETE | `/api/desktop/workspaces/{id}`                              | Delete workspace           |
| POST   | `/api/desktop/workspaces/{id}/switch`                       | Switch to workspace        |
| GET    | `/api/desktop/workspaces/{id}/layout`                       | Get workspace layout       |
| PUT    | `/api/desktop/workspaces/{id}/layout`                       | Update workspace layout    |
| POST   | `/api/desktop/workspaces/{id}/tabs`                         | Add tab to workspace       |
| DELETE | `/api/desktop/workspaces/{id}/tabs/{tab_id}`                | Remove tab                 |
| POST   | `/api/desktop/workspaces/{id}/tabs/{tab_id}/activate`       | Activate tab               |
| POST   | `/api/desktop/workspaces/{id}/panels`                       | Add panel to workspace     |
| DELETE | `/api/desktop/workspaces/{id}/panels/{panel_id}`            | Remove panel               |

### 13.4 Notifications

| Method | Path                                                | Description                  |
|--------|-----------------------------------------------------|------------------------------|
| GET    | `/api/desktop/notifications`                        | List all notifications       |
| GET    | `/api/desktop/notifications/unread/count`           | Unread notification count    |
| POST   | `/api/desktop/notifications`                        | Send a notification          |
| DELETE | `/api/desktop/notifications/{id}`                   | Dismiss a notification       |
| POST   | `/api/desktop/notifications/{id}/click`             | Mark notification clicked    |

### 13.5 Configuration

| Method | Path                          | Description                    |
|--------|-------------------------------|--------------------------------|
| GET    | `/api/desktop/config`         | Get full desktop configuration |
| PUT    | `/api/desktop/config`         | Update configuration           |
| GET    | `/api/desktop/config/theme`   | Get current theme              |
| PUT    | `/api/desktop/config/theme`   | Set theme (light/dark/system)  |

### 13.6 Diagnostics & Performance

| Method | Path                                                 | Description                       |
|--------|------------------------------------------------------|-----------------------------------|
| GET    | `/api/desktop/diagnostics`                           | Run full diagnostics              |
| GET    | `/api/desktop/diagnostics/health`                    | Quick health check                |
| GET    | `/api/desktop/performance`                           | Current performance metrics       |
| GET    | `/api/desktop/performance/history/{metric}`          | Historical performance data       |
| POST   | `/api/desktop/performance/monitor/start`             | Start performance monitoring      |
| POST   | `/api/desktop/performance/monitor/stop`              | Stop performance monitoring       |

### 13.7 Menus

| Method | Path                            | Description              |
|--------|---------------------------------|--------------------------|
| GET    | `/api/desktop/menus`            | List application menus  |
| GET    | `/api/desktop/menus/default`    | Get default menu config |
| POST   | `/api/desktop/menus`            | Create a custom menu    |

### 13.8 Files & Clipboard

| Method | Path                          | Description                |
|--------|-------------------------------|----------------------------|
| POST   | `/api/desktop/file/open`      | Open file dialog           |
| POST   | `/api/desktop/file/save`      | Save file dialog           |
| GET    | `/api/desktop/clipboard`      | Get clipboard content      |
| PUT    | `/api/desktop/clipboard`      | Set clipboard content      |

### 13.9 Terminal

| Method | Path                                | Description          |
|--------|-------------------------------------|----------------------|
| GET    | `/api/desktop/terminals`            | List terminal tabs   |
| POST   | `/api/desktop/terminals`            | Open new terminal    |
| DELETE | `/api/desktop/terminals/{id}`       | Close terminal       |

### 13.10 Shortcuts & Commands

| Method | Path                                  | Description                     |
|--------|---------------------------------------|---------------------------------|
| GET    | `/api/desktop/shortcuts`              | List all keyboard shortcuts     |
| GET    | `/api/desktop/command-palette`        | List command palette items      |
| GET    | `/api/desktop/search?q=...`           | Global search across workspaces |

### 13.11 Database

| Method | Path                          | Description                  |
|--------|-------------------------------|------------------------------|
| GET    | `/api/desktop/database`       | Get local database info      |

### 13.12 Runtime Discovery

| Method | Path                                          | Description                     |
|--------|-----------------------------------------------|---------------------------------|
| GET    | `/api/desktop/runtimes`                       | List discovered runtimes        |
| POST   | `/api/desktop/runtimes/discover`              | Trigger runtime discovery       |
| GET    | `/api/desktop/runtimes/{type}`                | Get runtime details by type     |
| POST   | `/api/desktop/runtimes/{type}/verify`         | Verify a runtime is installed   |

### 13.13 Updates

| Method | Path                                    | Description                      |
|--------|-----------------------------------------|----------------------------------|
| GET    | `/api/desktop/updates/check`            | Check for updates (channel param)|
| GET    | `/api/desktop/updates/status`           | Current update status            |
| GET    | `/api/desktop/updates/history`          | Update history                   |
| GET    | `/api/desktop/updates/pending`          | Pending update manifest          |
| GET    | `/api/desktop/updates/version`          | Current installed version        |
| POST   | `/api/desktop/updates/download`         | Download an update               |
| POST   | `/api/desktop/updates/install`          | Install a downloaded update      |

### 13.14 Channels

| Method | Path                              | Description                    |
|--------|-----------------------------------|--------------------------------|
| GET    | `/api/desktop/channels`           | List available channels        |
| GET    | `/api/desktop/channels/current`   | Get current channel            |
| PUT    | `/api/desktop/channels`           | Set update channel             |

### 13.15 Rollback

| Method | Path                                   | Description                  |
|--------|----------------------------------------|------------------------------|
| POST   | `/api/desktop/rollback`                | Rollback to a version        |
| GET    | `/api/desktop/rollback/available`      | List available versions      |

### 13.16 Installer

| Method | Path                                        | Description                      |
|--------|---------------------------------------------|----------------------------------|
| POST   | `/api/desktop/installer/generate`           | Generate an installer            |
| POST   | `/api/desktop/installer/generate-all`       | Generate all platform installers |
| GET    | `/api/desktop/installer/supported-types`    | List supported installer types   |
| POST   | `/api/desktop/installer/validate`           | Validate an installer file       |

### 13.17 First Run Wizard

| Method | Path                                | Description                   |
|--------|-------------------------------------|-------------------------------|
| GET    | `/api/desktop/first-run`            | Get first run state           |
| POST   | `/api/desktop/first-run/step`       | Execute a wizard step         |
| POST   | `/api/desktop/first-run/complete`   | Mark first run as complete    |

### 13.18 Offline Mode

| Method | Path                              | Description                   |
|--------|-----------------------------------|-------------------------------|
| GET    | `/api/desktop/offline`            | Get offline state             |
| POST   | `/api/desktop/offline/enable`     | Enable offline mode           |
| POST   | `/api/desktop/offline/disable`    | Disable offline mode          |
| GET    | `/api/desktop/offline/events`     | List queued offline events    |
| POST   | `/api/desktop/offline/sync`       | Sync queued events            |

### 13.19 Backup & Restore

| Method | Path                              | Description                   |
|--------|-----------------------------------|-------------------------------|
| POST   | `/api/desktop/backup`             | Create a backup               |
| GET    | `/api/desktop/backups`            | List available backups        |
| POST   | `/api/desktop/restore`            | Restore from a backup         |
| GET    | `/api/desktop/restore/points`     | List restore points           |

### 13.20 Drag & Drop

| Method | Path                         | Description              |
|--------|------------------------------|--------------------------|
| POST   | `/api/desktop/dragdrop`      | Handle a drop event      |

---

## 14. EventBus Integration

The desktop runtime publishes events through the `DesktopEventPublisher`. Key event topics:

| Topic                           | Payload                            |
|---------------------------------|------------------------------------|
| `desktop.started`               | `{started_at}`                     |
| `desktop.ready`                 | `{}`                               |
| `desktop.stopped`               | `{}`                               |
| `desktop.window.opened`         | `{window_id, label}`               |
| `desktop.window.closed`         | `{window_id}`                      |
| `desktop.workspace.created`     | `{workspace_id, name}`             |
| `desktop.workspace.switched`    | `{workspace_id}`                   |
| `desktop.layout.changed`        | `{workspace_id, layout_id}`        |
| `desktop.notification.created`  | `{notification_id, title, level}`  |
| `desktop.notification.clicked`  | `{notification_id}`                |
| `desktop.theme.changed`         | `{theme}`                          |

---

## 15. Configuration

Desktop configuration is managed by `DesktopConfigurationManager`. Key settings include:

| Setting            | Default   | Description                        |
|--------------------|-----------|------------------------------------|
| `theme`            | `system`  | UI theme (light, dark, system)     |
| `language`         | `en`      | Interface language                 |
| `font_size`        | `14`      | Base font size in pixels           |
| `sidebar_width`    | `240`     | Sidebar width in pixels            |
| `auto_start`       | `false`   | Auto-start on login                |
| `notifications_enabled` | `true` | Desktop notification toggle        |
| `animations_enabled` | `true`  | UI animation toggle                |
