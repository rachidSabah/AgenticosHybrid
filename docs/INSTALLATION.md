# Installation Guide — AgenticOS v1.0.0-rc1

This guide covers installing AgenticOS on Windows, Linux, and macOS. AgenticOS runs as a native desktop application (via Tauri v2) with an optional headless backend mode for server deployments.

---

## 1. System Requirements

### Windows
- **OS:** Windows 10 22H2 or later, or Windows 11
- **RAM:** 8 GB minimum (16 GB recommended)
- **Storage:** 2 GB for application files, plus additional space for AI models and data
- **WebView2:** Microsoft Edge WebView2 runtime (included on Windows 11, auto-installed on Windows 10)
- **Optional:** Python 3.14, Node.js 18+, Git (for runtime discovery features)

### Linux
- **OS:** Ubuntu 22.04+, Debian 12+, Fedora 38+, or any distribution with FUSE support
- **RAM:** 8 GB minimum (16 GB recommended)
- **Storage:** 2 GB for application files
- **FUSE:** `libfuse2` (for AppImage) — `apt install libfuse2` on Debian/Ubuntu
- **Optional:** Python 3.14, Node.js 18+, Docker, Git

### macOS
- **OS:** macOS 12 (Monterey) or later
- **RAM:** 8 GB minimum (16 GB recommended)
- **Storage:** 2 GB for application files
- **Optional:** Python 3.14, Node.js 18+, Homebrew, Git

---

## 2. Windows Installation

### 2.1 MSI Installer (Recommended)

