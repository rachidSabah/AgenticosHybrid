# WSL2 Setup (Windows host)

Agentic OS runs natively in WSL2 (Ubuntu). Docker Desktop must have
**WSL2 integration** enabled for your distro.

## One-time

```bash
# In PowerShell (admin): install WSL2 + Ubuntu if needed
wsl --install -d Ubuntu

# Inside WSL2 Ubuntu:
sudo apt update && sudo apt install -y curl git build-essential
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env

# Clone / open the project (this repo lives at /mnt/e/AAIOS)
cd /mnt/e/AAIOS
uv python install 3.13
uv sync
```

## Run

```bash
# Local (in-process bus, no Docker)
BUS_TYPE=local uv run python -m agentic_os serve

# Or full stack via Docker (from the repo root)
BUS_TYPE=redis docker compose up --build
```

## Notes

- Docker sockets from WSL2 reach the Windows Docker Desktop daemon automatically.
- For the **Claude Code** adapter to drive real agents, install the `claude` CLI
  inside the same WSL2 environment and export `ANTHROPIC_API_KEY`.
- Use `PROVIDER_DEFAULT=mock` for offline dev/CI (no network, deterministic).
