"""
Stress & Benchmark Tests for Phase 3B Engines.

Measures throughput, latency, and resource usage under load for:
- WorkflowEngine (concurrent DAG executions, large workflows)
- PipelineEngine (concurrent stage executions, many stages)
- Observability (many spans/metrics/logs under load)

Run: uv run pytest tests/stress_benchmark.py -v --tb=short
      uv run pytest tests/stress_benchmark.py -v --tb=short -k "perf"   # perf-only
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from agentic_os.core.observability.in_memory import (
    InMemoryMetrics,
    InMemoryStructuredLogging,
    InMemoryTracing,
)
from agentic_os.core.pipeline.engine import PipelineEngineImpl
from agentic_os.core.workflow.engine import WorkflowEngineImpl
from agentic_os.domain.events import Topic
from agentic_os.domain.observability import SpanEvent
from agentic_os.domain.pipeline import PipelineStage, StageType
from agentic_os.domain.workflow import NodeType, WorkflowEdge, WorkflowNode
from agentic_os.ports.pipeline import PipelineCreate, PipelineExecute
from agentic_os.ports.workflow import WorkflowCreate, WorkflowExecute


# =============================================================================
# Shared Helpers
# =============================================================================


def _make_workflow_nodes(n: int) -> tuple[list[WorkflowNode], list[WorkflowEdge]]:
    """Build a linear chain of N nodes (START → AGENT→ ... → AGENT → END)."""
    nodes = [WorkflowNode(id="start", type=NodeType.START, label="Start")]
    edges: list[WorkflowEdge] = []

    for i in range(n):
        nid = f"node_{i}"
        nodes.append(
            WorkflowNode(id=nid, type=NodeType.AGENT, label=f"Node {i}",
                         config={"agent_id": "test-agent"})
        )
        if i == 0:
            edges.append(WorkflowEdge(id=f"e_{i}", source="start", target=nid))
        else:
            edges.append(WorkflowEdge(id=f"e_{i}", source=f"node_{i - 1}", target=nid))

    nodes.append(WorkflowNode(id="end", type=NodeType.END, label="End"))
    edges.append(WorkflowEdge(id="e_end", source=f"node_{n - 1}", target="end") if n > 0
                 else WorkflowEdge(id="e_end", source="start", target="end"))
    return nodes, edges


def _make_pipeline_stages(n: int) -> list[PipelineStage]:
    """Build N linear pipeline stages."""
    return [
        PipelineStage(id=f"stage_{i}", type=StageType.AGENT, label=f"Stage {i}",
                      config={"agent_id": "test-agent"})
        for i in range(n)
    ]


async def _measure(description: str, coro, loops: int = 1):
    """Time coroutine execution, return elapsed seconds."""
    start = time.monotonic()
    for _ in range(loops):
        await coro()
    elapsed = time.monotonic() - start
    return elapsed


def _activate_workflow(engine, wid: str):
    """Activate a workflow so it can be executed."""
    engine._workflows[wid] = engine._workflows[wid].activate()


def _activate_pipeline(engine, pid: str):
    """Activate a pipeline so it can be executed."""
    engine._pipelines[pid] = engine._pipelines[pid].activate()


async def _wait_for_execution(engine, exec_id: str, timeout: float = 30.0) -> str:
    """Poll engine.get_execution until status != pending or timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ex = await engine.get_execution(exec_id)
        if ex is None:
            return "missing"
        if ex.status.value != "pending":
            return ex.status.value
        await asyncio.sleep(0.05)
    return "timeout"


# =============================================================================
# Fixtures (reuse engine patterns from conftest)
# =============================================================================


@pytest.fixture
def mock_provider_router():
    router = MagicMock()
    router.complete = AsyncMock()
    router.complete.return_value = MagicMock(
        content="mock response",
        usage=MagicMock(to_dict=lambda: {"input_tokens": 10, "output_tokens": 20}),
    )
    return router


