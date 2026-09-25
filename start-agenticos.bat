@echo off
setlocal EnableDelayedExpansion
title AgenticOS Hybrid Engine - Mission Control

rem ============================================================================
rem  AgenticOS launcher - Windows 10/11
rem
rem  MAINTAINER NOTE: this file MUST keep CRLF line endings. cmd.exe is
rem  unreliable with LF-only batch files (goto/label lookups can fail at
rem  512-byte buffer boundaries and the window closes with no error).
rem  .gitattributes marks *.bat as -text so the committed CRLF bytes are
rem  served verbatim in every checkout and every GitHub source ZIP.
rem ============================================================================

rem -- Set ROOT to the folder that contains this bat file --------------------
cd /d "%~dp0"
set "ROOT=%cd%"
if not "%~1"=="" if exist "%~1\apps\mission-control" (
    cd /d "%~1"
    set "ROOT=%cd%"
)

rem -- Ensure logs directory exists ------------------------------------------
if not exist "%ROOT%\logs" mkdir "%ROOT%\logs"

echo [AgenticOS] Root: %ROOT%
echo [AgenticOS] If this is not your AgenticosHybrid checkout, close this window
echo [AgenticOS] and run start-agenticos.bat from the repo root instead.
echo.
rem -- Fast startup environment flags ----------------------------------------
set AGENTICOS_DIRECT_WORKSPACE=1
set AGENTICOS_SKIP_BRAIN_AUTODETECT=1
set AGENTICOS_DESKTOP_CHECK_UPDATES_ON_START=0

rem -- Kill any stale processes on ports 8000 and 3000 -----------------------
echo [AgenticOS] Clearing stale processes on ports 8000 and 3000...
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":8000 " ^| findstr "LISTENING"') do taskkill /F /PID %%p >nul 2>&1
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":3000 " ^| findstr "LISTENING"') do taskkill /F /PID %%p >nul 2>&1
ping -n 2 127.0.0.1 >nul

rem -- Detect Python executable ----------------------------------------------
set "PYTHON_EXE="
if exist "%ROOT%\.venv\Scripts\python.exe" goto python_venv
where python.exe >nul 2>&1
if errorlevel 1 goto python_missing
set "PYTHON_EXE=python"
echo [AgenticOS] Python: System
goto python_found

:python_venv
set "PYTHON_EXE=%ROOT%\.venv\Scripts\python.exe"
echo [AgenticOS] Python: Virtual Environment
goto python_found

:python_missing
echo [AgenticOS] ERROR: Python was not found on this system.
echo [AgenticOS] Install Python 3.12+ from https://www.python.org/downloads/
echo [AgenticOS] (tick "Add python.exe to PATH" in the installer), then run
echo [AgenticOS] start-agenticos.bat again.
echo.
pause
exit /b 1

:python_found
rem -- Pre-flight: verify the backend is importable with this Python ---------
echo [AgenticOS] Checking backend dependencies...
"%PYTHON_EXE%" -c "import agentic_os, fastapi, uvicorn" >nul 2>&1
if errorlevel 1 goto deps_missing
echo [AgenticOS] Dependencies OK.
goto deps_ok

:deps_missing
echo.
echo [AgenticOS] ============================================================
echo [AgenticOS]  ERROR: backend dependencies are NOT importable with:
echo [AgenticOS]    %PYTHON_EXE%
echo [AgenticOS]  This is common right after downloading the source ZIP:
echo [AgenticOS]  the archive contains no .venv, and the system Python has
echo [AgenticOS]  no AgenticOS packages. Python 3.12+ is required.
echo [AgenticOS] ------------------------------------------------------------
echo [AgenticOS]  MANUAL FIX - open a terminal at the repo root and run:
echo [AgenticOS]    uv sync
echo [AgenticOS]  or, with plain Python:
echo [AgenticOS]    python -m venv .venv
echo [AgenticOS]    .venv\Scripts\python -m pip install -e .
echo [AgenticOS]  Then run start-agenticos.bat again.
echo [AgenticOS] ============================================================
choice /C YN /M "[AgenticOS] Install dependencies into .venv now"
if errorlevel 2 goto deps_refused
echo [AgenticOS] Installing - this needs internet and can take minutes...
where uv.exe >nul 2>&1
if errorlevel 1 goto install_pip
echo [AgenticOS] Using uv to provision .venv...
uv sync
if errorlevel 1 goto install_failed
goto install_verify

