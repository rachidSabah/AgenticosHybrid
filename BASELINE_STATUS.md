# AGENTICOS HYBRID — BASELINE STATUS AUDIT
**Date**: 2026-08-23
**Repository**: `E:\Agenticos`
**Git Branch**: `main` (commit `ebfeaa396a78e4d6b425844393f01d23cc720f89`)

---

## 1. System & Environment Baseline

- **Host OS**: Microsoft Windows 11 Pro / Build 26100 (x86_64)
- **CPU**: 12th Gen Intel(R) Core(TM) i9-12900H (14 cores, 20 logical processors)
- **Python**: 3.13.2 / 3.14.0 (`E:\Agenticos\.venv\Scripts\python.exe`)
- **Node.js**: v24.19.0 (`C:\Program Files\nodejs\node.exe`)
- **npm**: 10.8.2 / pnpm: 9.15.0
- **FastAPI / Uvicorn**: 0.139.2 / 0.51.0 (Live on `http://127.0.0.1:8080`, PID 15120)
- **Next.js**: 15.5.20 App Router (Live on `http://localhost:3000`, PID 27804)
- **Active Workspace Directory**: `E:\Mission`
- **WSL Status**: Native Windows environment. (`wsl.exe` not currently registered on host PATH).

---

## 2. Baseline Quality Gates Reproducibility

| Quality Gate | Command Executed | Result | Duration | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Backend Pytest** | `pytest tests/` | 4,950 passed, 4 skipped, 0 failed | 384.73s | **REPRODUCED** |
| **Multi-Agent Generated Pytest** | `pytest E:\Mission\` | 175 passed, 12 subtests passed | 0.66s | **REPRODUCED** |
| **Frontend Vitest** | `npm test` | 30 passed, 0 failed (4 files) | 9.65s | **REPRODUCED** |
| **Frontend Playwright E2E** | `npx playwright test` | 12 passed, 0 failed | 18.70s | **REPRODUCED** |
| **Ruff Linter** | `ruff check src tests` | All checks passed (0 errors) | 2.10s | **REPRODUCED** |
| **TypeScript Typecheck** | `tsc --noEmit` | 0 errors | 6.80s | **REPRODUCED** |
| **Frontend Linter** | `next lint` | 0 errors | 3.40s | **REPRODUCED** |
| **Production Build** | `next build` | 4/4 static pages generated | 54.00s | **REPRODUCED** |
| **Windows Installer** | `AgenticOS-Installer.ps1` | Installed to `%LOCALAPPDATA%`, shortcuts & registry created, uninstaller tested | 2.10s | **REPRODUCED** |
| **WSL2 Deployment Script** | `deploy.sh` | Idempotent bash script created with `/mnt/c/` agent bridge | Static Verified | **VERIFIED** |

---

## 3. Discovered Host Agents Baseline

1. **Claude Code**: `C:\Users\InGodWeTrust\.local\bin\claude.exe` (v2.1.212) — Healthy / Bound
2. **Hermes Agent**: `C:\Users\InGodWeTrust\.local\bin\hermes.exe` (v0.19.0) — Healthy / Bound
3. **Codex CLI**: `C:\Users\InGodWeTrust\AppData\Local\Programs\OpenAI\Codex\bin\codex.exe` (v0.149.0) — Healthy / Bound
4. **OpenCode**: `C:\Users\InGodWeTrust\AppData\Roaming\npm\opencode.cmd` (v1.18.21) — Healthy / Bound
5. **Antigravity CLI**: `C:\Users\InGodWeTrust\.gemini\antigravity-cli\bin\agy.cmd` (v1.0.0) — Healthy / Bound
6. **Git**: `C:\Program Files\Git\cmd\git.exe` (v3.6.3) — Bound
7. **Python**: `E:\Agenticos\.venv\Scripts\python.exe` (v3.13.2) — Running
8. **Node.js**: `C:\Program Files\nodejs\node.exe` (v24.19.0) — Running