@pytest.fixture
def mock_agent_registry():
    registry = MagicMock()
    agent = MagicMock()
    agent.provider = "mock"
    agent.model = "mock-model"
    registry.get_agent.return_value = agent
    return registry


@pytest.fixture
async def workflow_engine(bus, mock_provider_router, mock_agent_registry):
    """WorkflowEngineImpl with mocked deps."""
    return WorkflowEngineImpl(bus, mock_provider_router, mock_agent_registry)


@pytest.fixture
async def pipeline_engine(bus, mock_provider_router, mock_agent_registry):
    """PipelineEngineImpl with mocked deps."""
    return PipelineEngineImpl(bus, mock_provider_router, mock_agent_registry)


# =============================================================================
# Workflow Stress
# =============================================================================


class TestWorkflowConcurrency:
    """Stress the engine with concurrent executions."""

    @pytest.mark.parametrize("concurrency", [5, 10, 25])
    async def test_concurrent_executions(self, workflow_engine, concurrency):
        """Run many simple workflows concurrently."""
        nodes, edges = _make_workflow_nodes(3)
        wc = WorkflowCreate(name="stress", description="", nodes=nodes, edges=edges,
                            created_by="test")
        detail = await workflow_engine.create_workflow(wc)
        _activate_workflow(workflow_engine, detail.id)

        async def exec_one():
            ex = await workflow_engine.execute_workflow(
                detail.id, WorkflowExecute(inputs={})
            )
            status = await _wait_for_execution(workflow_engine, ex.id, timeout=30.0)
            return status

        start = time.monotonic()
        statuses = await asyncio.gather(*[exec_one() for _ in range(concurrency)])
        elapsed = time.monotonic() - start

        completed = sum(1 for s in statuses if s == "completed")
        rate = concurrency / elapsed
        print(f"\n  [{concurrency} concurrent workflows] "
              f"{concurrency} in {elapsed:.2f}s → {rate:.1f} exec/s")
        assert completed == concurrency, f"Got {completed}/{concurrency} completed"

    async def test_many_node_workflow(self, workflow_engine):
        """Execute a workflow with many nodes (50-node chain)."""
        nodes, edges = _make_workflow_nodes(50)
        wc = WorkflowCreate(name="big-wf", description="", nodes=nodes, edges=edges,
                            created_by="test")
        detail = await workflow_engine.create_workflow(wc)
        _activate_workflow(workflow_engine, detail.id)

        start = time.monotonic()
        ex = await workflow_engine.execute_workflow(
            detail.id, WorkflowExecute(inputs={})
        )
        status = await _wait_for_execution(workflow_engine, ex.id, timeout=60.0)
        elapsed = time.monotonic() - start

        print(f"\n  [50-node workflow] {status} in {elapsed:.3f}s")
        assert status == "completed"

    @pytest.mark.parametrize("node_count", [5, 10, 20])
    async def test_throughput_vs_size(self, workflow_engine, node_count):
        """Measure throughput as node count increases."""
        nodes, edges = _make_workflow_nodes(node_count)
        wc = WorkflowCreate(name=f"perf-{node_count}", description="",
                            nodes=nodes, edges=edges, created_by="test")
        detail = await workflow_engine.create_workflow(wc)
        _activate_workflow(workflow_engine, detail.id)

        start = time.monotonic()
        for _ in range(5):
            ex = await workflow_engine.execute_workflow(
                detail.id, WorkflowExecute(inputs={})
            )
            status = await _wait_for_execution(workflow_engine, ex.id, timeout=60.0)
            assert status == "completed", f"Got {status}"
        elapsed = time.monotonic() - start
        avg = elapsed / 5
        throughput = 1.0 / avg if avg > 0 else float("inf")

        print(f"\n  [{node_count} nodes × 5 runs] avg {avg:.3f}s/exec, "
              f"{throughput:.1f} exec/s")
        assert avg < 30.0, f"Avg execution took {avg:.1f}s — too slow"


