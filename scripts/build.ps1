<#
.SYNOPSIS
    Production build script for AgenticOS Desktop Runtime (Windows).
.DESCRIPTION
    Builds Mission Control frontend, compiles Rust/Tauri backend,
    generates installers (NSIS, MSI), portable ZIP, and checksums.
.PARAMETER Config
    Build configuration: Release (default) or Debug.
.PARAMETER SkipFrontend
    Skip the frontend npm build step.
.PARAMETER SkipRust
    Skip the Rust/Tauri cargo build step.
.PARAMETER OutDir
    Output directory for artifacts. Default: dist/
.EXAMPLE
    .\scripts\build.ps1
    .\scripts\build.ps1 -Config Debug -OutDir artifacts
#>

param(
    [ValidateSet("Release", "Debug")]
    [string]$Config = "Release",
    [switch]$SkipFrontend,
    [switch]$SkipRust,
    [string]$OutDir = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$MissionDir = Join-Path $RepoRoot "apps\mission-control"
$TauriDir = Join-Path $MissionDir "src-tauri"

if (-not $OutDir) {
    $OutDir = Join-Path $RepoRoot "dist"
}
$ArtifactsDir = Join-Path $OutDir "artifacts"
$ReleaseDir = if ($Config -eq "Release") { "release" } else { "debug" }

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AgenticOS Production Build" -ForegroundColor Cyan
Write-Host "  Config: $Config" -ForegroundColor Cyan
Write-Host "  Output: $OutDir" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# ---- Prerequisites ----
Write-Host "`n[1/5] Checking prerequisites..." -ForegroundColor Yellow
$missing = @()

if (-not (Get-Command node -ErrorAction SilentlyContinue)) { $missing += "Node.js" }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { $missing += "npm" }
if (-not (Get-Command rustc -ErrorAction SilentlyContinue)) { $missing += "Rust (rustc)" }
if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) { $missing += "Cargo" }

if ($missing.Count -gt 0) {
    Write-Warning "Missing prerequisites: $($missing -join ', ')"
    Write-Warning "Install missing tools and re-run."
    Write-Warning "  Rust: https://rustup.rs"
    Write-Warning "  Node.js: https://nodejs.org"
    if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) {
        # Non-fatal for now since CI handles Rust builds
        Write-Warning "Rust/Cargo not found - will skip Tauri build step."
        $SkipRust = $true
    }
}

# ---- MinGW toolchain detection (x86_64-pc-windows-gnu) ----
if (-not $SkipRust -and (Get-Command cargo -ErrorAction SilentlyContinue)) {
    $mingwFound = $false
    $mingwCandidates = @(
        "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\BrechtSanders.WinLibs.POSIX.UCRT_Microsoft.Winget.Source_8wekyb3d8bbwe\mingw64\bin"
        "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\MartinStorsjo.LLVM-MinGW.UCRT_Microsoft.Winget.Source_8wekyb3d8bbwe\llvm-mingw-20260616-ucrt-x86_64\bin"
        "C:\mingw64\bin"
    )
    foreach ($candidate in $mingwCandidates) {
        $gccPath = Join-Path $candidate "x86_64-w64-mingw32-gcc.exe"
        if (Test-Path $gccPath) {
            Write-Host "  MinGW toolchain: $candidate" -ForegroundColor Green
            $env:PATH = $candidate + ";" + $env:PATH
            $mingwFound = $true
            $MinGWPath = $candidate
            break
        }
    }
    # WinLibs installs windres/dlltool WITHOUT the target prefix that
    # tauri-winres looks for, so create prefixed copies on demand.
    if ($mingwFound) {
        foreach ($tool in @("windres", "dlltool")) {
            $bare = Join-Path $MinGWPath "$tool.exe"
            $prefixed = Join-Path $MinGWPath "x86_64-w64-mingw32-$tool.exe"
            if ((Test-Path $bare) -and -not (Test-Path $prefixed)) {
                Copy-Item $bare $prefixed -Force
                Write-Host "  added x86_64-w64-mingw32-$tool alias" -ForegroundColor Gray
            }
        }
    }
    if (-not $mingwFound) {
        $rustTarget = & rustc -vV 2>$null | Select-String "host:" | ForEach-Object { $_ -replace "host: ", "" }
        Write-Host "  rustc host: $rustTarget" -ForegroundColor Gray
        Write-Host "  no MinGW in PATH; install WinLibs MinGW to bundle x86_64-pc-windows-gnu." -ForegroundColor Gray
    }
}

