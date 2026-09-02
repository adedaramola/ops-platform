# OpsDesk project status and resume handoff

Last updated: 2026-09-02 (America/New_York)

## Current completion checkpoint

- OpsDesk `0.7.0` implements Phases 1–11 and is deployed to the portfolio AWS environment by the
  immutable ECR digest recorded below.
- RAG Platform remains an independent repository and now exposes the authenticated, retrieval-only
  `/v1/search` contract with approved-source filtering, bounded excerpts, validated citations, raw
  query redaction, and trace/workflow correlation.
- The independent multi-LLM gateway accepts the same bounded correlation contract and records trace
  and workflow identifiers as non-metric CloudWatch context.
- OpsDesk migration head is `0005_workflow_trace_context`; W3C trace context is persisted across the
  transactional outbox and SQS boundary and forwarded by the Agent to both independent services.
- The EKS observability repository defines the CloudWatch Observability add-on through Pod Identity,
  a cross-system dashboard, queue/RDS alarms, optional gateway/RAG signals, and initial SLOs.
- The release documentation now includes architecture, security/privacy, resilience, backup/restore,
  connected demo, and limitations records. The password minimum is restored to 12 characters.
- The local PostgreSQL 17 logical backup/restore exercise passed at migration `0005` with all 15
  public tables. AWS RDS snapshot/PITR restore remains an explicitly unexecuted operator exercise.

## Final local validation (2026-08-31)

- OpsDesk: Ruff lint/format, strict mypy, Bandit, dependency audit, secret scan, migration upgrade,
  six Kubernetes renders, and the PostgreSQL backup/restore exercise passed. The full suite passed
  with 113 tests and 86.17% coverage.
- RAG Platform: Ruff lint/format, strict mypy, Bandit, and scoped secret scans passed. The
  deterministic suite passed with 161 tests, 3 skipped live-Weaviate checks, 1 deselected
  credential/judge-gated evaluation, and 85.61% coverage.
- Multi-LLM gateway: Ruff lint/format, strict mypy, Bandit, dependency audit, scoped secret scans,
  and all 82 tests passed with 75.47% coverage.
- EKS observability: Terraform formatting and configuration validation passed. No Terraform plan or
  apply was run.
- The RAG Platform development/CI Chroma dependency remains on the current upstream release with
  published advisories and no fixed release available at this checkpoint. It is restricted to an
  embedded local client and must not be exposed as a server; the production contract uses private
  Weaviate. This residual risk must be reevaluated before release or any trust-boundary change.
- The connected AWS infrastructure, live Weaviate retrieval contract, immutable artifact publish,
  deployment, branch merges, and authenticated human review/apply walkthrough were completed on
  2026-09-01/02. Judge-backed DeepEval and isolated RDS snapshot/PITR restore remain unexecuted.

## Connected AWS deployment (2026-09-02)

- All four active repositories are on `main`; the owner chose validated direct-to-`main` pushes for
  subsequent work instead of pull requests.
- RAG Platform is deployed at `https://rag.cafeinaded.com`. Its authenticated `/v1/search`
  endpoint returned HTTP 200 with one bounded chunk from the only approved source,
  `opsdesk-demo-runbook`; unauthenticated search returns 403.
- The RAG EC2 nodes are managed through Systems Manager. The production embedding backend uses
  `BAAI/bge-small-en-v1.5` locally because the configured OpenAI account had no remaining embedding
  credits. The persistent Weaviate EBS volume now survives instance replacement.
- The EKS Terraform changes applied without durable-resource deletions: cross-system
  dashboard/alarms, scoped RAG credential access, CloudWatch Container Insights through Pod
  Identity, and a one-node dev worker group. CloudWatch Application Signals auto-instrumentation is
  disabled because its injected Java container conflicted with Restricted Pod Security.
- OpsDesk migration `opsdesk-migrate-v0005` completed. The web deployment is 2/2 Ready, the CPU
  Agent is 1/1 Ready, the dispatcher is active, and both the work queue and DLQ are empty.
- Public OpsDesk readiness is HTTP 200 at `https://opsdesk.cafeinaded.com/health/ready`. From the
  Agent pod, both RAG Platform and the multi-LLM gateway health endpoints return HTTP 200.