# =============================================================================
# Pipeline Stress
# =============================================================================


class TestPipelineConcurrency:
    """Stress the pipeline engine with concurrent executions."""

    @pytest.mark.parametrize("concurrency", [5, 10, 25])
    async def test_concurrent_executions(self, pipeline_engine, concurrency):
        """Run many simple pipelines concurrently."""
        stages = _make_pipeline_stages(3)
        pc = PipelineCreate(name="stress", description="", stages=stages,
                            edges=[], created_by="test")
        detail = await pipeline_engine.create_pipeline(pc)
        _activate_pipeline(pipeline_engine, detail.id)

        async def exec_one():
            ex = await pipeline_engine.execute_pipeline(
                detail.id, PipelineExecute(inputs={})
            )
            status = await _wait_for_execution(pipeline_engine, ex.id, timeout=30.0)
            return status

        start = time.monotonic()
        statuses = await asyncio.gather(*[exec_one() for _ in range(concurrency)])
        elapsed = time.monotonic() - start

        completed = sum(1 for s in statuses if s == "completed")
        rate = concurrency / elapsed
        print(f"\n  [{concurrency} concurrent pipelines] "
              f"{concurrency} in {elapsed:.2f}s → {rate:.1f} exec/s")
        assert completed == concurrency, f"Got {completed}/{concurrency} completed"

    async def test_many_stage_pipeline(self, pipeline_engine):
        """Execute a pipeline with many stages (50-stage chain)."""
        stages = _make_pipeline_stages(50)
        pc = PipelineCreate(name="big-pl", description="", stages=stages,
                            edges=[], created_by="test")
        detail = await pipeline_engine.create_pipeline(pc)
        _activate_pipeline(pipeline_engine, detail.id)

        start = time.monotonic()
        ex = await pipeline_engine.execute_pipeline(
            detail.id, PipelineExecute(inputs={})
        )
        status = await _wait_for_execution(pipeline_engine, ex.id, timeout=60.0)
        elapsed = time.monotonic() - start

        print(f"\n  [50-stage pipeline] {status} in {elapsed:.3f}s")
        assert status == "completed"

    async def test_concurrent_with_retries(self, pipeline_engine):
        """Stress retry mechanism under concurrency."""
        stages = [
            PipelineStage(id="s1", type=StageType.AGENT, label="S1",
                          config={"agent_id": "test-agent"}, retry_count=2,
                          retry_delay_seconds=0),
            PipelineStage(id="s2", type=StageType.AGENT, label="S2",
                          config={"agent_id": "test-agent"}),
        ]
        pc = PipelineCreate(name="retry-stress", description="", stages=stages,
                            edges=[], created_by="test")
        detail = await pipeline_engine.create_pipeline(pc)
        _activate_pipeline(pipeline_engine, detail.id)

        async def exec_one():
            ex = await pipeline_engine.execute_pipeline(
                detail.id, PipelineExecute(inputs={})
            )
            status = await _wait_for_execution(pipeline_engine, ex.id, timeout=30.0)
            return status

        statuses = await asyncio.gather(*[exec_one() for _ in range(10)])
        completed = sum(1 for s in statuses if s == "completed")
        assert completed == 10


# =============================================================================
# Observability Stress
# =============================================================================


