# Security and privacy review

This review covers the public OpsDesk product boundary and its integrations. It is a portfolio
threat model, not a claim of third-party certification or a substitute for a production assessment.

## Trust boundaries and controls

| Threat | Boundary | Primary controls | Residual risk / operator action |
|---|---|---|---|
| Account takeover | Browser → OpsDesk | Argon2id, 12–128 character passwords, opaque rotating sessions, secure cookies, CSRF, login throttling | Add breached-password screening and MFA before handling sensitive real users |
| Cross-user ticket access | Route → service/repository | Backend role and ownership checks on every read/mutation; authorization tests | Review each new query and endpoint for object-level authorization |
| Internal-note disclosure | OpsDesk → Agent/RAG/gateway | Separate schemas/tables; minimized Agent context; privacy regression tests | Do not add generic ticket serialization to AI tools |
| Prompt injection | Approved evidence/ticket text → model | Evidence is data-delimited; tools are fixed; output is typed; no autonomous mutation; human approval | A reviewer must treat every draft and citation as untrusted advice |
| Citation spoofing | Gateway → Agent → OpsDesk | Citation IDs must be a subset of the current authenticated RAG response | Source correctness still depends on RAG ingestion governance |
| Credential theft | Runtime configuration | Secrets Manager contracts, Pod Identity, scoped service tokens, no secrets in images/logs | Rotate on suspected exposure; avoid Terraform values containing secret material |
| Replay/duplication | SQS/internal API | Transactional outbox, idempotency keys, unique suggestion, replay-safe apply | DLQ redrive remains a reviewed operator action |
| Telemetry leakage | All services → telemetry | Bounded attributes, correlation IDs only, raw prompt/query/note exclusion | Inspect new instrumentation and retention before rollout |
| Dependency compromise | Build pipeline | Locked dependencies, minimal images, CI tests/scans, immutable release tags | Review and patch findings; produce an SBOM/signature in a future release |
| Infrastructure exposure | Internet → AWS | HTTPS ingress, private RDS, scoped security groups, restricted EKS API CIDRs | RAG Platform network hardening remains owned by its repository |

## Password and session policy

New passwords require 12–128 characters. OpsDesk does not impose composition rules that encourage
predictable substitutions. Existing Argon2id hashes remain valid; changing input validation does
not rewrite stored hashes. Sessions are random server-side records with absolute and idle expiry,
rotation on authentication, revocation on logout/deactivation, and production-only secure cookies.

Before using OpsDesk for real customer data, add breached-password screening, MFA for staff, a
formal recovery flow, and verified email ownership. Those controls are deliberately not simulated.

## Data classification and retention

- Restricted: password hashes, session/token values, internal notes, service credentials, prompts,
  RAG queries and evidence excerpts. These must not enter logs, traces, metrics, or public APIs.
- Internal: ticket descriptions/comments and draft contents. They remain within the authorized
  OpsDesk/Agent/gateway workflow and are never metric labels.
- Audit metadata: workflow IDs, citation/source IDs, provider/model class, token counts, cost,
  review action and timestamps. These may be retained for operational accountability.

OpsDesk does not automatically index tickets in RAG Platform. Each repository owns its storage,
backup, access policy, and deletion lifecycle.

## Release checklist

1. Run unit/integration/contract tests and the dependency/static/configuration scans.
2. Inspect the rendered Kubernetes resources and production image user/capabilities.
3. Review Terraform plans separately in the infrastructure repositories; do not apply by default.
4. Verify secret ARNs and scoped credentials without printing secret values.
5. Run the backup/restore and failure exercises in [RESILIENCE.md](RESILIENCE.md).
6. Record unresolved findings and limitations; do not describe an unexecuted check as passed.
