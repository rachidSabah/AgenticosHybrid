# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.2.x   | ✅        |
| < 0.2   | ❌        |

## Reporting a Vulnerability

If you discover a security vulnerability in AgenticOS, please report it
privately. **Do not open a public issue** for security-sensitive findings.

- Email: **security@agenticos.dev**
- Or use GitHub's private vulnerability reporting on the repository.

We will acknowledge receipt within 72 hours and aim to provide a remediation
plan within 14 days, depending on severity.

## Security Model

AgenticOS is built around least-privilege and defense-in-depth. Key controls
(see `docs/adr/0009-security-framework.md`):

- **RBAC** — roles (`admin`, `operator`, `agent`, `auditor`, `guest`) map to a
  deny-by-default set of coarse permissions. Unknown capabilities are denied.
- **Workspace isolation** — every agent executes within a sandboxed workspace
  root; `..` traversal is neutralised.
- **Approval gate** — capabilities flagged `requires_approval` (terminal, git,
  docker, filesystem) cannot execute without an explicit human decision.
- **Audit log** — every authorization and approval decision is recorded in an
  append-only trail (`/api/security/audit`).
- **Encrypted secrets** — provider API keys are stored encrypted at rest with
  Fernet; the master key is supplied via `AGENTIC_OS_MASTER_KEY` or a key file.

## Secret Handling Guidance

- Never commit real API keys, tokens, or certificates. Use `.env` (gitignored)
  and `.env.example` (committed template) only.
- Rotate any credential that may have been exposed.
- Prefer short-lived, scoped tokens over long-lived secrets.