1. Download the MSI package from the [GitHub Releases](https://github.com/rachidSabah/AgenticOS/releases) page (look for `AgenticOS-Setup-x64.msi`).
2. Double-click the MSI file to launch the Windows Installer.
3. Follow the setup wizard:
   - Accept the license agreement
   - Choose destination folder (default: `C:\Program Files\AgenticOS`)
   - Select start menu folder
   - Choose optional tasks (create desktop shortcut, add to PATH)
   - Click **Install**
4. Once installed, launch AgenticOS from the Start Menu or desktop shortcut.

### 2.2 EXE Installer

1. Download `AgenticOS-Setup-x64.exe` from the Releases page.
2. Right-click the EXE and select **Run as administrator**.
3. The installer extracts and runs the setup wizard (same steps as MSI above).

### 2.3 Portable ZIP

1. Download `AgenticOS-Portable-x64.zip` from the Releases page.
2. Extract the ZIP archive to your desired location (e.g., `C:\Tools\AgenticOS`).
3. Run `AgenticOS.exe` from the extracted folder.
4. No installation or administrator privileges required.

### 2.4 Silent / Unattended Installation

For enterprise deployments, both MSI and EXE support silent installation:

```powershell
# MSI silent install
msiexec /i AgenticOS-Setup-x64.msi /quiet /norestart INSTALLDIR="C:\AgenticOS" DESKTOP_SHORTCUT=1

# EXE silent install
AgenticOS-Setup-x64.exe /S /D=C:\AgenticOS
```

**MSI properties:**
| Property           | Values          | Default                    |
|--------------------|-----------------|----------------------------|
| `INSTALLDIR`       | Path            | `C:\Program Files\AgenticOS` |
| `DESKTOP_SHORTCUT` | `0` or `1`      | `1`                        |
| `START_MENU`       | `0` or `1`      | `1`                        |
| `ADD_TO_PATH`      | `0` or `1`      | `0`                        |

---

## 3. Linux Installation

### 3.1 AppImage (Recommended)

1. Download `AgenticOS-x86_64.AppImage` from the Releases page.
2. Make the file executable and run:

```bash
chmod +x AgenticOS-x86_64.AppImage
./AgenticOS-x86_64.AppImage
```

3. (Optional) Integrate into the application menu:
```bash
./AgenticOS-x86_64.AppImage --install
```

**Dependencies:** Ensure `libfuse2` is installed:
```bash
# Debian/Ubuntu
sudo apt install libfuse2

# Fedora
sudo dnf install fuse-libs
```

### 3.2 DEB Package (Debian/Ubuntu)

```bash
# Download the .deb package
wget https://github.com/rachidSabah/AgenticOS/releases/download/v1.0.0-rc1/AgenticOS_1.0.0-rc1_amd64.deb

# Install
sudo dpkg -i AgenticOS_1.0.0-rc1_amd64.deb
sudo apt install -f   # resolve any missing dependencies

# Launch
agenticos
```

### 3.3 RPM Package (Fedora/RHEL)

```bash
# Download the .rpm package
wget https://github.com/rachidSabah/AgenticOS/releases/download/v1.0.0-rc1/AgenticOS-1.0.0-rc1.x86_64.rpm

# Install
sudo rpm -i AgenticOS-1.0.0-rc1.x86_64.rpm
# or
sudo dnf install ./AgenticOS-1.0.0-rc1.x86_64.rpm

# Launch
agenticos
```

### 3.4 Portable ZIP

```bash
# Download and extract
wget https://github.com/rachidSabah/AgenticOS/releases/download/v1.0.0-rc1/AgenticOS-Portable-x64.zip
unzip AgenticOS-Portable-x64.zip -d ~/AgenticOS

# Run
~/AgenticOS/agenticos
```

---

## 4. macOS Installation

### 4.1 DMG Image

1. Download `AgenticOS-x64.dmg` or `AgenticOS-arm64.dmg` (Apple Silicon) from the Releases page.
2. Open the DMG file.
3. Drag the AgenticOS icon into the **Applications** folder.
4. Eject the DMG.
5. Launch AgenticOS from Applications (you may need to right-click and select **Open** the first time to bypass Gatekeeper).

### 4.2 PKG Installer

1. Download `AgenticOS-x64.pkg` or `AgenticOS-arm64.pkg` from the Releases page.
2. Double-click the PKG file to launch the installer.
3. Follow the installation wizard.

### 4.3 Portable ZIP

```bash
# Download and extract
wget https://github.com/rachidSabah/AgenticOS/releases/download/v1.0.0-rc1/AgenticOS-Portable-x64.zip
unzip AgenticOS-Portable-x64.zip -d ~/AgenticOS

# Run
~/AgenticOS/AgenticOS.app/Contents/MacOS/agenticos
```

---

### 4.4 CLI Entry Point (All Platforms)

AgenticOS ships with a `agentic-os` CLI command for headless/backend usage:

```bash
# Start the backend API server
agentic-os serve

# Show help
agentic-os --help

# Show version
agentic-os --version
```

---

## 5. Verifying the Installation

All installer packages include SHA256 checksums published alongside the release assets.

### 5.1 Verify SHA256 Checksum

```bash
# Windows (PowerShell)
Get-FileHash AgenticOS-Setup-x64.msi -Algorithm SHA256
# Compare the output with the checksum in the RELEASE_NOTES or checksums.txt file

# Linux/macOS
sha256sum AgenticOS-x86_64.AppImage
# Compare against the published checksum
```

### 5.2 Verify Application Starts

```powershell
# Check the application runs
agenticos --version
# Expected output: AgenticOS v1.0.0-rc1

# Check the API is reachable (backend mode)
curl http://localhost:8000/healthz
# Expected: {"status":"ok","bus":"local"}
```

### 5.3 Verify Runtime Discovery

```powershell
# Trigger runtime discovery
curl http://localhost:8000/api/desktop/runtimes/discover -X POST
# Expected: {"total_discovered": N, "runtimes": [...], "duration_seconds": ...}
```

---

## 6. First Run Experience

On first launch, the **First Run Wizard** guides you through a 9-step setup:

1. **Welcome** — License agreement and introductory information
2. **Workspace** — Create your default workspace
3. **Configuration** — Set language, theme, and preferences
4. **Runtime Discovery** — Auto-detect installed runtimes (Python, Node.js, Docker, Git, AI CLIs)
5. **Provider Setup** — Configure AI providers (API keys for OpenAI, Anthropic, etc.)
6. **Plugin Initialization** — Enable built-in plugins
7. **Database Setup** — Initialize the local SQLite database
8. **Health Check** — Verify the system is ready
9. **Complete** — Enter the desktop runtime

The wizard can be skipped or completed via the API for unattended setups.

---

## 7. Troubleshooting

### 7.1 Application fails to start

| Issue                          | Solution                                                    |
|--------------------------------|-------------------------------------------------------------|
| Missing WebView2 (Windows)     | Download from https://developer.microsoft.com/en-us/microsoft-edge/webview2/ |
| FUSE not installed (Linux)     | `sudo apt install libfuse2` or `sudo dnf install fuse-libs` |
| Gatekeeper blocks app (macOS)  | Right-click → Open, or `xattr -d com.apple.quarantine /Applications/AgenticOS.app` |
| Port 8000 already in use       | Change port via `AGENTIC_OS_PORT=8001 agenticos`            |
| Python not found               | Install Python 3.14+ via `uv python install 3.14`           |

### 7.2 Runtime Discovery doesn't find tools

Ensure the tool is installed and on your system PATH:

```bash
# Verify Python
python --version

# Verify Node.js
node --version

# Verify Docker
docker --version

# Verify Git
git --version

# Verify Ollama
ollama --version
```

### 7.3 Update fails

- Check that you have internet connectivity
- Verify the update channel is accessible (try switching to `stable`)
- Check `~/.agentic_os/logs/` for detailed error logs
- Run `curl http://localhost:8000/api/desktop/updates/check` to verify the release API is reachable

### 7.4 Offline mode not syncing

- Ensure network connectivity is restored
- Check the event queue via `GET /api/desktop/offline/events`
- Trigger manual sync via `POST /api/desktop/offline/sync`

---

## 8. Uninstallation

### Windows

```powershell
# Via Settings
Settings → Apps → Apps & features → AgenticOS → Uninstall

# Via Control Panel
Control Panel → Programs → Programs and Features → AgenticOS → Uninstall

# Silent uninstall
msiexec /x AgentICOS-Setup-x64.msi /quiet
```

### Linux

```bash
# DEB package
sudo apt remove agenticos

# RPM package
sudo dnf remove agenticos

# AppImage — simply delete the AppImage file and the integration files:
rm ~/.local/share/applications/agenticos.desktop 2>/dev/null
rm -rf ~/.config/agenticos 2>/dev/null

# Portable ZIP — delete the extraction directory
rm -rf ~/AgenticOS
```

### macOS

```bash
# Drag from Applications to Trash, or:
rm -rf /Applications/AgenticOS.app
rm -rf ~/Library/Application\ Support/com.agentic.os
rm -rf ~/Library/Preferences/com.agentic.os.plist
rm -rf ~/Library/Caches/com.agentic.os
```

### Remove all user data (optional)

```bash
rm -rf ~/.agentic_os   # Configuration, workspaces, database, backups, logs
```

---

## 9. Enterprise / Silent Installation

### Windows (Group Policy / SCCM)

Deploy the MSI via Group Policy:

1. Place `AgenticOS-Setup-x64.msi` on a network share
2. In Group Policy Management Editor: Computer Configuration → Software Settings → Software Installation → New → Package
3. Select the MSI and choose **Assigned** (mandatory install)
4. The MSI supports all standard Windows Installer properties for customization

### Linux (apt / dnf repository)

Configure the AgenticOS APT repository:

```bash
# Debian/Ubuntu
echo "deb https://apt.agentic.os/stable /" | sudo tee /etc/apt/sources.list.d/agenticos.list
curl -fsSL https://apt.agentic.os/key.gpg | sudo apt-key add -
sudo apt update
sudo apt install agenticos
```

### macOS (MDM)

Deploy via Jamf, Kandji, or Intune:

1. Package the `.pkg` or `.app` with your MDM tool
2. Configure post-install scripts to set default configuration
3. Use `defaults write com.agentic.os AutoStart -bool true` to enable auto-start
4. First run can be completed silently via the API: `POST /api/desktop/first-run/complete`

### Complete Silent Setup Script

```powershell
# PowerShell (Windows) — Silent install + configure + start
msiexec /i AgenticOS-Setup-x64.msi /quiet /norestart
Start-Sleep -Seconds 5
$base = "http://localhost:8000"

# Wait for service
do { Start-Sleep 1 } while ((Invoke-WebRequest "$base/healthz" -UseBasicParsing).StatusCode -ne 200)

# Complete first run
Invoke-RestMethod -Method Post -Uri "$base/api/desktop/first-run/complete"

# Run discovery
Invoke-RestMethod -Method Post -Uri "$base/api/desktop/runtimes/discover"

Write-Output "AgenticOS installed and configured."
```

---

## 10. Configuration Files

| File                                      | Purpose                        |
|-------------------------------------------|--------------------------------|
| `~/.agentic_os/config.json`              | Desktop runtime configuration  |
| `~/.agentic_os/state.db`                 | Local SQLite database          |
| `~/.agentic_os/logs/`                    | Application logs               |
| `~/.agentic_os/backups/`                 | Backup archives                |
| `~/.agentic_os/cache/`                   | Discovery and data cache       |
| `~/.config/agentic-os/config.json`       | Linux alternative config path  |
| `~/Library/Application Support/com.agentic.os/config.json` | macOS config path |
| `%APPDATA%/AgenticOS/config.json`        | Windows config path            |

---

## 11. Build from Source

For development builds, see the `README.md` or the development guide:

```bash
# Prerequisites: Python 3.14+, Node.js 18+, Rust (for Tauri)
git clone https://github.com/rachidSabah/AgenticOS.git
cd AgenticOS

# Backend
uv sync
uv run python -m agentic_os serve

# Frontend (in another terminal)
cd apps/mission-control
npm install
npm run dev

# Desktop (Tauri) — requires MSVC on Windows
cd apps/mission-control
npm run tauri dev
```