- The deployed image is
  `900009968072.dkr.ecr.us-east-1.amazonaws.com/opsdesk@sha256:8eacbba9863fc784a13b4db52af14330b18319a716e2406d53ff1d0cee7266b5`,
  built from OpsDesk commit `687cfe0d27a27d76751467810a3e344d06e8fe6a` and tagged `0.7.0`/`687cfe0`.
- Temporary Terraform plan files created for the RAG and EKS applies were deleted after use; no
  credential values were printed. The unrelated multi-LLM `terraform/tfdestroy` remains untouched.

## Working agreements

- Keep the project strictly within `requirements.md`; do not add adjacent platform features.
- Optimize for a functional portfolio demonstration, not perfection.
- Spend time on working AWS deployment rather than GitHub process.
- `ops-platform` owns OpsDesk application code, database migrations, the CPU Agent, API contracts,
  tests, and portable Kubernetes defaults.
- `eks-observability-platform` owns AWS Terraform, EKS integration overlays, workload IAM, ingress,
  RDS, SQS/DLQ, and observability infrastructure.
- The existing multi-LLM repository is the only model gateway. Do not build another gateway.
  Phase 7 uses the required deterministic fake; Phase 8 connects the existing multi-LLM service.
- GPU infrastructure is not required. The Agent is CPU-only.

## Completed before Phase 7

- Phases 1-5 application foundation, authentication, authorization, tickets, administration,
  security controls, deployment contracts, and observability baseline.
- Phase 6 AWS environment in `us-east-1`: VPC, EKS `opsdesk-dev`, private PostgreSQL RDS,
  ECR, SQS work queue and DLQ, HTTPS ALB ingress, Route 53, ACM, and deployed non-AI OpsDesk.
- Public application was verified at `https://opsdesk.cafeinaded.com` before shutdown.
- Registration, login, ticket creation, comments, ticket search, TLS readiness, and role workflows
  were smoke-tested.
- `abdaramola@gmail.com` is an active administrator.
- `agent@cafeinaded.com` is an active human support agent. Its password is intentionally not
  recorded in this file.
- Existing smoke ticket `OPS-000001` has UUID `9494adf9-d74a-464d-9160-ad9fcf051d47`.

## Phase 7 implemented in `ops-platform`

The current feature branch contains a narrow asynchronous AI response-draft workflow:

- Alembic revision `0003_ai_workflows`.
- Transactional `ai_workflows`, `ai_suggestions`, immutable `ai_review_events`, and durable
  `ai_outbox_events` records.
- `POST /api/v1/tickets/{ticket_id}/ai-suggestions` returns HTTP 202.
- `GET /api/v1/ai-workflows/{workflow_id}` returns bounded workflow and suggestion metadata.
- Authenticated internal Agent APIs fetch minimized ticket context and submit typed results.
- Agent context includes title, description, and public comments only. It excludes internal notes,
  requester identity, sessions, and database credentials.
- Human review supports editing, approval, rejection, and separate application as a public comment.
- Application re-checks reviewer authorization and ticket version and is idempotent.
- Agent result submission and request dispatch are idempotent.
- The deterministic Phase 7 draft tool has explicit allowlisting, step/token/time bounds, typed
  input/output, and treats ticket text as untrusted.
- Separate CPU-only Agent process (`opsdesk-agent`) has no database import or runtime database
  Secret.
- SQS dispatcher uses a transactional outbox and a bounded Kubernetes CronJob.
- Ticket UI labels AI content and displays type, provider/model class, RAG use, citations,
  generation time, estimated cost availability, and approval state.
- AI remains disabled by default in the base deployment so core readiness and ticket operations do
  not depend on it.
- Version advanced to `0.5.0`; Phase 7 readiness expected migration `0003_ai_workflows`.

## Phase 7 validation completed

- Local migration `0002_ticket_domain -> 0003_ai_workflows`: passed.
- Ruff lint and format checks: passed.
- Strict mypy: passed.
- Kubernetes render for base, migration, and optional AI packages: passed.
- Full test suite: 93 passed.
- Coverage: 86.57% (required minimum is 80%).
- Integration tests cover staff authorization, private-note/identity exclusion, service-token
  rejection, request and result idempotency, editable approval, idempotent application, public
  comment creation, and stale-ticket rejection.
