# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.0.x (RC) | ✅ |
| 0.x | ❌ |

## Security Architecture Overview

AgenticOS is built on a defense-in-depth, least-privilege security model. Every layer of the hexagonal architecture enforces security boundaries:

```
User / CLI / Mission Control
        │
┌───────┴──────────────────────────────────┐
│  API Gateway (FastAPI)                   │
│  - CORS enforcement                     │
│  - API key validation                   │
│  - Bearer token authentication          │
│  - Rate limiting                        │
└───────┬──────────────────────────────────┘
        │
┌───────┴──────────────────────────────────┐
│  Security Framework (core/security/)     │
│  - RBAC (deny-by-default)               │
│  - Capability→permission mapping        │
│  - Human approval gate                  │
│  - Append-only audit log                │
│  - Workspace isolation                  │
└───────┬──────────────────────────────────┘
        │
┌───────┴──────────────────────────────────┐
│  Vault (encrypted secret storage)        │
│  - AES-256-GCM encryption               │
│  - Fernet master key                    │
│  - Provider API key management          │
└─────────────────────────────────────────┘
```

All authorization decisions pass through three gates:
1. **Authentication** — Who is the principal? (API key, bearer token)
2. **Authorization** — Does the principal's role permit the capability?
3. **Approval** — Does the capability require explicit human consent?

## Credential Storage (Encrypted Vault)

Provider API keys, tokens, and other secrets are stored in an encrypted vault backed by Fernet symmetric encryption. The master encryption key is supplied via:

- `AGENTIC_OS_MASTER_KEY` environment variable
- A key file at `~/.agentic_os/master.key`

The vault exposes two operations:

```python
await vault.store_key(name, api_key)   # encrypt and persist
await vault.get_key(name)              # retrieve and decrypt
```

Keys are never logged, never exposed in API responses (except `status` which returns existence only), and are zeroed from memory after use.

## Secret Encryption (AES-256-GCM)

All secrets at rest are encrypted using **AES-256-GCM** via the `cryptography` library:

- **Algorithm**: AES-256 in GCM (Galois/Counter Mode)
- **Key derivation**: PBKDF2-HMAC-SHA256 with 600,000 iterations
- **Nonce**: 12-byte random nonce per encryption operation
- **Authentication tag**: 16-byte GCM tag provides integrity verification
- **Storage format**: Fernet-compatible tokens (version || timestamp || IV || ciphertext || HMAC)

The master key is never stored alongside the encrypted payloads. Vault data is stored in `~/.agentic_os/vault/` with file permissions restricted to the owning user (0600).

## Workspace Isolation (Sandboxed Workspaces)

Every agent executes within a dedicated workspace root. The Security Framework enforces:

- **Path sandboxing**: All `..` traversal attempts are neutralized. File system operations are constrained to the agent's workspace directory.
- **Capability gating**: Workspace-scoped operations require matching `workspace_id` in the authorization request.
- **Workspace CRUD**: Workspaces are created, listed, and deleted through the Security Framework API (`/api/security/workspace/{agent_id}`).
- **Cross-workspace isolation**: No agent can read or modify files in another agent's workspace without explicit `admin` role authorization.

```python
request = ToolRequest(
    principal=principal,
    capability="tool.filesystem",
    workspace=workspace_id,  # enforced isolation
    requires_approval=True,
)
```

## Plugin Permissions (Capability-Based Security Model)

AgenticOS uses a **capability-based** security model for plugins, not coarse role-based permissions. Each plugin declares the capabilities it requires in its manifest:

```json
{
  "capabilities": ["tool.filesystem", "memory.read"],
  "requires_approval": ["tool.filesystem"]
}
```

The capability engine (`core/capability/`) maps capabilities to permissions at runtime:

| Plugin Capability | Required Permission | Requires Approval |
|------------------|---------------------|-------------------|
| `tool.terminal` | `tool.terminal` | Yes |
| `tool.git` | `tool.git` | Yes |
| `tool.docker` | `tool.docker` | Yes |
| `tool.filesystem` | `tool.filesystem` | Yes |
| `tool.browser` | `tool.browser` | Yes |
| `memory.read` | `memory.read` | No |
| `memory.write` | `memory.write` | No |
| `provider.manage` | `provider.manage` | Yes |
| `agent.compose` | `agent.compose` | No |
| `security.audit` | `security.audit` | No |

Capabilities flagged `requires_approval` cannot execute without an explicit human decision via the approval gate.

## Provider Permissions (API Key Management, Scope-Limited Access)

Provider configurations are managed through the Provider Management API. API keys are stored in the encrypted vault and never returned in API responses:

- **Store**: `POST /api/providers/{name}/api-key` — encrypts and stores the key
- **Status**: `GET /api/providers/{name}/api-key/status` — returns only existence (boolean)
- **Scope**: Each provider configuration can be scoped to specific models, agents, or capabilities at the routing layer

The routing policy (`latency`, `cost`, `round_robin`) determines how provider access is distributed, but all provider calls are subject to the same RBAC authorization as any other capability.

## Audit Logging

Every security-relevant event is recorded in an **append-only audit trail**. Audit entries include:

| Field | Description |
|-------|-------------|
| `id` | Unique entry identifier (hex uuid) |
| `timestamp` | UTC timestamp of the event |
| `principal` | The actor (user or agent ID) |
| `action` | e.g. `tool.denied`, `approval.granted`, `role.assigned` |
| `target` | The resource or capability targeted |
| `outcome` | `allow`, `deny`, `approved`, `rejected` |
| `meta` | Arbitrary structured metadata |

