"""Manual proxy binding + full Nexus isolation (spec: no preconfigured proxies).

Covers:
* Isolation — no endpoint ships preconfigured; an empty/corrupt proxy store
  yields an EMPTY chain; no bearer is ever fabricated; fail-fast on active
  profile access.
* Manual binding API — bind / unbind / live-test / model discovery against a
  REAL local HTTP server (no mocks: the probe hits actual sockets).
* Honest failure — a closed port reports reachable=false with the transport
  error, never fabricated health.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from fastapi.testclient import TestClient

from agentic_os.domain import proxy_profile as pp
from agentic_os.domain.proxy_profile import (
    ProxyProfile,
    get_active_profile,
    get_proxy_chain,
)

# ── Isolation ────────────────────────────────────────────────────────────────


@pytest.fixture
def isolated_proxy_file(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTICOS_PROXY_FILE", str(tmp_path / "proxy.json"))
    yield tmp_path / "proxy.json"


def test_no_default_endpoint_is_hardcoded():
    """The proxy module must not contain any preconfigured host or port."""
    source = open(pp.__file__, encoding="utf-8").read()
    assert "8787" not in source, "hardcoded gateway port found in proxy module"
    assert "_NEXUS_DEFAULT" not in source, "nexus default profile resurrected"
    assert "127.0.0.1" not in source, "hardcoded host found in proxy module"


def test_missing_store_yields_empty_chain(isolated_proxy_file):
    chain = get_proxy_chain()
    assert chain.is_empty()


def test_corrupt_store_yields_empty_chain(isolated_proxy_file):
    isolated_proxy_file.write_text("{{{not json", encoding="utf-8")
    assert get_proxy_chain().is_empty()


def test_active_profile_fails_fast_when_nothing_bound(isolated_proxy_file):
    with pytest.raises(RuntimeError) as exc:
        get_active_profile()
    assert "no proxy profiles configured" in str(exc.value)
    assert "/api/proxy" in str(exc.value)  # remediation is named


def test_api_key_never_fabricated(isolated_proxy_file):
    assert ProxyProfile(name="x", base_url="https://x/v1").api_key() == ""


# ── Real HTTP test server (no mocks — actual sockets) ───────────────────────


class _ModelServerHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path.endswith("/models"):
            body = json.dumps(
                {
                    "object": "list",
                    "data": [
                        {"id": "test-model-a", "object": "model"},
                        {"id": "test-model-b", "object": "model"},
                    ],
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):  # silence per-request stderr
        pass


@pytest.fixture(scope="module")
def real_endpoint_server():
    server = HTTPServer(("127.0.0.1", 0), _ModelServerHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/v1"
    server.shutdown()


# ── Binding API ──────────────────────────────────────────────────────────────


@pytest.fixture
def client(isolated_proxy_file):
    from agentic_os.api.app import create_app
    from agentic_os.kernel import Kernel

    kernel = Kernel()
    platform = kernel.platform()
    app = create_app(platform)
    return TestClient(app)


class TestBindingLifecycle:
    def test_add_then_list(self, client, real_endpoint_server):
        r = client.post(
            "/api/proxy/profile/add",
            json={
                "name": "my-gateway",
                "base_url": real_endpoint_server,
                "api_key_env": "",
                "model": "",
                "wire": "chat",
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["added"] == "my-gateway"

        listed = client.get("/api/proxy/profile").json()["profiles"]
        assert [p["name"] for p in listed] == ["my-gateway"]
        assert listed[0]["base_url"] == real_endpoint_server

    def test_duplicate_name_rejected(self, client, real_endpoint_server):
        payload = {"name": "dup", "base_url": real_endpoint_server, "wire": "chat"}
        assert client.post("/api/proxy/profile/add", json=payload).status_code == 200
        r = client.post("/api/proxy/profile/add", json=payload)
        assert r.status_code == 409
        assert "already exists" in r.json()["detail"]

    @pytest.mark.parametrize(
        "payload,fragment",
        [
            ({"name": "", "base_url": "http://x/v1"}, "name is required"),
            ({"name": "no-scheme", "base_url": "ftp://x/v1"}, "http:// or https://"),
            ({"name": "bad-wire", "base_url": "http://x/v1", "wire": "grpc"}, "wire"),
            ({"base_url": "http://x/v1"}, "name is required"),
        ],
    )
    def test_validation_rejects_bad_payloads(self, client, payload, fragment):
        r = client.post("/api/proxy/profile/add", json=payload)
        assert r.status_code == 400
        assert fragment in r.json()["detail"]

    def test_delete_then_404(self, client, real_endpoint_server):
        assert (
            client.post(
                "/api/proxy/profile/add",
                json={"name": "gone", "base_url": real_endpoint_server},
            ).status_code
            == 200
        )
        assert client.delete("/api/proxy/profile/gone").json()["removed"] == "gone"
        assert client.get("/api/proxy/profile").json()["profiles"] == []
        r = client.delete("/api/proxy/profile/gone")
        assert r.status_code == 404
        assert "no binding named" in r.json()["detail"]


class TestLiveProbe:
    def test_test_connection_against_real_server(self, client, real_endpoint_server):
        r = client.post(
            "/api/proxy/test",
            json={"name": "probe-me", "base_url": real_endpoint_server, "wire": "chat"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["reachable"] is True
        assert data["status_code"] == 200
        assert isinstance(data["latency_ms"], (int, float))
        assert data["models_count"] == 2
        assert set(data["models_sample"]) == {"test-model-a", "test-model-b"}
        assert data["persisted"] is False
        # Nothing was persisted by a probe
        assert client.get("/api/proxy/profile").json()["profiles"] == []

    def test_test_connection_against_closed_port_is_honest(self, client):
        r = client.post(
            "/api/proxy/test",
            json={"name": "dead", "base_url": "http://127.0.0.1:1/v1", "wire": "chat"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["reachable"] is False
        assert data["status_code"] is None
        assert data["error"]  # the real transport error is surfaced
        assert data["models_count"] is None

    def test_models_endpoint_returns_real_catalog(self, client, real_endpoint_server):
        client.post(
            "/api/proxy/profile/add",
            json={"name": "catalog", "base_url": real_endpoint_server},
        )
        r = client.get("/api/proxy/models", params={"name": "catalog"})
        assert r.status_code == 200
        data = r.json()
        assert data["error"] is None
        assert data["models"] == ["test-model-a", "test-model-b"]

    def test_models_unknown_binding_404(self, client):
        r = client.get("/api/proxy/models", params={"name": "never-bound"})
        assert r.status_code == 404

    def test_health_empty_chain_honest(self, client):
        r = client.get("/api/proxy/health").json()
        assert r["reachable"] is False
        assert r["proxies"] == []
        assert r["active"] is None

    def test_health_dead_binding_honest(self, client):
        client.post(
            "/api/proxy/profile/add",
            json={"name": "dead", "base_url": "http://127.0.0.1:1/v1"},
        )
        r = client.get("/api/proxy/health").json()
        assert r["reachable"] is False
        assert r["proxies"][0]["reachable"] is False
        assert r["proxies"][0]["error"]
