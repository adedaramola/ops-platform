# OpsDesk

OpsDesk is a server-rendered support-ticket and knowledge-management application. The core product is a modular FastAPI monolith backed by PostgreSQL and remains fully functional when every AI integration is disabled.

This repository is currently at **Phase 5: production packaging and deployment contracts**.

## Implemented in Phase 2

- Python 3.12, FastAPI, SQLAlchemy 2, PostgreSQL, and Alembic
- Registration, login, logout, authentication status, and account page
- Argon2id password hashes and opaque server-side sessions
- Configurable absolute and idle session expiration
- Session-bound CSRF protection for forms and JSON mutations
- Fixed user, support-agent, and administrator roles
- Persistent login throttling
- Sanitized authentication audit records
- Structured JSON logs and validated request IDs
- Liveness, readiness, and aggregate health endpoints
- Non-root multi-stage container and Docker Compose stack
- Ruff, mypy, Pytest, migration validation, and baseline GitHub Actions CI

## Implemented in Phase 3

- User-isolated ticket creation, detail, search, filters, and stable pagination
- Sequence-backed ticket numbers such as `OPS-000001`
- Open, In Progress, Waiting for User, Resolved, and Closed workflow enforcement
- Low, Medium, High, and Critical priorities
- Agent claim and administrator reassignment commands
- Optimistic concurrency through ticket versions and HTTP 409 conflicts
- Public comments and separately stored private internal notes
- Immutable, privacy-filtered ticket activity and sanitized administrative audits
- User, agent, and administrator dashboards
- Administrator user roles, activation, categories, statistics, and audit review
- Server-rendered Jinja2 pages with progressively enhanced HTMX navigation
- Versioned `/api/v1` endpoints with cookie-security and error schemas in OpenAPI

## Implemented in Phase 4

- Prometheus exposition at `/metrics` with bounded HTTP, login, ticket, authorization,
  database, and application-error labels
- Configurable OpenTelemetry HTTP, SQLAlchemy, and important service spans
- Incoming W3C trace-context propagation plus request/trace correlation in JSON logs
- Non-blocking OTLP/HTTP export that does not participate in readiness
- Optional, rate- and concurrency-bounded demo traffic with clean cancellation
- Realistic success traffic and controlled `401`, `403`, `404`, `409`, `422`, and `429`
  outcomes
- Development-only bounded slow and `500` scenarios with production configuration guards
- Pinned official Prometheus and OpenTelemetry Collector Compose services

## Implemented in Phase 5

- Production image version `0.6.0` with fixed numeric UID/GID `10001:10001`
- Alembic configuration and migrations included in the same immutable application image
- Read-only-root-compatible runtime with a bounded writable `/tmp`
- Production validation for PostgreSQL, development credentials, and database pool limits
- Configurable SQLAlchemy pool size, overflow, timeout, recycle, and connection timeout
- Portable Kustomize packages that keep migration and application rollout ordering explicit
- Restricted pod/container security contexts, probes, resources, disruption budget, and ingress policy
- External PostgreSQL and runtime-secret contract ready for private Amazon RDS
- CI checks for image contents, numeric identity, read-only startup, manifests, and Kubernetes schemas
- Migration, rollout, rollback, database-compatibility, and AWS ownership documentation

AWS infrastructure, EKS, and RDS provisioning are intentionally deferred to Phase 6 and belong to
the separate EKS observability platform repository.

## Quick start with Docker Compose

Requirements: Docker with Compose support.

```bash
docker compose up --build
```

Open:

- Application: <http://localhost:8000>
- Tickets: <http://localhost:8000/tickets>
- Administration (admin role): <http://localhost:8000/admin>
- OpenAPI: <http://localhost:8000/docs>
- Liveness: <http://localhost:8000/health/live>
- Readiness: <http://localhost:8000/health/ready>
- Prometheus exposition: <http://localhost:8000/metrics>

The Compose stack uses clearly marked development-only credentials. Do not reuse them outside local development.

Stop the stack while retaining PostgreSQL data:

```bash
docker compose down
```

To remove the development database as well:

```bash
docker compose down --volumes
```