The audit log is queryable via `GET /api/security/audit` (requires `security.audit` permission). Entries are immutable once written.

## Certificate Validation (TLS, Code Signing)

### TLS Certificate Validation
- All outbound HTTPS connections use the system certificate store
- Custom CA certificates can be configured per-provider
- Certificate hostname verification is enforced
- Self-signed certificates are rejected by default

### Code Signing
- Installers are signed during generation (configurable in `InstallerConfig.sign`)
- Code signing certificates are validated against the configured trust store
- Timestamp servers are supported for long-lived signature validity
- Package integrity uses SHA-256 checksums

## Update Verification (SHA256 Checksums, Signature Verification)

Update manifests include cryptographic integrity verification fields:

```python
@dataclass
class UpdateManifest:
    version: str
    download_url: str
    checksum_sha256: str       # SHA-256 hash of the update payload
    signature: str             # Cryptographic signature of the checksum
    size_bytes: int
    min_version: str
    # ...
```

The update process verifies:
1. **Checksum**: SHA-256 hash of the downloaded payload matches the manifest
2. **Signature**: The checksum is verified against the project's signing public key
3. **Minimum version**: The update is applicable to the current installation
4. **Channel**: The update matches the configured channel (stable/beta/nightly)

Updates that fail verification are discarded and logged as security events.

## Code Integrity (Runtime Integrity Checks)

The Hardening subsystem (`core/desktop/hardening.py`) performs periodic integrity checks:

```python
@dataclass
class IntegrityCheckResult:
    status: IntegrityStatus  # HEALTHY | DEGRADED | FAILED | UNKNOWN
    checks: list[dict]       # Individual check results
    # ...
```

Integrity checks include:
- **File integrity**: Core application files are checksum-verified against known hashes
- **Process integrity**: Running processes are validated against expected signatures
- **Memory integrity**: Heap memory is scanned for unexpected modifications
- **Startup validation**: All subsystems are verified during application startup

Checks run at configurable intervals (default: 300 seconds) and on startup. Failed checks trigger alerts and, in configured environments, automatic recovery procedures.

## RBAC (Role-Based Access Control)

AgenticOS defines five built-in roles. Every authorization starts from **deny-by-default**:

| Role | Typical Permissions | Use Case |
|------|-------------------|----------|
| `admin` | All permissions, including security management | System administrators |
| `operator` | Tool execution, memory access, provider management | Day-to-day operators |
| `agent` | Composed capabilities limited to assigned workspace | AI agents |
| `auditor` | Read-only access to audit logs and security state | Compliance auditing |
| `guest` | Read-only access to non-sensitive state | View-only access |

Roles are assigned via:
```http
POST /api/security/assign
{
  "principal": "user@example.com",
  "role": "operator"
}
```

The MCP Runtime extends RBAC with fine-grained MCP permissions (see `domain/security.py` for the full list: `mcp.server.create`, `mcp.tool.invoke`, `mcp.resource.read`, etc.).

## Tool Permissions (Approval Workflows for Sensitive Operations)

Capabilities flagged `requires_approval` require explicit human authorization before execution. The approval workflow:

1. **Agent requests tool execution** with capability `tool.filesystem` (requires_approval=true)
2. **System creates a `ToolRequest`** with status `pending`
3. **Approval gate notifies** human operators (via notification or API polling)
4. **Human decides** via `POST /api/security/approval/{request_id}/decide`
5. **Decision is recorded** in the audit log
6. **Tool executes only if approved**

```http
POST /api/security/approval/{request_id}/decide
{
  "approved": true,
  "by": "admin@example.com"
}
```

Approval requests can be queried via `GET /api/security/approval/{request_id}` and all decisions are audited.

## Security Best Practices

1. **Master key management**: Store `AGENTIC_OS_MASTER_KEY` in a secure secrets manager (Vault, AWS Secrets Manager, etc.), never in version control
2. **API key rotation**: Rotate provider API keys regularly. Use short-lived, scoped tokens where possible
3. **Network segmentation**: Run AgenticOS in a trusted network. Do not expose the API port (8000) to the public internet
4. **CORS configuration**: Review the allowed origins in `create_app()` — restrict to known dashboard URLs
5. **Audit monitoring**: Regularly review the audit log at `/api/security/audit` for suspicious patterns
6. **Plugin vetting**: Only install plugins from trusted sources. Review plugin manifest capabilities before installation
7. **Update channel**: Use the `stable` channel for production deployments. Test `beta`/`nightly` in staging environments
8. **Minimum permissions**: Assign the least permissive role that satisfies the principal's requirements
9. **Workspace isolation**: Ensure every agent operates in its own workspace with no cross-workspace access

## Reporting Vulnerabilities

If you discover a security vulnerability in AgenticOS, please report it privately. **Do not open a public issue** for security-sensitive findings.

- **Email**: security@agenticos.dev
- **GitHub**: Use the repository's private vulnerability reporting feature

We will acknowledge receipt within **72 hours** and aim to provide a remediation plan within **14 days**, depending on severity. We request that you do not publicly disclose the vulnerability until we have released a fix and notified users.

### What to include:
- Description of the vulnerability
- Affected components and versions
- Steps to reproduce
- Potential impact
- Any suggested mitigations

We appreciate responsible disclosure and will credit reporters (with permission) in our security advisories.
