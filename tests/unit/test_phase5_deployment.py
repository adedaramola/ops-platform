from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
KUBERNETES = ROOT / "deploy" / "kubernetes"


def _document(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_application_deployment_uses_restricted_runtime_contract() -> None:
    deployment = _document(KUBERNETES / "base" / "application" / "deployment.yaml")
    pod_spec = deployment["spec"]["template"]["spec"]
    container = pod_spec["containers"][0]

    assert deployment["spec"]["replicas"] == 2
    assert pod_spec["automountServiceAccountToken"] is False
    assert pod_spec["securityContext"]["runAsNonRoot"] is True
    assert pod_spec["securityContext"]["runAsUser"] == 10001
    assert container["securityContext"] == {
        "allowPrivilegeEscalation": False,
        "readOnlyRootFilesystem": True,
        "capabilities": {"drop": ["ALL"]},
    }
    assert container["resources"]["requests"]
    assert container["resources"]["limits"]
    assert container["startupProbe"]["httpGet"]["path"] == "/health/live"
    assert container["livenessProbe"]["httpGet"]["path"] == "/health/live"
    assert container["readinessProbe"]["httpGet"]["path"] == "/health/ready"


def test_runtime_secret_is_required_but_never_included_in_base() -> None:
    deployment = _document(KUBERNETES / "base" / "application" / "deployment.yaml")
    env_from = deployment["spec"]["template"]["spec"]["containers"][0]["envFrom"]
    secret_names = {item["secretRef"]["name"] for item in env_from if "secretRef" in item}
    root_kustomization = (KUBERNETES / "base" / "kustomization.yaml").read_text(encoding="utf-8")

    assert secret_names == {"opsdesk-runtime"}
    assert "secret.example.yaml" not in root_kustomization


def test_migration_job_is_separate_and_bounded() -> None:
    job = _document(KUBERNETES / "base" / "migration" / "job.yaml")
    pod_spec = job["spec"]["template"]["spec"]
    container = pod_spec["containers"][0]

    assert job["metadata"]["name"] == "opsdesk-migrate-v0002"
    assert job["spec"]["backoffLimit"] == 2
    assert job["spec"]["activeDeadlineSeconds"] == 300
    assert pod_spec["serviceAccountName"] == "opsdesk-migrator"
    assert pod_spec["automountServiceAccountToken"] is False
    assert container["command"][-2:] == ["upgrade", "head"]
    assert container["securityContext"]["readOnlyRootFilesystem"] is True


def test_production_config_disables_dangerous_optional_workloads() -> None:
    config_map = _document(KUBERNETES / "base" / "common" / "configmap.yaml")
    data = config_map["data"]

    assert data["OPS_ENVIRONMENT"] == "production"
    assert data["OPS_ENABLE_DEV_SEED"] == "false"
    assert data["OPS_ENABLE_CONTROLLED_FAILURES"] == "false"
    assert data["OPS_TRAFFIC_ENABLED"] == "false"
    assert data["OPS_OTEL_ENABLED"] == "false"
    assert "OPS_DATABASE_URL" not in data
    assert "OPS_CSRF_SECRET_KEY" not in data