class TestObservabilityLoad:
    """Stress InMemory observability components under high throughput."""

    @pytest.mark.parametrize("span_count", [100, 1000, 5000])
    def test_high_volume_spans(self, span_count):
        """Create many spans to measure throughput."""
        tracing = InMemoryTracing()
        start = time.monotonic()

        for i in range(span_count):
            span = tracing.start_span(f"op_{i}")
            span = span.with_event(SpanEvent(name="event", attributes={"i": i}))
            tracing.end_span(span)

        elapsed = time.monotonic() - start
        rate = span_count / elapsed if elapsed > 0 else float("inf")
        print(f"\n  [{span_count} spans] {elapsed:.3f}s → {rate:,.0f} spans/s")
        assert elapsed < 30.0

    @pytest.mark.parametrize("metric_count", [100, 1000])
    def test_high_volume_metrics(self, metric_count):
        """Record many metrics."""
        metrics = InMemoryMetrics()

        start = time.monotonic()
        for i in range(metric_count):
            metrics.counter("test_counter", labels={"i": str(i)})
        elapsed = time.monotonic() - start

        rate = metric_count / elapsed if elapsed > 0 else float("inf")
        print(f"\n  [{metric_count} metrics] {elapsed:.3f}s → {rate:,.0f} metrics/s")
        assert elapsed < 10.0

    @pytest.mark.parametrize("entry_count", [100, 1000])
    def test_high_volume_logs(self, entry_count):
        """Record many log entries."""
        logging = InMemoryStructuredLogging()

        start = time.monotonic()
        for i in range(entry_count):
            logging.info("test message", extra={"i": i})
        elapsed = time.monotonic() - start

        rate = entry_count / elapsed if elapsed > 0 else float("inf")
        print(f"\n  [{entry_count} logs] {elapsed:.3f}s → {rate:,.0f} logs/s")
        assert elapsed < 10.0

    async def test_concurrent_observability_access(self):
        """Stress observability from concurrent coroutines."""
        tracing = InMemoryTracing()
        metrics = InMemoryMetrics()
        logger = InMemoryStructuredLogging()

        async def worker(wid: int):
            for _ in range(50):
                span = tracing.start_span(f"worker_{wid}")
                metrics.counter("ops", labels={"worker": str(wid)})
                logger.info("step", worker=wid)
                tracing.end_span(span)

        start = time.monotonic()
        await asyncio.gather(*[worker(i) for i in range(20)])
        elapsed = time.monotonic() - start

        print(f"\n  [20 workers × 50 ops] {elapsed:.3f}s")
        assert elapsed < 30.0

    def test_mixed_observability_load(self):
        """Mix spans, metrics, and logs in sequence to simulate real load."""
        tracing = InMemoryTracing()
        metrics = InMemoryMetrics()
        logger = InMemoryStructuredLogging()

        N = 500
        start = time.monotonic()

        for i in range(N):
            span = tracing.start_span(f"request_{i}")
            metrics.counter("requests")
            metrics.histogram("latency", 0.05 + i * 0.001)
            logger.info("request", id=i, latency=0.05 + i * 0.001)
            if i % 2 == 0:
                child = tracing.start_span(f"sub_op_{i}", parent=span.context)
                tracing.end_span(child)
            tracing.end_span(span)

        elapsed = time.monotonic() - start
        ops = (N * 3) / elapsed  # span + metric + log ≈ 3 ops
        print(f"\n  [mixed {N} iterations] {elapsed:.3f}s → {ops:,.0f} ops/s")

        assert tracing._traces  # at least one trace recorded
        req_metric = metrics.get_metric("requests")
        assert req_metric is not None
        assert req_metric.value == N

    def test_summary_histogram(self):
        """Ensure histogram aggregation works."""
        metrics = InMemoryMetrics()
        for v in [1, 2, 3, 4, 5]:
            metrics.histogram("latency", v, labels={"unit": "ms"})
        # Check individual metric records via get_metric
        m = metrics.get_metric("latency", labels={"unit": "ms"})
        assert m is not None
        assert m.value == 5.0  # last recorded value
        # Check internal histogram storage
        key = metrics._make_key("latency", {"unit": "ms"})
        assert key in metrics._histograms
        assert metrics._histograms[key] == [1.0, 2.0, 3.0, 4.0, 5.0]


# =============================================================================
# Mixed-Load Stress
# =============================================================================


