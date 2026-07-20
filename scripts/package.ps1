<#
.SYNOPSIS
    Package build artifacts into distribution-ready format.
.DESCRIPTION
    Takes artifacts from build.ps1 output and prepares them for
    GitHub Release upload. Validates checksums and generates metadata.
.PARAMETER ArtifactsDir
    Directory containing build artifacts. Default: dist/artifacts/
.PARAMETER OutDir
    Output directory for packaged assets. Default: dist/packages/
.PARAMETER Version
    Override version string. Default: read from tauri.conf.json
.EXAMPLE
    .\scripts\package.ps1
    .\scripts\package.ps1 -ArtifactsDir .\dist\artifacts -OutDir .\dist\packages
#>

param(
    [string]$ArtifactsDir = "",
    [string]$OutDir = "",
    [string]$Version = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$MissionDir = Join-Path $RepoRoot "apps\mission-control"
$TauriDir = Join-Path $MissionDir "src-tauri"

if (-not $ArtifactsDir) { $ArtifactsDir = Join-Path $RepoRoot "dist\artifacts" }
if (-not $OutDir) { $OutDir = Join-Path $RepoRoot "dist\packages" }
if (-not $Version) {
    $tauriConfig = Get-Content (Join-Path $TauriDir "tauri.conf.json") -Raw | ConvertFrom-Json
    $Version = $tauriConfig.version
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AgenticOS Packaging" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# Verify artifacts exist
if (-not (Test-Path $ArtifactsDir)) {
    Write-Error "Artifacts directory not found: $ArtifactsDir`nRun scripts\build.ps1 first."
    exit 1
}

# Create output directory
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

# Validate artifacts
Write-Host "`nValidating artifacts..." -ForegroundColor Yellow
$required = @(
    "AgenticOS-Setup-x64.exe",
    "AgenticOS-Setup-x64.msi",
    "AgenticOS-Portable-x64.zip"
)
$missing = @()
foreach ($r in $required) {
    $path = Join-Path $ArtifactsDir $r
    if (Test-Path $path) {
        $size = (Get-Item $path).Length
        $sizeStr = if ($size -gt 1MB) { "{0:N2} MB" -f ($size / 1MB) } else { "{0:N0} KB" -f ($size / 1KB) }
        Write-Host "  ✓ $r ($sizeStr)" -ForegroundColor Green
    }
    else {
        Write-Host "  ✗ $r (missing)" -ForegroundColor Red
        $missing += $r
    }
}

# Copy artifacts to packages directory
Write-Host "`nCopying artifacts..." -ForegroundColor Yellow
Copy-Item "$ArtifactsDir\*" $OutDir -Force -ErrorAction SilentlyContinue

# Validate checksums
$checksumsPath = Join-Path $ArtifactsDir "SHA256SUMS.txt"
if (Test-Path $checksumsPath) {
    Write-Host "`nValidating SHA256 checksums..." -ForegroundColor Yellow
    Get-Content $checksumsPath | ForEach-Object {
        if ($_ -match "^([a-f0-9]+)\s+(.+)$") {
            $expectedHash = $matches[1]
            $fileName = $matches[2]
            $filePath = Join-Path $OutDir $fileName
            if (Test-Path $filePath) {
                $actualHash = (Get-FileHash $filePath -Algorithm SHA256).Hash.ToLower()
                if ($actualHash -eq $expectedHash) {
                    Write-Host "  ✓ $fileName" -ForegroundColor Green
                }
                else {
                    Write-Host "  ✗ $fileName (hash mismatch)" -ForegroundColor Red
                }
            }
        }
    }
}

# Generate release manifest
Write-Host "`nGenerating release manifest..." -ForegroundColor Yellow
$CommitHash = git -C $RepoRoot rev-parse HEAD 2>$null
if (-not $CommitHash) { $CommitHash = "unknown" }

$manifest = @{
    version = $Version
    releaseDate = (Get-Date -Format "yyyy-MM-dd")
    platform = "windows-x64"
    minimumOSVersion = "Windows 10 1809"
    architecture = "x86_64"
    artifacts = @{}
}

foreach ($r in $required) {
    $path = Join-Path $OutDir $r
    if (Test-Path $path) {
        $file = Get-Item $path
        $hash = (Get-FileHash $path -Algorithm SHA256).Hash.ToLower()
        $manifest.artifacts[$r] = @{
            size = $file.Length
            sha256 = $hash
        }
    }
}

$manifestPath = Join-Path $OutDir "release-manifest.json"
$manifest | ConvertTo-Json -Depth 5 | Out-File -FilePath $manifestPath -Encoding utf8
Write-Host "  Manifest: $manifestPath" -ForegroundColor Green

# Summary
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  Package Summary" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

if ($missing.Count -gt 0) {
    Write-Host "  Missing artifacts:" -ForegroundColor Yellow
    foreach ($m in $missing) {
        Write-Host "    · $m" -ForegroundColor Yellow
    }
}
else {
    Write-Host "  All required artifacts present." -ForegroundColor Green
}

Write-Host "  Output: $OutDir" -ForegroundColor Green
Write-Host "`nDone." -ForegroundColor Cyan