:install_pip
if exist "%ROOT%\.venv\Scripts\python.exe" goto install_pip_run
echo [AgenticOS] Creating .venv with %PYTHON_EXE% ...
"%PYTHON_EXE%" -m venv "%ROOT%\.venv"
if errorlevel 1 goto install_failed
:install_pip_run
echo [AgenticOS] Installing packages with pip...
"%ROOT%\.venv\Scripts\python.exe" -m pip install -e "%ROOT%"
if errorlevel 1 goto install_failed

:install_verify
set "PYTHON_EXE=%ROOT%\.venv\Scripts\python.exe"
echo [AgenticOS] Re-checking dependencies with: %PYTHON_EXE%
"%PYTHON_EXE%" -c "import agentic_os, fastapi, uvicorn" >nul 2>&1
if errorlevel 1 goto install_failed
echo [AgenticOS] Dependencies installed and verified.
goto deps_ok

:install_failed
echo.
echo [AgenticOS] ERROR: automatic dependency installation failed.
echo [AgenticOS] The real error is printed above. Common causes:
echo [AgenticOS]   - no internet access
echo [AgenticOS]   - system Python below 3.12 (check: python --version)
echo [AgenticOS] Fix manually with the commands shown above, then rerun.
echo.
pause
exit /b 1

:deps_refused
echo [AgenticOS] The backend cannot start without its dependencies.
echo [AgenticOS] Nothing was changed on this machine.
echo.
pause
exit /b 1

:deps_ok
rem -- Write backend launcher script (single-line appends: safe for paths
rem -- that contain parentheses or ampersands, unlike parenthesized blocks) --
set "CHILD=%ROOT%\logs\_start_backend.bat"
echo @echo off> "%CHILD%"
echo set AGENTICOS_DIRECT_WORKSPACE=1 >> "%CHILD%"
echo set AGENTICOS_SKIP_BRAIN_AUTODETECT=1 >> "%CHILD%"
echo set AGENTICOS_DESKTOP_CHECK_UPDATES_ON_START=0 >> "%CHILD%"
echo cd /d "%ROOT%" >> "%CHILD%"
echo "%PYTHON_EXE%" -m agentic_os serve --host 127.0.0.1 --port 8000 ^> "%ROOT%\logs\backend.log" 2^>^&1 >> "%CHILD%"
echo echo %%errorlevel%% ^> "%ROOT%\logs\backend_exit.txt">> "%CHILD%"
if not exist "%CHILD%" goto launcher_failed

rem -- Write frontend launcher script (mode decided here, logic-free child) --
set "FE_CMD=call npm.cmd run dev -- -H 127.0.0.1 -p 3000"
if not exist "%ROOT%\apps\mission-control\out\index.html" goto fe_write
if not exist "%ROOT%\apps\mission-control\node_modules\serve\build\main.js" goto fe_write
set "FE_CMD=node node_modules\serve\build\main.js -s out -l 3000"
:fe_write
set "FCHILD=%ROOT%\logs\_start_frontend.bat"
echo @echo off> "%FCHILD%"
echo cd /d "%ROOT%\apps\mission-control" >> "%FCHILD%"
echo %FE_CMD% ^> "%ROOT%\logs\frontend.log" 2^>^&1 >> "%FCHILD%"
echo echo %%errorlevel%% ^> "%ROOT%\logs\frontend_exit.txt">> "%FCHILD%"
if not exist "%FCHILD%" goto launcher_failed

