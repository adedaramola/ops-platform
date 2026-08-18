# OpsDesk

OpsDesk is a server-rendered support-ticket and knowledge-management application. The core product is a modular FastAPI monolith backed by PostgreSQL and remains fully functional when every AI integration is disabled.

This repository is currently at **Phase 2: core foundation and secure authentication**.

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

Ticket workflows are intentionally deferred to Phase 3.

## Quick start with Docker Compose

Requirements: Docker with Compose support.

```bash
docker compose up --build
```

Open:

- Application: <http://localhost:8000>
- OpenAPI: <http://localhost:8000/docs>
- Liveness: <http://localhost:8000/health/live>
- Readiness: <http://localhost:8000/health/ready>

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

## Configuration and security notes

- All configuration uses the `OPS_` environment-variable prefix.
- Production and staging reject insecure cookies, the default CSRF secret, and development seeding.
- Never commit `.env`, credentials, session values, or production connection strings.
- Logs intentionally exclude emails, passwords, cookies, authorization headers, and user-generated content.
- `/health/live` does not depend on PostgreSQL. `/health/ready` verifies PostgreSQL and the expected migration revision.

The detailed local requirements and phased implementation plan are intentionally ignored by Git.
