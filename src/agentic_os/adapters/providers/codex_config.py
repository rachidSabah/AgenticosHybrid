"""Render ~/.codex/config.toml from the active AgenticOS proxy profile.

Codex reads its own config file, so AgenticOS cannot inject a proxy at
invocation time — it must write the config. This module owns that file.

Verified against Codex v0.153.2:
* ``--full-auto`` does not exist; file writes require ``-s workspace-write``.
* Non-git directories require ``--skip-git-repo-check``.
* ``env_key`` must name a real env var, or Codex sends an empty bearer token.
"""

from __future__ import annotations

from pathlib import Path

from agentic_os.domain.proxy_profile import ProxyProfile

_BASE_TEMPLATE = """model = "{model}"
model_provider = "{name}"
{reasoning}
[model_providers.{name}]
name = "{name}"
base_url = "{base_url}"
wire_specification = "chat"
{env_key}
"""

# Keys Codex owns that we must never clobber: workspace trust and Windows
# sandbox settings are user-level, unrelated to proxy selection.
_PRESERVE_PREFIXES = ("[projects", "trust_level", "[windows", "sandbox", "[tui")


def render_codex_config(profile: ProxyProfile, reasoning_effort: str = "medium") -> str:
    """Render a complete config.toml for the given proxy."""
    env_key = f'env_key = "{profile.api_key_env}"' if profile.api_key_env else 'env_key = "USERPROFILE"'
    reasoning = f'model_reasoning_effort = "{reasoning_effort}"' if reasoning_effort else ""
    return _BASE_TEMPLATE.format(
        model=profile.model or "gpt-5.6-terra",
        name=profile.name,
        base_url=profile.base_url,
        env_key=env_key,
        reasoning=reasoning,
    )


def _preserved_lines(existing: str) -> list[str]:
    kept: list[str] = []
    for line in existing.splitlines():
        stripped = line.strip()
        if stripped.startswith(_PRESERVE_PREFIXES):
            kept.append(line)
    return kept


def write_codex_config(profile: ProxyProfile, path: str | None = None) -> Path:
    """Write the config for ``profile``, preserving trust/sandbox blocks.

    Returns the path written. Creates parent directories as needed.
    """
    target = Path(path) if path else Path.home() / ".codex" / "config.toml"
    target.parent.mkdir(parents=True, exist_ok=True)

    existing = ""
    if target.exists():
        try:
            existing = target.read_text(encoding="utf-8")
        except Exception:
            existing = ""

    preserved = _preserved_lines(existing)
    out = render_codex_config(profile)
    if preserved:
        out += "\n" + "\n".join(preserved) + "\n"

    target.write_text(out, encoding="utf-8")
    return target
