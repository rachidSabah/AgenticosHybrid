# Contributing to AgenticOS

Thank you for your interest in contributing! AgenticOS is built with a strict
hexagonal (clean) architecture and a quality-first culture.

## Architecture Principles

1. **Ports before implementations.** Every subsystem exposes its interfaces in
   `src/agentic_os/ports/` *before* any concrete adapter exists. Concrete code
   lives in `adapters/`, business logic in `core/`, entities in `domain/`.
2. **Frozen public interfaces.** Once a port is validated, do not change its
   signature without an ADR and a deprecation window.
3. **No placeholders.** Every committed feature must be functional and
   integrated. No half-finished modules.
4. **Tests required.** Every change ships with automated tests; integration
   (live) coverage is strongly preferred for new subsystems.
5. **Documentation.** Every module is documented; significant decisions get an
   ADR in `docs/adr/`.

## Local Development

```bash
uv python install 3.13
uv sync
uv run agentic-os serve          # local dev server (BUS_TYPE=local)
```

## Quality Gates (CI)

All of the following must pass before merge:

- `ruff format --check`
- `ruff check`
- `ty` (strict type checking — no `# type: ignore`)
- `pytest` (unit + integration)
- Suppression / legacy-annotation grep

Run the local sequence with:

```bash
./scripts/ci.sh        # macOS / Linux
.\scripts\ci.ps1       # Windows (PowerShell)
```

Use `--only` / `--skip` to iterate on a subset, or `--dry-run` to preview.

## Commit Conventions

We use Conventional Commits:

- `feat:` new capability/feature
- `fix:` bug fix
- `refactor:` no behavior change
- `docs:` documentation only
- `test:` test additions/changes
- `chore:` tooling/version bumps

Example: `feat(providers): add round-robin routing policy`.

## Versioning

Production changes on `main` require a semver bump in `pyproject.toml` (and a
`uv lock`) in the **same** commit. See the repository `CLAUDE.md` / AGENTS.md
for the full rules.

## Pull Requests

- Target `main`; require review + passing CI.
- Keep PRs focused; large changes should be discussed via an issue or ADR first.
- Update `CHANGELOG.md` and relevant docs with your change.
