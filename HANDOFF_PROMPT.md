# Continuation handoff prompt

Use this context for the remaining connected demo and recovery validation. It does not authorize
new live AWS changes beyond the already deployed environment.

---

You are taking over a multi-repository AWS portfolio project after the connected deployment
checkpoint on 2026-09-02. Inspect every worktree before acting. Preserve user changes and untracked
files, never expose credentials, and do not mutate AWS until the owner explicitly approves it.

## Objective and boundaries

OpsDesk is a secure support-ticket application on EKS with optional, asynchronous, human-reviewed
AI assistance. The repositories remain separate and integrate only through bounded service,
queue, telemetry, and infrastructure contracts:

1. `ops-platform` owns FastAPI OpsDesk, PostgreSQL/Alembic migrations, the CPU Agent, SQS dispatch,
   integration clients, tests, and portable Kubernetes bases. Current branch at the checkpoint:
   `main`; deployed version `0.7.0`; migration head
   `0005_workflow_trace_context`.
2. `rag_platform` owns approved documents, embeddings, retrieval, citation evidence, API auth, and
   its independent deployment. Its product name is “RAG Platform.” Its current branch is `main`.
3. `multi-llm-platform` owns the independently deployed Lambda/API Gateway model router, provider
   credentials, cache isolation, usage/cost accounting, and monitoring. Its current branch is
   `main`. Preserve its unrelated untracked `scripts/` and sensitive
   `terraform/tfdestroy`; do not inspect, commit, or delete the saved plan.
4. `eks-observability-platform` owns VPC, EKS, RDS, ECR, SQS/DLQ, IAM, ingress, Kubernetes overlays,
   CloudWatch collection, dashboards, alarms, and SLO documentation. Its current branch is `main`.
5. `gitops-auto-remediation` is retained for reference but explicitly de-scoped. Do not integrate
   or deploy it unless the owner changes that decision.

No repository imports another repository’s application code, owns another service’s data, or
copies its credentials. The browser calls only OpsDesk. The Agent calls RAG Platform and the
multi-LLM gateway and has no database credential. Consequential output always requires an
authorized human review and separate apply action.

## Completed local implementation

- Phase 9: authenticated retrieval-only `POST /v1/search`, approved source filtering, bounded
  evidence, citation validation, raw-query redaction, graceful fallback, and citation display.
- Phase 10: W3C `traceparent` and workflow correlation across OpsDesk, transactional outbox, SQS,
  Agent, RAG Platform, and gateway; bounded AI metrics; CloudWatch EKS add-on via Pod Identity;
  cross-system dashboard/alarms and initial SLOs.
- Phase 11: 12-character length-first password policy; architecture, threat/privacy, resilience,
  demo, limitations, and observability documents; a local PostgreSQL 17 logical backup/restore
  exercise; release candidate `0.7.0`.

The local restore proof passed at migration `0005_workflow_trace_context` with 15 public tables.
It does not prove RDS snapshot or point-in-time recovery.

## Live-state checkpoint

The EKS worker, RDS, HTTPS ALB, OpsDesk `0.7.0`, Agent, dispatcher, RAG Platform, and lean multi-LLM
gateway are active. OpsDesk is Ready, the Agent can reach both independent services, RAG retrieval
returns only the approved `opsdesk-demo-runbook` source, and both SQS queues were empty at the
checkpoint. Reverify with the read-only lifecycle status procedure before acting. Do not start,
stop, destroy, rotate, or subscribe merely to inspect state.

## Next operations

1. Use an existing authorized administrator session to execute the new-ticket, AI-draft,
   citation-review, approval, and separate-apply flow in `DEMO.md`. Never bypass the human review
   boundary or reset an existing credential without explicit owner direction.
2. Verify the resulting workflow correlation, RAG/gateway metadata, queues, DLQ, and privacy-safe
   logs without recording raw ticket/evidence content.
3. Restore an RDS snapshot/PITR into an isolated target and record measured RTO/RPO before claiming
   the AWS recovery requirement complete.

## Working rules

- Read `requirements.md`, `PROJECT_STATUS.md`, `ARCHITECTURE.md`, `SECURITY.md`, `RESILIENCE.md`,
  `DEMO.md`, and each repository’s local instructions before changing code.
- Keep AI optional and exclude private notes, credentials, raw prompts/queries/evidence, and user
  content from logs, traces, metrics, screenshots, and public evidence.
- Use immutable revisions and scoped secrets; never print secret values or inspect saved plans.
- Use reviewed Terraform plans. Terraform validation is not an apply, a local logical restore is
  not RDS PITR, and deterministic fake output is not a live model call.
- Preserve idempotency, bounded retries/deadlines, citation provenance, least privilege, and human
  approval. Do not add self-healing automation.
- The owner chose direct pushes to `main` for speed. Validate each change before pushing and keep
  repositories separate.

Start by reporting repository and live runtime status, then continue from the human-demo boundary.

---
