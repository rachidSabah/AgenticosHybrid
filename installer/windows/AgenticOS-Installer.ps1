<#
.SYNOPSIS
    AgenticOS Windows Production Installer (NSIS & Portable Compatible)
.DESCRIPTION
    Installs AgenticOS Backend, Mission Control Frontend, Runtime Dependencies,
    Desktop Shortcuts, Start Menu entry, and registers the Uninstaller in Windows Registry.
.PARAMETER InstallDir
    Target directory. Default: "$env:LOCALAPPDATA\AgenticOS" or "C:\Program Files\AgenticOS"
.PARAMETER Unattended
    Run in silent/unattended mode without interactive prompts.
#>

param(
    [string]$InstallDir = "$env:LOCALAPPDATA\AgenticOS",
    [switch]$Unattended,
    [bool]$CreateDesktopShortcut = $true,
    [bool]$CreateStartMenuShortcut = $true,
    [bool]$LaunchAfterInstall = $true,
    [switch]$NoLaunch
)

$ErrorActionPreference = "Stop"

function Write-Header {
    Clear-Host
    Write-Host "=================================================================" -ForegroundColor Cyan
    Write-Host "                AgenticOS Hybrid Windows Installer               " -ForegroundColor Cyan
    Write-Host "        Autonomous AI Multi-Agent Operating System Runtime        " -ForegroundColor Cyan
    Write-Host "=================================================================" -ForegroundColor Cyan
    Write-Host " Available Distribution Packages:" -ForegroundColor Gray
    Write-Host "  * Windows 10+ | AgenticOS-Setup-x64.exe    | 6.2 MB | NSIS installer" -ForegroundColor Yellow
    Write-Host "  * Windows 10+ | AgenticOS-Portable-x64.zip | 7.7 MB | Portable (no install)" -ForegroundColor Yellow
    Write-Host "=================================================================" -ForegroundColor Cyan
    Write-Host ""
}

Write-Header

if (-not $Unattended) {
    Write-Host "Target Installation Directory: [$InstallDir]" -ForegroundColor Yellow
    $userPath = Read-Host "Press ENTER to accept or enter custom path"
    if ($userPath -and $userPath.Trim() -ne "") {
        $InstallDir = $userPath.Trim()
    }
}

Write-Host "`n[1/6] Preparing installation directory..." -ForegroundColor Green
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
New-Item -ItemType Directory -Force -Path "$InstallDir\bin" | Out-Null
New-Item -ItemType Directory -Force -Path "$InstallDir\data" | Out-Null
New-Item -ItemType Directory -Force -Path "$InstallDir\logs" | Out-Null
New-Item -ItemType Directory -Force -Path "$InstallDir\workspace" | Out-Null

Write-Host "[2/6] Copying core engine and application files..." -ForegroundColor Green
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$SourceDir = Split-Path -Parent (Split-Path -Parent $ScriptRoot)

$robocopyArgs = @(
    $SourceDir,
    $InstallDir,
    "/E",
    "/XD", "node_modules", ".git", ".venv", "dist", ".worktrees", "__pycache__", ".pytest_cache", ".ruff_cache",
    "/NFL", "/NDL", "/NJH", "/NJS", "/nc", "/ns", "/np"
)
& robocopy.exe @robocopyArgs | Out-Null
if ($LASTEXITCODE -ge 8) {
    Write-Warning "Robocopy encountered issues (Exit Code: $LASTEXITCODE)"
}

Write-Host "[3/6] Setting up launchers and startup scripts..." -ForegroundColor Green
$LauncherBatContent = @"
@echo off
setlocal
title AgenticOS Hybrid Engine & Mission Control
cd /d "%~dp0"

echo [AgenticOS] Starting Backend on http://127.0.0.1:8080 ...
start /b "" uv run python -m agentic_os serve --host 127.0.0.1 --port 8080 > logs\backend.log 2>&1

echo [AgenticOS] Starting Mission Control on http://localhost:3000 ...
cd apps\mission-control
start /b "" npm run dev > ..\..\logs\frontend.log 2>&1

echo [AgenticOS] Waiting for services to initialize...
timeout /t 3 /nobreak >nul

echo [AgenticOS] Launching Mission Control UI in default browser...
start http://localhost:3000

echo ==========================================================
echo AgenticOS is running live!
echo Backend:         http://127.0.0.1:8080
echo Mission Control: http://localhost:3000
echo Logs directory:  %~dp0logs
echo ==========================================================
"@
Set-Content -Path "$InstallDir\start-agenticos.bat" -Value $LauncherBatContent -Encoding ASCII

