# AgenticOS Python SDK

The AgenticOS SDK lives under `src/agentic_os/sdk/` and provides three sub-packages for building on top of AgenticOS programmatically:

- **`agentic_os.sdk.mcp`** — Model Context Protocol server creation and management
- **`agentic_os.sdk.learning`** — Learning & Optimization Engine client
- **`agentic_os.sdk.swarm`** — Multi-agent Swarm Orchestration client

All SDK classes are async-native and designed to work within the AgenticOS kernel (`Platform`). They require access to internal ports (e.g., `MCPRegistryPort`, `LearningManager`, `SwarmManagerPort`) obtained from the platform bundle.

---

## MCP SDK (`agentic_os.sdk.mcp`)

The MCP SDK provides a high-level developer interface for creating MCP servers, managing tools/resources/prompts, and integrating with the MCP runtime.

### Classes

#### `McpServerSdk`
The main entry point for creating and managing MCP servers programmatically.

```python
from agentic_os.sdk.mcp import McpServerSdk

# Create via factory methods
sdk = McpServerSdk.create_stdio(
    name="my-server",
    command="node",
    args=["server.js"],
    env={"NODE_ENV": "production"},
    description="My custom MCP server",
)

# Or create with SSE transport
sdk = McpServerSdk.create_sse(
    name="remote-server",
    url="https://example.com/mcp",
    headers={"Authorization": "Bearer token"},
)

# Or create with Streamable HTTP transport
sdk = McpServerSdk.create_streamable_http(
    name="http-server",
    url="https://example.com/mcp",
)
```

**Lifecycle methods:**

| Method | Description |
|--------|-------------|
| `initialize()` | Validate configuration and prepare for registration |
| `register(registry)` | Register with an `MCPRegistryPort` |
| `bind_registry(registry)` | Bind a registry without registering yet |
| `start()` | Start the MCP server process |
| `stop()` | Stop the MCP server process |
| `shutdown()` | Full shutdown: stop + unregister |

**Tool/Resource/Prompt management:**

```python
from agentic_os.domain.mcp import MCPTool, MCPResource, MCPPrompt

tool = MCPTool(name="my_tool", description="Does something", input_schema={})
await sdk.add_tool(tool)

resource = MCPResource(uri="file:///data", name="data", mime_type="application/json")
await sdk.add_resource(resource)

prompt = MCPPrompt(name="greeting", description="Say hello", arguments=[])
await sdk.add_prompt(prompt)
```

**Status queries:**

```python
status = sdk.status()      # MCPServerStatus enum
detail = sdk.detail()      # MCPServerDetail | None
config = sdk.config()      # MCPServerConfig | None
```

#### `ToolSdk` / `ToolBuilder`
Fluent builder for constructing `MCPTool` definitions.

```python
from agentic_os.sdk.mcp import ToolSdk

tool = ToolSdk("search").describe("Search the web").with_input_schema({
    "type": "object",
    "properties": {
        "query": {"type": "string"},
    },
}).build()
```

#### `ResourceSdk`
Builder for constructing `MCPResource` definitions.

```python
from agentic_os.sdk.mcp import ResourceSdk

resource = ResourceSdk("file:///logs/app.log").with_name("App Log").with_mime("text/plain").build()
```

#### `PromptSdk`
Builder for constructing `MCPPrompt` definitions.

```python
from agentic_os.sdk.mcp import PromptSdk

prompt = PromptSdk("summarize").with_description("Summarize text").with_arguments([
    {"name": "text", "type": "string", "required": True}
]).build()
```

#### `McpAuthHelper`
Authentication helper for MCP server connections.

```python
from agentic_os.sdk.mcp import McpAuthHelper

auth = McpAuthHelper(api_key="sk-...", bearer_token="...")
headers = auth.get_headers()
```

#### `McpConfigHelper`
Configuration convenience wrapper for MCP server settings.