# ---- Version Metadata ----
Write-Host "`n[2/5] Reading version metadata..." -ForegroundColor Yellow
$tauriConfigPath = Join-Path $TauriDir "tauri.conf.json"
$tauriConfig = Get-Content $tauriConfigPath -Raw | ConvertFrom-Json
$AppVersion = $tauriConfig.version
$ProductName = $tauriConfig.productName
$prevErr = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$CommitHash = git -C $RepoRoot rev-parse HEAD 2>$null
if (-not $CommitHash) { $CommitHash = "unknown" }
$BuildDate = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
$GitTag = git -C $RepoRoot describe --tags --exact-match 2>$null
if (-not $GitTag) { $GitTag = "untagged" }
$ErrorActionPreference = $prevErr

Write-Host "  Version:   $AppVersion" -ForegroundColor Green
Write-Host "  Commit:    $CommitHash" -ForegroundColor Green
Write-Host "  Tag:       $GitTag" -ForegroundColor Green

# ---- Clean & prepare output ----
Write-Host "`n[3/5] Preparing output directories..." -ForegroundColor Yellow
if (Test-Path $OutDir) {
    Remove-Item -Recurse -Force "$OutDir\*" -ErrorAction SilentlyContinue
}
New-Item -ItemType Directory -Force -Path $ArtifactsDir | Out-Null
Write-Host "  Output: $OutDir" -ForegroundColor Green
Write-Host "  Artifacts: $ArtifactsDir" -ForegroundColor Green

# ---- Frontend build (Next.js) ----
if (-not $SkipFrontend) {
    Write-Host "`n[4/5] Building Mission Control frontend..." -ForegroundColor Yellow
    Push-Location $MissionDir
    try {
        Write-Host "  Installing npm dependencies..." -ForegroundColor Gray
        npm ci --legacy-peer-deps 2>&1 | ForEach-Object { Write-Host "    $_" }

        Write-Host "  Building Next.js static export..." -ForegroundColor Gray
        npm run build 2>&1 | ForEach-Object { Write-Host "    $_" }

        if (-not (Test-Path (Join-Path $MissionDir "out"))) {
            throw "Frontend build failed: 'out/' directory not found. Check next build output above."
        }
        Write-Host "  Frontend build complete." -ForegroundColor Green
    }
    finally {
        Pop-Location
    }
}
else {
    Write-Host "`n[4/5] Skipping frontend build (-SkipFrontend)." -ForegroundColor Gray
}

