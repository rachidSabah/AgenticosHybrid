# Troubleshooting Guide

## Common Installation Issues

### `uv` command not found
**Cause**: `uv` is not installed or not in PATH.

**Solution**: Install uv using the official installer:
```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### `Python 3.14 not found` during `uv sync`
**Cause**: Python 3.14 is not installed on the system.

**Solution**: Let uv download and install the correct version:
```bash
uv python install 3.14
uv sync
```

### `uv sync` fails with dependency resolution errors
**Cause**: Conflicting dependency versions or platform-specific wheels unavailable.

**Solution**:
```bash
uv sync --reinstall
```
If the issue persists, check `uv.lock` is committed and up to date. Try clearing the cache:
```bash
uv cache clear
uv sync
```

### Build errors on Windows (Rust/Tauri)
**Cause**: Missing MSVC Build Tools for Rust compilation.

**Solution**: Install Visual Studio 2022 Build Tools from https://visualstudio.microsoft.com/downloads/#build-tools-for-visual-studio-2022, selecting the "Desktop development with C++" workload. Then initialize the environment:
```powershell
& "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
```

### Port 8000 already in use
**Cause**: Another process is using the default API port.

**Solution**: Start the backend on a different port:
```bash
uv run python -m agentic_os serve --port 8001
```
Update the frontend proxy configuration accordingly.

---

## Desktop Runtime Fails to Start

### Symptom: `RuntimeError: DesktopRuntime not initialised on the Platform`
**Cause**: The desktop runtime is optional and requires a Tauri-enabled build or explicit desktop mode.

**Solution**: Ensure you are running inside the Tauri shell or pass `--enable-desktop` flag if available. On a headless server, the desktop runtime is expected to be unavailable.

### Symptom: Desktop starts but shows blank window
**Cause**: Mission Control frontend not built or wrong URL.

**Solution**:
1. Build the frontend: `npm --prefix apps/mission-control run build`
2. Check the desktop config: `GET /api/desktop/config` — verify the `workspace_dir` exists
3. Check logs for CORS or WebSocket connection errors

### Symptom: Window operations fail silently
**Cause**: The underlying Tauri window manager API is platform-specific and may not be available in all environments.

**Solution**: Check `GET /api/desktop/diagnostics` for platform information. Some window operations (fullscreen, transparency) may not be supported on all operating systems or window managers.

---

## Runtime Discovery Not Finding Runtimes

### Symptom: `GET /api/desktop/runtimes` returns empty list
**Cause**: No runtimes discovered yet, or discovery providers are disabled.

**Solution**:
1. Trigger a discovery scan: `POST /api/desktop/runtimes/discover`
2. Check if discovery providers are enabled: `GET /api/discovery/providers`
3. Enable providers: `PUT /api/discovery/providers/path` with `{"enabled": true}`
4. Verify runtimes are installed and accessible from PATH

### Symptom: Specific runtime not detected (e.g., Docker, Node, Python)
**Cause**: The runtime is either not installed or not on the system PATH.

**Solution**:
1. Verify the runtime is installed: `python --version`, `node --version`, `docker --version`
2. Check PATH includes the runtime's installation directory
3. For Docker, ensure Docker Desktop is running
4. For WSL runtimes, ensure WSL is installed and distributions are configured
5. Check discovery cache: `GET /api/discovery/cache` — clear if stale: `DELETE /api/discovery/cache`

### Symptom: Discovery scan is slow
**Cause**: Many providers being checked, or a provider is hanging.

**Solution**: Disable unused discovery providers:
```http
PUT /api/discovery/providers/vscode
{"enabled": false}
```
Reduce the scan profile's scope or increase the scan interval.

---

## Update Fails to Download

### Symptom: `POST /api/desktop/updates/download` returns failure
**Cause**: Network connectivity issues, invalid manifest, or insufficient disk space.

**Solution**:
1. Check network connectivity: Can you reach the update server?
2. Verify the update manifest: `GET /api/desktop/updates/pending` — confirm `download_url` is valid
3. Check disk space: `GET /api/desktop/performance` — verify `disk_free_gb` has enough space
4. Check update status: `GET /api/desktop/updates/status` — may be `failed`
5. Review logs for specific error messages (connection timeout, SSL error, etc.)

### Symptom: Update checksum verification fails
**Cause**: Corrupted download or man-in-the-middle tampering.

**Solution**:
1. Re-download the update
2. Verify the update channel is correct (stable/beta/nightly)
3. Check the system clock is accurate (affects signature verification)
4. If the issue persists, the update server may be serving corrupted files

### Symptom: Update installs but rollback occurs automatically
**Cause**: Startup validation after update failed, triggering automatic rollback.

**Solution**:
1. Check `GET /api/desktop/updates/history` for rollback records
2. Review logs for startup validation errors
3. Try installing the update manually with `POST /api/desktop/updates/install`
4. If rollback keeps failing, use `POST /api/desktop/rollback` with a specific target version

---

## Offline Mode Not Syncing

### Symptom: Offline events are queued but never sync
**Cause**: The system remains in offline state or auto-sync is disabled.

**Solution**:
1. Check offline state: `GET /api/desktop/offline` — should be `online` or `synchronizing`
2. Force sync: `POST /api/desktop/offline/sync`
3. Check queued events: `GET /api/desktop/offline/events`
4. Verify network connectivity is restored
5. Review `OfflineConfig.sync_interval_seconds` — default is 300 seconds

### Symptom: Offline mode cannot be enabled
**Cause**: Offline manager not initialized (headless mode).

**Solution**: The offline manager requires the desktop runtime. In headless/API-only mode, offline mode is not available.

---

## Backup Fails

### Symptom: `POST /api/desktop/backup` returns error
**Cause**: Insufficient disk space, invalid output path, or scope configuration issue.

**Solution**:
1. Check the output path exists and is writable
2. Verify disk space: `GET /api/desktop/performance` — `disk_free_gb`
3. Reduce backup scope: use `BackupScope.CONFIG` instead of `FULL`
4. Disable encryption temporarily to isolate the issue (`encrypt: false`)
5. Check the backup directory is not on a network drive (may cause permission issues)

### Symptom: Restore fails
**Cause**: Backup file is corrupted, incompatible version, or missing dependencies.

**Solution**:
1. Verify the backup file exists and is accessible
2. Check the backup was created by a compatible version of AgenticOS
3. Try restore with `verify_before: true` (default)
4. Check logs for specific error details
5. List available restore points: `GET /api/desktop/restore/points`

---

## Database Errors

### Symptom: `DatabaseInfo` shows status `error` or `disconnected`
**Cause**: SQLite database file is corrupted, locked, or inaccessible.

**Solution**:
1. Check the database path: `GET /api/desktop/database`
2. Ensure no other process has the database locked
3. Verify the database file is not read-only
4. If corrupted, restore from the latest backup
5. Check migration history for failed migrations

### Symptom: Migration errors on startup
**Cause**: Database schema is out of sync with the application version.

**Solution**:
1. Check `DatabaseInfo.migration_count` vs expected
2. Review migration error logs
3. If safe, delete the database file (backup first!) and let it recreate
4. Restore from a pre-upgrade backup

---

## Performance Issues

### Symptom: High CPU usage
**Cause**: Continuous discovery scanning, hot-reload, or intensive WebSocket activity.

**Solution**:
1. Check `GET /api/discovery/hot-reload/status` — stop if not needed: `POST /api/discovery/hot-reload/stop`
2. Increase discovery scan interval in profile configuration
3. Reduce the number of active WebSocket connections
4. Disable unused MCP servers
5. Check for runaway tasks in orchestration

### Symptom: High memory usage
**Cause**: Cached discovery data, telemetry history, or MCP server processes.

**Solution**:
1. Clear discovery cache: `DELETE /api/discovery/cache`
2. Reduce telemetry max entries in learning profiles
3. Stop unused MCP servers
4. Check for memory leaks (see Memory Leaks section)

### Symptom: Slow API responses
**Cause**: Provider latency, large model loading, or synchronous operations.

**Solution**:
1. Check provider health: `GET /api/provider-health`
2. Review routing policy: `POST /api/routing/policy` with `{"policy": "latency"}`
3. Check rate limit status: `GET /api/rate-limits`
4. Review performance metrics: `GET /api/desktop/performance`

---

## Memory Leaks

### Symptom: Memory usage steadily increases over time
**Cause**: Suspected memory leak in a subsystem (MCP servers, plugins, or telemetry).

**Solution**:
1. Enable memory leak detection in HardeningConfig
2. Check `MemoryLeakReport` in diagnostics
3. Review the growth rate: `growth_rate_mb_per_minute`
4. Isolate the leak:
   - Restart MCP servers one by one
   - Disable plugins
   - Clear telemetry history
5. Use `POST /api/desktop/performance/monitor/start` for detailed tracking

---

## Plugin Installation Failures

### Symptom: Plugin install returns error
**Cause**: Missing dependencies, incompatible version, or security policy rejection.

**Solution**:
1. Check plugin manifest for required capabilities
2. Verify the plugin supports your AgenticOS version
3. Check security audit log for policy rejections: `GET /api/security/audit`
4. Ensure all plugin dependencies are installed
5. Try installing from a local path vs remote registry

### Symptom: Plugin loads but capabilities fail authorization
**Cause**: The requesting agent's role does not have the required permissions.

**Solution**:
1. Review plugin capabilities in manifest
2. Assign appropriate role to the agent: `POST /api/security/assign`
3. Check if the capability requires approval and the approval gate is responding
4. Review audit log for denied authorization attempts

---

## Provider Connection Errors

### Symptom: Provider test fails (`POST /api/providers/{name}/test`)
**Cause**: Invalid API key, wrong base URL, network connectivity, or provider outage.

**Solution**:
1. Verify API key is stored: `GET /api/providers/{name}/api-key/status`
2. Re-store the API key: `POST /api/providers/{name}/api-key`
3. Check provider config: `GET /api/provider-configs`
4. Verify the base URL is correct and reachable
5. Check if the provider service is experiencing an outage
6. Review provider health: `GET /api/provider-health`

### Symptom: Provider health shows `UNKNOWN` or `UNHEALTHY`
**Cause**: Provider has not been tested yet, or the adapter failed to connect.

**Solution**:
1. Trigger a health check: `POST /api/providers/{name}/test`
2. Check the error field in health status for details
3. Ensure the provider adapter is built correctly
4. Check rate limits: `GET /api/rate-limits`

---

## Logs Location and How to Read Them

### Log Locations

| Platform | Location |
|----------|----------|
| Linux/macOS | `~/.agentic_os/logs/` |
| Windows | `%APPDATA%\AgenticOS\logs\` |
| Backend (uv run) | Stdout/stderr (configure `AGENTIC_OS_LOG_LEVEL`) |

### Log Level Configuration
```bash
# Set via environment variable
export AGENTIC_OS_LOG_LEVEL=DEBUG