```python
from agentic_os.sdk.mcp import McpConfigHelper

config_helper = McpConfigHelper(
    name="my-server",
    transport="stdio",
    command="python",
    args=["-m", "mcp_server"],
)
config = config_helper.build_config()
```

#### `RegistrationHelper`
Helper for batch registration of multiple MCP servers.

```python
from agentic_os.sdk.mcp import RegistrationHelper

helper = RegistrationHelper(registry)
await helper.register_all([sdk1, sdk2, sdk3])
await helper.unregister_all()
await helper.list_registered()
```

#### `McpValidator`
Input validation against the MCP protocol specification.

```python
from agentic_os.sdk.mcp import McpValidator

validator = McpValidator()
tool = MCPTool(name="test", description="...", input_schema={})
validator.validate_tool(tool)
```

#### `McpTestHelper`, `FakeMCPRegistry`, `FakeMCPManager`
Testing utilities for writing unit tests against the MCP runtime.

```python
from agentic_os.sdk.mcp import McpTestHelper, FakeMCPRegistry

helper = McpTestHelper()
fake_registry = FakeMCPRegistry()

# Create a fake server for testing
server = helper.create_fake_server(name="test-server")
detail = await fake_registry.register_server(
    MCPServerCreate(name="test-server", transport="stdio", command="echo")
)
```

### Creating MCP Servers

Full MCP server creation workflow:

```python
from agentic_os.sdk.mcp import McpServerSdk

async def setup_mcp_server(registry):
    # 1. Create and initialize
    sdk = McpServerSdk.create_stdio(
        name="data-analyzer",
        command="python",
        args=["-m", "data_analyzer_mcp"],
        tags=["data", "analysis"],
    )
    await sdk.initialize()

    # 2. Register with the runtime
    detail = await sdk.register(registry)

    # 3. Add tools, resources, prompts
    tool = ToolSdk("analyze").describe("Analyze a dataset").with_input_schema({
        "type": "object",
        "properties": {
            "file_path": {"type": "string"},
        },
        "required": ["file_path"],
    }).build()
    await sdk.add_tool(tool)

    # 4. Start the server
    await sdk.start()

    return sdk
```

### Registering Tools and Resources

Tools and resources added to an `McpServerSdk` are automatically published to the MCP runtime registry when the server starts. The registry exposes them via the discovery API:

```python
# Tools are discoverable via the MCP Manager
tools = await mcp_manager.get_server_tools(server_id)
resources = await mcp_manager.list_server_resources(server_id)
prompts = await mcp_manager.list_server_prompts(server_id)
```

### Authentication and Configuration

MCP SDK authentication is handled via `McpAuthHelper`:

```python
auth = McpAuthHelper(
    api_key="sk-...",
    bearer_token="eyJ...",
)
```

Server configuration (transport type, command, arguments, environment, URL, headers) is managed through `McpConfigHelper` or built directly using `MCPServerConfig` factory methods:

```python
from agentic_os.domain.mcp import MCPServerConfig

config = MCPServerConfig.create_stdio(
    name="my-server",
    command="node",
    args=["server.js"],
    env={"PORT": "3000"},
)
```

Supported transports:
- `stdio` — Subprocess-based, communicates over stdin/stdout
- `sse` — Server-Sent Events over HTTP
- `streamable_http` — Streamable HTTP transport

---

## Learning SDK (`agentic_os.sdk.learning`)

The Learning SDK provides programmatic access to the Learning & Optimization Engine.

### `LearningClient`

```python
from agentic_os.sdk.learning import LearningClient

client = LearningClient(manager)
```

### Recording Executions

```python
history = await client.record_execution(
    execution_id="exec-001",
    engine_type="generic",
    engine_name="engine-1",
    duration_ms=1520.0,
    status="completed",
    cost=0.0025,
    retry_count=0,
    error_type=None,
    model_used="gpt-4",         # passed as **metadata
    swarm_id="swarm-1",         # passed as **metadata
)
```

### Recommendations

