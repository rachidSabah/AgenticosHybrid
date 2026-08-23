@echo off
setlocal enabledelayedexpansion
title AgenticOS Hybrid — Mission Control Launcher
cd /d "%~dp0"

echo ================================================================
echo           AGENTICOS HYBRID — AUTONOMOUS AI PLATFORM
echo ================================================================
echo.

set "BACKEND_PORT=8080"
set "FRONTEND_PORT=3000"
set "BACKEND_URL=http://127.0.0.1:%BACKEND_PORT%"
set "FRONTEND_URL=http://localhost:%FRONTEND_PORT%"

REM 1. Locate Python executable / uv
set "PYTHON_EXE="
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    where uv >nul 2>&1
    if !errorlevel! equ 0 (
        set "PYTHON_EXE=uv run python"
    ) else (
        where python >nul 2>&1
        if !errorlevel! equ 0 (
            set "PYTHON_EXE=python"
        )
    )
)

if "%PYTHON_EXE%"=="" (
    echo [ERROR] No Python environment found!
    echo Please install Python 3.12+ or run: uv sync --dev
    pause
    exit /b 1
)

REM 2. Check if Backend is already running
powershell -Command "$c = Test-NetConnection -ComputerName 127.0.0.1 -Port %BACKEND_PORT% -WarningAction SilentlyContinue; if ($c.TcpTestSucceeded) { exit 0 } else { exit 1 }" >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Backend is already running on %BACKEND_URL%
) else (
    echo [1/3] Starting Backend Control Plane on %BACKEND_URL% ...
    if not exist "logs" mkdir "logs"
    start "AgenticOS Backend :%BACKEND_PORT%" cmd /c "%PYTHON_EXE% -m agentic_os serve --host 127.0.0.1 --port %BACKEND_PORT% > logs\backend.log 2>&1"
)

REM 3. Check if Frontend is already running
powershell -Command "$c = Test-NetConnection -ComputerName 127.0.0.1 -Port %FRONTEND_PORT% -WarningAction SilentlyContinue; if ($c.TcpTestSucceeded) { exit 0 } else { exit 1 }" >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Frontend is already running on %FRONTEND_URL%
) else (
    echo [2/3] Starting Mission Control Frontend on %FRONTEND_URL% ...
    if exist "apps\mission-control" (
        start "AgenticOS Frontend :%FRONTEND_PORT%" cmd /c "cd /d apps\mission-control && set NEXT_PUBLIC_API_BASE=%BACKEND_URL%&& npm run dev > ..\..\logs\frontend.log 2>&1"
    )
)

REM 4. Health Check Loop
echo [3/3] Waiting for AgenticOS services to become healthy...
set "HEALTHY=0"
for /l %%i in (1,1,20) do (
    powershell -Command "try { $r = Invoke-RestMethod -Uri '%BACKEND_URL%/healthz' -TimeoutSec 1; if ($r.status -eq 'ok') { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
    if !errorlevel! equ 0 (
        set "HEALTHY=1"
        goto :launched
    )
    timeout /t 1 /nobreak >nul
)

:launched
echo.
echo ================================================================
echo   AGENTICOS HYBRID IS ONLINE!
echo   Mission Control UI : %FRONTEND_URL%
echo   Backend API / SSE  : %BACKEND_URL%
echo   API Documentation  : %BACKEND_URL%/docs
echo   Active Workspace   : E:\Mission
echo ================================================================
echo.
echo Launching default web browser...
start "" "%FRONTEND_URL%"
echo.
echo Tip: Keep this window open or minimize it. To stop services, close the backend/frontend windows.