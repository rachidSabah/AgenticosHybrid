<#
.SYNOPSIS
    AgenticOS Uninstaller
#>
[CmdletBinding()]
param(
    [switch]$Force
)

$InstallDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Write-Host "=================================================" -ForegroundColor Yellow
Write-Host "           AgenticOS Uninstallation              " -ForegroundColor Yellow
Write-Host "=================================================" -ForegroundColor Yellow
Write-Host "Target Directory: $InstallDir"

# 1. Terminate running background servers
Write-Host "`n[1/3] Stopping AgenticOS processes..." -ForegroundColor Gray
Get-Process | Where-Object { 
    ($_.ProcessName -match "python|node") -and ($_.Path -like "*$InstallDir*")
} | Stop-Process -Force -ErrorAction SilentlyContinue

# 2. Remove Shortcuts
Write-Host "[2/3] Removing desktop and start menu shortcuts..." -ForegroundColor Gray
$DesktopPath = [Environment]::GetFolderPath("Desktop")
Remove-Item "$DesktopPath\AgenticOS Mission Control.lnk" -Force -ErrorAction SilentlyContinue

$StartMenuPrograms = [Environment]::GetFolderPath("Programs")
Remove-Item "$StartMenuPrograms\AgenticOS" -Recurse -Force -ErrorAction SilentlyContinue

# 3. Clean Registry
Remove-Item -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\AgenticOS" -Force -ErrorAction SilentlyContinue

# 4. Remove Files
Write-Host "[3/3] Removing installed files..." -ForegroundColor Gray
Remove-Item -Path "$InstallDir" -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "`nAgenticOS has been completely uninstalled." -ForegroundColor Green