# Or on startup
uv run python -m agentic_os serve --log-level DEBUG
```

### Log Format
Logs are structured JSON using `structlog`:
```json
{
  "event": "server_started",
  "timestamp": "2026-07-20T10:30:00Z",
  "logger": "api",
  "level": "info",
  "server_id": "abc123"
}
```

### Key Log Patterns

| Pattern | Meaning |
|---------|---------|
| `authorization.denied` | Security framework denied a capability |
| `approval.*` | Human approval gate events |
| `engine.*` | Runtime engine lifecycle events |
| `discovery.*` | Runtime discovery scan events |
| `mcp.*` | MCP server lifecycle and tool events |
| `swarm.*` | Orchestration and swarm events |
| `desktop.*` | Desktop runtime events |
| `update.*` | Update lifecycle events |
| `backup.*` | Backup and restore events |

### Reading Logs with grep
```bash
# Find authorization failures
grep "authorization.denied" ~/.agentic_os/logs/*.log

# Track a specific MCP server
grep "server_id=abc123" ~/.agentic_os/logs/*.log

# Watch logs in real-time (Linux/macOS)
tail -f ~/.agentic_os/logs/agentic-os.log

# Windows PowerShell equivalent
Get-Content -Path "$env:APPDATA\AgenticOS\logs\agentic-os.log" -Tail 50 -Wait
```