# ---- Rust/Tauri build ----
if (-not $SkipRust) {
    Write-Host "`n[5/5] Building Rust/Tauri backend..." -ForegroundColor Yellow

    # Step A: Build embedded Python backend (agentic_os.exe)
    Write-Host "  [5A] Compiling standalone backend executable (agentic_os.exe)..." -ForegroundColor Gray
    Push-Location $RepoRoot
    try {
        $prevErr = $ErrorActionPreference
        $ErrorActionPreference = "Continue"

        # Use the .spec file if it exists (it bundles all hidden imports declaratively)
        $SpecFile = Join-Path $RepoRoot "agentic_os.spec"
        if (Test-Path $SpecFile) {
            Write-Host "  Using existing agentic_os.spec for PyInstaller build" -ForegroundColor Gray
            & uv run --with pyinstaller pyinstaller --noconfirm --distpath (Join-Path $RepoRoot "dist") $SpecFile
        } else {
            & uv run --with pyinstaller pyinstaller `
                --noconfirm --onefile --name agentic_os `
                --distpath (Join-Path $RepoRoot "dist") `
                --hidden-import=uvicorn.logging `
                --hidden-import=uvicorn.loops `
                --hidden-import=uvicorn.loops.auto `
                --hidden-import=uvicorn.protocols `
                --hidden-import=uvicorn.protocols.http `
                --hidden-import=uvicorn.protocols.http.auto `
                --hidden-import=uvicorn.protocols.websockets `
                --hidden-import=uvicorn.protocols.websockets.auto `
                --hidden-import=uvicorn.lifespan `
                --hidden-import=uvicorn.lifespan.on `
                --hidden-import=anyio._backends._asyncio `
                --hidden-import=anyio._backends._trio `
                --hidden-import=agentic_os.cli `
                src/agentic_os/__main__.py
        }
        $pyiExit = $LASTEXITCODE
        $ErrorActionPreference = $prevErr
        if ($pyiExit -ne 0) {
            throw "PyInstaller failed with exit code $pyiExit"
        }
    }
    finally {
        Pop-Location
    }

    # Step B: Copy backend executable to Tauri resources
    $ResBackendDir = Join-Path $TauriDir "resources\backend"
    New-Item -ItemType Directory -Force -Path $ResBackendDir | Out-Null
    # PyInstaller puts the binary in dist/ by default
    $CompiledBackend = Join-Path $RepoRoot "dist\agentic_os.exe"
    if (-not (Test-Path $CompiledBackend)) {
        # Fallback: check $OutDir in case build script re-routed output
        $CompiledBackend = Join-Path $OutDir "agentic_os.exe"
    }
    if (Test-Path $CompiledBackend) {
        Copy-Item $CompiledBackend (Join-Path $ResBackendDir "agentic_os.exe") -Force
        Write-Host "  + Bundled backend into resources: $ResBackendDir\agentic_os.exe" -ForegroundColor Green
    } else {
        throw "Failed to compile embedded backend executable. Searched: dist\agentic_os.exe and $OutDir\agentic_os.exe"
    }

    # Step C: Pre-copy WebView2Loader.dll to resources/ (BEFORE Tauri build bundles it)
    $ResDir = Join-Path $TauriDir "resources"
    $TargetRelease = Join-Path $TauriDir "target\$ReleaseDir"
    $WV2Path = Join-Path $TargetRelease "WebView2Loader.dll"
    $WV2ResourceDest = Join-Path $ResDir "WebView2Loader.dll"

    # Strategy 1: Copy from Tauri target directory (if previous Rust build exists)
    if (Test-Path $WV2Path) {
        Copy-Item $WV2Path $WV2ResourceDest -Force
        Write-Host "  + WebView2Loader.dll: target -> resources" -ForegroundColor Green
    } else {
        # Strategy 2: Pre-build Rust to generate WebView2Loader.dll, then copy
        Write-Host "  + Pre-building Rust target to generate WebView2Loader.dll..." -ForegroundColor Gray
        Push-Location $TauriDir
        try {
            $prevErr = $ErrorActionPreference
            $ErrorActionPreference = "Continue"
            & cargo build --release 2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0 -and (Test-Path $WV2Path)) {
                Copy-Item $WV2Path $WV2ResourceDest -Force
                Write-Host "  + WebView2Loader.dll: cargo build -> resources" -ForegroundColor Green
            } else {
                # Strategy 3: Check NuGet cache for WebView2Loader.dll
                $nugetPaths = @(
                    "$env:USERPROFILE\.cargo
egistry\src\*\webview2-com-sys-*\lib\WebView2Loader.dll",
                    "$env:LOCALAPPDATA\Microsoft\WebView2\*\WebView2Loader.dll",
                    "C:\Program Files (x86)\Microsoft WebView2\*\WebView2Loader.dll"
                )
                $found = $false
                foreach ($pattern in $nugetPaths) {
                    $matches = Get-ChildItem -Path $pattern -ErrorAction SilentlyContinue
                    if ($matches) {
                        Copy-Item $matches[0].FullName $WV2ResourceDest -Force
                        Write-Host "  + WebView2Loader.dll: NuGet/system -> resources" -ForegroundColor Green
                        $found = $true
                        break
                    }
                }
                if (-not $found) {
                    Write-Host "  ⚠ WebView2Loader.dll not found — installers will rely on Evergreen WebView2 Runtime" -ForegroundColor Yellow
                }
            }
            $ErrorActionPreference = $prevErr
        }
        finally {
            Pop-Location
        }
    }

    Push-Location $TauriDir
    try {
        Write-Host "  [5B] Running cargo tauri build (Config: $Config)..." -ForegroundColor Gray

        # Clean stale bundle artifacts to prevent version-mismatched EXE/MSI from
        # prior builds being picked up by the artifact collector.
        $BundleCleanDir = Join-Path $TauriDir "target\$ReleaseDir\bundle"
        if (Test-Path $BundleCleanDir) {
            Remove-Item -Recurse -Force $BundleCleanDir -ErrorAction SilentlyContinue
            Write-Host "  + Cleaned stale bundle artifacts" -ForegroundColor Gray
        }

        # Determine Tauri CLI
        $TauriCli = "npx"

        $TauriArgs = @("tauri", "build", "--bundles", "nsis,msi")
        if ($Config -eq "Debug") {
            $TauriArgs += "--debug"
        }

        $prevErr = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & $TauriCli $TauriArgs
        $buildExit = $LASTEXITCODE
        $ErrorActionPreference = $prevErr

        if ($buildExit -ne 0 -and $buildExit -ne $null) {
            throw "Tauri build failed with exit code $buildExit"
        }

        # Step D: After build, ensure WebView2Loader.dll is in resources and next to binary
        if (Test-Path $WV2Path) {
            Copy-Item $WV2Path $WV2ResourceDest -Force
            Write-Host "  + WebView2Loader.dll synced to resources" -ForegroundColor Green
        }

        Write-Host "  Tauri build complete." -ForegroundColor Green
    }
    finally {
        Pop-Location
    }
}
else {
    Write-Host "`n[5/5] Skipping Rust/Tauri build (-SkipRust)." -ForegroundColor Gray
}

