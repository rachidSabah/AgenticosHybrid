"""
Phase 4 — Zero-Config Local GPU Hub & Hardware Profiling.

Spec §16/§17 remediation: this hub previously reported a hardcoded
"NVIDIA GeForce RTX 4090", 24 GB VRAM, 48.0 °C and a canned list of
"downloaded" models with invented tokens_per_sec values. None of that was
measured. Until real hardware enumeration is wired (e.g. nvidia-smi /
psutil / Metal), the telemetry endpoint reports NO DATA (zeros / empty
model list) instead of invented hardware.
"""

from __future__ import annotations

from typing import Any


class LocalGPUHub:
    """GPU/local-model telemetry. Reports NO DATA until real probes exist."""

    def __init__(self) -> None:
        # No fabricated device identity: empty means "not detected".
        self.device_name = ""
        self.total_vram_gb = 0.0
        self.allocated_vram_gb = 0.0
        self.gpu_temp_c = 0.0
        self.is_offline_mode = False
        # No fabricated model catalog: only models actually registered by a
        # real inference engine (Ollama/vLLM/llama.cpp) would appear here.
        self._models: list[dict[str, Any]] = []

    def get_gpu_telemetry(self) -> dict[str, Any]:
        return {
            "device_name": self.device_name or None,
            "total_vram_gb": self.total_vram_gb,
            "allocated_vram_gb": self.allocated_vram_gb,
            "vram_utilization_pct": (
                round((self.allocated_vram_gb / self.total_vram_gb) * 100, 1)
                if self.total_vram_gb > 0
                else 0.0
            ),
            "gpu_temp_c": self.gpu_temp_c or None,
            "is_offline_mode": self.is_offline_mode,
            "hardware_detected": bool(self.device_name),
            "models": list(self._models),
        }

    def toggle_offline(self, offline: bool) -> dict[str, Any]:
        self.is_offline_mode = offline
        return {"is_offline_mode": self.is_offline_mode}

    def load_model(self, model_id: str) -> dict[str, Any]:
        # No real inference engine is wired, so no model can be loaded.
        return {
            "model_id": model_id,
            "status": "unavailable",
            "reason": "no local inference engine detected",
        }

    def unload_model(self, model_id: str) -> dict[str, Any]:
        return {
            "model_id": model_id,
            "status": "unavailable",
            "reason": "no local inference engine detected",
        }

    def download_model(self, model_id: str) -> dict[str, Any]:
        # No real inference engine / registry is wired, so no model can be
        # downloaded. Honest refusal instead of a fake "downloading" state.
        return {
            "model_id": model_id,
            "status": "unavailable",
            "reason": "no local inference engine detected",
        }


# Honest singleton: all telemetry is zero/NO-DATA until real hardware
# probes are wired (see module docstring).
gpu_hub = LocalGPUHub()
