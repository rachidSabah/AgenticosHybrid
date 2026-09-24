@echo off
setlocal EnableDelayedExpansion
title AgenticOS Hybrid Engine - Mission Control
cd /d "%~dp0"

rem ── Ensure logs directory exists ─────────────────────────────────────────
if not exist "logs" mkdir logs

rem ── Write generated files directly into the workspace root ───────────────
set AGENTICOS_DIRECT_WORKSPACE=1

rem ── Speed up startup: skip slow brain auto-detection on Windows ──────────
set AGENTICOS_SKIP_BRAIN_AUTODETECT=1

rem ── Disable desktop update-check (crashes asyncio on Windows startup) ────
set AGENTICOS_DESKTOP_CHECK_UPDATES_ON_START=0

rem ── Kill any stale processes on port 8000 and 3000 ──────────────────────
echo [AgenticOS] Clearing ports 8000 and 3000...
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    taskkill /F /PID %%p >nul 2>&1
)
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":3000 " ^| findstr "LISTENING"') do (
    taskkill /F /PID %%p >nul 2>&1
)
rem Give OS a moment to release ports
timeout /t 2 /nobreak >nul

rem ── Detect Python / Backend Command ────────────────────────────────────
set "BACKEND_CMD="
if exist "%~dp0.venv\Scripts\python.exe" (
    echo [AgenticOS] Using local virtual environment Python
    set "BACKEND_CMD=\"%~dp0.venv\Scripts\python.exe\" -m agentic_os serve --host 127.0.0.1 --port 8000"
) else (
    where uv.exe >nul 2>&1
    if !errorlevel! == 0 (
        echo [AgenticOS] Using uv runner
        set "BACKEND_CMD=uv run python -m agentic_os serve --host 127.0.0.1 --port 8000"
    ) else if exist "%LOCALAPPDATA%\hermes\bin\uv.exe" (
        echo [AgenticOS] Using hermes uv runner
        set "BACKEND_CMD=\"%LOCALAPPDATA%\hermes\bin\uv.exe\" run python -m agentic_os serve --host 127.0.0.1 --port 8000"
    ) else (
        echo [AgenticOS] Using system python
        set "BACKEND_CMD=python -m agentic_os serve --host 127.0.0.1 --port 8000"
    )
)

rem ── Start Backend in a minimized window ──────────────────────────────────
echo [AgenticOS] Starting Backend on http://127.0.0.1:8000 ...
start "AgenticOS Backend" /min cmd /c "%BACKEND_CMD% > "%~dp0logs\backend.log" 2>&1"

rem ── Wait for backend to be ready (up to 120 seconds) ─────────────────────
echo [AgenticOS] Waiting for backend (up to 120s — first run does brain discovery)...
set /a WAITED=0
:wait_backend
timeout /t 3 /nobreak >nul
curl.exe -s -f --max-time 2 http://127.0.0.1:8000/healthz >nul 2>&1
if !errorlevel! == 0 goto backend_ready
set /a WAITED+=3
if !WAITED! GEQ 120 (
    echo.
    echo [AgenticOS] WARNING: Backend did not respond after 120s.
    echo [AgenticOS] Last log lines:
    powershell -NoProfile -Command "Get-Content '%~dp0logs\backend.log' -Tail 10 -ErrorAction SilentlyContinue"
    echo.
    echo [AgenticOS] Continuing to frontend anyway...
    goto start_frontend
)
if !WAITED! GEQ 10 (
    echo [AgenticOS]   ... backend starting, please wait (!WAITED!s elapsed)...
)
goto wait_backend

:backend_ready
echo [AgenticOS] Backend is READY on http://127.0.0.1:8000

:start_frontend
rem ── Start Frontend ────────────────────────────────────────────────────────
if exist "%~dp0apps\mission-control\out\index.html" (
    echo [AgenticOS] Starting Mission Control (Production Build) on http://127.0.0.1:3000 ...
    start "AgenticOS Mission Control" /min cmd /c "cd /d "%~dp0apps\mission-control" && npx.cmd serve -s out -l 3000 > "%~dp0logs\frontend.log" 2>&1"
) else (
    echo [AgenticOS] Starting Mission Control (Dev Server) on http://127.0.0.1:3000 ...
    echo [AgenticOS] NOTE: First compile takes 20-40 seconds. Please wait for the browser to open.
    start "AgenticOS Mission Control" /min cmd /c "cd /d "%~dp0apps\mission-control" && npm.cmd run dev -- -H 127.0.0.1 -p 3000 > "%~dp0logs\frontend.log" 2>&1"
)

rem ── Wait for frontend to be ready (up to 90 seconds) ─────────────────────
echo [AgenticOS] Waiting for Mission Control UI (up to 90s on first compile)...
set /a WAITED=0
:wait_frontend
timeout /t 3 /nobreak >nul
curl.exe -s -f --max-time 2 http://127.0.0.1:3000/ >nul 2>&1
if !errorlevel! == 0 goto frontend_ready
set /a WAITED+=3
if !WAITED! GEQ 90 (
    echo [AgenticOS] WARNING: Frontend did not respond after 90s.
    echo [AgenticOS] Check logs\frontend.log for details.
    goto open_browser
)
if !WAITED! GEQ 9 (
    echo [AgenticOS]   ... compiling UI modules (!WAITED!s elapsed)...
)
goto wait_frontend

:frontend_ready
echo [AgenticOS] Mission Control is READY on http://127.0.0.1:3000

:open_browser
rem ── Open Browser ─────────────────────────────────────────────────────────
echo [AgenticOS] Opening Mission Control in browser...
start http://127.0.0.1:3000

echo.
echo ===========================================================
echo  AgenticOS is running!
echo  Backend:         http://127.0.0.1:8000
echo  Mission Control: http://127.0.0.1:3000
echo  Backend log:     %~dp0logs\backend.log
echo  Frontend log:    %~dp0logs\frontend.log
echo ===========================================================
echo  Keep this window open. Press Ctrl+C to stop.
echo.
pause
