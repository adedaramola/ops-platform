# OpsDesk architecture

OpsDesk is a modular FastAPI monolith for ticketing, authentication, authorization, human review,
and audit history. It remains useful when every AI component is disabled or unavailable.

```text
Browser
  |
OpsDesk API/UI (EKS) ---- PostgreSQL (RDS)
  |
transactional outbox -> SQS -> CPU Agent (separate EKS workload)
                              |                    |
                         RAG Platform        Multi-LLM gateway
                         (separate repo)      (separate repo/Lambda)
```

The repositories and runtimes are intentionally independent:

| Repository | Owns | Integration contract |
|---|---|---|
| `ops-platform` | Product, Agent code, workflows, reviews, migrations, portable manifests | Versioned internal Agent API, SQS message, RAG and gateway clients |
| `rag_platform` | Approved documents, embeddings, retrieval, citation evidence | Authenticated `POST /v1/search` |
| `multi-llm-platform` | Provider routing, fallback, cache isolation, usage and cost | Authenticated `POST /v1/chat` |
| `eks-observability-platform` | AWS network, EKS, RDS, SQS, ingress, IAM, dashboards and alarms | Terraform inputs and Kubernetes overlays |
| GitOps repository | Reconciliation declarations | Immutable source revisions and image tags |

No repository imports another repository's application code or shares its database. Wiring uses
URLs, scoped credentials, bounded JSON contracts, stable AWS identifiers, and W3C trace context.
The browser never calls AI dependencies directly. Only the CPU Agent can call RAG Platform and the
multi-LLM gateway, and the Agent has no database credentials.

## AI workflow

An authorized agent requests a suggestion. OpsDesk commits the workflow and outbox event in one
database transaction. The dispatcher publishes the workflow ID and optional `traceparent` to SQS.
The Agent retrieves a minimized ticket context through the internal API, optionally retrieves
approved evidence, and asks the gateway for a structured draft. OpsDesk validates and stores the
result as pending. An authorized human may edit, approve, reject, and explicitly apply it.

Citation excerpts and prompts are transient. OpsDesk persists only the citation identifier,
approved source identifier, and optional page alongside bounded provider usage metadata.

## Operational properties

- PostgreSQL and the current Alembic revision are required for readiness; AI systems are not.
- Queue delivery, result submission, and suggestion application are idempotent.
- Private notes are excluded at the service boundary before Agent serialization.
- Metrics use bounded labels, and logs/traces exclude ticket and retrieved text.
- Deployment artifacts are non-root, read-only where practical, and configuration-driven.

See [SECURITY.md](SECURITY.md), [RESILIENCE.md](RESILIENCE.md), and [DEPLOYMENT.md](DEPLOYMENT.md)
for the controls and operating procedures behind this design.
