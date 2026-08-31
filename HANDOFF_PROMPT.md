# Continuation handoff prompt

Use this context for a future reviewed release or deployment session. It does not authorize live
AWS changes.

---

You are taking over a multi-repository AWS portfolio project after the local Phase 11 completion
checkpoint on 2026-08-31. Inspect every worktree before acting. Preserve user changes and untracked
files, never expose credentials, and do not mutate AWS until the owner explicitly approves it.

## Objective and boundaries

OpsDesk is a secure support-ticket application on EKS with optional, asynchronous, human-reviewed
AI assistance. The repositories remain separate and integrate only through bounded service,
queue, telemetry, and infrastructure contracts:

1. `ops-platform` owns FastAPI OpsDesk, PostgreSQL/Alembic migrations, the CPU Agent, SQS dispatch,
   integration clients, tests, and portable Kubernetes bases. Current branch at the checkpoint:
   `feat/dockerhub-retention`; release candidate version `0.7.0`; migration head
   `0005_workflow_trace_context`.
2. `rag_platform` owns approved documents, embeddings, retrieval, citation evidence, API auth, and
   its independent deployment. Its product name is “RAG Platform.” Its working branch was
   `eval-26394740052`; preserve the owner’s pre-existing Terraform edits.
3. `multi-llm-platform` owns the independently deployed Lambda/API Gateway model router, provider
   credentials, cache isolation, usage/cost accounting, and monitoring. Its working branch was
   `agent/production-readiness-roadmap`. Preserve its unrelated untracked `scripts/` and sensitive
   `terraform/tfdestroy`; do not inspect, commit, or delete the saved plan.
4. `eks-observability-platform` owns VPC, EKS, RDS, ECR, SQS/DLQ, IAM, ingress, Kubernetes overlays,
   CloudWatch collection, dashboards, alarms, and SLO documentation. Its working branch was
   `phase6/rds-log-privacy`.
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

## Live-state caution

The last recorded state has EKS workers/application and RDS intentionally paused for cost control,
while the lean multi-LLM gateway remains deployed by owner decision. Do not assume this is still
true: use the read-only lifecycle status procedure in
`eks-observability-platform/deploy/opsdesk/OPERATIONS.md` when live-state verification is approved.
Do not start, stop, apply, destroy, rotate, subscribe, merge, or publish merely to inspect state.

## Next release operations

1. Review each repository’s dirty state and separate owner-authored changes from the Phase 9–11
   implementation.
2. Run the documented lint, type, test, migration, manifest, Terraform, dependency, static, and
   secret/configuration checks. Report executed and unexecuted checks separately.
3. Open or update one reviewed PR per repository. Keep repositories separate; do not create a
   monorepo or copy source between them.
4. After CI passes, publish immutable artifacts and pin exact image/source revisions.
5. Only with explicit AWS approval: review Terraform plans, resume EKS/RDS, apply observability
   changes, wire the independent RAG Platform and gateway identifiers/credentials, and execute the
   connected demo in `DEMO.md`.
6. Restore an RDS snapshot/PITR into an isolated target and record measured RTO/RPO before claiming
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

Start by reporting repository status and validation gaps. Do not change live resources.

---
