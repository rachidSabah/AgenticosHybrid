@echo off
setlocal
title AgenticOS Hybrid Engine - Mission Control
cd /d "%~dp0"

rem Ensure logs directory exists
if not exist "logs" mkdir logs

rem Write generated files directly into the workspace root so a "create a
rem website" mission lands files where the user expects. Without this, a git
rem workspace executes in a worktree that is never merged back.
set AGENTICOS_DIRECT_WORKSPACE=1

rem Verify and install root dependencies for WhatsApp gateway
if not exist "node_modules\@whiskeysockets\baileys" (
    echo [AgenticOS] Installing WhatsApp gateway dependencies...
    call npm.cmd install --no-audit --no-fund
)

echo [AgenticOS] Starting Backend on http://127.0.0.1:8001 ...
start "AgenticOS Backend" /b uv run python -m agentic_os serve --host 127.0.0.1 --port 8001 > logs\backend.log 2>&1

echo [AgenticOS] Starting Mission Control on http://localhost:3001 ...
start "AgenticOS Mission Control" /b cmd /c "cd /d ""%~dp0apps\mission-control"" && npm.cmd run dev > ""%~dp0logs\frontend.log"" 2>&1"

echo [AgenticOS] Waiting for services to initialize...
timeout /t 4 /nobreak >nul

echo [AgenticOS] Launching Mission Control UI in default browser...
start http://localhost:3001

echo ==========================================================
echo AgenticOS is running live!
echo Backend:         http://127.0.0.1:8001
echo Mission Control: http://localhost:3001
echo Logs directory:  %~dp0logs
echo ==========================================================
echo Keep this window open or minimize it. Press Ctrl+C to stop.
echo.
pause
