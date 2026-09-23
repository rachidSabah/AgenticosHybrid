<#
.SYNOPSIS
    Complete Uninstallation Script for AgenticOS Hybrid Engine & Mission Control.
.DESCRIPTION
    Safely stops all running AgenticOS background daemons, processes, and child workers,
    removes Desktop and Start Menu shortcuts, cleans up Windows registry entries,
    and removes installation directories, temporary workspaces, and local session caches.
.PARAMETER TargetDir
    Installation directory to remove. Defaults to $env:LOCALAPPDATA\AgenticOS.
.PARAMETER RemoveUserSessions
    Switch to also purge local session caches (~/.agentic_os). Default: $true.
.PARAMETER Silent
    Execute without interactive user confirmation prompts.
#>

param(
    [string]$TargetDir = "$env:LOCALAPPDATA\AgenticOS",
    [switch]$RemoveUserSessions = $true,
    [switch]$Silent = $false
)

$ErrorActionPreference = "Continue"

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "                 AgenticOS Complete Uninstaller                  " -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

if (-not $Silent) {
    Write-Host "Target Installation to remove: [$TargetDir]" -ForegroundColor Yellow
    $confirm = Read-Host "Are you sure you want to completely remove AgenticOS? (y/N)"
    if ($confirm -ne "y" -and $confirm -ne "Y") {
        Write-Host "Uninstallation canceled by user." -ForegroundColor Gray
        exit 0
    }
}

Write-Host "`n[1/5] Terminating active AgenticOS processes..." -ForegroundColor Green
$stoppedCount = 0

# Stop any processes associated with AgenticOS target directory or known ports
Get-Process | Where-Object {
    ($_.ProcessName -match "python|node|uv") -and
    ($_.Path -like "*$TargetDir*" -or $_.CommandLine -like "*agentic_os*" -or $_.CommandLine -like "*mission-control*")
} | ForEach-Object {
    try {
        Write-Host "  - Stopping process: $($_.ProcessName) (PID: $($_.Id))" -ForegroundColor Gray
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
        $stoppedCount++
    } catch {}
}

# Also gracefully release any processes holding port 8000, 3000, 8001, or 3001 if spawned by AgenticOS
Get-NetTCPConnection -LocalPort 8000, 3000, 8001, 3001 -ErrorAction SilentlyContinue | Where-Object { $_.OwningProcess -gt 0 } | ForEach-Object {
    try {
        $p = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue
        if ($p -and ($p.Path -like "*$TargetDir*" -or $p.Path -like "*AOS*")) {
            Write-Host "  - Releasing port $($_.LocalPort) from PID $($p.Id)" -ForegroundColor Gray
            Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
        }
    } catch {}
}
Write-Host "  + Terminated $stoppedCount process(es)." -ForegroundColor Gray

Write-Host "[2/5] Removing Desktop and Start Menu shortcuts..." -ForegroundColor Green
$DesktopPath = [Environment]::GetFolderPath("Desktop")
$PublicDesktopPath = [Environment]::GetFolderPath("CommonDesktopDirectory")

foreach ($dPath in @($DesktopPath, $PublicDesktopPath)) {
    if (Test-Path "$dPath\AgenticOS Mission Control.lnk") {
        Remove-Item "$dPath\AgenticOS Mission Control.lnk" -Force -ErrorAction SilentlyContinue
        Write-Host "  + Removed Desktop shortcut: $dPath\AgenticOS Mission Control.lnk" -ForegroundColor Gray
    }
}

$StartMenuPrograms = [Environment]::GetFolderPath("Programs")
$CommonStartMenuPrograms = [Environment]::GetFolderPath("CommonPrograms")

foreach ($smPath in @($StartMenuPrograms, $CommonStartMenuPrograms)) {
    if (Test-Path "$smPath\AgenticOS") {
        Remove-Item "$smPath\AgenticOS" -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "  + Removed Start Menu folder: $smPath\AgenticOS" -ForegroundColor Gray
    }
}

Write-Host "[3/5] Cleaning Windows Registry uninstall entries..." -ForegroundColor Green
$regPaths = @(
    "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\AgenticOS",
    "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\AgenticOS"
)
foreach ($rp in $regPaths) {
    if (Test-Path $rp) {
        Remove-Item -Path $rp -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "  + Removed registry key: $rp" -ForegroundColor Gray
    }
}

Write-Host "[4/5] Removing installation files and runtime workspace..." -ForegroundColor Green
if (Test-Path $TargetDir) {
    Write-Host "  + Removing directory: $TargetDir" -ForegroundColor Gray
    Remove-Item -Path $TargetDir -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "[5/5] Purging local caches and sessions..." -ForegroundColor Green
if ($RemoveUserSessions) {
    $userSessionDir = Join-Path $env:USERPROFILE ".agentic_os"
    if (Test-Path $userSessionDir) {
        Write-Host "  + Removing session directory: $userSessionDir" -ForegroundColor Gray
        Remove-Item -Path $userSessionDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "`n=================================================================" -ForegroundColor Cyan
Write-Host "       AgenticOS was completely and successfully uninstalled!    " -ForegroundColor Green
Write-Host "=================================================================" -ForegroundColor Cyan
