# AgenticOS Windows Installer Script
# Run from PowerShell: iwr -useb https://raw.githubusercontent.com/rachidSabah/AgenticosHybrid/main/scripts/install-windows.ps1 | iex
# Or locally: .\scripts\install-windows.ps1

[CmdletBinding()]
param(
    [string]$InstallDir = "$env:LOCALAPPDATA\AgenticOS",
    [string]$Version = "latest",
    [switch]$Portable,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$REPO = "rachidSabah/AgenticosHybrid"
$PRODUCT = "AgenticOS"

function Write-Banner {
    Write-Host ""
    Write-Host "  ╔═══════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "  ║        AgenticOS Installer            ║" -ForegroundColor Cyan
    Write-Host "  ║  AI Agent Operating System for Windows║" -ForegroundColor Cyan
    Write-Host "  ╚═══════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""
}

function Test-Administrator {
    $current = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
    return $current.IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)
}

function Get-LatestRelease {
    $url = "https://api.github.com/repos/$REPO/releases/latest"
    try {
        $release = Invoke-RestMethod -Uri $url -Headers @{ "User-Agent" = "AgenticOS-Installer" }
        return $release
    } catch {
        Write-Host "  [ERROR] Could not fetch release info: $_" -ForegroundColor Red
        exit 1
    }
}

function Get-DownloadUrl {
    param($release, $pattern)
    $asset = $release.assets | Where-Object { $_.name -like $pattern } | Select-Object -First 1
    if (-not $asset) {
        Write-Host "  [ERROR] Could not find asset matching '$pattern' in release $($release.tag_name)" -ForegroundColor Red
        Write-Host "  Available assets:" -ForegroundColor Yellow
        $release.assets | ForEach-Object { Write-Host "    - $($_.name)" -ForegroundColor Yellow }
        exit 1
    }
    return $asset.browser_download_url
}

function Verify-Sha256 {
    param($filePath, $expectedHash)
    $actualHash = (Get-FileHash $filePath -Algorithm SHA256).Hash.ToLower()
    if ($actualHash -ne $expectedHash.ToLower()) {
        Write-Host "  [ERROR] Checksum mismatch!" -ForegroundColor Red
        Write-Host "    Expected: $expectedHash" -ForegroundColor Red
        Write-Host "    Actual:   $actualHash" -ForegroundColor Red
        Remove-Item $filePath -Force
        exit 1
    }
    Write-Host "  [OK] Checksum verified" -ForegroundColor Green
}

Write-Banner

# Check Windows version
$winVer = [System.Environment]::OSVersion.Version
if ($winVer.Major -lt 10 -or ($winVer.Major -eq 10 -and $winVer.Build -lt 19041)) {
    Write-Host "  [WARNING] AgenticOS requires Windows 10 22H2 (build 19045) or later." -ForegroundColor Yellow
    Write-Host "  Detected: Windows $($winVer.Major).$($winVer.Build)" -ForegroundColor Yellow
}

Write-Host "  Fetching latest release from GitHub..." -ForegroundColor Cyan
$release = Get-LatestRelease
Write-Host "  Latest version: $($release.tag_name)" -ForegroundColor Green

if ($Portable) {
    # ── Portable ZIP installation ──────────────────────────────────────
    Write-Host ""
    Write-Host "  Installing portable version to: $InstallDir" -ForegroundColor Cyan
    $zipUrl = Get-DownloadUrl $release "*Portable*x64*.zip"
    $zipPath = "$env:TEMP\AgenticOS-Portable.zip"

    Write-Host "  Downloading: $zipUrl" -ForegroundColor DarkGray
    Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath -UseBasicParsing

    if (Test-Path $InstallDir) {
        if ($Force) {
            Remove-Item $InstallDir -Recurse -Force
        } else {
            Write-Host "  [ERROR] Install directory already exists: $InstallDir" -ForegroundColor Red
            Write-Host "         Use -Force to overwrite." -ForegroundColor Yellow
            exit 1
        }
    }

    Write-Host "  Extracting..." -ForegroundColor Cyan
    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
    Expand-Archive -Path $zipPath -DestinationPath $InstallDir -Force
    Remove-Item $zipPath

    # Add to PATH for this user
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($userPath -notlike "*$InstallDir*") {
        [Environment]::SetEnvironmentVariable("Path", "$userPath;$InstallDir", "User")
        Write-Host "  [OK] Added $InstallDir to user PATH" -ForegroundColor Green
    }

    Write-Host ""
    Write-Host "  ✓ AgenticOS Portable installed to: $InstallDir" -ForegroundColor Green
    Write-Host "  ✓ Run: $InstallDir\start.bat   (or start.ps1)" -ForegroundColor Green

} else {
    # ── NSIS Installer (recommended) ──────────────────────────────────
    Write-Host ""
    Write-Host "  Downloading NSIS installer..." -ForegroundColor Cyan
    $exeUrl = Get-DownloadUrl $release "*Setup*x64*.exe"
    $exePath = "$env:TEMP\AgenticOS-Setup.exe"

    Write-Host "  Downloading: $exeUrl" -ForegroundColor DarkGray
    Invoke-WebRequest -Uri $exeUrl -OutFile $exePath -UseBasicParsing
    Write-Host "  Download complete: $exePath" -ForegroundColor Green

    # Try to get checksum
    try {
        $checksumAsset = $release.assets | Where-Object { $_.name -eq "SHA256SUMS.txt" } | Select-Object -First 1
        if ($checksumAsset) {
            $checksums = (Invoke-WebRequest -Uri $checksumAsset.browser_download_url -UseBasicParsing).Content
            $line = $checksums -split "`n" | Where-Object { $_ -like "*Setup*x64*.exe*" } | Select-Object -First 1
            if ($line) {
                $hash = ($line -split "\s+")[0].Trim()
                Write-Host "  Verifying checksum..." -ForegroundColor Cyan
                Verify-Sha256 -filePath $exePath -expectedHash $hash
            }
        }
    } catch {
        Write-Host "  [WARNING] Could not verify checksum (skipping): $_" -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "  Launching installer..." -ForegroundColor Cyan
    Write-Host "  (If UAC prompts, click Yes to allow installation)" -ForegroundColor Yellow
    Write-Host ""
    Start-Process -FilePath $exePath -Wait
    Remove-Item $exePath -Force -ErrorAction SilentlyContinue

    Write-Host ""
    Write-Host "  ✓ AgenticOS $($release.tag_name) installed!" -ForegroundColor Green
    Write-Host "  ✓ Launch AgenticOS from the Start Menu or Desktop shortcut." -ForegroundColor Green
}

Write-Host ""
Write-Host "  Need help? Visit: https://github.com/$REPO" -ForegroundColor DarkGray
Write-Host ""