```python
# Generate a recommendation
rec = await client.generate_recommendation(
    category="routing",
    current_policy="latency",
    failure_rate=0.15,
)

# List recommendations
recs = await client.get_recommendations(limit=20)
```

### Running Benchmarks

```python
benchmark = await client.run_benchmark(
    name="provider-latency-comparison",
    targets=["openai", "anthropic", "ollama"],
    iterations=10,
)
```

### Managing Experiments

```python
# Create an experiment
experiment = await client.create_experiment(
    name="routing-policy-a-b-test",
    experiment_type="a_b_test",
    control_config={"policy": "latency"},
    treatment_config={"policy": "cost"},
)

# Start and complete
await client.start_experiment(experiment.id)
await client.complete_experiment(experiment.id)
```

### Learning Metrics and Optimization

```python
# Get aggregated learning metrics
metrics = await client.get_learning_metrics()

# Optimize a target
result = await client.optimize(
    target="latency",
    max_iterations=100,
    tolerance=0.05,
)

# Evaluate a target
evaluation = await client.evaluate(
    target_id="engine-1",
    target_type="engine",
    accuracy=0.95,
    latency_ms=1200.0,
)
```

### Profiles and Policies

```python
# Create a learning profile
profile = await client.create_profile(
    name="production-optimization",
    targets=["latency", "cost"],
    metrics=["duration_ms", "cost"],
    telemetry_granularity="hourly",
)

# Create an optimization policy
policy = await client.create_policy(
    name="latency-threshold",
    target="latency",
    effect="deny",
    conditions={"max_latency_ms": 5000},
)
```

---

## Swarm SDK (`agentic_os.sdk.swarm`)

The Swarm SDK provides a high-level interface for multi-agent orchestration.

### `SwarmClient`

```python
from agentic_os.sdk.swarm import SwarmClient

client = SwarmClient(swarm_manager, task_orchestrator)
await client.initialize()
```

### Creating Swarms

```python
# Create a swarm
spec = await client.create_swarm(
    name="code-review-team",
    topology="hierarchical",  # mesh, star, hierarchical, ring, sequential
    tags=["code-review", "python"],
)

# List swarms
all_swarms = await client.list_swarms()

# Get a specific swarm
swarm = await client.get_swarm(swarm_id)

# Delete a swarm
await client.delete_swarm(swarm_id)
```

### Submitting Tasks

```python
# Create a goal
goal = await client.create_goal(
    description="Refactor the authentication module to use OAuth2",
    title="Auth Module Refactor",
    swarm_id=swarm_id,
)

# Decompose into a plan
plan = await client.decompose_goal(goal.id)

# Execute the plan
result = await client.execute_plan(plan.id)

# Or use the high-level run_goal shortcut
run_result = await client.run_goal(
    description="Refactor the authentication module",
    swarm_id=swarm_id,
)
# run_result.goal_id, run_result.plan, run_result.success
```

### `SwarmRunResult`

The `SwarmRunResult` dataclass wraps the output of `run_goal()`:

| Field | Type | Description |
|-------|------|-------------|
| `goal_id` | `str` | The created goal ID |
| `plan` | `OrchestrationPlan` | The execution plan with task statuses |
| `success` | `bool` | Whether all tasks completed successfully |

### Querying Plans

```python
plan = await client.get_plan(plan_id)
# Check task statuses from plan.subtasks
```

---

## Installation & Dependencies

The SDK is included with AgenticOS — no separate installation required. Optional dependencies:

```bash
# MCP Docker adapter
uv add "agentic-os[mcp-docker]"

# MCP PostgreSQL adapter
uv add "agentic-os[mcp-postgres]"

# All MCP adapters
uv add "agentic-os[mcp]"
```

All SDK modules are imported from `agentic_os.sdk.*`:

```python
from agentic_os.sdk.mcp import McpServerSdk, ToolSdk
from agentic_os.sdk.learning import LearningClient
from agentic_os.sdk.swarm import SwarmClient, SwarmRunResult
```
