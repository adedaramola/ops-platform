# Resilience and recovery

OpsDesk treats PostgreSQL as required and all AI/telemetry systems as optional. `/health/live`
reports process health; `/health/ready` checks the database and Alembic revision; `/health` returns
a sanitized aggregate. An unavailable RAG Platform, gateway, Agent, queue, or trace exporter must
not block ordinary ticket work.

## PostgreSQL backup and restore

AWS RDS owns automated snapshots, retention, and point-in-time recovery. A production restore test
must restore into a new, isolated instance, use a newly scoped application credential, run the
readiness and migration checks, compare representative row counts, and only then consider a DNS or
configuration cutover. Never overwrite the source database during a restore exercise.

The repository provides a local logical proof:

```bash
docker compose up -d postgres
uv run alembic upgrade head
make backup-restore-test
```

The script runs version-matched tools inside the pinned local PostgreSQL container, dumps
`opsdesk_db`, restores into the fixed temporary database `opsdesk_restore_verification`, compares
the Alembic revision and public-table count, and removes the temporary database and dump. It does
not accept a remote host and does not claim to validate RDS snapshot/PITR behavior.

## Failure exercises

| Scenario | Expected behavior | Evidence |
|---|---|---|
| AI disabled | Suggestion request returns a controlled unavailable response; ticket CRUD/readiness work | Configuration and API tests |
| RAG Platform unavailable | Agent continues with an ungrounded gateway draft or configured safe fallback; no false citations | Agent contract tests |
| Gateway unavailable | Agent does not fabricate a provider result; SQS retries are bounded and may reach DLQ | Agent/gateway failure tests and queue alarms |
| Duplicate queue/result delivery | Existing workflow/suggestion is returned; no duplicate ticket comment | Integration tests |
| Ticket changes before review | Approval is rejected as stale | Integration tests |
| Database unavailable | Readiness fails without exposing connection details; liveness remains process-only | Health tests and deployment probes |
| Trace exporter unavailable | Request remains successful; telemetry export is best-effort | Telemetry configuration contract |
| Migration failure | Rollout remains stopped; investigate and prefer a forward corrective migration | Pre-deploy Job contract |

Development-only controlled latency and error routes can demonstrate bounded HTTP failures. Their
configuration is rejected in test, staging, and production.

## Queue recovery

Inspect workflow state, message receive count, oldest-message age, and DLQ contents before acting.
Correct the dependency or contract failure first. Redrive only selected messages and verify that
the workflow is still eligible; result submission and application are idempotent, but redrive is
never automated by an alarm.

## Recovery acceptance

Recovery is complete only when readiness is healthy, migration revision is current, ticket reads
and writes pass, authorization/privacy smoke tests pass, queue age returns to baseline, and no
unexpected error-rate increase appears. Document actual timestamps and results outside the repo if
they contain account or incident identifiers.
