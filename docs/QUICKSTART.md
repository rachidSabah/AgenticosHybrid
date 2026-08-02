# Quickstart

Get AgenticOS running in under 5 minutes.

## Prerequisites

- **Python ≥ 3.12** — [install](https://www.python.org/downloads/)
- **Node.js ≥ 20** — [install](https://nodejs.org/)
- **uv** (Python package manager) — [install](https://docs.astral.sh/uv/getting-started/installation/)

## 1. Clone

```bash
git clone https://github.com/rachidSabah/AgenticosHybrid.git
cd AgenticosHybrid
```

## 2. Install Backend

```bash
uv sync
```

## 3. Install Frontend

```bash
cd apps/mission-control
npm install
cd ../..
```

## 4. Start the Backend

```bash
uv run python launch_backend.py serve --host 127.0.0.1 --port 8000
```

You should see:

```
[AgenticOS-Startup] LocalDiscovery: STARTED — N agents found
[AgenticOS-Startup] Executive: STARTED
[AgenticOS-Startup] Cognitive: STARTED
[AgenticOS-Startup] Swarm: STARTED
[AgenticOS-Startup] Ecosystem: STARTED
[AgenticOS-Startup] Cluster: STARTED
[AgenticOS-Startup] REST-API: LISTENING — http://127.0.0.1:8000
```

## 5. Start Mission Control

In a new terminal:

```bash
cd apps/mission-control
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000 npm run dev
```

Open <http://localhost:3000>.

## 6. Verify

```bash
curl http://127.0.0.1:8000/healthz
# → {"status":"ok","bus":"local",...}
```

## Next Steps

- Read the [Architecture](ARCHITECTURE.md) overview
- Explore the [REST API](README.md#api-guide)
- Browse the [ADR docs](docs/adr/)
- Check the [Roadmap](ROADMAP.md) for phase history

## Troubleshooting

See [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).
