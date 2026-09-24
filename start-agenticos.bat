@echo off
setlocal EnableDelayedExpansion
title AgenticOS Hybrid Engine - Mission Control

cd /d "%~dp0."
set "ROOT=%cd%"

rem ── Ensure logs directory exists ─────────────────────────────────────────
if not exist "%ROOT%\logs" mkdir "%ROOT%\logs"

rem ── Fast startup environment flags ────────────────────────────────────────
set AGENTICOS_DIRECT_WORKSPACE=1
set AGENTICOS_SKIP_BRAIN_AUTODETECT=1
set AGENTICOS_DESKTOP_CHECK_UPDATES_ON_START=0

rem ── Kill any stale processes on ports 8000 and 3000 ─────────────────────
echo [AgenticOS] Clearing stale processes on ports 8000 and 3000...
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    taskkill /F /PID %%p >nul 2>&1
)
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":3000 " ^| findstr "LISTENING"') do (
    taskkill /F /PID %%p >nul 2>&1
)
timeout /t 1 /nobreak >nul

rem ── Start Nexus Gateway if installed and not running ─────────────────────
curl.exe -s -f --max-time 1 http://127.0.0.1:8787/healthz >nul 2>&1
if !errorlevel! neq 0 (
    if exist "%USERPROFILE%\.agent-nexus\repo" (
        echo [AgenticOS] Starting local Model Gateway on http://127.0.0.1:8787 ...
        start "Nexus Gateway" /min cmd /c "cd /d "%USERPROFILE%\.agent-nexus\repo" && pnpm.cmd --filter @anx/gateway dev"
        timeout /t 3 /nobreak >nul
    )
)

rem ── Detect Python executable ─────────────────────────────────────────────
set "PYTHON_EXE="
if exist "%ROOT%\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT%\.venv\Scripts\python.exe"
    echo [AgenticOS] Python: Virtual Environment
) else (
    where python.exe >nul 2>&1
    if !errorlevel! == 0 (
        set "PYTHON_EXE=python"
        echo [AgenticOS] Python: System
    ) else (
        echo [AgenticOS] ERROR: Python not found. Please install Python or setup .venv.
        pause
        exit /b 1
    )
)

rem ── Create clean launcher scripts (avoids Windows cmd quote escaping bugs) ──
(
echo @echo off
echo set AGENTICOS_DIRECT_WORKSPACE=1
echo set AGENTICOS_SKIP_BRAIN_AUTODETECT=1
echo set AGENTICOS_DESKTOP_CHECK_UPDATES_ON_START=0
echo cd /d "%ROOT%"
echo "%PYTHON_EXE%" -m agentic_os serve --host 127.0.0.1 --port 8000 ^> "%ROOT%\logs\backend.log" 2^>^&1
) > "%ROOT%\logs\_start_backend.bat"

(
echo @echo off
echo cd /d "%ROOT%\apps\mission-control"
if exist "%ROOT%\apps\mission-control\out\index.html" (
    echo node node_modules\serve\build\main.js -s out -l 3000 ^> "%ROOT%\logs\frontend.log" 2^>^&1
) else (
    echo npm.cmd run dev -- -H 127.0.0.1 -p 3000 ^> "%ROOT%\logs\frontend.log" 2^>^&1
)
) > "%ROOT%\logs\_start_frontend.bat"

rem ── Start Backend ────────────────────────────────────────────────────────
echo [AgenticOS] Starting Backend on http://127.0.0.1:8000 ...
start "AgenticOS Backend" /min cmd /c "%ROOT%\logs\_start_backend.bat"

rem ── Wait for backend ready ───────────────────────────────────────────────
echo [AgenticOS] Waiting for backend...
set /a WAITED=0
:wait_backend
timeout /t 2 /nobreak >nul
curl.exe -s -f --max-time 2 http://127.0.0.1:8000/healthz >nul 2>&1
if !errorlevel! == 0 goto backend_ready
set /a WAITED+=2
if !WAITED! GEQ 60 (
    echo.
    echo [AgenticOS] WARNING: Backend taking longer than usual.
    powershell -NoProfile -Command "Get-Content '%ROOT%\logs\backend.log' -Tail 8 -ErrorAction SilentlyContinue"
    echo.
    goto start_frontend
)
if !WAITED! GEQ 6 (
    echo [AgenticOS]   ... backend initializing ^(!WAITED!s^)...
)
goto wait_backend

:backend_ready
echo [AgenticOS] Backend READY (http://127.0.0.1:8000)

:start_frontend
rem ── Start Frontend ───────────────────────────────────────────────────────
if exist "%ROOT%\apps\mission-control\out\index.html" (
    echo [AgenticOS] Starting Mission Control (Production Build) on http://localhost:3000 ...
) else (
    echo [AgenticOS] Starting Mission Control (Dev Mode) on http://localhost:3000 ...
)
start "AgenticOS Frontend" /min cmd /c "%ROOT%\logs\_start_frontend.bat"

rem ── Wait for frontend ready ──────────────────────────────────────────────
echo [AgenticOS] Waiting for Mission Control UI...
set /a WAITED=0
:wait_frontend
timeout /t 2 /nobreak >nul
curl.exe -s -f --max-time 2 http://127.0.0.1:3000/ >nul 2>&1
if !errorlevel! == 0 goto frontend_ready
set /a WAITED+=2
if !WAITED! GEQ 60 (
    echo [AgenticOS] WARNING: Frontend still initializing. Opening browser anyway...
    goto open_browser
)
if !WAITED! GEQ 6 (
    echo [AgenticOS]   ... UI compiling/loading ^(!WAITED!s^)...
)
goto wait_frontend

:frontend_ready
echo [AgenticOS] Mission Control READY (http://localhost:3000)

:open_browser
echo [AgenticOS] Launching browser...
start "" "http://localhost:3000"

echo.
echo ===========================================================
echo   AgenticOS Mission Control is running!
echo.
echo   UI:          http://localhost:3000
echo   Backend:     http://127.0.0.1:8000
echo   Logs:        %ROOT%\logs\
echo ===========================================================
echo   Keep this window open while using AgenticOS.
echo   Press any key or Ctrl+C to stop both servers.
echo ===========================================================
echo.
pause >nul

echo.
echo [AgenticOS] Shutting down servers...
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    taskkill /F /PID %%p >nul 2>&1
)
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":3000 " ^| findstr "LISTENING"') do (
    taskkill /F /PID %%p >nul 2>&1
)
echo [AgenticOS] Servers stopped cleanly.
timeout /t 2 /nobreak >nul
