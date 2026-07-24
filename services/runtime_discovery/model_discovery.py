"""AI model discovery — detects locally available AI/LLM models.

Discovers AI models from known locations and model registries:
- Ollama models (via ``ollama list`` CLI)
- HuggingFace cache (``~/.cache/huggingface/``)
- LM Studio models (``~/.lmstudio/models/``)
- vLLM model directories
- Custom model paths

Each discovered model is returned as a standardized ``DiscoveredModel``
that can be integrated into the Runtime Discovery pipeline.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.logging import get_logger

_log = get_logger(__name__)

__all__ = [
    "ModelDiscovery",
    "DiscoveredModel",
    "ModelFramework",
]

from enum import StrEnum


class ModelFramework(StrEnum):
    """Supported model frameworks."""

    OLLAMA = "ollama"
    HUGGINGFACE = "huggingface"
    LM_STUDIO = "lm_studio"
    VLLM = "vllm"
    TRANSFORMERS = "transformers"
    CUSTOM = "custom"


@dataclass
class DiscoveredModel:
    """A discovered AI/LLM model on the local system."""

    name: str
    framework: ModelFramework
    path: str | None = None
    version: str | None = None
    size_bytes: int | None = None
    quantization: str | None = None
    family: str | None = None
    parameters: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    discovered_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "framework": self.framework.value,
            "path": self.path,
            "version": self.version,
            "size_bytes": self.size_bytes,
            "quantization": self.quantization,
            "family": self.family,
            "parameters": self.parameters,
            "metadata": dict(self.metadata),
            "discovered_at": self.discovered_at.isoformat(),
        }


class ModelDiscovery:
    """Discovers locally available AI/LLM models.

    Queries each supported model framework and returns discovered models
    with metadata including size, version, and quantization.
    """

    def __init__(self) -> None:
        self._ollama_binary: str | None = None

    # ── Public API ──

    async def discover_all(self) -> list[DiscoveredModel]:
        """Discover models from all supported frameworks."""
        models: list[DiscoveredModel] = []
        errors: list[str] = []

        for method in (
            self._discover_ollama,
            self._discover_huggingface,
            self._discover_lm_studio,
            self._discover_vllm,
        ):
            try:
                result = await method()
                models.extend(result)
            except Exception as exc:
                errors.append(str(exc))

        if errors:
            _log.debug("Model discovery errors: %s", "; ".join(errors))

        _log.info("Discovered %d models across all frameworks", len(models))
        return models

    async def discover_by_framework(self, framework: ModelFramework) -> list[DiscoveredModel]:
        """Discover models from a specific framework only."""
        dispatcher = {
            ModelFramework.OLLAMA: self._discover_ollama,
            ModelFramework.HUGGINGFACE: self._discover_huggingface,
            ModelFramework.LM_STUDIO: self._discover_lm_studio,
            ModelFramework.VLLM: self._discover_vllm,
        }
        method = dispatcher.get(framework)
        if method is None:
            return []
        return await method()

    # ── Ollama ──

    async def _discover_ollama(self) -> list[DiscoveredModel]:
        """Discover models via ``ollama list`` CLI."""
        binary = self._resolve_ollama()
        if binary is None:
            return []

        try:
            result = subprocess.run(
                [binary, "list"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return []

            models: list[DiscoveredModel] = []
            for line in result.stdout.strip().split("\n")[1:]:  # skip header
                if not line.strip():
                    continue
                parts = line.split()
                if not parts:
                    continue
                name = parts[0]
                model = DiscoveredModel(
                    name=name,
                    framework=ModelFramework.OLLAMA,
                    parameters=parts[1] if len(parts) > 1 else None,
                    size_bytes=self._parse_size(parts[2]) if len(parts) > 2 else None,
                    metadata={"source": "ollama_list"},
                )
                models.append(model)
            return models
        except FileNotFoundError:
            return []
        except subprocess.TimeoutExpired:
            _log.debug("Ollama list timed out")
            return []
        except Exception as exc:
            _log.debug("Ollama discovery failed: %s", exc)
            return []

    def _resolve_ollama(self) -> str | None:
        """Find the ollama binary."""
        if self._ollama_binary:
            return self._ollama_binary
        import shutil

        binary = shutil.which("ollama")
        if binary:
            self._ollama_binary = binary
        return binary

    # ── HuggingFace ──

    async def _discover_huggingface(self) -> list[DiscoveredModel]:
        """Discover models from the HuggingFace cache directory."""
        cache_dir = self._hf_cache_dir()
        if cache_dir is None:
            return []

        models: list[DiscoveredModel] = []
        try:
            for entry in cache_dir.iterdir():
                if entry.is_dir():
                    # Check for model files (safetensors, bin, etc.)
                    model_files = list(entry.glob("*.safetensors")) + list(entry.glob("*.bin"))
                    if model_files:
                        total_size = sum(f.stat().st_size for f in model_files)
                        models.append(
                            DiscoveredModel(
                                name=entry.name.replace(".", "/", 1) if "." in entry.name else entry.name,
                                framework=ModelFramework.HUGGINGFACE,
                                path=str(entry),
                                size_bytes=total_size,
                                metadata={"source": "hf_cache", "model_files": len(model_files)},
                            )
                        )
        except PermissionError:
            _log.debug("Permission denied reading HF cache: %s", cache_dir)
        except OSError as exc:
            _log.debug("Error reading HF cache: %s", exc)

        return models

    @staticmethod
    def _hf_cache_dir() -> Path | None:
        """Return the HuggingFace cache directory path, if it exists."""
        # Check HF_HOME env var first, then default ~/.cache/huggingface/
        hf_home = os.environ.get("HF_HOME")
        if hf_home:
            candidate = Path(hf_home) / "hub"
            if candidate.is_dir():
                return candidate

        default = Path.home() / ".cache" / "huggingface" / "hub"
        return default if default.is_dir() else None

    # ── LM Studio ──

    async def _discover_lm_studio(self) -> list[DiscoveredModel]:
        """Discover models from LM Studio's model directory."""
        lm_studio_dir = self._lm_studio_dir()
        if lm_studio_dir is None:
            return []

        models: list[DiscoveredModel] = []
        try:
            for model_dir in lm_studio_dir.iterdir():
                if not model_dir.is_dir():
                    continue
                gguf_files = list(model_dir.glob("*.gguf"))
                for gguf in gguf_files:
                    name = f"{model_dir.name}/{gguf.stem}"
                    quantization = self._detect_quantization(gguf.stem)
                    models.append(
                        DiscoveredModel(
                            name=name,
                            framework=ModelFramework.LM_STUDIO,
                            path=str(gguf),
                            size_bytes=gguf.stat().st_size,
                            quantization=quantization,
                            metadata={"source": "lm_studio"},
                        )
                    )
        except PermissionError:
            _log.debug("Permission denied reading LM Studio dir: %s", lm_studio_dir)
        except OSError as exc:
            _log.debug("Error reading LM Studio dir: %s", exc)

        return models

    @staticmethod
    def _lm_studio_dir() -> Path | None:
        """Return the LM Studio models directory, if it exists."""
        candidate = Path.home() / ".lmstudio" / "models"
        return candidate if candidate.is_dir() else None

    # ── vLLM ──

    async def _discover_vllm(self) -> list[DiscoveredModel]:
        """Discover models served by a local vLLM instance."""
        import shutil

        vllm_binary = shutil.which("vllm")
        if vllm_binary is None:
            return []

        # vLLM doesn't have a list command; check common model dirs
        model_dirs = self._vllm_model_dirs()
        models: list[DiscoveredModel] = []
        for model_dir in model_dirs:
            if not model_dir.is_dir():
                continue
            try:
                for entry in model_dir.iterdir():
                    if entry.is_dir() and self._looks_like_model(entry):
                        models.append(
                            DiscoveredModel(
                                name=entry.name,
                                framework=ModelFramework.VLLM,
                                path=str(entry),
                                metadata={"source": "vllm_dir"},
                            )
                        )
            except PermissionError:
                continue
        return models

    @staticmethod
    def _vllm_model_dirs() -> list[Path]:
        """Return candidate vLLM model directories."""
        return [
            Path.home() / ".cache" / "vllm",
            Path.home() / ".vllm" / "models",
            Path("/models"),
        ]

    @staticmethod
    def _looks_like_model(directory: Path) -> bool:
        """Heuristic check if a directory contains model files."""
        for pattern in ("*.safetensors", "*.bin", "*.pt", "config.json"):
            if list(directory.glob(pattern)):
                return True
        return False

    # ── Utilities ──

    @staticmethod
    def _parse_size(size_str: str) -> int | None:
        """Parse a size string (e.g. '3.5GB', '450MB') to bytes."""
        try:
            size_str = size_str.strip().upper()
            if size_str.endswith("GB"):
                return int(float(size_str[:-2]) * 1024**3)
            if size_str.endswith("MB"):
                return int(float(size_str[:-2]) * 1024**2)
            if size_str.endswith("KB"):
                return int(float(size_str[:-2]) * 1024)
            return int(size_str)
        except (ValueError, IndexError):
            return None

    @staticmethod
    def _detect_quantization(name: str) -> str | None:
        """Detect quantization from a model filename."""
        name_upper = name.upper()
        for q in ("Q2_K", "Q3_K", "Q4_K_M", "Q4_K_S", "Q5_K_M", "Q5_K_S", "Q6_K", "Q8_0", "FP16", "FP32"):
            if q in name_upper:
                return q
        return None
