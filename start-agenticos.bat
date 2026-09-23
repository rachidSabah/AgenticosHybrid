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

rem ── Start Backend ─────────────────────────────────────────────────────────
echo [AgenticOS] Starting Backend on http://127.0.0.1:8000 ...
start "AgenticOS Backend" /min cmd /c "uv run python -m agentic_os serve --host 127.0.0.1 --port 8000 > logs\backend.log 2>&1"

rem ── Wait for backend to be ready (up to 60 seconds) ──────────────────────
echo [AgenticOS] Waiting for backend to be ready...
set /a WAITED=0
:wait_backend
timeout /t 2 /nobreak >nul
curl.exe -s -o nul -w "%%{http_code}" http://127.0.0.1:8000/healthz 2>nul | findstr /C:"200" >nul
if !errorlevel! == 0 goto backend_ready
set /a WAITED+=2
if !WAITED! GEQ 60 (
    echo [AgenticOS] WARNING: Backend did not respond after 60s. Check logs\backend.log
    goto start_frontend
)
echo [AgenticOS]   ... backend starting (%WAITED%s elapsed)
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

rem ── Wait for frontend to be ready (up to 90 seconds) ────────────────────
echo [AgenticOS] Waiting for Mission Control UI to be ready...
set /a WAITED=0
:wait_frontend
timeout /t 2 /nobreak >nul
curl.exe -s -o nul -w "%%{http_code}" http://127.0.0.1:3000/ 2>nul | findstr /C:"200" >nul
if !errorlevel! == 0 goto frontend_ready
set /a WAITED+=2
if !WAITED! GEQ 90 (
    echo [AgenticOS] WARNING: Frontend did not respond after 90s. Check logs\frontend.log
    goto open_browser
)
echo [AgenticOS]   ... initializing UI (%WAITED%s elapsed)
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
