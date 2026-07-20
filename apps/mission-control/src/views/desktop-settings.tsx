"use client";

import { useCallback, useEffect, useState } from "react";
import { Panel, Stat, Badge, Empty } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import type { DesktopConfig, HardeningConfig, KeyboardShortcut, CommandPaletteItem } from "@/lib/desktop-types";

function Toggle({ value, onChange, label }: { value: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-sm text-muted">{label}</span>
      <button
        onClick={() => onChange(!value)}
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
  const [theme, setTheme] = useState("dark");
  const [autoSaveInterval, setAutoSaveInterval] = useState(60);

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
        setTheme(cfg.theme);
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
      if (partial.theme !== undefined) setTheme(partial.theme);
      if (partial.auto_save_interval_seconds !== undefined) setAutoSaveInterval(partial.auto_save_interval_seconds);
    } catch (err) {
      setError(String(err));
    }
    setSaving(false);
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
    <div className="grid h-full grid-cols-12 gap-4 overflow-auto p-4">
      {error && (
        <div className="col-span-12 rounded-lg border border-danger/40 bg-danger/5 px-4 py-2 text-xs text-danger">{error}</div>
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
                    onClick={() => updateConfig({ theme: mode })}
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
                  className="w-24 rounded-lg border border-border/60 bg-surface/20 px-3 py-2 text-xs text-text"
                />
                <button
                  onClick={() => updateConfig({ auto_save_interval_seconds: autoSaveInterval })}
                  disabled={saving}
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
            <div className="grid grid-cols-3 gap-4 pt-2">
              <div>
                <label className="mb-1 block text-[11px] text-faint">Integrity Check Interval (s)</label>
                <input
                  type="number"
                  value={hardening.integrity_check_interval_seconds}
                  onChange={(e) => updateHardening({ integrity_check_interval_seconds: parseInt(e.target.value, 10) || 0 })}
                  className="w-full rounded-lg border border-border/60 bg-surface/20 px-3 py-2 text-xs text-text"
                />
              </div>
              <div>
                <label className="mb-1 block text-[11px] text-faint">Memory Leak Threshold (MB)</label>
                <input
                  type="number"
                  value={hardening.memory_leak_threshold_mb}
                  onChange={(e) => updateHardening({ memory_leak_threshold_mb: parseInt(e.target.value, 10) || 0 })}
                  className="w-full rounded-lg border border-border/60 bg-surface/20 px-3 py-2 text-xs text-text"
                />
              </div>
              <div>
                <label className="mb-1 block text-[11px] text-faint">Thread Count Threshold</label>
                <input
                  type="number"
                  value={hardening.thread_count_threshold}
                  onChange={(e) => updateHardening({ thread_count_threshold: parseInt(e.target.value, 10) || 0 })}
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
