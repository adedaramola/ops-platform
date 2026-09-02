# OpsDesk Deployment Contract

This document defines the Phase 5 production runtime contract. It prepares OpsDesk for AWS without
provisioning or changing any AWS or Kubernetes resources. AWS Terraform and environment-specific
overlays belong to the separate EKS observability platform repository.

## Production image

Build the image from the repository root:

```bash
docker build -t opsdesk:0.7.0 .
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

The optional Agent deployment has separate service credentials. Its internal OpsDesk token is read
from `opsdesk-runtime`; gateway and RAG credentials may be supplied directly for local development
or resolved from narrowly scoped Secrets Manager ARNs through the Agent's workload identity. The
portable AI ConfigMap keeps RAG disabled until an environment overlay provides all of:

- `OPS_AGENT_RAG_BASE_URL`
- `OPS_AGENT_RAG_API_KEY` or `OPS_AGENT_RAG_API_KEY_SECRET_ARN`
- `OPS_AGENT_RAG_SOURCE_IDS`, as a JSON array matching the RAG Platform allowlist

RAG unavailability does not affect OpsDesk readiness or ordinary ticket operations.

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
├── dockerhub/         # public-image application, migration and optional AI overlays
└── secret.example.yaml
```

The root base deliberately excludes the migration Job so applying the application cannot start a
migration and rollout concurrently.

The base has no Ingress, cloud annotations, certificate, storage class, or AWS identity binding.
It retains the local image name `opsdesk:0.7.0` so platform overlays can select a registry without
editing the reusable manifests. The Docker Hub overlays under `deploy/kubernetes/dockerhub` select
`docker.io/walexdee/opsdesk:0.7.0`; production operators should replace that tag with the immutable
digest emitted by the publishing workflow. AWS operators may instead select an immutable ECR
digest.

## Docker Hub publication

The `Publish Docker image` workflow builds `linux/amd64` and `linux/arm64` images only after the
`CI` workflow succeeds on `main`. It publishes the following tags to the repository configured by
the `DOCKERHUB_IMAGE` GitHub variable:

- `sha-<full-git-sha>`: immutable revision tag for deployments.
- `<version>-<short-git-sha>`: immutable human-readable release tag.
- `<version>` and `latest`: convenient moving tags for discovery and local evaluation.

After a successful push, the workflow groups tags by image digest and retains the three newest
release revisions: the current release and two rollback points. It always preserves `latest` and
removes the version, release-revision, and SHA tags attached to releases outside that window.

Configure the GitHub repository before enabling publication:

1. Create the Docker Hub repository `walexdee/opsdesk`.
2. Create a Docker Hub access token with Read, Write, and Delete permission, scoped to only the
   required repository or namespace. Delete permission is required for automatic retention.
3. Set the GitHub repository variable `DOCKERHUB_USERNAME` to `walexdee`.
4. Set the GitHub repository variable `DOCKERHUB_IMAGE` to `walexdee/opsdesk`.
5. Add the access token as the GitHub repository secret `DOCKERHUB_TOKEN`.
6. Set `DOCKERHUB_PUBLISH_ENABLED` to `true` and manually run `Publish Docker image` once.

The publishing job is skipped while `DOCKERHUB_PUBLISH_ENABLED` is not `true`. This permits the
workflow to merge safely before credentials exist. Never store the Docker Hub token in a file,
command example, repository variable, workflow output, or committed configuration.

If **Build and publish** succeeds but **Retain the three newest release revisions** fails with HTTP
403, the new image is already available and only retention failed. Verify that the token owner can
administer the configured repository and replace `DOCKERHUB_TOKEN` with a repository-scoped token
that has Read, Write, and Delete permission. Rerun the failed workflow and verify that obsolete
version, release-revision, and SHA tags were removed. Do not make retention non-blocking merely to
turn the workflow green; a failed cleanup must remain visible. Revoke the replaced token only after
the rerun succeeds, and never print either token.

After the first successful publication, pull and inspect the image with:

```bash
docker pull docker.io/walexdee/opsdesk:0.7.0
docker image inspect docker.io/walexdee/opsdesk:0.7.0
```

Render the public-image application and migration packages with:

```bash
kubectl kustomize deploy/kubernetes/dockerhub
kubectl kustomize deploy/kubernetes/dockerhub/migration
```

The optional AI package is rendered separately with
`kubectl kustomize deploy/kubernetes/dockerhub/ai`. All packages still require environment-specific
Secrets, PostgreSQL, ingress, DNS, and TLS configuration.

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
docker build -t opsdesk:0.7.0 .
```

CI additionally checks the numeric image user, embedded migration assets, absence of development
packages, read-only-root startup, health endpoint, Kubernetes schemas, and manifest security tests.

Phase 5 does not authorize a deployment. AWS provisioning and the first real EKS/RDS rollout begin
only in Phase 6 after separate review.