## Local development

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env
docker compose up -d postgres
alembic upgrade head
uvicorn opsdesk.main:app --reload --port 8000
```

Quality checks:

```bash
ruff format --check src tests migrations
ruff check src tests migrations
mypy
pytest --cov --cov-report=term-missing
alembic check
```

## Production deployment contract

Phase 5 defines portable Kubernetes packages under `deploy/kubernetes` without applying resources.
The migration Job is intentionally rendered separately from the application so a deployment
pipeline must wait for Alembic before rolling out OpsDesk.

See [DEPLOYMENT.md](DEPLOYMENT.md) for the image contract, required runtime secrets, external
PostgreSQL configuration, manifest layout, rollout order, and rollback rules.

Docker Hub publication is configured for `docker.io/walexdee/opsdesk` and remains disabled until
the repository access token is stored in GitHub and the explicit publishing variable is enabled.
The deployment guide documents the immutable tags, public-image Kubernetes overlays, and initial
setup procedure.

For the current cross-repository AWS checkpoint and a copy-paste continuation prompt, see
[HANDOFF_PROMPT.md](HANDOFF_PROMPT.md). Live pause/resume operations are owned by the EKS platform
repository's `deploy/opsdesk/OPERATIONS.md` runbook.

## Optional development accounts

Seed accounts are disabled by default. To enable them locally, set all of the following in `.env`:

```dotenv
OPS_ENVIRONMENT=development
OPS_ENABLE_DEV_SEED=true
OPS_SEED_USER_PASSWORD=<local-password>
OPS_SEED_AGENT_PASSWORD=<local-password>
OPS_SEED_ADMIN_PASSWORD=<local-password>
```

Then run:

```bash
opsdesk-seed
```

The seed command refuses to run outside the development environment.

The generated identities are `demo-user@opsdesk.example.com`,
`demo-agent@opsdesk.example.com`, and `demo-admin@opsdesk.example.com`.

## Optional observability stack

OpsDesk metrics are always available without another service. Enable trace export and start the
pinned official Prometheus and OpenTelemetry Collector images with:

```bash
OPS_OTEL_ENABLED=true docker compose --profile observability up --build -d
```

Open Prometheus at <http://localhost:9090>. Representative queries include
`rate(opsdesk_http_requests_total[1m])` and
`histogram_quantile(0.95, sum by (le) (rate(opsdesk_http_request_duration_seconds_bucket[5m])))`.
The local Collector uses its debug exporter, so representative spans are visible through:

```bash
docker compose --profile observability logs otel-collector
```

The application uses OTLP/HTTP at `OPS_OTEL_EXPORTER_OTLP_ENDPOINT`. Export is disabled by
default, and an unavailable Collector never changes application responses or readiness.

## Optional demo traffic

The demo workload is disabled by default. The `demo` profile explicitly seeds designated local
accounts and runs the traffic CLI using the OpsDesk image:

```bash
OPS_TRAFFIC_DURATION_SECONDS=30 \
OPS_TRAFFIC_RATE_PER_SECOND=0.5 \
OPS_TRAFFIC_CONCURRENCY=2 \
docker compose --profile demo run --build --rm traffic
```

Rate is measured in complete scenarios per second. Each scenario logs in, creates and searches
for a ticket, comments, assigns it, changes priority, and moves it through status transitions.
The first scenario also produces controlled client-error outcomes. Every generated request carries
the bounded `traffic_source=demo` marker, which is observability metadata only and grants no access.

To include bounded slow and `500` development scenarios, opt in explicitly on both the API and
traffic workload:

```bash
OPS_ENABLE_CONTROLLED_FAILURES=true \
docker compose --profile demo run --build --rm traffic
```

Configuration validation rejects controlled failures outside development and rejects demo traffic
in production. `SIGINT` and `SIGTERM` stop the generator and cancel in-flight scenarios cleanly.

## Configuration and security notes

- All configuration uses the `OPS_` environment-variable prefix.
- Production and staging reject insecure cookies, the default CSRF secret, and development seeding.
- Never commit `.env`, credentials, session values, or production connection strings.
- Logs intentionally exclude emails, passwords, cookies, authorization headers, and user-generated content.
- `/health/live` does not depend on PostgreSQL. `/health/ready` verifies PostgreSQL and the expected migration revision.
- PostgreSQL is published on host port `5433` to avoid common local port `5432` collisions.
- Regular-user queries never load private-note rows, and private-note activity is filtered from user history.
- Search logs contain only bounded filter-presence fields, never raw search terms.
- Metric labels and span attributes exclude user IDs, ticket IDs, request IDs, emails, queries,
  descriptions, comments, internal notes, credentials, and connection strings.

## Ticket API overview

- `GET|POST /api/v1/tickets`
- `GET /api/v1/tickets/{ticket_id}`
- `GET|POST /api/v1/tickets/{ticket_id}/comments`
- `GET|POST /api/v1/tickets/{ticket_id}/internal-notes` (agent/admin only)
- `GET /api/v1/tickets/{ticket_id}/activity`
- Purpose-specific assignment, status, priority, and category commands
- `GET /api/v1/dashboard`
- User, category, statistics, and audit administration endpoints

All API mutations require a session-bound CSRF token from `GET /api/v1/auth/csrf`.

The detailed local requirements and phased implementation plan are intentionally ignored by Git.
