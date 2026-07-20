// ── Desktop Runtime types (Phase 4, M6) ──

export interface DesktopRuntimeState {
  status: string;
  windows: WindowInfo[];
  active_workspace_id: string;
  workspaces: Workspace[];
  performance: DesktopPerformanceMetrics;
  diagnostics: DesktopDiagnosticsInfo;
  config: DesktopConfig;
  database: DatabaseInfo | null;
  theme: string;
  started_at: string | null;
  uptime_seconds: number;
  error: string | null;
}

export interface WindowInfo {
  id: string;
  label: string;
  title: string;
  url: string;
  width: number;
  height: number;
  x: number | null;
  y: number | null;
  state: string;
  focused: boolean;
  created_at: string;
}

export interface Workspace {
  id: string;
  name: string;
  status: string;
  layout: WorkspaceLayout | null;
  tabs: TabInfo[];
  is_dirty: boolean;
  created_at: string;
  updated_at: string;
}

export interface TabInfo {
  id: string;
  title: string;
  url: string;
  icon: string | null;
  active: boolean;
  order: number;
}

export interface WorkspaceLayout {
  id: string;
  name: string;
  orientation: string;
  panels: PanelConfig[];
}

export interface PanelConfig {
  id: string;
  title: string;
  position: string;
  state: string;
  width: number;
  height: number;
}

export interface DesktopPerformanceMetrics {
  cpu_usage_percent: number;
  memory_usage_percent: number;
  memory_used_mb: number;
  memory_total_mb: number;
  disk_usage_percent: number;
  disk_free_gb: number;
  disk_total_gb: number;
  process_count: number;
  window_count: number;
  uptime_seconds: number;
}

export interface DesktopDiagnosticsInfo {
  os_name: string;
  os_version: string;
  os_arch: string;
  hostname: string;
  python_version: string;
  app_version: string;
  display_resolution: string;
  display_count: number;
  language: string;
  timezone: string;
}

export interface DesktopConfig {
  theme: string;
  language: string;
  auto_start: boolean;
  minimize_to_tray: boolean;
  confirm_on_close: boolean;
  enable_notifications: boolean;
  enable_auto_save: boolean;
  auto_save_interval_seconds: number;
  check_updates: boolean;
  telemetry_enabled: boolean;
}

export interface DatabaseInfo {
  path: string;
  size_mb: number;
  table_count: number;
  status: string;
}

export interface RuntimeInfo {
  runtime_type: string;
  name: string;
  version: string;
  path: string;
  executable: string;
  capabilities: string[];
  detected_at: string;
  verified: boolean;
  source: string;
}

export interface RuntimeDiscoveryResult {
  total_discovered: number;
  runtimes: RuntimeInfo[];
  duration_seconds: number;
  errors: string[];
}

export interface ReleaseInfo {
  version: string;
  tag: string;
  url: string;
  published_at: string | null;
  release_notes: string;
  prerelease: boolean;
  channel: string;
}

export interface UpdateManifest {
  version: string;
  download_url: string;
  checksum_sha256: string;
  size_bytes: number;
  release_date: string;
  min_version: string;
  changelog: string[];
  mandatory: boolean;
  channel: string;
}

export interface UpdateResult {
  success: boolean;
  previous_version: string;
  new_version: string;
  installed_at: string;
  duration_seconds: number;
  error: string | null;
  rolled_back: boolean;
}

export interface UpdateHistoryRecord {
  id: string;
  from_version: string;
  to_version: string;
  channel: string;
  status: string;
  installed_at: string;
  error: string | null;
}

export interface BackupConfig {
  scope: string;
  output_path: string;
  compress: boolean;
  encrypt: boolean;
  max_backups: number;
}

export interface BackupResult {
  success: boolean;
  backup_path: string;
  size_bytes: number;
  scope: string;
  duration_seconds: number;
  error: string | null;
}

export interface OfflineConfig {
  enabled: boolean;
  max_cache_size_mb: number;
  sync_interval_seconds: number;
  queue_offline_events: boolean;
  auto_sync_on_connect: boolean;
}

export interface OfflineEvent {
  id: string;
  event_type: string;
  queued_at: string;
  synced: boolean;
  error: string | null;
}

export interface InstallerConfig {
  installer_type: string;
  app_name: string;
  app_version: string;
  publisher: string;
  description: string;
  desktop_shortcut: boolean;
  start_menu_shortcut: boolean;
  auto_start: boolean;
}

export interface InstallerResult {
  success: boolean;
  installer_path: string;
  installer_type: string;
  size_bytes: number;
  checksum_sha256: string;
  duration_seconds: number;
  error: string | null;
}

export interface HardeningConfig {
  validate_on_startup: boolean;
  integrity_check_interval_seconds: number;
  enable_memory_leak_detection: boolean;
  enable_thread_monitoring: boolean;
  enable_auto_repair: boolean;
  enable_recovery_mode: boolean;
  memory_leak_threshold_mb: number;
  thread_count_threshold: number;
  graceful_shutdown_timeout_seconds: number;
}

export interface IntegrityCheckResult {
  status: string;
  checked_at: string;
  duration_seconds: number;
  checks: Array<{ name: string; status: string }>;
  warnings: string[];
  errors: string[];
}

export interface SelfDiagnosticsReport {
  status: string;
  services: Array<{ name: string; status: string }>;
  warnings: string[];
  errors: string[];
  recommendations: string[];
}

export interface MemoryLeakReport {
  detected: boolean;
  current_memory_mb: number;
  baseline_memory_mb: number;
  growth_rate_mb_per_minute: number;
  recommendations: string[];
}

export interface ThreadReport {
  total_threads: number;
  active_threads: number;
  threshold_exceeded: boolean;
  threshold: number;
}

export interface CleanupResult {
  success: boolean;
  duration_seconds: number;
  items_cleaned: number;
  actions: Array<{ action: string; status: string }>;
}

export interface RepairResult {
  success: boolean;
  repaired: string[];
  failed: string[];
  duration_seconds: number;
}

export interface ResourceUsageSummary {
  cpu_percent: number;
  memory_mb: number;
  thread_count: number;
  open_handles: number;
  network_connections: number;
  disk_io_bytes_per_sec: number;
}

export interface FirstRunState {
  completed: boolean;
  current_step: string;
  workspace_created: boolean;
  config_saved: boolean;
  runtimes_discovered: boolean;
  provider_configured: boolean;
  plugins_initialized: boolean;
  skipped_steps: string[];
}

export interface KeyboardShortcut {
  id: string;
  key: string;
  modifiers: string[];
  action: string;
  label: string;
  enabled: boolean;
  category: string;
}

export interface CommandPaletteItem {
  id: string;
  label: string;
  description: string;
  action: string;
  category: string;
  shortcut: string | null;
  enabled: boolean;
}

export interface SearchResult {
  id: string;
  title: string;
  description: string;
  category: string;
  url: string;
  score: number;
}

export interface DesktopNotification {
  id: string;
  title: string;
  message: string;
  level: string;
  source: string;
  created_at: string;
  persistent: boolean;
}