- Agent tests cover deterministic typed output and absence of database imports.

## Phase 7 AWS changes completed

- Terraform in `eks-observability-platform/terraform/environments/dev/messaging.tf` now defines:
  - `opsdesk-dev-agent`: receive/delete access to only `opsdesk-dev-agent-work`;
  - `opsdesk-dev-ai-dispatcher`: send access to only `opsdesk-dev-agent-work`;
  - EKS Pod Identity associations for `opsdesk/opsdesk-agent` and
    `opsdesk/opsdesk-ai-dispatcher`.
- Reviewed Terraform plan was `6 to add, 0 to change, 0 to destroy`; apply succeeded.
- Immutable ECR image:
  `900009968072.dkr.ecr.us-east-1.amazonaws.com/opsdesk@sha256:70370ef616b9a41a0a1f485df20d293117e608987d4fb258216b19917bdc4164`.
- RDS migration Job `opsdesk-migrate-v0003` completed successfully.
- Migration troubleshooting: direct local rendering initially used `opsdesk-runtime` (application
  role) instead of the AWS overlay's `opsdesk-migration` Secret. The application role correctly
  lacked schema creation. The documented migration-role grant was verified, the Job was rewired to
  the dedicated migration Secret, and the migration then completed in 10 seconds.
- The temporary diagnostic Jobs and temporary RDS master-credential Secrets were deleted. The RDS
  managed master credential remains in AWS Secrets Manager.
- Deployments `opsdesk` and `opsdesk-agent` both rolled out successfully with zero restarts.
- The first `opsdesk-ai-dispatcher` CronJob completed successfully.
- A random internal Agent token was added to the existing `opsdesk-runtime` Kubernetes Secret and
  was never displayed or written to this repository.
- Public `/health/ready` returned `{"status":"ready"}` after rollout.

## Prior shutdown state (2026-08-24)

The integrated environment was paused again on 2026-08-24 without destroying reproducible
resources. The state was verified on 2026-08-25:

- OpsDesk Kubernetes Ingress was deleted and ALB `opsdesk-dev` is absent.
- EKS managed node group `platform-d0c4648a0fe022b5fc2d0572a3` has `minSize=0`,
  `desiredSize=0`, `maxSize=2`; its Auto Scaling Group has zero instances.
- Kubernetes Deployments `opsdesk` and `opsdesk-agent` were scaled to zero and the dispatcher
  CronJob was suspended. Reapplying the reviewed overlays restores declared replicas.
- RDS instance `opsdesk-dev` is `stopped`; its database and backups are retained.
- The multi-LLM Lambda gateway remains deployed and available by explicit user decision. Its lean
  profile has no provisioned concurrency, scheduler, VPC/NAT, Aurora, or ElastiCache.
- The existing internal Agent token was copied, without being printed or rotated, into the managed
  `opsdesk/dev/runtime` secret so the Kubernetes Secrets can be recovered after a rebuild.
- EKS control plane, NAT gateway, ECR images, RDS storage/backups, SQS/DLQ, Route 53, ACM, Secrets
  Manager, CloudWatch, and Terraform state remain and still incur baseline cost.
- RDS automatically restarts after AWS's maximum seven-day stop period if it is not manually
  started sooner.
- Account-neutral clone-to-deploy implementation plus resume/pause are documented in the EKS
  repository at `deploy/opsdesk/OPERATIONS.md`. Terraform-output-driven overlay configuration,
  secret recovery, and lifecycle actions are supported by scripts instead of requiring this AWS
  account's identifiers in a new deployment.

## Phase 7 live state and pause decision

- The AWS runtime, HTTPS ingress, DNS, RDS, application, CPU Agent, and dispatcher were restored.
- Live ticket `OPS-000002` completed workflow `3757fef4-2843-4608-bf7d-67db5ee5cd28` through the
  outbox, SQS, CPU Agent, and pending human suggestion path.
- The outbox was published once; the work queue and DLQ were empty after processing.
- A live minimized-context probe returned only the allowed fields and excluded the private marker,
  requester identity, administrator identity, and agent identity.
- The suggestion was approved by a human administrator but was intentionally not applied as a
  public comment. The user chose to pause further application work and prioritize cross-repository
  portfolio integration.
