# Continuation handoff prompt

Copy the prompt below into a new development session. It is deliberately self-contained and should
be treated as the starting context, not as authorization to change live AWS resources.

---

You are taking over a multi-repository AWS portfolio project on 2026-08-25. Work as a careful senior
engineer collaborating with the owner. First inspect the repositories and confirm the current state;
do not recreate completed work, reset worktrees, expose secrets, or mutate AWS until the owner asks
to resume implementation.

## Objective

The portfolio demonstrates a secure support application on EKS, asynchronous human-reviewed AI
assistance, a separate cost-aware multi-LLM Lambda gateway, and eventually an independent RAG
platform plus end-to-end observability. Optimize for a working, explainable portfolio demonstration.
Do not overinvest in UI polish. The repositories must remain cloneable and deployable into another
operator's AWS account. Treat identifiers for account `900009968072` only as the owner's existing
instance checkpoint, never as a prerequisite for a fresh deployment.

## Repositories already worked on

1. `ops-platform` — active product repository.
   - Remote: `https://github.com/adedaramola/ops-platform.git`
   - Branch: `fix/phase5-ci-config-isolation`
   - Integration commit: `69f0e7353d7d9b68198a411cba11b470fc249741`
   - Owns FastAPI OpsDesk, PostgreSQL/Alembic migrations, authentication/roles/tickets, UI,
     metrics/tracing hooks, asynchronous AI workflow, SQS dispatcher, CPU Agent, gateway client,
     tests, and portable Kubernetes bases.

2. `eks-observability-platform` — active AWS/EKS platform repository.
   - Remote: `https://github.com/adedaramola/eks-observability-platform.git`
   - Branch: `phase6/rds-log-privacy`
   - Portable implementation checkpoint: `c4d3a16` (including operator checkpoint `b172bdd` and
     integration commit `fa27adceb5a7d3ee6400032a460b3425b71e214b`)
   - Owns Terraform for VPC/EKS/RDS/ECR/SQS/IAM/Route 53/ACM/ALB and AWS-specific OpsDesk
     Kustomize overlays. It is also the repository in which the remaining EKS observability layer
     belongs. `deploy/opsdesk/OPERATIONS.md` contains both the account-neutral clone-to-deploy path
     and the existing-instance lifecycle procedure. Read it before provisioning or operating.

3. `multi-llm-platform` — active, separately deployed model gateway.
   - Remote: `https://github.com/adedaramola/multi-llm-platform`
   - Branch: `agent/production-readiness-roadmap`
   - Deployment commit: `517905364581cf7ea6e74374fd011b7f631a5430`
   - Owns the Python 3.12 ARM64 Lambda gateway, API Gateway, provider routing/fallback, caller-bound
     API keys, rate limits, per-caller usage/cost accounting, optional cache profile, Terraform,
     monitoring, and deployment workflow.

4. `gitops-auto-remediation` — work preserved but de-scoped.
   - Remote: `https://github.com/adedaramola/gitops-auto-remediation.git`
   - Branch: `agent/harden-remediation-safety`
   - Latest saved commit: `53188c8`
   - Safety logic, recovery behavior, tests, documentation, and Terraform linting were hardened.
     The owner decided autonomous remediation is unnecessary. Do not deploy, integrate, or include
     it in the target architecture unless the owner explicitly reverses that decision.

An independent RAG platform is planned for Phase 9 but has not yet been worked on in this sequence.
The current workspace has no authoritative RAG Git worktree, so locate or clone the correct repo
before proposing changes.

## Completed architecture and proof

- OpsDesk phases 1-6: secure FastAPI application; user, support-agent, and administrator roles;
  ticket workflows; PostgreSQL/Alembic; tests; container; Kubernetes deployment contract; EKS/RDS
  deployment; TLS at `opsdesk.cafeinaded.com`.
- Phase 7: durable AI workflows/outbox, SQS dispatcher, CPU-only Agent, minimized context, typed
  tools, immutable review audit, and mandatory human approval plus separate application. Private
  notes and requester/session identity do not reach the Agent.