rem -- Health-check tool availability ----------------------------------------
set "HAVE_CURL=1"
where curl.exe >nul 2>&1
if errorlevel 1 set "HAVE_CURL=0"
if "%HAVE_CURL%"=="1" goto curl_ok
echo [AgenticOS] WARNING: curl.exe was not found - backend/UI health cannot be
echo [AgenticOS]          probed. Fixed waits will be used instead. Windows 10
echo [AgenticOS]          1803+ ships curl.exe; older systems can install it.
:curl_ok

rem -- Start Backend ---------------------------------------------------------
echo [AgenticOS] Starting Backend on http://127.0.0.1:8000 ...
if exist "%ROOT%\logs\backend_exit.txt" del "%ROOT%\logs\backend_exit.txt" >nul 2>&1
if exist "%ROOT%\logs\backend.log" move /y "%ROOT%\logs\backend.log" "%ROOT%\logs\backend.prev.log" >nul 2>&1
start "AgenticOS Backend" /min cmd /c "%ROOT%\logs\_start_backend.bat"

rem -- Wait for backend ready ------------------------------------------------
echo [AgenticOS] Waiting for backend...
set /a WAITED=0

:wait_backend
ping -n 3 127.0.0.1 >nul
if "%HAVE_CURL%"=="0" goto be_probe_done
curl.exe -s -f --max-time 2 http://127.0.0.1:8000/healthz >nul 2>&1
if !errorlevel! == 0 goto backend_ready
:be_probe_done
rem -- The launcher writes logs\backend_exit.txt the moment the backend
rem -- process exits for ANY reason: report it honestly instead of hanging.
if exist "%ROOT%\logs\backend_exit.txt" goto backend_died
set /a WAITED+=2
if "!HAVE_CURL!"=="0" if !WAITED! GEQ 15 goto backend_uncertain
if !WAITED! GEQ 60 goto backend_timeout
if !WAITED! GEQ 6 echo [AgenticOS]   ... backend initializing ^(!WAITED!s^)...
goto wait_backend

:backend_ready
echo [AgenticOS] Backend READY - http://127.0.0.1:8000
goto start_frontend

:backend_died
echo.
echo [AgenticOS] ============================================================
echo [AgenticOS]  ERROR: the backend process exited before becoming healthy.
echo [AgenticOS]  Last lines of logs\backend.log:
echo [AgenticOS]  ------------------------------------------------------------
powershell -NoProfile -Command "Get-Content -LiteralPath '%ROOT%\logs\backend.log' -Tail 40 -ErrorAction SilentlyContinue"
echo [AgenticOS]  ------------------------------------------------------------
echo [AgenticOS]  Full log: %ROOT%\logs\backend.log
echo [AgenticOS]  Common causes:
echo [AgenticOS]    - port 8000 already in use by another program
echo [AgenticOS]    - a runtime error - read the traceback printed above
echo [AgenticOS] ============================================================
echo.
pause
exit /b 1

:backend_timeout
echo [AgenticOS] WARNING: the backend did not answer /healthz within 60s.
echo [AgenticOS] It may still be initializing. Last lines of logs\backend.log:
echo [AgenticOS] ------------------------------------------------------------
powershell -NoProfile -Command "Get-Content -LiteralPath '%ROOT%\logs\backend.log' -Tail 40 -ErrorAction SilentlyContinue"
echo [AgenticOS] ------------------------------------------------------------
echo [AgenticOS] Continuing - Mission Control will report backend state honestly.
goto start_frontend

:backend_uncertain
echo [AgenticOS] curl.exe not found - backend health could not be verified.
echo [AgenticOS] Continuing. If the UI reports the backend unavailable, check
echo [AgenticOS] %ROOT%\logs\backend.log for the real error.
goto start_frontend

:launcher_failed
echo.
echo [AgenticOS] ERROR: could not write the launcher script under %ROOT%\logs
echo [AgenticOS] Check folder permissions (read-only folder? antivirus block?)
echo [AgenticOS] and run start-agenticos.bat again.
echo.
pause
exit /b 1

