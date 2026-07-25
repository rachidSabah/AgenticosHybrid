"""BrainCatalog — maps tool-types to brain classes and provides a
catalogue of known cloud AI vendors and their capabilities.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from agentic_os.domain.brains import BrainRecord, BrainRuntime, BrainStatus, BrainType, BrainVendor
from agentic_os.infrastructure.logging import get_logger

log = get_logger("brains.catalog")


@dataclass(frozen=True)
class VendorInfo:
    """Metadata about a cloud AI vendor in the catalog."""

    name: str
    vendor: BrainVendor
    default_runtime: BrainRuntime = BrainRuntime.CLOUD
    api_type: str = "cloud"
    base_url: str = ""
    known_models: tuple[str, ...] = field(default_factory=tuple)
    supported_capabilities: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ToolMapping:
    """Maps a tool_type string to a brain classification."""

    tool_type: str
    brain_type: BrainType
    default_vendor: BrainVendor
    default_runtime: BrainRuntime
    description: str = ""
    known_versions: tuple[str, ...] = field(default_factory=tuple)


# ── Built-in tool-type mappings ─────────────────────────────────────────────

_BUILTIN_TOOL_MAPPINGS: dict[str, ToolMapping] = {
    "claude-code": ToolMapping(
        tool_type="claude-code",
        brain_type=BrainType.LOCAL_CLI,
        default_vendor=BrainVendor.CLAUDE_CODE,
        default_runtime=BrainRuntime.NATIVE,
        description="Anthropic Claude Code CLI agent",
        known_versions=("0.x", "1.x"),
    ),
    "hermes": ToolMapping(
        tool_type="hermes",
        brain_type=BrainType.LOCAL_CLI,
        default_vendor=BrainVendor.HERMES,
        default_runtime=BrainRuntime.PYTHON,
        description="Hermes Agent (Nous Research)",
        known_versions=("0.x", "1.x"),
    ),
    "gemini-cli": ToolMapping(
        tool_type="gemini-cli",
        brain_type=BrainType.LOCAL_CLI,
        default_vendor=BrainVendor.GEMINI_CLI,
        default_runtime=BrainRuntime.NATIVE,
        description="Google Gemini CLI agent",
        known_versions=("1.x",),
    ),
    "codex": ToolMapping(
        tool_type="codex",
        brain_type=BrainType.LOCAL_CLI,
        default_vendor=BrainVendor.CODEX,
        default_runtime=BrainRuntime.NATIVE,
        description="OpenAI Codex CLI agent",
        known_versions=("0.x",),
    ),
    "opencode": ToolMapping(
        tool_type="opencode",
        brain_type=BrainType.LOCAL_CLI,
        default_vendor=BrainVendor.OPENCODE,
        default_runtime=BrainRuntime.NATIVE,
        description="OpenCode CLI agent",
        known_versions=("0.x",),
    ),
    "aider": ToolMapping(
        tool_type="aider",
        brain_type=BrainType.LOCAL_CLI,
        default_vendor=BrainVendor.AIDER,
        default_runtime=BrainRuntime.PYTHON,
        description="Aider AI pair programming CLI",
        known_versions=("0.x",),
    ),
    "continue": ToolMapping(
        tool_type="continue",
        brain_type=BrainType.LOCAL_CLI,
        default_vendor=BrainVendor.CONTINUE,
        default_runtime=BrainRuntime.NODE,
        description="Continue (open-source AI code assistant)",
        known_versions=("0.x", "1.x"),
    ),
}

# ── Cloud vendor catalog ────────────────────────────────────────────────────

_CLOUD_VENDOR_CATALOG: dict[BrainVendor, VendorInfo] = {
    BrainVendor.OPENAI: VendorInfo(
        name="OpenAI",
        vendor=BrainVendor.OPENAI,
        api_type="openai",
        base_url="https://api.openai.com/v1",
        known_models=("gpt-4o", "gpt-4o-mini", "o1", "o3"),
        supported_capabilities=(
            "chat",
            "completion",
            "embeddings",
            "vision",
            "function_calling",
            "streaming",
        ),
    ),
    BrainVendor.ANTHROPIC: VendorInfo(
        name="Anthropic",
        vendor=BrainVendor.ANTHROPIC,
        api_type="anthropic",
        base_url="https://api.anthropic.com/v1",
        known_models=("claude-sonnet-4", "claude-haiku-3.5"),
        supported_capabilities=(
            "chat",
            "vision",
            "tool_use",
            "streaming",
            "extended_thinking",
        ),
    ),
    BrainVendor.GOOGLE: VendorInfo(
        name="Google",
        vendor=BrainVendor.GOOGLE,
        api_type="google",
        base_url="https://generativelanguage.googleapis.com/v1",
        known_models=("gemini-2.0-flash", "gemini-2.0-pro"),
        supported_capabilities=(
            "chat",
            "vision",
            "tool_use",
            "streaming",
            "code_execution",
        ),
    ),
    BrainVendor.MISTRAL: VendorInfo(
        name="Mistral AI",
        vendor=BrainVendor.MISTRAL,
        api_type="openai",
        base_url="https://api.mistral.ai/v1",
        known_models=("mistral-large", "mistral-small", "codestral"),
        supported_capabilities=(
            "chat",
            "completion",
            "embeddings",
            "function_calling",
            "streaming",
        ),
    ),
    BrainVendor.GROQ: VendorInfo(
        name="Groq",
        vendor=BrainVendor.GROQ,
        api_type="openai",
        base_url="https://api.groq.com/openai/v1",
        known_models=("llama-3.3-70b", "mixtral-8x7b"),
        supported_capabilities=("chat", "streaming"),
    ),
    BrainVendor.AZURE: VendorInfo(
        name="Azure OpenAI",
        vendor=BrainVendor.AZURE,
        api_type="azure",
        base_url="https://<resource>.openai.azure.com",
        known_models=("gpt-4o", "gpt-4o-mini"),
        supported_capabilities=(
            "chat",
            "completion",
            "embeddings",
            "vision",
            "function_calling",
            "streaming",
        ),
    ),
    BrainVendor.AWS: VendorInfo(
        name="AWS Bedrock",
        vendor=BrainVendor.AWS,
        api_type="aws_bedrock",
        base_url="https://bedrock-runtime.<region>.amazonaws.com",
        known_models=("claude-sonnet-4", "llama-3"),
        supported_capabilities=("chat", "completion", "embeddings"),
    ),
    BrainVendor.VERTEX: VendorInfo(
        name="Vertex AI",
        vendor=BrainVendor.VERTEX,
        api_type="vertex",
        base_url="https://<region>-aiplatform.googleapis.com",
        known_models=("gemini-2.0-flash", "claude-sonnet-4"),
        supported_capabilities=(
            "chat",
            "vision",
            "streaming",
            "embeddings",
        ),
    ),
    BrainVendor.OPENROUTER: VendorInfo(
        name="OpenRouter",
        vendor=BrainVendor.OPENROUTER,
        api_type="openai",
        base_url="https://openrouter.ai/api/v1",
        known_models=(),
        supported_capabilities=("chat", "streaming", "function_calling"),
    ),
    BrainVendor.OLLAMA: VendorInfo(
        name="Ollama",
        vendor=BrainVendor.OLLAMA,
        default_runtime=BrainRuntime.NATIVE,
        api_type="openai",
        base_url="http://localhost:11434/v1",
        known_models=("llama-3", "mistral", "codellama"),
        supported_capabilities=("chat", "completion", "embeddings", "streaming"),
    ),
    BrainVendor.DEEPSEEK: VendorInfo(
        name="DeepSeek",
        vendor=BrainVendor.DEEPSEEK,
        api_type="openai",
        base_url="https://api.deepseek.com/v1",
        known_models=("deepseek-chat", "deepseek-reasoner"),
        supported_capabilities=("chat", "completion", "streaming", "reasoning"),
    ),
}

# ── Catalog class ───────────────────────────────────────────────────────────


class BrainCatalog:
    """Catalogue of known tool-type → brain mappings and cloud AI vendors.

    Provides lookup helpers for mapping tool identifier strings to their
    corresponding :class:`BrainType`, :class:`BrainVendor`, and
    :class:`BrainRuntime`.  Also exposes a cloud vendor catalogue with
    known models and capabilities.

    This class is stateless and thread-safe by design.
    """

    # ── Tool-type mappings ──────────────────────────────────────────────────

    def get_mapping(self, tool_type: str) -> ToolMapping | None:
        """Return the :class:`ToolMapping` for *tool_type*, or ``None``."""
        return _BUILTIN_TOOL_MAPPINGS.get(tool_type)

    def register_mapping(self, mapping: ToolMapping) -> None:
        """Add or replace a tool-type mapping at runtime.

        .. note::
            Mutates the shared ``_BUILTIN_TOOL_MAPPINGS`` dict.  This is
            a deliberate design choice for plugin registration; callers
            should treat it as an idempotent operation.
        """
        _BUILTIN_TOOL_MAPPINGS[mapping.tool_type] = mapping
        log.debug("Registered tool mapping: %s", mapping.tool_type)

    def list_mappings(self) -> list[ToolMapping]:
        """Return all known tool-type mappings."""
        return list(_BUILTIN_TOOL_MAPPINGS.values())

    def resolve(self, tool_type: str) -> tuple[BrainType, BrainVendor, BrainRuntime] | None:
        """Resolve a tool type to its brain classification tuple.

        Returns ``(brain_type, vendor, runtime)`` or ``None`` if the
        tool type is unknown.
        """
        mapping = self.get_mapping(tool_type)
        if mapping is None:
            return None
        return mapping.brain_type, mapping.default_vendor, mapping.default_runtime

    # ── Cloud vendor catalogue ──────────────────────────────────────────────

    def get_vendor(self, vendor: BrainVendor) -> VendorInfo | None:
        """Return the :class:`VendorInfo` for a given vendor enum."""
        return _CLOUD_VENDOR_CATALOG.get(vendor)

    def list_vendors(self) -> list[VendorInfo]:
        """Return all known cloud vendors with their metadata."""
        return list(_CLOUD_VENDOR_CATALOG.values())

    def list_vendor_names(self) -> list[str]:
        """Return the display names of all known cloud vendors."""
        return [v.name for v in _CLOUD_VENDOR_CATALOG.values()]

    def register_vendor(self, info: VendorInfo) -> None:
        """Add or replace a cloud vendor entry at runtime.

        Useful for plugin-registered or custom vendors.
        """
        _CLOUD_VENDOR_CATALOG[info.vendor] = info
        log.debug("Registered vendor: %s", info.name)

    # ── Utilities ───────────────────────────────────────────────────────────

    def get_supported_models(self, vendor: BrainVendor) -> tuple[str, ...]:
        """Return known models for a vendor, or an empty tuple."""
        info = self.get_vendor(vendor)
        return info.known_models if info else ()

    def get_supported_capabilities(self, vendor: BrainVendor) -> tuple[str, ...]:
        """Return known capabilities for a vendor, or an empty tuple."""
        info = self.get_vendor(vendor)
        return info.supported_capabilities if info else ()

    # ── Factory ─────────────────────────────────────────────────────────────

    def create_from_dict(self, data: dict[str, Any]) -> BrainRecord:
        """Create a :class:`BrainRecord` from a plain dictionary.

        Fields are populated with defaults for any missing key.
        """
        vendor_str = data.get("vendor", "custom")
        try:
            vendor = BrainVendor(vendor_str) if isinstance(vendor_str, str) else BrainVendor.CUSTOM
        except ValueError:
            vendor = BrainVendor.CUSTOM

        try:
            btype = BrainType(data.get("brain_type", "local_cli"))
        except ValueError:
            btype = BrainType.LOCAL_CLI

        try:
            runtime = BrainRuntime(data.get("runtime", "unknown"))
        except ValueError:
            runtime = BrainRuntime.UNKNOWN

        try:
            status = BrainStatus(data.get("status", "discovered"))
        except ValueError:
            status = BrainStatus.DISCOVERED

        caps = tuple(data.get("capabilities", data.get("supported_tools", ())))
        models = tuple(data.get("supported_models", ()))

        return BrainRecord(
            id=data.get("id", str(uuid4())),
            display_name=data.get("display_name", data.get("name", vendor.name.title())),
            brain_type=btype,
            vendor=vendor,
            runtime=runtime,
            version=data.get("version", ""),
            status=status,
            health=float(data.get("health", 1.0)),
            capabilities=caps,
            supported_models=models,
            memory_usage=float(data.get("memory_usage", 0)),
            cpu_usage=float(data.get("cpu_usage", 0)),
            latency=float(data.get("latency", 0)),
            throughput=float(data.get("throughput", 0)),
            workspace=data.get("workspace", ""),
            current_tasks=int(data.get("current_tasks", 0)),
            queue_depth=int(data.get("queue_depth", 0)),
            connection_state=data.get("connection_state", "disconnected"),
            uptime=float(data.get("uptime", 0)),
            tags=tuple(data.get("tags", ())),
            metadata=data.get("metadata", {}),
        )
