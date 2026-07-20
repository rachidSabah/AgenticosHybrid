param(
    [ValidateSet("all", "exe", "msi", "portable", "checksums")]
    [string]$Target = "all"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$MissionControl = Join-Path $RepoRoot "apps/mission-control"
$OutDir = Join-Path $RepoRoot "dist"

Write-Host "=== AgenticOS Windows Build Script ===" -ForegroundColor Cyan
Write-Host "Repository: $RepoRoot"
Write-Host "Target: $Target"

# Step 1: Build frontend
Write-Host "`n[1/4] Building frontend..." -ForegroundColor Yellow
Push-Location $MissionControl
npm install
if ($LASTEXITCODE -ne 0) { throw "npm install failed" }
npm run build
if ($LASTEXITCODE -ne 0) { throw "npm run build failed" }
Pop-Location

# Step 2: Initialize MSVC environment
Write-Host "`n[2/4] Initializing MSVC environment..." -ForegroundColor Yellow
$vcvars = "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
if (Test-Path $vcvars) {
    & $vcvars
} else {
    Write-Warning "MSVC not found at $vcvars - trying default path"
}

# Step 3: Build Tauri artifacts
Push-Location $MissionControl

if ($Target -in @("all", "exe")) {
    Write-Host "`n[3/4] Building EXE (NSIS setup)..." -ForegroundColor Yellow
    cargo tauri build --bundles nsis
    if ($LASTEXITCODE -ne 0) { throw "EXE build failed" }
}

if ($Target -in @("all", "msi")) {
    Write-Host "`n[3/4] Building MSI..." -ForegroundColor Yellow
    cargo tauri build --bundles msi
    if ($LASTEXITCODE -ne 0) { throw "MSI build failed" }
}

Pop-Location

# Step 4: Create portable ZIP
if ($Target -in @("all", "portable")) {
    Write-Host "`n[3/4] Creating portable ZIP..." -ForegroundColor Yellow
    $exePath = "$MissionControl/src-tauri/target/release/agentic-os.exe"
    $zipPath = "$MissionControl/src-tauri/target/release/bundle/nsis/AgenticOS_1.0.0-1_x64-portable.zip"
    
    if (Test-Path $zipPath) { Remove-Item $zipPath }
    
    if (Test-Path $exePath) {
        $compress = @{
            Path = $exePath, "$MissionControl/out"
            DestinationPath = $zipPath
            CompressionLevel = "Optimal"
        }
        Compress-Archive @compress
        Write-Host "Portable ZIP created: $zipPath"
    } else {
        Write-Warning "Binary not found at $exePath"
    }
}

# Step 5: Generate checksums
if ($Target -in @("all", "checksums")) {
    Write-Host "`n[4/4] Generating SHA256 checksums..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
    
    # Copy artifacts
    $releaseDir = "$MissionControl/src-tauri/target/release"
    $artifacts = @()
    
    $exe = "$releaseDir/agentic-os.exe"
    $msi = "$releaseDir/bundle/msi/AgenticOS_1.0.0-1_x64_en-US.msi"
    $nsis = "$releaseDir/bundle/nsis/AgenticOS_1.0.0-1_x64-setup.exe"
    $zip = "$releaseDir/bundle/nsis/AgenticOS_1.0.0-1_x64-portable.zip"
    
    if (Test-Path $exe) { Copy-Item $exe "$OutDir/AgenticOS-Desktop-x64.exe"; $artifacts += "$OutDir/AgenticOS-Desktop-x64.exe" }
    if (Test-Path $msi) { Copy-Item $msi "$OutDir/AgenticOS-Setup-x64.msi"; $artifacts += "$OutDir/AgenticOS-Setup-x64.msi" }
    if (Test-Path $nsis) { Copy-Item $nsis "$OutDir/AgenticOS-Setup-x64.exe"; $artifacts += "$OutDir/AgenticOS-Setup-x64.exe" }
    if (Test-Path $zip) { Copy-Item $zip "$OutDir/AgenticOS-Portable-x64.zip"; $artifacts += "$OutDir/AgenticOS-Portable-x64.zip" }
    
    $shaPath = "$OutDir/SHA256SUMS.txt"
    Remove-Item $shaPath -ErrorAction SilentlyContinue
    
    foreach ($f in $artifacts) {
        $hash = (Get-FileHash $f -Algorithm SHA256).Hash.ToLower()
        $name = Split-Path $f -Leaf
        "$hash  $name" | Out-File -FilePath $shaPath -Append -Encoding ASCII
    }
    
    Write-Host "`n=== SHA256 Checksums ===" -ForegroundColor Green
    Get-Content $shaPath
    
    Write-Host "`n=== Artifacts ===" -ForegroundColor Green
    Get-ChildItem $OutDir | Where-Object { -not $_.PSIsContainer } | 
        Select-Object Name, Length, @{N="SHA256";E={(Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower()}} |
        Format-Table -AutoSize
}

Write-Host "`n=== Build Complete ===" -ForegroundColor Cyan