:start_frontend
rem -- Start Frontend --------------------------------------------------------
if exist "%ROOT%\apps\mission-control\node_modules" goto fe_modules_ok
echo.
echo [AgenticOS] ============================================================
echo [AgenticOS]  apps\mission-control\node_modules is missing.
echo [AgenticOS]  This is normal right after downloading the source ZIP:
echo [AgenticOS]  the archive ships no installed JavaScript packages, and
echo [AgenticOS]  Mission Control cannot start without them.
echo [AgenticOS] ------------------------------------------------------------
echo [AgenticOS]  MANUAL FIX - open a terminal at the repo root and run:
echo [AgenticOS]    cd apps\mission-control
echo [AgenticOS]    npm install
echo [AgenticOS]  Then run start-agenticos.bat again.
echo [AgenticOS] ============================================================
choice /C YN /M "[AgenticOS] Install frontend dependencies now"
if errorlevel 2 goto fe_deps_refused
echo [AgenticOS] Locating npm...
where npm.cmd >nul 2>&1
if errorlevel 1 goto npm_missing
echo [AgenticOS] Installing - this needs internet and can take minutes...
cd /d "%ROOT%\apps\mission-control"
call npm.cmd install
if errorlevel 1 goto fe_install_failed
if not exist "%ROOT%\apps\mission-control\node_modules" goto fe_install_failed
echo [AgenticOS] Frontend dependencies installed and verified.
cd /d "%ROOT%"
goto fe_modules_ok

:fe_deps_refused
echo [AgenticOS] Mission Control cannot start without its dependencies.
echo [AgenticOS] Nothing was changed on this machine. You can rerun
echo [AgenticOS] start-agenticos.bat and answer Y any time.
echo.
pause
exit /b 1

:npm_missing
echo.
echo [AgenticOS] ERROR: npm was not found on this system.
echo [AgenticOS] Install Node.js 20 LTS from https://nodejs.org/en/download
echo [AgenticOS] (npm ships with Node.js), open a NEW terminal, then run
echo [AgenticOS] start-agenticos.bat again.
echo.
pause
exit /b 1

:fe_install_failed
echo.
echo [AgenticOS] ERROR: npm install failed. The real error is printed above.
echo [AgenticOS] Common causes:
echo [AgenticOS]   - no internet access
echo [AgenticOS]   - Node.js older than 18 (check: node --version)
echo [AgenticOS] Fix the cause, then rerun start-agenticos.bat.
echo.
pause
exit /b 1

:fe_modules_ok
if not exist "%ROOT%\apps\mission-control\out\index.html" goto fe_dev
if not exist "%ROOT%\apps\mission-control\node_modules\serve\build\main.js" goto fe_static_noserve
echo [AgenticOS] Starting Mission Control (Production Build) on http://localhost:3000 ...
goto fe_start

:fe_static_noserve
echo [AgenticOS] Static export found but serve package missing - using Dev Mode.
:fe_dev
where npm.cmd >nul 2>&1
if errorlevel 1 goto npm_missing
echo [AgenticOS] Starting Mission Control (Dev Mode) on http://localhost:3000 ...
:fe_start
rem -- Fresh sentinel + rotated log for this run -----------------------
if exist "%ROOT%\logs\frontend_exit.txt" del "%ROOT%\logs\frontend_exit.txt" >nul 2>&1
if exist "%ROOT%\logs\frontend.log" move /y "%ROOT%\logs\frontend.log" "%ROOT%\logs\frontend.prev.log" >nul 2>&1
start "AgenticOS Frontend" /min cmd /c "%ROOT%\logs\_start_frontend.bat"

rem -- Wait for frontend ready -----------------------------------------------
echo [AgenticOS] Waiting for Mission Control UI...
set /a WAITED=0