# ---- Collect artifacts ----
Write-Host "`nCollecting build artifacts..." -ForegroundColor Yellow
$BundleDir = Join-Path $TauriDir "target\$ReleaseDir\bundle"
$BinaryPath = Join-Path $TauriDir "target\$ReleaseDir\agentic-os.exe"

if (Test-Path $BundleDir) {
    Write-Host "  Copying bundle artifacts..." -ForegroundColor Gray

    # NSIS installer
    $nsisFiles = Get-ChildItem (Join-Path $BundleDir "nsis") -Filter "*.exe" -ErrorAction SilentlyContinue
    foreach ($f in $nsisFiles) {
        $dest = Join-Path $ArtifactsDir "$ProductName-Setup-x64$($f.Extension)"
        Copy-Item $f.FullName $dest -Force
        Write-Host "    + $dest" -ForegroundColor Green
    }

    # MSI installer
    $msiFiles = Get-ChildItem (Join-Path $BundleDir "msi") -Filter "*.msi" -ErrorAction SilentlyContinue
    foreach ($f in $msiFiles) {
        $dest = Join-Path $ArtifactsDir "$ProductName-Setup-x64.msi"
        Copy-Item $f.FullName $dest -Force
        Write-Host "    + $dest" -ForegroundColor Green
    }

    # Portable ZIP: bundle binary + resources
    if (Test-Path $BinaryPath) {
        $PortableDir = Join-Path $OutDir "portable"
        New-Item -ItemType Directory -Force -Path $PortableDir | Out-Null

        Copy-Item $BinaryPath (Join-Path $PortableDir "agentic-os.exe") -Force

        # Copy WebView2Loader.dll next to the binary (required for portable runtime)
        # Try multiple locations in priority order
        $wv2Candidates = @(
            (Join-Path $TauriDir "target\$ReleaseDir\WebView2Loader.dll"),
            (Join-Path $TauriDir "resources\WebView2Loader.dll"),
            (Join-Path $TauriDir "target\$ReleaseDir\bundle\nsis\WebView2Loader.dll"),
            "$env:LOCALAPPDATA\Microsoft\WebView2\Evergreen\WebView2Loader.dll",
            "$env:ProgramFiles (x86)\Microsoft\WebView2\Runtime\WebView2Loader.dll"
        )
        $wv2Copied = $false
        foreach ($wv2Candidate in $wv2Candidates) {
            if (Test-Path $wv2Candidate) {
                Copy-Item $wv2Candidate (Join-Path $PortableDir "WebView2Loader.dll") -Force
                Write-Host "    + WebView2Loader.dll (from $wv2Candidate)" -ForegroundColor Green
                $wv2Copied = $true
                break
            }
        }
        if (-not $wv2Copied) {
            Write-Host "    ⚠ WebView2Loader.dll not bundled — portable ZIP requires Evergreen WebView2 Runtime" -ForegroundColor Yellow
        }

        # Copy resources if any exist
        $ResDir = Join-Path $TauriDir "target\$ReleaseDir\resources"
        if (Test-Path $ResDir) {
            Copy-Item -Recurse "$ResDir\*" $PortableDir -Force -ErrorAction SilentlyContinue
        }

        # Create launcher script
        $launcherContent = @'
@echo off
title AgenticOS Desktop Runtime
echo ========================================
echo  AgenticOS Desktop Runtime — Portable
echo ========================================
echo.
echo Checking WebView2 Runtime...

reg query "HKCU\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00FB3A3A6E2E}" /v pv >nul 2>nul
if %errorlevel% neq 0 (
    reg query "HKLM\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00FB3A3A6E2E}" /v pv >nul 2>nul
)
if %errorlevel% neq 0 (
    echo WebView2 Runtime not detected. Attempting to install...
    start /wait "" "%~dp0Microsoft.WebView2.Bootstrapper.exe" /silent /install
    if %errorlevel% neq 0 (
        echo Please install WebView2 Runtime manually from:
        echo https://developer.microsoft.com/microsoft-edge/webview2/
        pause
        exit /b 1
    )
)
echo Starting AgenticOS...
start "" "%~dp0agentic-os.exe"
'@
        Set-Content -Path (Join-Path $PortableDir "start.bat") -Value $launcherContent

        # Create PowerShell launcher
        $psLauncher = @'
$wv2Check = Get-ItemProperty -Path "HKCU:\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00FB3A3A6E2E}" -Name "pv" -ErrorAction SilentlyContinue
if (-not $wv2Check) {
    $wv2Check = Get-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00FB3A3A6E2E}" -Name "pv" -ErrorAction SilentlyContinue
}
if (-not $wv2Check) {
    Write-Host "WebView2 Runtime not detected. Installing..." -ForegroundColor Yellow
    $bootstrapper = "$PSScriptRoot\Microsoft.WebView2.Bootstrapper.exe"
    if (Test-Path $bootstrapper) {
        Start-Process -Wait -FilePath $bootstrapper -ArgumentList "/silent", "/install"
    } else {
        Write-Host "Please install WebView2 Runtime from: https://developer.microsoft.com/microsoft-edge/webview2/" -ForegroundColor Red
        Read-Host "Press Enter to continue"
    }
}
Write-Host "Starting AgenticOS Desktop Runtime..." -ForegroundColor Cyan
Start-Process -FilePath "$PSScriptRoot\agentic-os.exe"
'@
        Set-Content -Path (Join-Path $PortableDir "start.ps1") -Value $psLauncher

        # ZIP it
        $zipDest = Join-Path $ArtifactsDir "$ProductName-Portable-x64.zip"
        if (Get-Command Compress-Archive -ErrorAction SilentlyContinue) {
            Compress-Archive -Path "$PortableDir\*" -DestinationPath $zipDest -Force
            Write-Host "    + $zipDest" -ForegroundColor Green
        }
        else {
            # Fallback using .NET
            Add-Type -AssemblyName System.IO.Compression.FileSystem
            [System.IO.Compression.ZipFile]::CreateFromDirectory($PortableDir, $zipDest)
            Write-Host "    + $zipDest (.NET fallback)" -ForegroundColor Green
        }

        Remove-Item -Recurse -Force $PortableDir -ErrorAction SilentlyContinue
    }
}
else {
    Write-Warning "  Bundle directory not found: $BundleDir"
    Write-Warning "  Artifact collection skipped. Build may have failed."
}

