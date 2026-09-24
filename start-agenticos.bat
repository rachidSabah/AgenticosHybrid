@echo off
setlocal EnableDelayedExpansion
title AgenticOS Hybrid Engine - Mission Control
cd /d "%~dp0"

rem ── Ensure logs directory exists ─────────────────────────────────────────
if not exist "logs" mkdir logs

rem ── Write generated files directly into the workspace root ───────────────
set AGENTICOS_DIRECT_WORKSPACE=1

rem ── Kill any stale processes on port 8000 and 3000 ──────────────────────
echo [AgenticOS] Clearing ports 8000 and 3000...
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    taskkill /F /PID %%p >nul 2>&1
)
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":3000 " ^| findstr "LISTENING"') do (
    taskkill /F /PID %%p >nul 2>&1
)

rem ── Install WhatsApp gateway dependencies if missing ─────────────────────
if not exist "node_modules\@whiskeysockets\baileys" (
    echo [AgenticOS] Installing WhatsApp gateway dependencies...
    call npm.cmd install --no-audit --no-fund
)

rem ── Detect Python / Backend Command ────────────────────────────────────
set "BACKEND_CMD="
if exist "%~dp0.venv\Scripts\python.exe" (
    echo [AgenticOS] Using local virtual environment Python: %~dp0.venv\Scripts\python.exe
    set "BACKEND_CMD=""%~dp0.venv\Scripts\python.exe"" -m agentic_os serve --host 127.0.0.1 --port 8000"
) else (
    where uv.exe >nul 2>&1
    if !errorlevel! == 0 (
        echo [AgenticOS] Using uv runner: uv.exe
        set "BACKEND_CMD=uv run python -m agentic_os serve --host 127.0.0.1 --port 8000"
    ) else if exist "%LOCALAPPDATA%\hermes\bin\uv.exe" (
        echo [AgenticOS] Using uv runner: %LOCALAPPDATA%\hermes\bin\uv.exe
        set "BACKEND_CMD=""%LOCALAPPDATA%\hermes\bin\uv.exe"" run python -m agentic_os serve --host 127.0.0.1 --port 8000"
    ) else (
        echo [AgenticOS] Using system python
        set "BACKEND_CMD=python -m agentic_os serve --host 127.0.0.1 --port 8000"
    )
)

rem ── Start Backend ─────────────────────────────────────────────────────────
echo [AgenticOS] Starting Backend on http://127.0.0.1:8000 ...
start "AgenticOS Backend" /min cmd /c "%BACKEND_CMD% > ""%~dp0logs\backend.log"" 2>&1"

rem ── Wait for backend to be ready (up to 45 seconds) ──────────────────────
echo [AgenticOS] Waiting for backend to be ready...
set /a WAITED=0
:wait_backend
timeout /t 2 /nobreak >nul
curl.exe -s -f http://127.0.0.1:8000/healthz >nul 2>&1
if !errorlevel! == 0 goto backend_ready
set /a WAITED+=2
if !WAITED! GEQ 45 (
    echo [AgenticOS] WARNING: Backend did not respond after 45s. Check logs\backend.log
    if exist "%~dp0logs\backend.log" (
        echo [AgenticOS] Recent backend log lines:
        powershell -NoProfile -Command "Get-Content '%~dp0logs\backend.log' -Tail 6 -ErrorAction SilentlyContinue"
    )
    goto start_frontend
)
echo [AgenticOS]   ... backend starting (!WAITED!s elapsed)
goto wait_backend

:backend_ready
echo [AgenticOS] Backend is READY on http://127.0.0.1:8000

:start_frontend
rem ── Start Frontend ───────────────────────────────────────────────────────
if exist "%~dp0apps\mission-control\out\index.html" (
    echo [AgenticOS] Starting Mission Control (Production Bundle) on http://127.0.0.1:3000 ...
    start "AgenticOS Mission Control" /min cmd /c "cd /d ""%~dp0apps\mission-control"" && npx.cmd serve -s out -l 3000 > ""%~dp0logs\frontend.log"" 2>&1"
) else (
    echo [AgenticOS] Starting Mission Control (Development Server) on http://127.0.0.1:3000 ...
    start "AgenticOS Mission Control" /min cmd /c "cd /d ""%~dp0apps\mission-control"" && npm.cmd run dev -- -H 127.0.0.1 -p 3000 > ""%~dp0logs\frontend.log"" 2>&1"
)

rem ── Wait for frontend to be ready (up to 60 seconds) ────────────────────
echo [AgenticOS] Waiting for Mission Control UI to be ready...
set /a WAITED=0
:wait_frontend
timeout /t 2 /nobreak >nul
curl.exe -s -f http://127.0.0.1:3000/ >nul 2>&1
if !errorlevel! == 0 goto frontend_ready
set /a WAITED+=2
if !WAITED! GEQ 60 (
    echo [AgenticOS] WARNING: Frontend did not respond after 60s. Check logs\frontend.log
    goto open_browser
)
echo [AgenticOS]   ... initializing UI (!WAITED!s elapsed)
goto wait_frontend

:frontend_ready
echo [AgenticOS] Mission Control is READY on http://127.0.0.1:3000

:open_browser
echo [AgenticOS] Launching Mission Control in browser...
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
