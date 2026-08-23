#!/usr/bin/env bash
# ==============================================================================
# AgenticOS Hybrid — One-Line WSL2 & Linux Automated Deployment
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/rachidSabah/AgenticosHybrid/main/deploy.sh | bash
# Or locally:
#   ./deploy.sh
# ==============================================================================

set -euo pipefail

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${CYAN}==================================================================${NC}"
echo -e "${CYAN}        AgenticOS Hybrid — One-Line WSL2 / Linux Deployment       ${NC}"
echo -e "${CYAN}==================================================================${NC}"

INSTALL_DIR="${HOME}/.agentic_os/AgenticOS"
WORKSPACE_DIR="${HOME}/.agentic_os/workspace"

# 1. Environment & Distro Detection
echo -e "\n${YELLOW}[1/7] Detecting Host Environment & OS...${NC}"
OS_NAME=$(uname -s)
IS_WSL=false
if grep -qi "microsoft" /proc/version 2>/dev/null; then
    IS_WSL=true
    echo -e "  ${GREEN}✓ WSL2 Environment Detected${NC}"
else
    echo -e "  ${GREEN}✓ Linux Native Environment (${OS_NAME})${NC}"
fi

# 2. Package Manager and Dependency Installation
echo -e "\n${YELLOW}[2/7] Verifying System Dependencies (curl, git, python3, nodejs)...${NC}"
if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -qq
    sudo apt-get install -y -qq curl git python3 python3-pip python3-venv build-essential >/dev/null 2>&1 || true
elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y -q curl git python3 python3-pip make gcc >/dev/null 2>&1 || true
elif command -v pacman >/dev/null 2>&1; then
    sudo pacman -Sy --noconfirm curl git python python-pip base-devel >/dev/null 2>&1 || true
fi

# Install uv if missing
if ! command -v uv >/dev/null 2>&1; then
    echo -e "  Installing modern Python package manager (uv)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="${HOME}/.local/bin:${PATH}"
fi

# Install Node.js (via NodeSource if node < 18 or missing)
if ! command -v node >/dev/null 2>&1 || [ "$(node -v | cut -d'.' -f1 | tr -d 'v')" -lt 18 ]; then
    echo -e "  Installing Node.js LTS (20.x)..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - >/dev/null 2>&1 || true
    sudo apt-get install -y -qq nodejs >/dev/null 2>&1 || true
fi

echo -e "  ${GREEN}✓ Python: $(python3 --version)${NC}"
echo -e "  ${GREEN}✓ Node.js: $(node --version)${NC}"
echo -e "  ${GREEN}✓ uv: $(uv --version)${NC}"

# 3. Setup Installation Directory & Source Code
echo -e "\n${YELLOW}[3/7] Setting up AgenticOS Source & Directory Structure...${NC}"
mkdir -p "${INSTALL_DIR}"
mkdir -p "${WORKSPACE_DIR}"
mkdir -p "${HOME}/.agentic_os/logs"
mkdir -p "${HOME}/.agentic_os/data"

if [ -f "./pyproject.toml" ]; then
    echo -e "  Copying local repository..."
    cp -r ./* "${INSTALL_DIR}/" 2>/dev/null || true
else
    if [ ! -d "${INSTALL_DIR}/.git" ]; then
        echo -e "  Cloning repository into ${INSTALL_DIR}..."
        git clone --depth 1 https://github.com/rachidSabah/AgenticosHybrid.git "${INSTALL_DIR}"
    else
        echo -e "  Updating existing repository in ${INSTALL_DIR}..."
        git -C "${INSTALL_DIR}" pull --ff-only || true
    fi
fi

cd "${INSTALL_DIR}"

# 4. Backend Environment Setup
echo -e "\n${YELLOW}[4/7] Setting up Python Virtual Environment & Backend...${NC}"
uv venv .venv --python python3
source .venv/bin/activate
uv pip install -e .

# 5. Frontend Dependencies & Production Build
echo -e "\n${YELLOW}[5/7] Building Mission Control Frontend...${NC}"
cd apps/mission-control
npm ci --legacy-peer-deps
npm run build
cd "${INSTALL_DIR}"

# 6. Service Configuration & Agent Discovery
echo -e "\n${YELLOW}[6/7] Probing Host Agents & Bridging CLI Runtimes...${NC}"
# Probe Windows host binaries if running in WSL
if [ "$IS_WSL" = true ]; then
    echo -e "  Bridging Windows PATH binaries into WSL agent registry..."
    export PATH="${PATH}:/mnt/c/Users/${USER:-InGodWeTrust}/.local/bin:/mnt/c/Program Files/Git/cmd:/mnt/c/Program Files/nodejs"
fi

# 7. Start AgenticOS Background Services & Health Check
echo -e "\n${YELLOW}[7/7] Starting AgenticOS Hybrid Control Plane...${NC}"
# Terminate any previous instance
pkill -f "agentic_os serve" || true
pkill -f "next start" || true

# Start backend
uv run python -m agentic_os serve --host 0.0.0.0 --port 8080 > "${HOME}/.agentic_os/logs/backend.log" 2>&1 &
BACKEND_PID=$!

# Start frontend
cd apps/mission-control
npm run start -- -p 3000 > "${HOME}/.agentic_os/logs/frontend.log" 2>&1 &
FRONTEND_PID=$!
cd "${INSTALL_DIR}"

echo -e "  Waiting for backend health check on http://127.0.0.1:8080/healthz..."
for i in {1..30}; do
    if curl -s http://127.0.0.1:8080/healthz | grep -q "ok"; then
        echo -e "  ${GREEN}✓ Backend is Healthy! (PID: ${BACKEND_PID})${NC}"
        break
    fi
    sleep 1
done

echo -e "\n${GREEN}==================================================================${NC}"
echo -e "${GREEN}  AGENTICOS HYBRID IS LIVE AND READY!                             ${NC}"
echo -e "${GREEN}  Mission Control Frontend : http://localhost:3000                ${NC}"
echo -e "${GREEN}  Backend Control Plane    : http://127.0.0.1:8080                ${NC}"
echo -e "${GREEN}  Active Workspace Root    : ${WORKSPACE_DIR}                     ${NC}"
echo -e "${GREEN}  Logs Directory           : ${HOME}/.agentic_os/logs             ${NC}"
echo -e "${GREEN}==================================================================${NC}"