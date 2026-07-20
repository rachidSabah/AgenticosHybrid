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
- Version: 0.9.1
- Remote branch protection on `main` is REMOVED (direct pushes allowed via token)
- All commands use `uv` (not pip/npm for Python)
- `pythonpath = ["src"]` in pyproject.toml (repo root NOT in sys.path by default)
