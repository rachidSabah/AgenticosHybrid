# API Documentation

The REST + WebSocket control plane is implemented in `src/agentic_os/api/app.py`.

## Endpoints (Phase 2)

- Health/metrics: `GET /healthz`, `GET /metrics`
- Tasks/agents: `GET/POST /api/tasks`, `GET /api/agents`
- Provider Management: `/api/providers`, `/api/provider-configs`,
  `/api/provider-health`, `/api/cost`, `/api/rate-limits`, `/api/routing/policy`,
  `/api/models`, `/api/providers/{name}/test`, `/api/providers/{name}/benchmark`,
  `/api/providers/{name}/api-key`
- Capability: `/api/capabilities`, `/api/agents/compose`,
  `/api/agents/compose-for-task`
- Memory: `/api/memory`, `/api/memory/{scope}`, `/api/memory/{scope}/recall`,
  `/api/memory/{item_id}`, `/api/memory/retention`
- Security: `/api/security/authorize`, `/api/security/assign`,
  `/api/security/approval/{id}`, `/api/security/audit`,
  `/api/security/workspace/{agent_id}`
- Dashboard: `GET /providers` (minimal UI), `WS /ws/dashboard`

OpenAPI/Swagger docs are served by FastAPI at `/docs` and `/redoc` when the app
runs. Generated API reference will be added here in Phase 3.