- Phase 8: OpsDesk uses the existing multi-LLM gateway rather than duplicating a router in EKS.
  It uses a scoped Secrets Manager credential through EKS Pod Identity, cache policy `off`, bounded
  time/tokens, low-budget model ceiling, strict structured output, retry rules, and stored provider,
  model, token, cost, request-ID, and cache metadata.
- Multi-LLM is deployed once as a lean Lambda/API Gateway platform. It has four on-demand DynamoDB
  tables, three managed secrets, CloudWatch/X-Ray monitoring, and no provisioned concurrency,
  scheduled health checker, VPC/NAT, Aurora, ElastiCache, OpenAI provider, or EKS copy.
- Corrected live workflow `839be7c0-0d31-4a4e-94ca-d44c5c6f236e` completed through OpsDesk,
  outbox, SQS, Agent, Lambda gateway, Bedrock Nova Micro, and PostgreSQL. The resulting suggestion
  remains pending for human review and was never posted automatically.
- Latest known validations: OpsDesk unit suite 38 passed with Ruff/format/mypy/Kustomize checks;
  multi-LLM suite 81 passed at 75.16% coverage with Ruff/mypy/Terraform validate; EKS Terraform
  fmt/validate/TFLint and every overlay render passed. Gitleaks scans were clean before the saved
  integration commits.

## Live AWS state

- Account `900009968072`, region `us-east-1`.
- EKS cluster `opsdesk-dev` is retained, but managed node group
  `platform-d0c4648a0fe022b5fc2d0572a3` is `min=0`, `desired=0`, `max=2`; its Auto Scaling Group has
  zero EC2 instances.
- RDS `opsdesk-dev` is stopped with data retained. AWS restarts a stopped RDS instance after at
  most seven days.
- OpsDesk Ingress was deleted and ALB `opsdesk-dev` is absent. App and Agent were scaled to zero;
  dispatcher was suspended.
- The multi-LLM gateway remains deployed and must not be shut down. Endpoint:
  `https://nrh4gb8z19.execute-api.us-east-1.amazonaws.com`.
- Multi-LLM observed usage through 2026-08-25: 14 Lambda invocations, 10 successful recorded model
  requests, internal estimated model spend `$0.000728`. Its expected idle baseline is approximately
  `$1.20-$1.50/month`, primarily Secrets Manager and possibly CloudWatch alarms.
- EKS shutdown is reversible but does not eliminate EKS control-plane, NAT, retained storage,
  Secrets Manager, Route 53, or monitoring charges.

## Credentials and sensitive state

- Never print, paste, commit, or put secret values into plans, logs, prompts, or shell history.
- Provider and API keys were intentionally not rotated. Do not rotate them until the owner begins
  the next stage and explicitly approves rotation.
- `opsdesk/dev/runtime` contains application/migration credentials and the existing internal Agent
  token. The token was backed up without rotation or display. Use
  `eks-observability-platform/scripts/opsdesk-secrets.sh verify` to check only field presence.
- OpsDesk Agent can read only its scoped multi-LLM credential ARN through Pod Identity. It must not
  receive direct provider keys or a database URL.
- The multi-LLM worktree contains unrelated untracked `scripts/benchmark.py` and
  `terraform/tfdestroy`. The latter is a saved Terraform plan that may contain sensitive state.
  Never commit or inspect it, and obtain explicit approval before deleting it.

## Existing data useful for smoke tests

- `abdaramola@gmail.com` is an active administrator.
- `agent@cafeinaded.com` is an active human support agent. Passwords are not documented.
- Ticket `OPS-000001` is the original VPN smoke ticket.
- Ticket `OPS-000002` is the Phase 7/8 AI smoke-test ticket.
- Suggestion `9e3c0497-8377-426c-9a70-0086f7206c85` from the corrected workflow is pending. Preserve
  human review; never auto-approve or auto-apply it.

## Resume procedure when the owner asks

From `eks-observability-platform`:

```bash
git switch phase6/rds-log-privacy
git pull --ff-only
./scripts/opsdesk-lifecycle.sh status
./scripts/opsdesk-lifecycle.sh access
./scripts/opsdesk-lifecycle.sh start
```

`access` restricts the EKS public endpoint to the current `/32` and updates the ignored local
`terraform.tfvars`. `start` starts RDS and one worker, reapplies the pinned common/application/AI
overlays, unsuspends dispatch, recreates the ALB, and waits for public readiness. Do not run a
normal Terraform apply while the environment is intentionally paused because Terraform's desired
node count is one.

After resume, follow `deploy/opsdesk/OPERATIONS.md`: verify nodes/deployments/Ingress, both public
health endpoints, the SQS work queue and DLQ, administrator login, and one human-reviewed draft on
`OPS-000002`. To pause again use `./scripts/opsdesk-lifecycle.sh stop` and verify with `status`.

For a fresh deployment in another account, do not use the existing-instance commands or identifiers
as configuration. Follow sections 1-10 of `deploy/opsdesk/OPERATIONS.md`. Bootstrap new Terraform
backends, provide a domain controlled by that operator, deploy multi-LLM first, publish a new ECR
image, and run `scripts/configure-opsdesk-overlays.py` to derive account-specific ECR, ACM, SQS,
gateway, domain, and credential-ARN values from Terraform outputs. Account guards must match the new
Terraform state, not account `900009968072`.

## Remaining work, in recommended order

1. Confirm all four saved branches are pushed and decide whether to merge the three active feature
   branches to `main` through reviewed PRs. Do not merge GitOps into the architecture.
2. When instructed, resume EKS using the supported lifecycle script and run the full smoke checklist.
3. Phase 9: locate the authoritative RAG repository, define an approved-document and citation
   contract, integrate retrieval into the existing CPU Agent, enforce tenant/privacy boundaries,
   and prove citations in a human-reviewed suggestion. Do not add another LLM router.
4. Phase 10: complete the observability platform in `eks-observability-platform`; connect metrics,
   logs, and traces across ALB/OpsDesk/PostgreSQL/SQS/Agent/Lambda, then add useful dashboards,
   alerts, and measurable SLOs. Do not deploy a second observability repository.
5. Phase 11: perform provider failure, queue/DLQ, stale-review, rollback, restore, least-privilege,
   secret-handling, and cost-control exercises. Produce public architecture, threat-model, demo,
   operations, and evidence documentation.
6. Confirm the pending multi-LLM SNS email subscription. Rotate provider/API keys only at the
   owner-approved next-stage boundary.
7. Consider removing the sensitive saved `terraform/tfdestroy` file only after explicit approval.

## Working rules

- Lead with evidence: inspect branches, diffs, AWS identity, and live status before acting.
- Preserve user changes and untracked files. Never reset, discard, or overwrite unrelated work.
- Use immutable Git SHAs and ECR digests for deployment.
- Keep the router only on Lambda; do not deploy another copy into EKS.
- Keep AI optional and core OpsDesk health independent of provider availability.
- Preserve least privilege, context minimization, idempotency, bounded retries/timeouts, and human
  review. Generated text must never be posted automatically.
- Keep the UI as-is unless the owner explicitly reprioritizes it.
- Use reviewed Terraform plans for infrastructure changes. Short pause/resume is the only approved
  imperative drift and is handled by the lifecycle script.
- Do not hardcode the owner's AWS account, domain, certificate, queue URL, gateway URL, or secret ARN
  into reusable instructions. Derive fresh-deployment values from Terraform outputs. Exact existing
  values may appear only in a clearly labeled recovery checkpoint.
- Report exact commands, expected output, verification, rollback, cost impact, and any remaining
  risk so a mid-level developer can proceed without unstated assumptions.

Your first response should briefly confirm the four repository states, identify that EKS/RDS are
paused while multi-LLM remains live, and propose only the next owner-approved step. Do not start AWS
resources merely to inspect them.

---