# ---- Generate checksums ----
Write-Host "`nGenerating SHA256 checksums..." -ForegroundColor Yellow
$checksumsPath = Join-Path $ArtifactsDir "SHA256SUMS.txt"
$checksumLines = @()

Get-ChildItem $ArtifactsDir -File | ForEach-Object {
    $hash = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower()
    $checksumLines += "$hash  $($_.Name)"
    Write-Host "  $($hash.Substring(0, 16))...  $($_.Name)" -ForegroundColor Gray
}

$checksumLines | Out-File -FilePath $checksumsPath -Encoding ascii
Write-Host "  Checksums saved: $checksumsPath" -ForegroundColor Green

# ---- Installer report ----
Write-Host "`nGenerating installer report..." -ForegroundColor Yellow
$reportPath = Join-Path $ArtifactsDir "installer-report.json"
$artifacts = @()

Get-ChildItem $ArtifactsDir -File | Where-Object { $_.Name -ne "SHA256SUMS.txt" -and $_.Name -ne "installer-report.json" } | ForEach-Object {
    $artifacts += @{
        name = $_.Name
        size = $_.Length
        path = $_.FullName
    }
}

$report = @{
    version = $AppVersion
    productName = $ProductName
    commit = $CommitHash
    buildDate = $BuildDate
    gitTag = $GitTag
    config = $Config
    platform = "windows-x64"
    artifacts = $artifacts
    checksums = @($checksumLines | ForEach-Object { $_ })
}

$report | ConvertTo-Json -Depth 5 | Out-File -FilePath $reportPath -Encoding utf8
Write-Host "  Report: $reportPath" -ForegroundColor Green

# ---- Summary ----
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  Build Complete" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Version: $AppVersion" -ForegroundColor Green
Write-Host "  Commit:  $CommitHash" -ForegroundColor Green
Write-Host "  Tag:     $GitTag" -ForegroundColor Green
Write-Host "  Output:  $ArtifactsDir" -ForegroundColor Green
Write-Host ""

Get-ChildItem $ArtifactsDir -File | ForEach-Object {
    $size = if ($_.Length -gt 1MB) { "{0:N2} MB" -f ($_.Length / 1MB) } else { "{0:N0} KB" -f ($_.Length / 1KB) }
    Write-Host "  $($_.Name) ($size)" -ForegroundColor White
}

Write-Host "`nDone." -ForegroundColor Cyan
