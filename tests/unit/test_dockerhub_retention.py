from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]


def _load_retention_module() -> ModuleType:
    path = ROOT / "scripts" / "prune_dockerhub_releases.py"
    spec = importlib.util.spec_from_file_location("dockerhub_retention", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


retention = _load_retention_module()
Tag = retention.Tag


def _release(version: str, sha: str, digest: str, updated: str) -> list[object]:
    return [
        Tag(version, digest, updated),
        Tag(f"{version}-{sha[:12]}", digest, updated),
        Tag(f"sha-{sha}", digest, updated),
    ]


def test_retention_keeps_current_release_and_two_rollback_points() -> None:
    releases = [
        *_release("0.6.0", "a" * 40, "sha256:one", "2026-08-01T00:00:00Z"),
        *_release("0.7.0", "b" * 40, "sha256:two", "2026-08-02T00:00:00Z"),
        *_release("0.8.0", "c" * 40, "sha256:three", "2026-08-03T00:00:00Z"),
        *_release("0.9.0", "d" * 40, "sha256:four", "2026-08-04T00:00:00Z"),
        Tag("latest", "sha256:four", "2026-08-04T00:00:01Z"),
    ]

    assert retention.deletion_plan(releases, keep=3) == [
        "0.6.0",
        "0.6.0-aaaaaaaaaaaa",
        f"sha-{'a' * 40}",
    ]


def test_retention_counts_unique_digests_instead_of_tag_names() -> None:
    tags = [
        *_release("0.8.0", "a" * 40, "sha256:same", "2026-08-03T00:00:00Z"),
        Tag("candidate-aaaaaaaaaaaa", "sha256:same", "2026-08-03T00:00:01Z"),
        *_release("0.9.0", "b" * 40, "sha256:new", "2026-08-04T00:00:00Z"),
    ]

    assert retention.deletion_plan(tags, keep=2) == []


def test_latest_is_never_deleted_even_if_registry_metadata_is_inconsistent() -> None:
    tags = [
        *_release("0.6.0", "a" * 40, "sha256:old", "2026-08-01T00:00:00Z"),
        Tag("latest", "sha256:old", "2026-08-01T00:00:01Z"),
        *_release("0.7.0", "b" * 40, "sha256:new", "2026-08-02T00:00:00Z"),
    ]

    plan = retention.deletion_plan(tags, keep=1)

    assert "latest" not in plan
    assert "0.6.0" in plan


def test_non_release_tags_do_not_create_additional_releases() -> None:
    tags = [
        Tag("latest", "sha256:one", "2026-08-01T00:00:00Z"),
        Tag("development", "sha256:two", "2026-08-02T00:00:00Z"),
    ]

    assert retention.deletion_plan(tags, keep=1) == []