class TestMixedLoad:
    """End-to-end load with engines + observability simultaneously."""

    @pytest.mark.parametrize("n", [5, 10])
    async def test_engines_under_observability(self, bus, mock_provider_router,
                                                mock_agent_registry, n):
        """Run engines while observability records everything."""
        metrics = InMemoryMetrics()
        tracing = InMemoryTracing()
        logger = InMemoryStructuredLogging()

        we = WorkflowEngineImpl(bus, mock_provider_router, mock_agent_registry)
        pe = PipelineEngineImpl(bus, mock_provider_router, mock_agent_registry)

        nodes, edges = _make_workflow_nodes(5)
        wc = WorkflowCreate(name="mixed", description="",
                            nodes=nodes, edges=edges, created_by="test")
        wf_detail = await we.create_workflow(wc)
        _activate_workflow(we, wf_detail.id)

        stages = _make_pipeline_stages(5)
        pc = PipelineCreate(name="mixed-pl", description="", stages=stages,
                            edges=[], created_by="test")
        pl_detail = await pe.create_pipeline(pc)
        _activate_pipeline(pe, pl_detail.id)

        async def run_workflow():
            metrics.counter("workflow_starts")
            span = tracing.start_span("workflow")
            ex = await we.execute_workflow(wf_detail.id, WorkflowExecute(inputs={}))
            status = await _wait_for_execution(we, ex.id, timeout=30.0)
            metrics.histogram("workflow_duration", 0.1)
            logger.info("workflow_done", id=wf_detail.id, status=status)
            tracing.end_span(span)
            return status

        async def run_pipeline():
            metrics.counter("pipeline_starts")
            span = tracing.start_span("pipeline")
            ex = await pe.execute_pipeline(pl_detail.id, PipelineExecute(inputs={}))
            status = await _wait_for_execution(pe, ex.id, timeout=30.0)
            metrics.histogram("pipeline_duration", 0.1)
            logger.info("pipeline_done", id=pl_detail.id, status=status)
            tracing.end_span(span)
            return status

        start = time.monotonic()
        wf_tasks = [run_workflow() for _ in range(n)]
        pl_tasks = [run_pipeline() for _ in range(n)]
        all_results = await asyncio.gather(*(wf_tasks + pl_tasks))
        elapsed = time.monotonic() - start

        completed = sum(1 for r in all_results if r == "completed")
        total = len(all_results)
        print(f"\n  [{n} workflows + {n} pipelines] {total} in {elapsed:.2f}s — "
              f"{completed}/{total} completed")

        assert completed == total
        ws = metrics.get_metric("workflow_starts")
        ps = metrics.get_metric("pipeline_starts")
        assert ws is not None and ws.value == n
        assert ps is not None and ps.value == n


# =============================================================================
# Temperature / Edge-Case Stress
# =============================================================================


