# Agentic OS — Developer Notes for AI Agents

## CI
- Run `uv run ruff check && uv run ruff format --check` before pushing
- Run `uv run pytest tests/` to verify all tests pass
- CI runs on `ubuntu-latest`, Python 3.14, via `uv run pytest -v --tb=short`
- `services/` is excluded from ruff (exclude = ["services/"]) — it's a standalone service layer, not part of the `agentic_os` package

## Import Conventions
- Main package: `agentic_os.*` lives under `src/agentic_os/`
- Service layer: `services.runtime_discovery.*` lives under `services/runtime_discovery/`
- Test files that import from `services.runtime_discovery.*` must add the repo root to `sys.path` before imports:
  ```python
  import sys
  from pathlib import Path
  _repo_root = str(Path(__file__).resolve().parent.parent)
  if _repo_root not in sys.path:
      sys.path.insert(0, _repo_root)
  ```
- Per-file ruff ignore for E402 in test files: `"tests/test_sd_*.py" = ["E402"]`

## Key Info
- Version: 1.0.0-rc1
- Remote branch protection on `main` is REMOVED (direct pushes allowed via token)
- All commands use `uv` (not pip/npm for Python)
- `pythonpath = ["src"]` in pyproject.toml (repo root NOT in sys.path by default)

## Windows Development
- **Rust/MSVC**: Tauri requires MSVC build tools. Run vcvars64.bat from VS Build Tools before cargo:
  ```
  & "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
  ```
- **Start backend**: `uv run python -m agentic_os serve` (port 8000)
- **Start frontend**: `npm --prefix apps/mission-control run dev` (port 3000)
- **CORS**: Backend allows origins `localhost:3000`, `127.0.0.1:3000`, `tauri://localhost`
- **Static export**: `npm --prefix apps/mission-control run build` produces `out/` directory
- **Python version**: System Python may be 3.12; `uv run` uses project-managed 3.14
- **`__main__.py`**: Exists at `src/agentic_os/__main__.py` — enables `python -m agentic_os serve`
