"""Tests for the Autonomous OS API endpoints (Phases 1-10).

Covers: capability graph, mission lifecycle (10-state), intelligent
routing, collaboration, memory search, failure recovery, observability,
self-optimization, and security audit trail.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agentic_os.api.app import create_app
from agentic_os.kernel import Kernel


@pytest.fixture
async def client():
    """Create a test client backed by a real kernel."""
    kernel = Kernel()
    app = create_app(kernel.platform())
    with TestClient(app) as c:
        yield c


# ── Phase 1: Capability Graph ──


def test_capability_graph_returns_live_data(client):
    """GET /api/capabilities/graph returns live BrainRegistry data."""
    response = client.get("/api/capabilities/graph")
    assert response.status_code == 200
    data = response.json()
    assert "nodes" in data
    assert "edges" in data
    assert "index" in data
    assert "total" in data
    assert isinstance(data["nodes"], list)
    assert isinstance(data["edges"], list)
    assert isinstance(data["index"], dict)
    assert data["total"] == len(data["nodes"])


def test_capability_graph_node_fields(client):
    """Each capability graph node has all required fields."""
    response = client.get("/api/capabilities/graph")
    data = response.json()
    for node in data["nodes"]:
        assert "id" in node
        assert "name" in node
        assert "capabilities" in node
        assert "supported_tools" in node
        assert "supported_models" in node
        assert "health" in node
        assert "latency_ms" in node
        assert "status" in node
        assert "available" in node


# ── Phase 2: Intelligent Task Planner ──


def test_planner_decompose_requires_goal(client):
    """POST /api/planner/decompose requires a goal."""
    response = client.post("/api/planner/decompose", json={})
    assert response.status_code == 400


def test_planner_decompose_creates_mission(client):
    """POST /api/planner/decompose creates a mission + plan from a goal."""
    response = client.post("/api/planner/decompose", json={"goal": "Test the API"})
    assert response.status_code == 200
    data = response.json()
    assert "mission_id" in data
    assert "plan" in data
    assert "task_count" in data
    assert "estimated_total_minutes" in data


# ── Phase 3: Autonomous Routing ──


def test_routing_select_returns_best(client):
    """POST /api/routing/select returns the best runtime + alternatives."""
    response = client.post("/api/routing/select", json={"capability": "coding"})
    # May be 503 if no brains, or 200 with selection
    assert response.status_code in (200, 503, 504)
    if response.status_code == 200:
        data = response.json()
        assert "selected" in data
        assert "alternatives" in data
        assert "total_candidates" in data


# ── Phase 4: Multi-Agent Collaboration ──


def test_collaboration_delegate(client):
    """POST /api/collaboration/delegate publishes a delegation event."""
    response = client.post(
        "/api/collaboration/delegate",
        json={"from_agent": "a1", "to_agent": "a2", "task_id": "t1", "reason": "test"},
    )
    assert response.status_code == 200
    assert response.json()["delegated"] is True


def test_collaboration_delegate_requires_fields(client):
    """POST /api/collaboration/delegate validates required fields."""
    response = client.post("/api/collaboration/delegate", json={"from_agent": "a1"})
    assert response.status_code == 400


def test_collaboration_review(client):
    """POST /api/collaboration/review publishes a review event."""
    response = client.post(
        "/api/collaboration/review",
        json={"reviewer": "r1", "author": "a1", "verdict": "approve"},
    )
    assert response.status_code == 200
    assert response.json()["verdict"] == "approve"


def test_collaboration_vote(client):
    """POST /api/collaboration/vote records a vote."""
    response = client.post(
        "/api/collaboration/vote",
        json={"voter": "v1", "proposal_id": "p1", "vote": "yes"},
    )
    assert response.status_code == 200
    assert response.json()["vote_recorded"] is True


# ── Phase 5: Persistent Memory Search ──


def test_memory_search_empty_query(client):
    """GET /api/memory/search with empty query returns []."""
    response = client.get("/api/memory/search?q=")
    assert response.status_code == 200
    assert response.json() == []


def test_memory_search_returns_list(client):
    """GET /api/memory/search returns a list."""
    response = client.get("/api/memory/search?q=test")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_memory_history(client):
    """GET /api/memory/history/{key} returns a list."""
    response = client.get("/api/memory/history/test-key")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


# ── Phase 6: Failure Recovery ──


def test_recovery_retry_not_found(client):
    """POST /api/recovery/retry/{mission_id} 404s for unknown missions."""
    response = client.post("/api/recovery/retry/nonexistent")
    assert response.status_code == 404


def test_recovery_fallback_not_found(client):
    """POST /api/recovery/fallback/{mission_id} 404s for unknown missions."""
    response = client.post(
        "/api/recovery/fallback/nonexistent",
        json={"alternative_brain_id": "b1"},
    )
    assert response.status_code == 404


def test_recovery_checkpoints(client):
    """GET /api/recovery/checkpoints/{mission_id} returns a list."""
    response = client.get("/api/recovery/checkpoints/nonexistent")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


# ── Phase 7: Mission Execution Engine (10-state lifecycle) ──


def test_mission_lifecycle_states():
    """MissionStatus has all 10 required states."""
    from agentic_os.domain.mission import MissionStatus

    states = {s.value for s in MissionStatus}
    required = {
        "draft",
        "planning",
        "planned",
        "queued",
        "executing",
        "running",
        "waiting",
        "blocked",
        "retrying",
        "paused",
        "completed",
        "failed",
        "cancelled",
        "recovered",
    }
    assert required.issubset(states), f"Missing states: {required - states}"


def test_task_status_states():
    """TaskStatus has all required states."""
    from agentic_os.domain.mission import TaskStatus

    states = {s.value for s in TaskStatus}
    required = {
        "pending",
        "planned",
        "queued",
        "assigned",
        "running",
        "waiting",
        "blocked",
        "retrying",
        "completed",
        "failed",
        "skipped",
        "recovered",
    }
    assert required.issubset(states), f"Missing states: {required - states}"


# ── Phase 8: Live Observability ──


def test_obs_execution_graph(client):
    """GET /api/observability/execution-graph returns missions + tasks."""
    response = client.get("/api/observability/execution-graph")
    assert response.status_code == 200
    data = response.json()
    assert "missions" in data
    assert "total" in data


def test_obs_runtime_graph(client):
    """GET /api/observability/runtime-graph returns live runtimes."""
    response = client.get("/api/observability/runtime-graph")
    assert response.status_code == 200
    data = response.json()
    assert "runtimes" in data
    assert "total" in data


def test_obs_cost_graph(client):
    """GET /api/observability/cost-graph returns cost data."""
    response = client.get("/api/observability/cost-graph")
    assert response.status_code == 200
    assert "total_cost" in response.json()


def test_obs_failure_graph(client):
    """GET /api/observability/failure-graph returns failures."""
    response = client.get("/api/observability/failure-graph")
    assert response.status_code == 200
    assert "failures" in response.json()


# ── Phase 9: Self-Optimization ──


def test_opt_metrics(client):
    """GET /api/optimization/metrics returns live metrics."""
    response = client.get("/api/optimization/metrics")
    assert response.status_code == 200
    data = response.json()
    assert "success_rate" in data
    assert "failure_rate" in data
    assert "total_events" in data


def test_opt_feedback(client):
    """POST /api/optimization/feedback records feedback."""
    response = client.post(
        "/api/optimization/feedback",
        json={"brain_id": "b1", "success": True, "latency_ms": 100, "capability": "coding"},
    )
    assert response.status_code == 200
    assert response.json()["feedback_recorded"] is True


# ── Phase 10: Production Security ──


def test_security_audit_trail(client):
    """GET /api/security/audit-trail returns a list of security events."""
    response = client.get("/api/security/audit-trail")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_security_tool_permissions(client):
    """GET /api/security/tool-permissions returns permission config."""
    response = client.get("/api/security/tool-permissions")
    assert response.status_code == 200
    data = response.json()
    assert "permissions" in data
