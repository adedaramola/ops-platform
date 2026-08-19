# OpsDesk Deployment Contract

This document defines the Phase 5 production runtime contract. It prepares OpsDesk for AWS without
provisioning or changing any AWS or Kubernetes resources. AWS Terraform and environment-specific
overlays belong to the separate EKS observability platform repository.

## Production image

Build the image from the repository root:

```bash
docker build -t opsdesk:0.4.0 .
```

The runtime image:

- Pins the multi-architecture Python base image by digest.
- Uses numeric UID/GID `10001:10001`.
- Contains the installed application wheel, `alembic.ini`, and migrations.
- Does not contain tests, local configuration, deployment files, caches, or Git data.
- Writes temporary files only under `/tmp`.
- Handles `SIGTERM` and allows 25 seconds for graceful application shutdown.
- Exposes the process-only `/health/live` endpoint for its image health check.

Kubernetes runs one Uvicorn worker per pod and scales with replicas. Do not add multiple workers
without recalculating PostgreSQL connection limits.

## Runtime configuration

Non-sensitive production defaults are in
`deploy/kubernetes/base/common/configmap.yaml`. The required `opsdesk-runtime` Secret supplies:

- `OPS_DATABASE_URL`
- `OPS_CSRF_SECRET_KEY`

`deploy/kubernetes/secret.example.yaml` contains placeholders only. Do not apply it as-is and do
not commit a rendered Secret. The AWS platform must materialize the Secret from AWS Secrets Manager
or an equivalent approved integration.

The production database URL uses the psycopg driver and TLS:

```text
postgresql+psycopg://USER:PASSWORD@RDS_ENDPOINT:5432/opsdesk_db?sslmode=require
```

Passwords containing URL-reserved characters must be percent-encoded. Never print or store the
resolved URL in logs, command history, plans, or deployment output.

Database pool defaults are five persistent connections plus five overflow connections per pod.
The platform owner must verify:

```text
(replicas × (pool_size + max_overflow)) + migration/admin headroom < RDS max_connections
```

## Kubernetes layout

```text
deploy/kubernetes/
├── base/
│   ├── common/       # namespace, non-secret configuration and service identities
│   ├── migration/    # separately applied Alembic Job
│   └── application/  # Deployment, Service, NetworkPolicy and disruption budget
└── secret.example.yaml
```

The root base deliberately excludes the migration Job so applying the application cannot start a
migration and rollout concurrently.

The base has no Ingress, cloud annotations, image registry, certificate, storage class, or AWS
identity binding. The platform overlay owns those environment-specific decisions and must replace
`opsdesk:0.4.0` with an immutable ECR image digest or tag.

The base NetworkPolicy limits application ingress to TCP port 8000. AWS security groups and the
platform overlay must further limit ingress sources and define any required egress policy after the
VPC, RDS, DNS, and telemetry destinations are known.

## Required rollout sequence

Render and review both packages before applying them:

```bash
kubectl kustomize deploy/kubernetes/base
kubectl kustomize deploy/kubernetes/base/migration
```

The platform deployment process must perform this order:

1. Publish an immutable application image.
2. Apply `deploy/kubernetes/base/common` plus the AWS overlay's runtime Secret and identity bindings.
3. Apply the migration package using the exact same image digest intended for the application.
4. Wait for `job/opsdesk-migrate-v0002` to complete successfully.
5. Apply the application base plus AWS overlay.
6. Wait for `deployment/opsdesk` rollout completion.
7. Verify liveness, readiness, version, authentication, and a ticket workflow.

Representative commands after the platform overlay has supplied the image and Secret are:

```bash
kubectl apply -k deploy/kubernetes/base/common
kubectl apply -k deploy/kubernetes/base/migration
kubectl wait --namespace opsdesk --for=condition=complete \
  job/opsdesk-migrate-v0002 --timeout=5m
kubectl apply -k deploy/kubernetes/base
kubectl rollout status --namespace opsdesk deployment/opsdesk --timeout=5m
```

If the named migration Job already exists, confirm why it is being rerun before deleting and
recreating only that Job. Change the Job name whenever a new migration head is introduced.

## Migration safety

- Alembic is the sole schema owner.
- Migration and application images must match.
- Use expand-and-contract migrations for rolling releases.
- Add nullable/new structures first, deploy compatible code, and remove obsolete structures in a
  later release.
- Do not automatically run `alembic downgrade` during rollback.
- Back up and verify recovery before a destructive migration.
- `/health/ready` remains unavailable until PostgreSQL is reachable and the expected migration head
  is present.

## Application rollback

For an application-only failure:

1. Stop the rollout.
2. Restore the previous immutable image through the platform overlay.
3. Confirm the previous version is compatible with the current expanded schema.
4. Roll out and verify readiness and the core ticket workflow.

For a migration failure, leave the application rollout stopped. Inspect the Job and database state,
take a snapshot when appropriate, and prefer a forward corrective migration. A database restore or
downgrade requires explicit operator review.

## Validation

Local checks that do not contact a cluster:

```bash
make manifests
ruff format --check src tests migrations
ruff check src tests migrations
mypy
pytest --cov --cov-report=term-missing
docker build -t opsdesk:0.4.0 .
```

CI additionally checks the numeric image user, embedded migration assets, absence of development
packages, read-only-root startup, health endpoint, Kubernetes schemas, and manifest security tests.

Phase 5 does not authorize a deployment. AWS provisioning and the first real EKS/RDS rollout begin
only in Phase 6 after separate review.
