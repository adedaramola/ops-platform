from __future__ import annotations

import re
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

    assert job["metadata"]["name"] == "opsdesk-migrate-v0004"
    assert job["spec"]["backoffLimit"] == 2
    assert job["spec"]["activeDeadlineSeconds"] == 300
    assert pod_spec["serviceAccountName"] == "opsdesk-migrator"
    assert pod_spec["automountServiceAccountToken"] is False
    assert container["command"][-2:] == ["upgrade", "head"]
    assert {item["name"]: item["value"] for item in container["env"]}["OPS_AI_ENABLED"] == ("false")
    assert container["envFrom"][1]["secretRef"]["name"] == "opsdesk-migration"
    assert container["securityContext"]["readOnlyRootFilesystem"] is True


def test_production_config_disables_dangerous_optional_workloads() -> None:
    config_map = _document(KUBERNETES / "base" / "common" / "configmap.yaml")
    data = config_map["data"]

    assert data["OPS_ENVIRONMENT"] == "production"
    assert data["OPS_ENABLE_DEV_SEED"] == "false"
    assert data["OPS_ENABLE_CONTROLLED_FAILURES"] == "false"
    assert data["OPS_TRAFFIC_ENABLED"] == "false"
    assert data["OPS_OTEL_ENABLED"] == "false"
    assert data["OPS_AI_ENABLED"] == "false"
    assert "OPS_DATABASE_URL" not in data
    assert "OPS_CSRF_SECRET_KEY" not in data


def test_phase7_agent_is_cpu_only_and_has_no_database_credentials() -> None:
    deployment = _document(KUBERNETES / "ai" / "agent-deployment.yaml")
    pod_spec = deployment["spec"]["template"]["spec"]
    container = pod_spec["containers"][0]

    assert deployment["spec"]["replicas"] == 1
    assert pod_spec["serviceAccountName"] == "opsdesk-agent"
    assert container["resources"]["limits"]["cpu"] == "250m"
    assert "nvidia.com/gpu" not in container["resources"]["limits"]
    assert {item["configMapRef"]["name"] for item in container["envFrom"]} == {
        "opsdesk-agent-runtime"
    }
    assert all("secretRef" not in item for item in container["envFrom"])
    secret_keys = {
        item["valueFrom"]["secretKeyRef"]["key"] for item in container["env"] if "valueFrom" in item
    }
    assert secret_keys == {"OPS_AI_INTERNAL_TOKEN"}
    assert "OPS_DATABASE_URL" not in {item["name"] for item in container["env"]}


def test_phase8_agent_routes_through_gateway_without_shared_cache() -> None:
    config_map = _document(KUBERNETES / "ai" / "runtime-configmap.yaml")
    data = config_map["data"]

    assert data["OPS_AGENT_REQUEST_TIMEOUT_SECONDS"] == "25"
    assert data["OPS_AGENT_LLM_GATEWAY_ENABLED"] == "true"
    assert data["OPS_AGENT_LLM_GATEWAY_BASE_URL"] == "REPLACE_WITH_LLM_GATEWAY_URL"
    assert data["OPS_AGENT_LLM_GATEWAY_API_KEY_SECRET_ARN"] == "REPLACE_WITH_LLM_GATEWAY_SECRET_ARN"
    assert data["OPS_AGENT_LLM_GATEWAY_CACHE_POLICY"] == "off"


def test_phase7_outbox_dispatcher_is_bounded_and_separate_from_agent() -> None:
    cronjob = _document(KUBERNETES / "ai" / "dispatcher-cronjob.yaml")
    job_spec = cronjob["spec"]["jobTemplate"]["spec"]
    container = job_spec["template"]["spec"]["containers"][0]

    assert cronjob["spec"]["concurrencyPolicy"] == "Forbid"
    assert job_spec["activeDeadlineSeconds"] == 50
    assert container["command"] == ["opsdesk-ai-dispatch"]


def test_docker_hub_overlays_use_the_canonical_public_image() -> None:
    expected_image = [
        {
            "name": "opsdesk",
            "newName": "docker.io/walexdee/opsdesk",
            "newTag": "0.6.0",
        }
    ]

    for relative_path in (
        "dockerhub/kustomization.yaml",
        "dockerhub/migration/kustomization.yaml",
        "dockerhub/ai/kustomization.yaml",
    ):
        assert _document(KUBERNETES / relative_path)["images"] == expected_image


def test_docker_hub_publisher_is_gated_and_uses_pinned_actions() -> None:
    workflow = (ROOT / ".github" / "workflows" / "publish-image.yml").read_text(encoding="utf-8")
    action_references = re.findall(r"^\s*uses:\s*[^@\s]+@([^\s]+)", workflow, re.MULTILINE)

    assert "workflow_run:" in workflow
    assert "pull_request:" not in workflow
    assert "vars.DOCKERHUB_PUBLISH_ENABLED == 'true'" in workflow
    assert "secrets.DOCKERHUB_TOKEN" in workflow
    assert "platforms: linux/amd64,linux/arm64" in workflow
    assert len(action_references) == 6
    assert all(re.fullmatch(r"[0-9a-f]{40}", reference) for reference in action_references)
