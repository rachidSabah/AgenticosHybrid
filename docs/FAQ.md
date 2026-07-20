# Frequently Asked Questions

## What is AgenticOS?

AgenticOS is a **local-first, event-bus-driven AI Agent Operating System**. It provides a runtime for building, orchestrating, and managing AI agents on your own hardware. Think of it as an operating system for AI workflows: it handles agent lifecycle, provider integrations, memory, security, multi-agent orchestration, and provides a desktop UI (Mission Control) for managing everything.

Key capabilities:
- **Universal Execution Engine** — Run agents using any runtime (Python, Node, Docker, Claude Code, Ollama, etc.)
- **MCP Runtime** — Full Model Context Protocol support for tool execution, resource management, and prompts
- **Swarm Orchestration** — Multi-agent coordination with planning, scheduling, and consensus
- **Learning & Optimization** — Telemetry-driven performance analysis, routing optimization, and A/B experimentation
- **Desktop Runtime** — Native Tauri desktop shell with windows, workspaces, notifications, and system tray
- **Security Framework** — RBAC, encrypted secret vault, approval gates, audit logging, workspace isolation

## Do I need Python installed?

Yes, but **AgenticOS manages its own Python version** through [uv](https://docs.astral.sh/uv/). You need Python 3.14+ available for initial setup, but after that `uv run` uses the project-managed Python interpreter.

```bash
uv python install 3.14
uv sync
uv run python -m agentic_os serve
```

## Do I need Docker?

No. Docker is optional and only required if you want to:
- Use the Docker discovery provider to detect Docker-based runtimes
- Run MCP servers that use the Docker adapter (`agentic-os[mcp-docker]`)
- Containerize your own agent runtimes

AgenticOS works perfectly without Docker for local process-based runtimes.

## How do I install plugins?

Plugins are installed through the Plugins API:

```http
POST /api/plugins
{
  "source": "registry",
  "name": "my-plugin",
  "version": "1.0.0"
}
```

Or from a local path:

```http
POST /api/plugins
{
  "source": "path",
  "path": "/path/to/plugin.zip"
}
```

Requirements:
- Plugins must include a manifest declaring required capabilities
- Installation respects the security framework (roles, permissions, approval gates)
- Plugins can provide custom tools, agents, providers, MCP servers, workflow nodes, or pipeline stages

See the Plugin SDK (`PLUGIN_SDK.md`) for writing custom plugins.

## How do I update AgenticOS?

AgenticOS supports automatic updates through the Desktop Runtime:

```http
# Check for updates
GET /api/desktop/updates/check?channel=stable

# Download available update
POST /api/desktop/updates/download
{
  "version": "1.0.0-rc1",
  "download_url": "...",
  "checksum_sha256": "...",
  "signature": "..."
}

# Install the downloaded update
POST /api/desktop/updates/install
{
  "version": "1.0.0-rc1"
}
```

Update channels:
| Channel | Description |
|---------|-------------|
| `stable` | Production-ready releases |
| `beta` | Pre-release candidates |
| `nightly` | Daily development builds |

To change channels: `PUT /api/desktop/channels` with `{"channel": "beta"}`.

Updates are verified using SHA-256 checksums and cryptographic signatures before installation. Rollback is available if an update fails startup validation.

## Can I use it offline?

Yes. AgenticOS has a built-in **offline mode** that queues events and synchronizes when connectivity is restored.

```http
# Enable offline mode
POST /api/desktop/offline/enable

# Check state
GET /api/desktop/offline

# View queued events
GET /api/desktop/offline/events

# Force synchronize
POST /api/desktop/offline/sync
```

In offline mode:
- Provider API calls are queued (if the provider is unreachable)
- Discovery scans use cached results
- The Desktop Runtime continues to function with local data
- Events are automatically synced when connectivity is restored

Offline mode is only available when the Desktop Runtime is running.

## Is my data encrypted?

Yes. AgenticOS encrypts sensitive data at multiple levels:

1. **Provider API keys** — Encrypted at rest using AES-256-GCM via the Fernet vault. The master key is supplied via `AGENTIC_OS_MASTER_KEY` environment variable or a key file.
2. **Backups** — Optional encryption for backup archives (`BackupConfig.encrypt`).
3. **Secrets in transit** — All API traffic should be served over TLS in production (configurable).
4. **Update payloads** — SHA-256 checksums and cryptographic signatures verify update integrity.

Data not encrypted by default:
- Workspace files (encryption is roadmap)
- In-memory data (subject to OS-level memory protection)
- Event bus messages (unless the transport supports encryption, e.g., NATS TLS)

## How do I report a bug?

1. **Search existing issues** on GitHub to see if the bug is already reported
2. **Open a new issue** with:
   - AgenticOS version (`GET /api/desktop/updates/version`)
   - Operating system and version
   - Python version (`python --version`)
   - Steps to reproduce
   - Expected vs actual behavior
   - Logs (from `~/.agentic_os/logs/` or `%APPDATA%\AgenticOS\logs\`)
   - Any relevant configuration (sanitized of secrets)

For **security vulnerabilities**, do NOT open a public issue. Email **security@agenticos.dev** or use GitHub's private vulnerability reporting.
