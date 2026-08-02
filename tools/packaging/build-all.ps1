param(
    [ValidateSet("all", "exe", "msi", "portable", "checksums")]
    [string]$Target = "all"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$MissionControl = Join-Path $RepoRoot "apps/mission-control"
$TauriDir = Join-Path $MissionControl "src-tauri"
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

# Step 1.5: Ensure resources directory exists with at least one file for the bundler glob
$TauriResDir = Join-Path $TauriDir "resources"
if (-not (Test-Path $TauriResDir) -or -not (Get-ChildItem $TauriResDir -ErrorAction SilentlyContinue)) {
    New-Item -ItemType Directory -Force -Path $TauriResDir | Out-Null
    # Sentinel file so resources/* glob doesn't fail on empty directory
    Set-Content -Path (Join-Path $TauriResDir ".bundled") -Value "" -NoNewline
}

# Step 2: Initialize MSVC environment
Write-Host "`n[2/4] Initializing MSVC environment..." -ForegroundColor Yellow
$vcvars = "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
if (Test-Path $vcvars) {
    & $vcvars
} else {
    Write-Warning "MSVC not found at $vcvars - trying default path"
}

# Step 2.5: Build PyInstaller backend binary and setup resources
Write-Host "`n[2.5/4] Building standalone backend executable & copying resources..." -ForegroundColor Yellow
Push-Location $RepoRoot
Write-Host "  Running PyInstaller..."
$pyiOut = & uv run --with pyinstaller pyinstaller --noconfirm --onefile --name agentic_os --hidden-import=uvicorn.logging --hidden-import=uvicorn.loops --hidden-import=uvicorn.loops.auto --hidden-import=uvicorn.protocols --hidden-import=uvicorn.protocols.http --hidden-import=uvicorn.protocols.http.auto --hidden-import=uvicorn.protocols.websockets --hidden-import=uvicorn.protocols.websockets.auto --hidden-import=uvicorn.lifespan --hidden-import=uvicorn.lifespan.on src/agentic_os/__main__.py 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  PyInstaller FAILED (exit code $LASTEXITCODE). Will bundle source instead."
    Write-Host "  $pyiOut"
} else {
    Write-Host "  PyInstaller succeeded."
}
Pop-Location

$ResBackendDir = Join-Path $TauriDir "resources\backend"
New-Item -ItemType Directory -Force -Path $ResBackendDir | Out-Null

# Copy PyInstaller binary if built
$CompiledBackend = Join-Path $OutDir "agentic_os.exe"
if (Test-Path $CompiledBackend) {
    Copy-Item $CompiledBackend (Join-Path $ResBackendDir "agentic_os.exe") -Force
    Write-Host "  + Bundled PyInstaller backend binary" -ForegroundColor Green
}

# Always copy Python source alongside binary for uv/python fallback
$BackendSrcTarget = Join-Path $ResBackendDir "src"
if (Test-Path (Join-Path $RepoRoot "src\agentic_os")) {
    New-Item -ItemType Directory -Force -Path $BackendSrcTarget | Out-Null
    Copy-Item (Join-Path $RepoRoot "src\agentic_os") (Join-Path $ResBackendDir "src\") -Recurse -Force
    Copy-Item (Join-Path $RepoRoot "pyproject.toml") (Join-Path $ResBackendDir "pyproject.toml") -Force
    Write-Host "  + Bundled Python source for uv/python fallback" -ForegroundColor Green
}

$WV2Path = Join-Path $TauriDir "target\release\WebView2Loader.dll"
if (Test-Path $WV2Path) {
    Copy-Item $WV2Path (Join-Path $TauriDir "resources\WebView2Loader.dll") -Force
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
        $portableItems = @($exePath)
        $backendDir = "$TauriDir/resources/backend"
        if (Test-Path $backendDir) {
            $portableItems += $backendDir
        }
        $compress = @{
            Path = $portableItems
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