:wait_frontend
ping -n 3 127.0.0.1 >nul
if "%HAVE_CURL%"=="0" goto fe_probe_done
curl.exe -s -f --max-time 2 http://127.0.0.1:3000/ >nul 2>&1
if !errorlevel! == 0 goto frontend_ready
:fe_probe_done
rem -- The launcher writes logs\frontend_exit.txt the moment the UI
rem -- process exits for ANY reason: report it honestly instead of
rem -- hanging on "UI loading" messages.
if exist "%ROOT%\logs\frontend_exit.txt" goto frontend_died
set /a WAITED+=2
if "!HAVE_CURL!"=="0" if !WAITED! GEQ 30 goto frontend_uncertain
if !WAITED! GEQ 60 goto frontend_timeout
if !WAITED! GEQ 6 echo [AgenticOS]   ... UI loading ^(!WAITED!s^)...
goto wait_frontend

:frontend_ready
echo [AgenticOS] Mission Control READY - http://localhost:3000
goto open_browser

:frontend_died
echo.
echo [AgenticOS] ============================================================
echo [AgenticOS]  ERROR: the Mission Control process exited before it
echo [AgenticOS]  could serve anything. Last lines of logs\frontend.log:
echo [AgenticOS]  ------------------------------------------------------------
powershell -NoProfile -Command "Get-Content -LiteralPath '%ROOT%\logs\frontend.log' -Tail 40 -ErrorAction SilentlyContinue"
echo [AgenticOS]  ------------------------------------------------------------
echo [AgenticOS]  Full log: %ROOT%\logs\frontend.log
echo [AgenticOS]  Common causes:
echo [AgenticOS]    - Node.js missing or older than 18 (check: node --version)
echo [AgenticOS]    - port 3000 already in use by another program
echo [AgenticOS]    - a broken install - delete apps\mission-control\node_modules,
echo [AgenticOS]      run start-agenticos.bat again and accept the reinstall
echo [AgenticOS] ============================================================
echo.
pause
exit /b 1

:frontend_timeout
echo [AgenticOS] WARNING: Mission Control did not answer within 60s.
echo [AgenticOS] Last lines of logs\frontend.log:
echo [AgenticOS] ------------------------------------------------------------
powershell -NoProfile -Command "Get-Content -LiteralPath '%ROOT%\logs\frontend.log' -Tail 40 -ErrorAction SilentlyContinue"
echo [AgenticOS] ------------------------------------------------------------
echo [AgenticOS] Opening the browser anyway - the page will show what works.
goto open_browser

:frontend_uncertain
echo [AgenticOS] curl.exe not found - UI health could not be verified.
echo [AgenticOS] Opening the browser anyway.

:open_browser
echo [AgenticOS] Launching browser...
start "" "http://localhost:3000" 2>nul
if errorlevel 1 rundll32 url.dll,FileProtocolHandler http://localhost:3000
if errorlevel 1 echo [AgenticOS] WARNING: could not auto-launch a browser. Open http://localhost:3000 manually.

echo.
echo ===========================================================
echo   AgenticOS Mission Control is running.
echo.
echo   UI:          http://localhost:3000
echo   Backend:     http://127.0.0.1:8000
echo   Logs:        %ROOT%\logs\
echo.
echo   Note: external proxy gateways (bound via Mission Control, Proxy
echo   Bindings view) are SEPARATE products on their own ports - they do
echo   not open a browser and are never required to run AgenticOS.
echo   Verify listeners:  netstat -ano ^| findstr ":3000 :8000"
echo ===========================================================
echo   Keep this window open while using AgenticOS.
echo   Press any key or Ctrl+C to stop both servers.
echo ===========================================================
echo.
pause >nul

echo.
echo [AgenticOS] Shutting down servers...
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":8000 " ^| findstr "LISTENING"') do taskkill /F /PID %%p >nul 2>&1
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":3000 " ^| findstr "LISTENING"') do taskkill /F /PID %%p >nul 2>&1
echo [AgenticOS] Servers stopped cleanly.
ping -n 3 127.0.0.1 >nul