- The application UI was streamlined and deployed. A mixed-content stylesheet issue behind the
  HTTPS ALB was corrected with a root-relative static asset URL.

## Phase 8 integration complete

- `multi-llm-platform` now has an explicit `off`, `private`, and `shared` cache policy contract.
- Shared caching is restricted to public data. Private exact and semantic cache entries are scoped
  by authenticated caller, and `caller_app` is bound to the API-key identity in production.
- The pgvector migration adds an indexed cache namespace while preserving existing entries as
  shared for backward compatibility.
- The gateway provisions a dedicated `opsdesk-agent` service credential: Secrets Manager stores
  the raw value and DynamoDB stores only its SHA-256 hash plus scoped caller metadata and limits.
- The OpsDesk CPU Agent has a typed gateway client with bounded tokens/timeouts, restricted data
  classification, private/off cache policy, stable workflow correlation, strict JSON validation,
  provider/model/cost capture, and safe retry on provider unavailability.
- Alembic revision `0004_gateway_usage` persists gateway request correlation, input/output tokens,
  cache policy/source/hit, and cost without changing ticket behavior. It was applied successfully
  to the AWS PostgreSQL database on 2026-08-24.
- The deterministic Phase 7 tool remains the disabled/local default; enabling the gateway requires
  an explicit URL and either a direct secret or Secrets Manager ARN.
- `eks-observability-platform` optionally grants the existing Agent Pod Identity permission to read
  only the scoped gateway credential ARN.
- The multi-LLM Terraform now defaults to a lean portfolio profile: no dedicated VPC/NAT,
  ElastiCache, Aurora/pgvector migration, scheduled provider probes, or provisioned concurrency.
  The full cache profile remains available through explicit variables. In lean mode OpsDesk must
  use gateway cache policy `off`.
- The router will be deployed exactly once as a Lambda-backed API, not duplicated in EKS. Lean
  mode omits the health-checker Lambda entirely, provisions secrets only for enabled providers,
  defaults to Bedrock plus Anthropic, and leaves OpenAI disabled. Low-budget OpsDesk requests now
  have a hard low-tier ceiling, including model-preference and streaming paths.
- Predeployment validation observed on 2026-08-24:
  - multi-LLM full suite: 81 passed, 75.16% coverage; lint and mypy passed;
  - OpsDesk unit suite: 38 passed; lint, format, mypy, offline migration rendering, and AI
    Kubernetes rendering passed;
  - both changed Terraform configurations validated; the lean multi-LLM profile also passed
    formatting, shell syntax, diff-whitespace, and redacted secret-diff checks;
  - no Terraform plan or apply was run during that validation checkpoint; the reviewed lean
    deployment and integration applies described below were performed afterward.
- Multi-LLM lean `dev` deployment completed in AWS account `900009968072`, `us-east-1`, on
  2026-08-24. The reviewed Terraform plan and apply were `37 to add, 0 to change, 0 to destroy`,
  followed by a no-change convergence plan. The public endpoint is
  `https://nrh4gb8z19.execute-api.us-east-1.amazonaws.com`.
- Deployed resources include one Python 3.12 ARM64 gateway Lambda with X-Ray and a versioned `live`
  alias, HTTP API Gateway, four on-demand DynamoDB tables, scoped IAM/GitHub OIDC, CloudWatch
  logs/dashboard/alarms, SNS, the Anthropic secret, and generated bootstrap/OpsDesk credentials.
  No VPC/NAT, Aurora, ElastiCache, OpenAI secret, health-checker Lambda, EventBridge schedule,
  provisioned concurrency, or EKS router copy was created.
- Live gateway verification passed: public health `200`, missing authentication `401`, scoped
  OpsDesk authentication and caller binding, strict draft JSON, cache `off`, direct Anthropic Haiku,
  and enforcement that a low-budget Sonnet preference remained on the low tier. The warm scoped
  OpsDesk request completed in 0.98 seconds, and Lambda logs contained no errors.
- The first cold public health request approached the API Gateway timeout, so the deployed OpsDesk
  Agent now uses a bounded 25-second gateway client timeout while retaining the 120-second total
  workflow deadline. The SNS email subscription was recreated for the intended endpoint, confirmed,
  and accepted a test publication on 2026-09-02.
