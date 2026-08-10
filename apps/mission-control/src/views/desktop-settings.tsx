"use client";

import { useCallback, useEffect, useState } from "react";
import { Panel, Stat, Badge, Empty } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { useTheme, ACCENT_PRESETS, DEFAULT_ACCENT } from "@/components/theme-provider";
import type { DesktopConfig, HardeningConfig, KeyboardShortcut, CommandPaletteItem } from "@/lib/desktop-types";

function Toggle({ value, onChange, label }: { value: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-sm text-muted">{label}</span>
      <button
        onClick={() => onChange(!value)}
        role="switch"
        aria-checked={value}
        aria-label={label}
        className={`relative h-6 w-11 rounded-full transition-colors ${value ? "bg-accent" : "bg-surface/60"}`}
      >
        <span className={`absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${value ? "translate-x-5" : "translate-x-0"}`} />
      </button>
    </div>
  );
}

export default function DesktopSettings() {
  const [config, setConfig] = useState<DesktopConfig | null>(null);
  const [hardening, setHardening] = useState<HardeningConfig | null>(null);
  const [shortcuts, setShortcuts] = useState<KeyboardShortcut[]>([]);
  const [paletteItems, setPaletteItems] = useState<CommandPaletteItem[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showHardening, setShowHardening] = useState(false);
  const [autoSaveInterval, setAutoSaveInterval] = useState(60);
  // Real app theme — wired to the global ThemeProvider so changes apply to the DOM.
  const { raw: theme, set: setAppTheme, accent, setAccent, resetAccent } = useTheme();

  const load = useCallback(async () => {
    try {
      const [cfg, hc, sc, cp] = await Promise.all([
        api.desktopConfig().catch(() => null),
        api.hardeningConfig().catch(() => null),
        api.listShortcuts().catch(() => [] as KeyboardShortcut[]),
        api.commandPalette().catch(() => [] as CommandPaletteItem[]),
      ]);
      if (cfg) {
        setConfig(cfg);
        setAutoSaveInterval(cfg.auto_save_interval_seconds);
      }
      setHardening(hc);
      setShortcuts(sc);
      setPaletteItems(cp);
    } catch (err) {
      setError(String(err));
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const updateConfig = async (partial: Partial<DesktopConfig>) => {
    if (!config) return;
    setSaving(true);
    try {
      const updated = await api.updateDesktopConfig(partial);
      setConfig(updated);
      if (partial.auto_save_interval_seconds !== undefined) setAutoSaveInterval(partial.auto_save_interval_seconds);
    } catch (err) {
      setError(String(err));
    }
    setSaving(false);
  };

  const changeTheme = async (mode: "light" | "dark" | "system") => {
    // Apply instantly to the real app theme (DOM class + localStorage)…
    setAppTheme(mode);
    // …and persist to the backend config.
    await updateConfig({ theme: mode });
  };

  const updateHardening = async (partial: Partial<HardeningConfig>) => {
    try {
      const updated = await api.updateHardeningConfig(partial);
      setHardening(updated);
    } catch (err) {
      setError(String(err));
    }
  };

  return (
    <div className="scroll-page grid grid-cols-1 gap-4 p-4 md:grid-cols-12" role="region" aria-label="Desktop Settings">
      {error && (
        <div role="alert" className="col-span-12 rounded-lg border border-danger/40 bg-danger/5 px-4 py-2 text-xs text-danger">{error}</div>
      )}

      <div className="col-span-12 flex items-center gap-3">
        <Stat label="Theme" value={theme} />
        {saving && <span className="text-xs text-faint">Saving…</span>}
      </div>

      <Panel title="General Settings" subtitle="Appearance & behavior" className="col-span-6 row-span-2">
        {config ? (
          <div className="space-y-4">
            <div>
              <label className="mb-1 block text-[11px] uppercase tracking-wide text-faint">Theme Mode</label>
              <div className="flex gap-2">
                {["light", "dark", "system"].map((mode) => (
                  <button
                    key={mode}
                    onClick={() => changeTheme(mode as "light" | "dark" | "system")}
                    aria-label={`${mode} theme`}
                    aria-pressed={theme === mode}
                    className={`rounded-lg px-4 py-2 text-xs font-medium transition ${
                      theme === mode
                        ? "bg-accent text-white"
                        : "border border-border/60 text-muted hover:bg-surface/20"
                    }`}
                  >
                    {mode.charAt(0).toUpperCase() + mode.slice(1)}
                  </button>
                ))}
              </div>
            </div>
            <Toggle value={config.auto_start} onChange={(v) => updateConfig({ auto_start: v })} label="Auto-start" />
            <Toggle value={config.minimize_to_tray} onChange={(v) => updateConfig({ minimize_to_tray: v })} label="Minimize to Tray" />
            <Toggle value={config.enable_notifications} onChange={(v) => updateConfig({ enable_notifications: v })} label="Notifications" />
            <Toggle value={config.confirm_on_close} onChange={(v) => updateConfig({ confirm_on_close: v })} label="Confirm on Close" />
            <Toggle value={config.telemetry_enabled} onChange={(v) => updateConfig({ telemetry_enabled: v })} label="Telemetry" />
          </div>
        ) : (
          <Empty title="Loading settings…" />
        )}
      </Panel>

      <Panel title="Accent Color" subtitle="Customize the system accent color" className="col-span-6 row-span-2">
        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-[11px] uppercase tracking-wide text-faint">Color Palette</label>
            <div className="flex flex-wrap gap-2">
              {ACCENT_PRESETS.map((c) => (
                <button
                  key={c}
                  onClick={() => setAccent(c)}
                  aria-label={`Set accent color ${c}`}
                  aria-pressed={accent.toLowerCase() === c.toLowerCase()}
                  title={c}
                  className={`h-8 w-8 rounded-full border-2 transition-transform hover:scale-110 ${
                    accent.toLowerCase() === c.toLowerCase()
                      ? "border-text ring-2 ring-accent/40 scale-110"
                      : "border-border/60"
                  }`}
                  style={{ backgroundColor: c }}
                />
              ))}
              <label
                className="relative flex h-8 w-8 cursor-pointer items-center justify-center rounded-full border-2 border-dashed border-border/60 text-[10px] text-faint transition-colors hover:border-accent hover:text-accent"
                title="Custom color"
              >
                <span>+</span>
                <input
                  type="color"
                  value={accent}
                  onChange={(e) => setAccent(e.target.value)}
                  aria-label="Pick a custom accent color"
                  className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
                />
              </label>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span
              className="inline-block h-5 w-5 rounded-full border border-border/60"
              style={{ backgroundColor: accent }}
              aria-hidden
            />
            <span className="font-mono text-xs text-muted">{accent.toUpperCase()}</span>
            <button
              onClick={resetAccent}
              className="ml-auto rounded-lg border border-border/60 px-3 py-1.5 text-xs text-muted transition hover:bg-surface/20"
            >
              Reset to Default
            </button>
          </div>
          <p className="text-[10px] leading-relaxed text-faint">
            The accent color applies instantly across all pages — buttons, highlights, active nav, and the AI Brain glow.
          </p>
        </div>
      </Panel>

      <Panel title="Auto-Save" subtitle="Interval configuration" className="col-span-6 row-span-2">
        {config ? (
          <div className="space-y-4">
            <Toggle value={config.enable_auto_save} onChange={(v) => updateConfig({ enable_auto_save: v })} label="Enable Auto-Save" />
            <div>
              <label className="mb-1 block text-[11px] uppercase tracking-wide text-faint">Interval (seconds)</label>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  min={5}
                  max={3600}
                  value={autoSaveInterval}
                  onChange={(e) => {
                    const val = parseInt(e.target.value, 10);
                    if (!isNaN(val)) setAutoSaveInterval(val);
                  }}
                  aria-label="Auto-save interval in seconds"
                  className="w-24 rounded-lg border border-border/60 bg-surface/20 px-3 py-2 text-xs text-text"
                />
                <button
                  onClick={() => updateConfig({ auto_save_interval_seconds: autoSaveInterval })}
                  disabled={saving}
                  aria-label="Apply auto-save interval"
                  className="rounded-lg bg-accent px-3 py-2 text-xs font-medium text-white transition hover:bg-accent/80 disabled:opacity-50"
                >
                  Apply
                </button>
              </div>
            </div>
            <Toggle value={config.check_updates} onChange={(v) => updateConfig({ check_updates: v })} label="Check Updates on Start" />
          </div>
        ) : (
          <Empty title="Loading settings…" />
        )}
      </Panel>

      <Panel title="Hardening" subtitle="Security & system hardening" className="col-span-12 row-span-2" contentClassName="p-0">
        <button
          onClick={() => setShowHardening(!showHardening)}
          aria-label={showHardening ? "Hide Hardening Configuration" : "Show Hardening Configuration"}
          className="flex w-full items-center gap-2 px-4 py-3 text-xs font-medium text-muted hover:bg-surface/10"
        >
          <span className={`transition-transform ${showHardening ? "rotate-90" : ""}`}>&#x25B6;</span>
          {showHardening ? "Hide" : "Show"} Hardening Configuration
        </button>
        {showHardening && hardening && (
          <div className="space-y-3 border-t border-border/40 px-4 py-3">
            <Toggle value={hardening.validate_on_startup} onChange={(v) => updateHardening({ validate_on_startup: v })} label="Validate on Startup" />
            <Toggle value={hardening.enable_memory_leak_detection} onChange={(v) => updateHardening({ enable_memory_leak_detection: v })} label="Memory Leak Detection" />
            <Toggle value={hardening.enable_thread_monitoring} onChange={(v) => updateHardening({ enable_thread_monitoring: v })} label="Thread Monitoring" />
            <Toggle value={hardening.enable_auto_repair} onChange={(v) => updateHardening({ enable_auto_repair: v })} label="Auto-Repair" />
            <Toggle value={hardening.enable_recovery_mode} onChange={(v) => updateHardening({ enable_recovery_mode: v })} label="Recovery Mode" />
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2">
              <div>
                <label className="mb-1 block text-[11px] text-faint">Integrity Check Interval (s)</label>
                <input
                  type="number"
                  value={hardening.integrity_check_interval_seconds}
                  onChange={(e) => updateHardening({ integrity_check_interval_seconds: parseInt(e.target.value, 10) || 0 })}
                  aria-label="Integrity check interval in seconds"
                  className="w-full rounded-lg border border-border/60 bg-surface/20 px-3 py-2 text-xs text-text"
                />
              </div>
              <div>
                <label className="mb-1 block text-[11px] text-faint">Memory Leak Threshold (MB)</label>
                <input
                  type="number"
                  value={hardening.memory_leak_threshold_mb}
                  onChange={(e) => updateHardening({ memory_leak_threshold_mb: parseInt(e.target.value, 10) || 0 })}
                  aria-label="Memory leak threshold in megabytes"
                  className="w-full rounded-lg border border-border/60 bg-surface/20 px-3 py-2 text-xs text-text"
                />
              </div>
              <div>
                <label className="mb-1 block text-[11px] text-faint">Thread Count Threshold</label>
                <input
                  type="number"
                  value={hardening.thread_count_threshold}
                  onChange={(e) => updateHardening({ thread_count_threshold: parseInt(e.target.value, 10) || 0 })}
                  aria-label="Thread count threshold"
                  className="w-full rounded-lg border border-border/60 bg-surface/20 px-3 py-2 text-xs text-text"
                />
              </div>
            </div>
            <div>
              <label className="mb-1 block text-[11px] text-faint">Graceful Shutdown Timeout (s)</label>
              <input
                type="number"
                value={hardening.graceful_shutdown_timeout_seconds}
                onChange={(e) => updateHardening({ graceful_shutdown_timeout_seconds: parseInt(e.target.value, 10) || 0 })}
                aria-label="Graceful shutdown timeout in seconds"
                className="w-32 rounded-lg border border-border/60 bg-surface/20 px-3 py-2 text-xs text-text"
              />
            </div>
          </div>
        )}
        {showHardening && !hardening && (
          <div className="px-4 py-3">
            <Empty title="No hardening config" />
          </div>
        )}
      </Panel>

      <Panel title="Keyboard Shortcuts" subtitle={`${shortcuts.length} bindings`} className="col-span-6 row-span-2">
        {shortcuts.length === 0 ? (
          <Empty title="No shortcuts" hint="Shortcuts are defined by the desktop runtime." />
        ) : (
          <div className="divide-y divide-border/40">
            <div className="flex items-center gap-3 px-2 py-2 text-[11px] font-semibold uppercase text-faint">
              <span className="w-20">Category</span>
              <span className="flex-1">Action</span>
              <span className="w-32">Key</span>
            </div>
            {shortcuts.map((s) => (
              <div key={s.id} className={`flex items-center gap-3 px-2 py-2 text-xs ${!s.enabled ? "opacity-40" : ""}`}>
                <span className="w-20 truncate text-faint">{s.category}</span>
                <span className="flex-1 text-muted">{s.label}</span>
                <span className="w-32 font-mono text-accent">
                  {[...s.modifiers, s.key].join("+")}
                </span>
              </div>
            ))}
          </div>
        )}
      </Panel>

      <Panel title="Command Palette" subtitle={`${paletteItems.length} items`} className="col-span-6 row-span-2">
        {paletteItems.length === 0 ? (
          <Empty title="No palette items" hint="Commands are registered by the desktop runtime." />
        ) : (
          <div className="divide-y divide-border/40">
            <div className="flex items-center gap-3 px-2 py-2 text-[11px] font-semibold uppercase text-faint">
              <span className="w-20">Category</span>
              <span className="flex-1">Label</span>
              <span className="w-24">Shortcut</span>
            </div>
            {paletteItems.map((p) => (
              <div key={p.id} className={`flex items-center gap-3 px-2 py-2 text-xs ${!p.enabled ? "opacity-40" : ""}`}>
                <span className="w-20 truncate text-faint">{p.category}</span>
                <div className="min-w-0 flex-1">
                  <span className="text-muted">{p.label}</span>
                  {p.description && <span className="ml-2 text-[10px] text-faint">{p.description}</span>}
                </div>
                <span className="w-24 text-right font-mono text-[10px] text-faint">{p.shortcut || "—"}</span>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
