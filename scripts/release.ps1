<#
.SYNOPSIS
    Prepare and upload GitHub Release for AgenticOS.
.DESCRIPTION
    Creates a GitHub Release with all build artifacts, generates
    release notes, and uploads assets using the GitHub CLI or API.
.PARAMETER Version
    Version tag (e.g. "v1.0.0-rc1"). Default: read from tauri.conf.json
.PARAMETER ArtifactsDir
    Directory containing packaged artifacts. Default: dist/packages/
.PARAMETER DryRun
    Print what would be done without uploading.
.PARAMETER Channel
    Release channel: stable, beta, or nightly. Default: stable
.EXAMPLE
    .\scripts\release.ps1 -Version v1.0.0-rc1
    .\scripts\release.ps1 -Version v1.0.0-rc1 -DryRun
#>

param(
    [string]$Version = "",
    [string]$ArtifactsDir = "",
    [switch]$DryRun,
    [ValidateSet("stable", "beta", "nightly")]
    [string]$Channel = "stable"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$MissionDir = Join-Path $RepoRoot "apps\mission-control"
$TauriDir = Join-Path $MissionDir "src-tauri"

if (-not $ArtifactsDir) { $ArtifactsDir = Join-Path $RepoRoot "dist\packages" }
if (-not $Version) {
    $tauriConfig = Get-Content (Join-Path $TauriDir "tauri.conf.json") -Raw | ConvertFrom-Json
    $Version = "v$($tauriConfig.version)"
}
elseif ($Version -notlike "v*") {
    $Version = "v$Version"
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AgenticOS Release $Version" -ForegroundColor Cyan
Write-Host "  Channel: $Channel" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# ---- Check prerequisites ----
$hasGh = Get-Command gh -ErrorAction SilentlyContinue
$hasCurl = Get-Command curl -ErrorAction SilentlyContinue

if (-not $hasGh -and -not $hasCurl) {
    Write-Error "Either GitHub CLI (gh) or curl is required for release."
    Write-Error "Install gh: https://cli.github.com"
    exit 1
}

# ---- Verify artifacts exist ----
Write-Host "`nVerifying release assets..." -ForegroundColor Yellow
$requiredAssets = @(
    "AgenticOS-Setup-x64.exe",
    "AgenticOS-Setup-x64.msi",
    "AgenticOS-Portable-x64.zip",
    "SHA256SUMS.txt",
    "release-manifest.json"
)

$assets = @()
$missingAssets = @()

foreach ($r in $requiredAssets) {
    $path = Join-Path $ArtifactsDir $r
    if (Test-Path $path) {
        $item = Get-Item $path
        $sizeStr = if ($item.Length -gt 1MB) { "{0:N2} MB" -f ($item.Length / 1MB) } else { "{0:N0} KB" -f ($item.Length / 1KB) }
        Write-Host "  ✓ $r ($sizeStr)" -ForegroundColor Green
        $assets += @{ name = $r; path = $path.FullName }
    }
    else {
        Write-Host "  ✗ $r (missing)" -ForegroundColor Red
        $missingAssets += $r
    }
}

if ($missingAssets.Count -gt 0) {
    Write-Warning "Missing assets: $($missingAssets -join ', ')"
    Write-Warning "Run scripts\build.ps1 then scripts\package.ps1 first."
    if (-not $DryRun) {
        $continue = Read-Host "Continue without these assets? (y/N)"
        if ($continue -ne "y") { exit 1 }
    }
}

# ---- Generate release notes ----
Write-Host "`nGenerating release notes..." -ForegroundColor Yellow
$changelogPath = Join-Path $RepoRoot "CHANGELOG.md"
$commitsSinceLastTag = git -C $RepoRoot log --oneline $(git -C $RepoRoot describe --tags --abbrev=0 2>$null)..HEAD 2>$null
if (-not $commitsSinceLastTag) { $commitsSinceLastTag = "Initial release." }

$releaseNotes = @"
## AgenticOS $Version

**Channel:** $Channel

### Installation

**Windows:**
- **Setup**: Download \`AgenticOS-Setup-x64.exe\` or \`AgenticOS-Setup-x64.msi\`
- **Portable**: Download \`AgenticOS-Portable-x64.zip\` and extract

**System Requirements:** Windows 10 1809 or later, 64-bit

### Changelog

$commitsSinceLastTag

### Checksums

See \`SHA256SUMS.txt\` attached to this release.

### Assets

"@

$assets | ForEach-Object {
    $releaseNotes += "- $($_.name)`n"
}

$notesPath = Join-Path $ArtifactsDir "release-notes.md"
$releaseNotes | Out-File -FilePath $notesPath -Encoding utf8
Write-Host "  Release notes: $notesPath" -ForegroundColor Green

# ---- Create GitHub Release ----
if ($DryRun) {
    Write-Host "`n[DRY RUN] Would create release:" -ForegroundColor Yellow
    Write-Host "  Tag: $Version" -ForegroundColor Gray
    Write-Host "  Assets:" -ForegroundColor Gray
    $assets | ForEach-Object { Write-Host "    - $($_.path)" -ForegroundColor Gray }
    Write-Host "`nDry run complete. Pass -DryRun to see what would happen." -ForegroundColor Cyan
    exit 0
}

Write-Host "`nCreating GitHub Release $Version..." -ForegroundColor Yellow

if ($hasGh) {
    # Using GitHub CLI
    $ghArgs = @(
        "release", "create", $Version,
        "--title", "AgenticOS $Version",
        "--notes-file", $notesPath,
        "--target", "main"
    )

    if ($Channel -eq "nightly") { $ghArgs += "--prerelease" }
    if ($Channel -eq "beta") { $ghArgs += "--prerelease" }

    # Add all assets
    $assets | ForEach-Object { $ghArgs += $_.path }

    Write-Host "  Running: gh $($ghArgs -join ' ')" -ForegroundColor Gray
    & gh $ghArgs 2>&1 | ForEach-Object { Write-Host "  $_" }

    if ($LASTEXITCODE -ne 0 -and $null -ne $LASTEXITCODE) {
        Write-Error "GitHub release creation failed."
        exit 1
    }
}
else {
    # Fallback: GitHub API
    $token = $env:GITHUB_TOKEN
    if (-not $token) {
        Write-Error "GITHUB_TOKEN environment variable is required when gh CLI is not available."
        exit 1
    }

    $repo = "rachidSabah/AgenticOS"
    $apiUrl = "https://api.github.com/repos/$repo/releases"

    $body = @{
        tag_name = $Version
        target_commitish = "main"
        name = "AgenticOS $Version"
        body = $releaseNotes
        prerelease = ($Channel -ne "stable")
    } | ConvertTo-Json

    Write-Host "  Creating release via API..." -ForegroundColor Gray
    $response = curl -s -X POST -H "Authorization: token $token" -H "Content-Type: application/json" $apiUrl -d $body | ConvertFrom-Json

    if (-not $response.id) {
        Write-Error "Release creation failed: $($response.message)"
        exit 1
    }

    $releaseId = $response.id
    Write-Host "  Release created: $($response.html_url)" -ForegroundColor Green

    # Upload assets
    Write-Host "  Uploading assets..." -ForegroundColor Yellow
    $uploadUrl = "https://uploads.github.com/repos/$repo/releases/$releaseId/assets"

    $assets | ForEach-Object {
        $fileName = $_.name
        $filePath = $_.path
        $contentType = switch ([System.IO.Path]::GetExtension($fileName)) {
            ".exe" { "application/vnd.microsoft.portable-executable" }
            ".msi" { "application/x-msi" }
            ".zip" { "application/zip" }
            ".txt" { "text/plain" }
            ".json" { "application/json" }
            ".md" { "text/markdown" }
            default { "application/octet-stream" }
        }

        Write-Host "  Uploading $fileName..." -ForegroundColor Gray
        curl -s -X POST -H "Authorization: token $token" -H "Content-Type: $contentType" `
            "$uploadUrl?name=$fileName" --data-binary "@$filePath" | Out-Null

        if ($LASTEXITCODE -eq 0) {
            Write-Host "    ✓ $fileName uploaded" -ForegroundColor Green
        }
        else {
            Write-Host "    ✗ $fileName upload failed" -ForegroundColor Red
        }
    }
}

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  Release $Version published!" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  https://github.com/rachidSabah/AgenticOS/releases/tag/$Version" -ForegroundColor Green
Write-Host "`nDone." -ForegroundColor Cyan