- Provider credentials were not rotated, per the user's decision, and no value is recorded here.
  OpsDesk retrieves only its scoped gateway credential through EKS Pod Identity and Secrets Manager;
  no direct gateway key is present in the Agent Deployment.
- OpsDesk 0.6.0 and the CPU Agent were deployed by immutable ECR digest. The gateway is enabled with
  cache policy `off`; application health, router health, the work queue, and the DLQ were verified.
- Live workflow `d5c712aa-7207-4822-b5b8-6fafb4d1b308` proved the complete transport and persistence
  path but exposed that Nova copied the original JSON schema example as placeholder text. The prompt
  contract was corrected, validation was strengthened, and a new immutable image was deployed.
- Corrected live workflow `839be7c0-0d31-4a4e-94ca-d44c5c6f236e` succeeded on its first attempt via
  `bedrock-nova-micro` / `amazon.nova-micro-v1:0` in 6.614 seconds. OpsDesk recorded 188 input tokens,
  78 output tokens, estimated cost `$0.000018`, a gateway request identifier, cache `off`/source
  `none`/hit `false`, and selected tools `draft_public_response` plus `multi_llm_gateway`.
- The corrected suggestion remains pending for human review and was not posted automatically. The
  work queue and DLQ were both empty after processing.
- Live ticket `OPS-000003` completed the connected RAG acceptance flow through workflow
  `13418d7f-3a2c-4ddc-9f15-10f9a738b9d6`: it succeeded on its first attempt, selected
  `draft_public_response`, `rag_search`, and `multi_llm_gateway`, recorded `rag_used=true`, and
  cited `C1` from approved source `opsdesk-demo-runbook`. The owner explicitly approved the draft
  and separately applied it; the persisted applied-comment link is valid. The ticket has two public
  comments and one internal note, and the audit trail records `approved` followed by `applied`.
- After the completed workflow, the work queue and DLQ both had zero visible, in-flight, or delayed
  messages.
- For interactive testing, the owner temporarily authorized the EKS public endpoint CIDR
  `0.0.0.0/0`; private endpoint access remains enabled. The Terraform validation that rejects
  allow-all CIDRs remains intact, so the live endpoint must be narrowed to explicit `/32` addresses
  after testing.
- OpsDesk Docker workflow run `33647802903`, triggered by documentation commit `e8a6a51`, built and
  published the multi-architecture image successfully. Its final retention step failed when Docker
  Hub returned HTTP 403 while deleting old tag `0.6.0`, so the overall workflow is red even though
  publication completed. The configured credential authenticated and pushed but did not authorize
  tag deletion. The owner deferred replacing `DOCKERHUB_TOKEN`; the follow-up is a scoped Docker Hub
  token with Read, Write, and Delete permission, followed by a workflow rerun and retention check.
  Do not expose the token or make retention non-blocking.

## Remaining release operations

- Replace the temporary EKS public endpoint CIDR `0.0.0.0/0` with explicit operator `/32` CIDRs
  after interactive testing.
- Execute an isolated RDS snapshot/PITR restore and record its measured RTO/RPO; local logical
  restore validation does not substitute for that AWS exercise.
- Replace the deferred GitHub `DOCKERHUB_TOKEN` with a repository-scoped Read/Write/Delete token,
  rerun Docker workflow `33647802903`, and verify that the three-release retention policy succeeds.
- Rotate provider/API keys only when the user begins the next stage; rotation was explicitly
  deferred.
- Keep GitOps auto-remediation de-scoped. It is not part of the integrated architecture.

## Saved repository checkpoint

- `ops-platform`: `main` at `e8a6a51` before this status update.
- `eks-observability-platform`: `main` at `cc702d7`.
- `multi-llm-platform`: `main` at `f58f616`.
- `rag_platform`: `main` at `cb7a3c9`.
- `gitops-auto-remediation`: branch `agent/harden-remediation-safety`, commit `53188c8`; preserved
  for reference but intentionally not deployed or integrated.

The multi-LLM worktree still contains unrelated untracked `scripts/benchmark.py` and a saved
Terraform plan at `terraform/tfdestroy`. Never commit or inspect the saved plan; request explicit
approval before deleting it. Do not reset or overwrite either untracked file.