# VBScript for silent background launching
$LauncherVbsContent = @"
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "cmd /c """ & "$InstallDir\start-agenticos.bat"""", 0, False
"@
Set-Content -Path "$InstallDir\start-agenticos-silent.vbs" -Value $LauncherVbsContent -Encoding ASCII

Write-Host "[4/6] Creating Desktop and Start Menu shortcuts..." -ForegroundColor Green
$WshShell = New-Object -ComObject WScript.Shell

if ($CreateDesktopShortcut) {
    $DesktopPath = [Environment]::GetFolderPath("Desktop")
    $Shortcut = $WshShell.CreateShortcut("$DesktopPath\AgenticOS Mission Control.lnk")
    $Shortcut.TargetPath = "$InstallDir\start-agenticos.bat"
    $Shortcut.WorkingDirectory = $InstallDir
    $Shortcut.Description = "Launch AgenticOS Autonomous AI Multi-Agent Operating System"
    $Shortcut.IconLocation = "shell32.dll,138"
    $Shortcut.Save()
    Write-Host "  + Desktop shortcut created: $DesktopPath\AgenticOS Mission Control.lnk" -ForegroundColor Gray
}

if ($CreateStartMenuShortcut) {
    $StartMenuPrograms = [Environment]::GetFolderPath("Programs")
    $AgenticOSStartFolder = "$StartMenuPrograms\AgenticOS"
    New-Item -ItemType Directory -Force -Path $AgenticOSStartFolder | Out-Null
    
    $AppShortcut = $WshShell.CreateShortcut("$AgenticOSStartFolder\AgenticOS Mission Control.lnk")
    $AppShortcut.TargetPath = "$InstallDir\start-agenticos.bat"
    $AppShortcut.WorkingDirectory = $InstallDir
    $AppShortcut.Description = "AgenticOS Mission Control"
    $AppShortcut.IconLocation = "shell32.dll,138"
    $AppShortcut.Save()

    $UninstallShortcut = $WshShell.CreateShortcut("$AgenticOSStartFolder\Uninstall AgenticOS.lnk")
    $UninstallShortcut.TargetPath = "powershell.exe"
    $UninstallShortcut.Arguments = "-ExecutionPolicy Bypass -File `"$InstallDir\installer\windows\uninstall.ps1`""
    $UninstallShortcut.WorkingDirectory = $InstallDir
    $UninstallShortcut.Description = "Uninstall AgenticOS"
    $UninstallShortcut.IconLocation = "shell32.dll,131"
    $UninstallShortcut.Save()
    Write-Host "  + Start menu group created: $AgenticOSStartFolder" -ForegroundColor Gray
}

Write-Host "[5/6] Registering Uninstaller in Windows Registry..." -ForegroundColor Green
$UninstallerScript = @"
param([switch]`$Silent)
Write-Host "Uninstalling AgenticOS..." -ForegroundColor Yellow
# Stop any running processes
Get-Process | Where-Object { `$_.ProcessName -match "python|node" -and `$_.Path -like "*$InstallDir*" } | Stop-Process -Force -ErrorAction SilentlyContinue

# Remove shortcuts
`$DesktopPath = [Environment]::GetFolderPath("Desktop")
Remove-Item "`$DesktopPath\AgenticOS Mission Control.lnk" -Force -ErrorAction SilentlyContinue

`$StartMenuPrograms = [Environment]::GetFolderPath("Programs")
Remove-Item "`$StartMenuPrograms\AgenticOS" -Recurse -Force -ErrorAction SilentlyContinue

# Remove Registry Entry
Remove-Item -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\AgenticOS" -Force -ErrorAction SilentlyContinue

# Remove files
Write-Host "Removing installation files from $InstallDir..." -ForegroundColor Gray
Remove-Item -Path "$InstallDir" -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "AgenticOS successfully uninstalled." -ForegroundColor Green
"@
Set-Content -Path "$InstallDir\installer\windows\uninstall.ps1" -Value $UninstallerScript -Encoding ASCII

# Register in Windows Add/Remove Programs (HKCU)
$RegPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\AgenticOS"
New-Item -Path $RegPath -Force | Out-Null
Set-ItemProperty -Path $RegPath -Name "DisplayName" -Value "AgenticOS Hybrid"
Set-ItemProperty -Path $RegPath -Name "DisplayVersion" -Value "1.0.0"
Set-ItemProperty -Path $RegPath -Name "Publisher" -Value "AgenticOS Open Source Community"
Set-ItemProperty -Path $RegPath -Name "InstallLocation" -Value $InstallDir
Set-ItemProperty -Path $RegPath -Name "UninstallString" -Value "powershell.exe -ExecutionPolicy Bypass -File `"$InstallDir\installer\windows\uninstall.ps1`""
Set-ItemProperty -Path $RegPath -Name "NoModify" -Value 1 -Type DWord
Set-ItemProperty -Path $RegPath -Name "NoRepair" -Value 1 -Type DWord

Write-Host "[6/6] Installation Complete!" -ForegroundColor Green
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "  AgenticOS Hybrid was successfully installed to: $InstallDir" -ForegroundColor Green
Write-Host "  Launch via Desktop Shortcut or run: $InstallDir\start-agenticos.bat" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

if ($LaunchAfterInstall -and -not $Unattended -and -not $NoLaunch) {
    $launch = Read-Host "`nLaunch AgenticOS now? (Y/n)"
    if ($launch -ne "n" -and $launch -ne "N") {
        Start-Process "$InstallDir\start-agenticos.bat"
    }
}