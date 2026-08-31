#!/usr/bin/env python3
"""Keep only the newest release revisions in a Docker Hub repository."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

DOCKER_HUB_API = "https://hub.docker.com"
RELEASE_TAG = re.compile(r"^(?!sha-).+-[0-9a-f]{12}$")


class RetentionError(RuntimeError):
    """Raised when the retention policy cannot be applied safely."""


@dataclass(frozen=True)
class Tag:
    name: str
    digest: str
    last_updated: str


def _request_json(request: Request) -> dict[str, Any]:
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except HTTPError as error:
        raise RetentionError(
            f"Docker Hub API returned HTTP {error.code} for {request.full_url}"
        ) from None
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise RetentionError(f"Docker Hub API request failed: {error}") from None

    if not isinstance(payload, dict):
        raise RetentionError("Docker Hub API returned an unexpected response")
    return payload


def list_tags(repository: str) -> list[Tag]:
    """Return every named tag in a public Docker Hub repository."""
    tags: list[Tag] = []
    query = urlencode({"page_size": 100})
    next_url: str | None = f"{DOCKER_HUB_API}/v2/repositories/{repository}/tags?{query}"

    while next_url:
        payload = _request_json(Request(next_url, headers={"Accept": "application/json"}))
        results = payload.get("results")
        if not isinstance(results, list):
            raise RetentionError("Docker Hub tag response did not contain a results list")

        for item in results:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            digest = item.get("digest")
            last_updated = item.get("last_updated")
            if all(isinstance(value, str) and value for value in (name, digest, last_updated)):
                tags.append(Tag(name=name, digest=digest, last_updated=last_updated))

        candidate = payload.get("next")
        if candidate is not None and not isinstance(candidate, str):
            raise RetentionError("Docker Hub tag response contained an invalid next link")
        next_url = candidate

    return tags


def deletion_plan(tags: Iterable[Tag], keep: int) -> list[str]:
    """Return tag names attached only to release revisions older than ``keep``."""
    if keep < 1:
        raise ValueError("keep must be at least 1")

    all_tags = list(tags)
    release_dates: dict[str, str] = {}
    for tag in all_tags:
        if RELEASE_TAG.fullmatch(tag.name):
            release_dates[tag.digest] = max(release_dates.get(tag.digest, ""), tag.last_updated)

    ordered_digests = sorted(release_dates, key=release_dates.__getitem__, reverse=True)
    obsolete_digests = set(ordered_digests[keep:])
    return sorted(
        tag.name for tag in all_tags if tag.digest in obsolete_digests and tag.name != "latest"
    )


def authenticate(username: str, secret: str) -> str:
    """Exchange a Docker Hub personal access token for an API access token."""
    body = json.dumps({"identifier": username, "secret": secret}).encode()
    request = Request(
        f"{DOCKER_HUB_API}/v2/auth/token",
        data=body,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
    payload = _request_json(request)
    access_token = payload.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise RetentionError("Docker Hub authentication response did not contain an access token")
    return access_token


def delete_tags(repository: str, tag_names: Iterable[str], access_token: str) -> None:
    """Delete tag names from Docker Hub without exposing the access token."""
    for tag_name in tag_names:
        encoded_tag = quote(tag_name, safe="")
        request = Request(
            f"{DOCKER_HUB_API}/v2/repositories/{repository}/tags/{encoded_tag}",
            headers={"Authorization": f"Bearer {access_token}"},
            method="DELETE",
        )
        try:
            with urlopen(request, timeout=30):
                pass
        except HTTPError as error:
            raise RetentionError(
                f"Docker Hub returned HTTP {error.code} while deleting tag {tag_name}"
            ) from None
        except (URLError, TimeoutError) as error:
            raise RetentionError(f"Could not delete Docker Hub tag {tag_name}: {error}") from None


def _required_environment(environ: Mapping[str, str], name: str) -> str:
    value = environ.get(name, "").strip()
    if not value:
        raise RetentionError(f"{name} is required")
    return value


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, help="Docker Hub namespace/repository")
    parser.add_argument("--keep", type=int, default=3, help="release revisions to retain")
    parser.add_argument("--dry-run", action="store_true", help="print without deleting tags")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.keep < 1:
        raise RetentionError("--keep must be at least 1")

    tags = list_tags(args.repository)
    planned = deletion_plan(tags, args.keep)
    if not planned:
        print(f"Retention satisfied: no tags exceed the newest {args.keep} releases")
        return 0

    print(f"Pruning {len(planned)} tag(s) outside the newest {args.keep} releases:")
    for tag_name in planned:
        print(f"- {tag_name}")

    if args.dry_run:
        print("Dry run complete; no tags were deleted")
        return 0

    username = _required_environment(os.environ, "DOCKERHUB_USERNAME")
    secret = _required_environment(os.environ, "DOCKERHUB_TOKEN")
    access_token = authenticate(username, secret)
    delete_tags(args.repository, planned, access_token)
    print("Docker Hub retention policy applied successfully")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RetentionError as error:
        print(f"Retention failed: {error}", file=sys.stderr)
        sys.exit(1)
