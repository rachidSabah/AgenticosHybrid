# Contributing to AgenticOS

Thank you for your interest in contributing to AgenticOS!

## Architecture Overview

AgenticOS follows a strict **hexagonal (clean) architecture** pattern:

```
User / CLI / Mission Control
        │
┌───────┴──────────────────────────────────┐
│  API (FastAPI) — REST + WebSocket         │
├──────────────────────────────────────────┤
│  CORE — orchestrator, runtime, MCP,      │
│         security, capability, memory,     │
│         discovery, learning, desktop      │
├──────────────────────────────────────────┤
│  DOMAIN — pure entities, no dependencies  │
├──────────────────────────────────────────┤
│  PORTS — abstract interfaces (Protocols)  │
├──────────────────────────────────────────┤
│  ADAPTERS — concrete implementations      │
└──────────────────────────────────────────┘
```

Key architectural rules:
1. **Ports before implementations.** Every subsystem exposes its interfaces in `src/agentic_os/ports/` before any concrete adapter exists.
2. **Frozen public interfaces.** Once a port is validated, do not change its signature without an ADR and deprecation window.
3. **No placeholders.** Every committed feature must be functional and integrated. No half-finished modules.
4. **Tests required.** Every change ships with automated tests. Integration (live) coverage is strongly preferred for new subsystems.
5. **Documentation.** Significant decisions get an ADR in `docs/adr/`.

## Development Setup

### Prerequisites
- Python 3.14+
- [uv](https://docs.astral.sh/uv/) >= 0.9 (project manager)
- Git
- (Windows) MSVC Build Tools for Tauri/Rust components

### Clone and Setup

```bash
git clone https://github.com/agentic-os/agentic-os.git
cd agentic-os
uv python install 3.14
uv sync
```

### Running the Backend

```bash
uv run python -m agentic_os serve
```

This starts the API server on `http://localhost:8000` with the local in-process event bus (`BUS_TYPE=local`).

### Running the Frontend (Mission Control)

```bash
npm --prefix apps/mission-control install
npm --prefix apps/mission-control run dev
```

Opens at `http://localhost:3000`.

### Windows-Specific Setup

For Tauri development on Windows, initialize the MSVC environment:

```powershell
& "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
```

## Code Style

AgenticOS uses [ruff](https://docs.astral.sh/ruff/) for formatting and linting with Python 3.14 target.

### Formatting
```bash
uv run ruff format . --check   # check formatting
uv run ruff format .            # auto-format
```

### Linting
```bash
uv run ruff check .
```

Selected rules: `E`, `F`, `I`, `B`, `UP` (with `B008` and `UP037` ignored).

### Type Annotations

All code must have complete type annotations. Strict type checking is enforced:

```bash
uv run ty .
```

No `# type: ignore` comments are permitted.

### Per-file Config
- `tests/test_sd_*.py` — E402 is ignored (services/ requires sys.path manipulation)
- `services/` — excluded from ruff entirely (standalone service layer)

## Testing

All tests use pytest with asyncio support:

```bash
uv run pytest                          # all tests
uv run pytest tests/ -v               # verbose
uv run pytest tests/ -x --tb=short    # stop on first failure
uv run pytest tests/test_sd_*.py      # runtime discovery tests
```

Test configuration:
- `asyncio_mode = auto` — async tests are auto-detected
- `pythonpath = ["src"]` — package imports work without sys.path manipulation
- Test files consuming from `services/` must add repo root to `sys.path` before imports

### Running CI Locally

```bash
# macOS / Linux
./scripts/ci.sh

# Windows (PowerShell)
.\scripts\ci.ps1

# Run only a subset
./scripts/ci.sh --only=lint

# Skip a stage
./scripts/ci.sh --skip=typecheck

# Preview
./scripts/ci.sh --dry-run
```

## Commit Conventions

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>
```

### Types
| Type | Usage |
|------|-------|
| `feat` | New capability or feature |
| `fix` | Bug fix |
| `refactor` | No behavior change |
| `docs` | Documentation only |
| `test` | Test additions or changes |
| `chore` | Tooling, version bumps, CI |

### Scopes (examples)
- `providers` — Provider management
- `mcp` — MCP Runtime
- `swarm` — Swarm orchestration
- `learning` — Learning engine
- `desktop` — Desktop runtime
- `security` — Security framework
- `api` — REST/WebSocket API
- `sdk` — Python SDK
- `ui` — Mission Control frontend

### Examples
```
feat(providers): add round-robin routing policy
fix(mcp): handle missing server in get_tools()
docs(api): add WebSocket examples
test(swarm): add consensus edge-case tests
chore: bump version to 0.9.2
```

## Pull Request Process

1. **Create an issue** or ADR for significant changes before coding
2. **Branch from `main`** using a descriptive name: `feat/my-feature`, `fix/my-bug`
3. **Keep PRs focused** — one feature/fix per PR. Large changes should be discussed via an issue or ADR first
4. **Ensure CI passes** — all quality gates (format, lint, typecheck, tests) must be green
5. **Update docs** — CHANGELOG.md, relevant docs, and ADRs if applicable
6. **Request review** — PRs require at least one approving review
7. **Target `main`** — all PRs merge into `main`
8. **Semver bump** — production changes on `main` require a semver bump in `pyproject.toml` (and `uv lock`) in the same commit

### PR Checklist
- [ ] Code follows style guidelines (ruff format, ruff check)
- [ ] Type annotations complete (ty passes)
- [ ] Tests added/updated and passing
- [ ] CHANGELOG.md updated
- [ ] Documentation updated (if applicable)
- [ ] No placeholder or dead code
- [ ] No secrets committed
- [ ] `uv lock` updated if dependencies changed

## Project Structure

```
src/agentic_os/
├── api/          # FastAPI REST + WebSocket endpoints
├── adapters/     # Concrete implementations (bus, providers, engines, discovery, MCP)
├── core/         # Business logic (runtime, MCP, security, capability, memory, etc.)
├── domain/       # Pure domain entities (Pydantic v2 / dataclasses)
├── infrastructure/ # Cross-cutting (logging, metrics, config)
├── ports/        # Abstract protocols/interfaces
├── sdk/          # Developer SDK (MCP, learning, swarm)
├── kernel.py     # Composition root
├── config.py     # Settings
├── cli.py        # CLI entry point
└── __main__.py   # python -m agentic_os entry

apps/
└── mission-control/  # Next.js frontend

services/
└── runtime_discovery/  # Standalone service layer (excluded from ruff)
```

## Versioning

AgenticOS follows [Semantic Versioning](https://semver.org/). Production changes on `main` require a semver bump in `pyproject.toml` and `uv lock` in the same commit.

Current version: `0.9.1` (pre-1.0.0-rc).

## Getting Help

- Open an issue on GitHub
- Check `docs/` for guides (TROUBLESHOOTING.md, FAQ.md, ARCHITECTURE.md)
- Review ADRs in `docs/adr/` for architectural decisions
