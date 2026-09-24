"use client";

import { useState, useEffect, useCallback } from "react";
import { Panel, Stat, Badge, Empty } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { Cpu, WifiOff, HardDrive, Zap, Download, RefreshCw, CheckCircle2 } from "lucide-react";

export function GPUAcceleration() {
  const [telemetry, setTelemetry] = useState<any | null>(null);
  const [offline, setOffline] = useState(false);
  const [loadingModel, setLoadingModel] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      const res = await api.get<any>("/api/desktop/gpu/telemetry");
      if (res) {
        setTelemetry(res);
        setOffline(res.is_offline_mode);
      }
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    void loadData();
    const id = setInterval(loadData, 4000);
    return () => clearInterval(id);
  }, [loadData]);

  const toggleOffline = async () => {
    const next = !offline;
    setOffline(next);
    await api.post("/api/desktop/gpu/offline", { offline: next });
    await loadData();
  };

  const handleLoadModel = async (modelId: string) => {
    setLoadingModel(modelId);
    try {
      await api.post("/api/desktop/gpu/load", { model_id: modelId });
      await loadData();
    } finally {
      setLoadingModel(null);
    }
  };

  const handleUnloadModel = async (modelId: string) => {
    setLoadingModel(modelId);
    try {
      await api.post("/api/desktop/gpu/unload", { model_id: modelId });
      await loadData();
    } finally {
      setLoadingModel(null);
    }
  };

  const handleDownloadModel = async (modelId: string) => {
    setLoadingModel(modelId);
    try {
      await api.post("/api/desktop/gpu/download", { model_id: modelId });
      await loadData();
    } finally {
      setLoadingModel(null);
    }
  };

  // Only models actually reported by the backend — never a fabricated catalog.
  const models: any[] = Array.isArray(telemetry?.models) ? telemetry.models : [];

  return (
    <div className="flex h-full flex-col bg-background text-text p-4 space-y-4 overflow-auto">
      {/* Telemetry Header */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        <Stat label="Hardware Acceleration" value={telemetry?.device_name || "—"} />
        <Stat
          label="VRAM Allocated"
          value={
            telemetry?.hardware_detected && telemetry?.total_vram_gb > 0
              ? `${telemetry.allocated_vram_gb} / ${telemetry.total_vram_gb} GB`
              : "—"
          }
        />
        <Stat
          label="GPU Temperature"
          value={telemetry?.gpu_temp_c != null ? `${telemetry.gpu_temp_c}°C` : "—"}
        />
        <div className="rounded-xl border border-border/60 bg-surface/20 p-3 flex items-center justify-between">
          <div>
            <div className="text-[11px] text-faint">Air-Gapped Mode</div>
            <div className="font-semibold text-sm">{offline ? "Offline Active" : "Online Mode"}</div>
          </div>
          <button
            onClick={toggleOffline}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
              offline ? "bg-amber-500/30 text-amber-300 border border-amber-500/40" : "bg-surface/40 text-faint hover:bg-surface/60"
            }`}
          >
            {offline ? "Disable" : "Enable Offline"}
          </button>
        </div>
      </div>

      {/* Local Model Discovery Matrix */}
      <Panel title="Zero-Config Local Model Hub (Ollama / vLLM / llama.cpp)" subtitle="Auto-discovered weights with DirectML / CUDA tensor acceleration">
        {models.length === 0 ? (
          <div className="p-2">
            <Empty title="No models detected" hint="No local inference engine has registered any models yet" />
          </div>
        ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {models.map((m: any) => (
            <div key={m.model_id} className="rounded-xl border border-border/60 bg-surface/20 p-4 space-y-3">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-xs">{m.name}</span>
                <Badge tone={m.is_active ? "ok" : m.is_downloaded ? "default" : "warn"}>
                  {m.is_active ? "Active In-VRAM" : m.is_downloaded ? "Ready" : "Not Downloaded"}
                </Badge>
              </div>
              <div className="grid grid-cols-2 gap-2 text-[11px] font-mono text-faint">
                <div>Model Size: {m.size_gb} GB</div>
                <div>VRAM Req: {m.vram_required_gb} GB</div>
                <div className="col-span-2 text-emerald-400 font-semibold">Speed: {m.tokens_per_sec} tokens/sec</div>
              </div>
              {m.is_downloaded ? (
                <button
                  onClick={() => (m.is_active ? handleUnloadModel(m.model_id) : handleLoadModel(m.model_id))}
                  disabled={loadingModel === m.model_id}
                  className={`w-full rounded-lg py-1.5 text-xs font-medium transition ${
                    m.is_active
                      ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 hover:bg-emerald-500/30"
                      : "bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 hover:bg-indigo-500/30"
                  }`}
                >
                  {loadingModel === m.model_id
                    ? "Updating VRAM…"
                    : m.is_active
                    ? "Model Loaded in VRAM (Click to Unload)"
                    : "Load into VRAM"}
                </button>
              ) : (
                <button
                  onClick={() => handleDownloadModel(m.model_id)}
                  disabled={loadingModel === m.model_id}
                  className="w-full flex items-center justify-center gap-1.5 rounded-lg bg-accent py-1.5 text-xs text-white font-medium hover:bg-accent/80 transition disabled:opacity-50"
                >
                  <Download size={14} />
                  {loadingModel === m.model_id ? "Downloading Weights…" : "Download Weights"}
                </button>
              )}
            </div>
          ))}
        </div>
        )}
      </Panel>
    </div>
  );
}