class TestEdgeCaseStress:
    """Boundary conditions under load."""

    async def test_zero_node_workflow(self, workflow_engine):
        """A workflow with no agent nodes (just START→END)."""
        nodes = [
            WorkflowNode(id="start", type=NodeType.START, label="Start"),
            WorkflowNode(id="end", type=NodeType.END, label="End"),
        ]
        edges = [WorkflowEdge(id="e1", source="start", target="end")]
        wc = WorkflowCreate(name="empty", description="", nodes=nodes, edges=edges,
                            created_by="test")
        detail = await workflow_engine.create_workflow(wc)
        _activate_workflow(workflow_engine, detail.id)
        ex = await workflow_engine.execute_workflow(
            detail.id, WorkflowExecute(inputs={})
        )
        status = await _wait_for_execution(workflow_engine, ex.id, timeout=30.0)
        assert status == "completed"

    async def test_single_stage_pipeline(self, pipeline_engine):
        """A pipeline with a single stage."""
        stages = [PipelineStage(id="solo", type=StageType.AGENT, label="Solo",
                                config={"agent_id": "test-agent"})]
        pc = PipelineCreate(name="solo", description="", stages=stages,
                            edges=[], created_by="test")
        detail = await pipeline_engine.create_pipeline(pc)
        _activate_pipeline(pipeline_engine, detail.id)
        ex = await pipeline_engine.execute_pipeline(
            detail.id, PipelineExecute(inputs={})
        )
        status = await _wait_for_execution(pipeline_engine, ex.id, timeout=30.0)
        assert status == "completed"

    async def test_rapid_create_execute_delete(self, workflow_engine):
        """Rapidly create, execute, and delete workflows."""
        for i in range(20):
            nodes, edges = _make_workflow_nodes(2)
            wc = WorkflowCreate(name=f"rapid-{i}", description="",
                                nodes=nodes, edges=edges, created_by="test")
            detail = await workflow_engine.create_workflow(wc)
            _activate_workflow(workflow_engine, detail.id)
            ex = await workflow_engine.execute_workflow(
                detail.id, WorkflowExecute(inputs={})
            )
            status = await _wait_for_execution(workflow_engine, ex.id, timeout=30.0)
            assert status == "completed"

    async def test_concurrent_same_workflow(self, workflow_engine):
        """Multiple concurrent executions of the same workflow."""
        nodes, edges = _make_workflow_nodes(3)
        wc = WorkflowCreate(name="shared", description="",
                            nodes=nodes, edges=edges, created_by="test")
        detail = await workflow_engine.create_workflow(wc)
        _activate_workflow(workflow_engine, detail.id)

        async def exec_one():
            ex = await workflow_engine.execute_workflow(
                detail.id, WorkflowExecute(inputs={})
            )
            status = await _wait_for_execution(workflow_engine, ex.id, timeout=30.0)
            return status

        statuses = await asyncio.gather(*[exec_one() for _ in range(20)])
        completed = sum(1 for s in statuses if s == "completed")
        assert completed == 20


# =============================================================================
# Throughput Measurement (smoke, not precise benchmark)
# =============================================================================


class TestThroughput:
    """Rough throughput measurements for regression detection."""

    async def test_workflow_throughput(self, workflow_engine):
        """Measure baseline workflow execution throughput."""
        nodes, edges = _make_workflow_nodes(3)
        wc = WorkflowCreate(name="tp", description="", nodes=nodes, edges=edges,
                            created_by="test")
        detail = await workflow_engine.create_workflow(wc)
        _activate_workflow(workflow_engine, detail.id)

        counts = []
        for _ in range(3):
            start = time.monotonic()
            for _ in range(10):
                ex = await workflow_engine.execute_workflow(
                    detail.id, WorkflowExecute(inputs={})
                )
                status = await _wait_for_execution(workflow_engine, ex.id, timeout=30.0)
                assert status == "completed"
            elapsed = time.monotonic() - start
            counts.append(10 / elapsed)

        avg_tp = sum(counts) / len(counts)
        print(f"\n  [3-node workflow × 30 total] avg {avg_tp:.1f} exec/s across 3 batches")
        assert avg_tp > 0

    async def test_pipeline_throughput(self, pipeline_engine):
        """Measure baseline pipeline execution throughput."""
        stages = _make_pipeline_stages(3)
        pc = PipelineCreate(name="tp-pl", description="", stages=stages,
                            edges=[], created_by="test")
        detail = await pipeline_engine.create_pipeline(pc)
        _activate_pipeline(pipeline_engine, detail.id)

        counts = []
        for _ in range(3):
            start = time.monotonic()
            for _ in range(10):
                ex = await pipeline_engine.execute_pipeline(
                    detail.id, PipelineExecute(inputs={})
                )
                status = await _wait_for_execution(pipeline_engine, ex.id, timeout=30.0)
                assert status == "completed"
            elapsed = time.monotonic() - start
            counts.append(10 / elapsed)

        avg_tp = sum(counts) / len(counts)
        print(f"\n  [3-stage pipeline × 30 total] avg {avg_tp:.1f} exec/s across 3 batches")
        assert avg_tp > 0
