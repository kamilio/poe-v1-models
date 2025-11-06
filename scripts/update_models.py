#!/usr/bin/env python3
"""Fetch Poe models metadata, enrich pricing, and persist outputs."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import subprocess
from pathlib import Path
import sys
from typing import Any, Dict, List, Mapping, Optional, Sequence
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from poe_v1_models.changelog import build_changelog_from_snapshots
from poe_v1_models.pipeline import PipelineResult, run_pipeline
from poe_v1_models.reporting import (
    build_checks_report,
    render_changelog_html,
    render_changelog_rss,
    render_index_html,
    render_checks_html,
)


MODELS_OUTPUT_PATH = Path("dist/models.json")
CHECKS_JSON_PATH = Path("dist/checks.json")
CHECKS_HTML_PATH = Path("dist/checks.html")
CHANGELOG_JSON_PATH = Path("dist/changelog.json")
CHANGELOG_HTML_PATH = Path("dist/changelog.html")
CHANGELOG_RSS_PATH = Path("dist/changelog.xml")
INDEX_HTML_PATH = Path("dist/index.html")
REMOTE_TIMEOUT = 10
RELEASE_FETCH_LIMIT = 30


def main() -> None:
    release_snapshots = fetch_release_snapshots(limit=RELEASE_FETCH_LIMIT)
    result = run_pipeline()
    write_models(result)
    write_checks(result)
    write_checks_html()
    write_index_html()
    local_snapshot = {
        "payload": result.payload,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metadata": {
            "release_tag": None,
            "release_name": "Local snapshot",
            "release_url": None,
            "source": "local",
        },
    }
    changelog_entries = build_changelog_from_snapshots(
        [*release_snapshots, local_snapshot],
        config=result.config,
    )
    write_changelog_json(changelog_entries)
    write_changelog_html()
    write_changelog_rss(changelog_entries)


def write_models(result: PipelineResult) -> None:
    MODELS_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    MODELS_OUTPUT_PATH.write_text(
        json.dumps(result.payload, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Created: {MODELS_OUTPUT_PATH}")


def write_checks(result: PipelineResult) -> None:
    report = build_checks_report(result)
    CHECKS_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHECKS_JSON_PATH.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Created: {CHECKS_JSON_PATH}")


def write_checks_html() -> None:
    CHECKS_HTML_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHECKS_HTML_PATH.write_text(render_checks_html(), encoding="utf-8")
    print(f"Created: {CHECKS_HTML_PATH}")


def write_index_html() -> None:
    INDEX_HTML_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_HTML_PATH.write_text(render_index_html(), encoding="utf-8")
    print(f"Created: {INDEX_HTML_PATH}")


def write_changelog_html() -> None:
    CHANGELOG_HTML_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHANGELOG_HTML_PATH.write_text(render_changelog_html(), encoding="utf-8")
    print(f"Created: {CHANGELOG_HTML_PATH}")


def write_changelog_json(entries: Sequence[Mapping[str, Any]]) -> None:
    CHANGELOG_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHANGELOG_JSON_PATH.write_text(
        json.dumps(list(entries), indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Created: {CHANGELOG_JSON_PATH}")


def write_changelog_rss(entries: Sequence[Mapping[str, Any]]) -> None:
    CHANGELOG_RSS_PATH.parent.mkdir(parents=True, exist_ok=True)
    base_url = (
        os.getenv("POE_MODELS_PUBLIC_BASE_URL")
        or os.getenv("POE_MODELS_SITE_URL")
        or os.getenv("PUBLIC_BASE_URL")
    )
    CHANGELOG_RSS_PATH.write_text(
        render_changelog_rss(entries, base_url=base_url),
        encoding="utf-8",
    )
    print(f"Created: {CHANGELOG_RSS_PATH}")


def fetch_release_snapshots(limit: int) -> List[Dict[str, Any]]:
    repository = resolve_repository()
    if not repository:
        print(
            "Skipping changelog generation: unable to resolve repository.",
            file=sys.stderr,
        )
        return []

    if "/" not in repository:
        print(
            f"Skipping changelog generation: malformed repository '{repository}'.",
            file=sys.stderr,
        )
        return []

    owner, repo = repository.split("/", 1)
    base_api = (os.getenv("GITHUB_API_URL") or "https://api.github.com").rstrip("/")
    releases_url = f"{base_api}/repos/{owner}/{repo}/releases?per_page={limit}"

    token = resolve_github_token()
    releases = _github_get_json(releases_url, token=token)
    if not isinstance(releases, list):
        print(
            "Skipping changelog generation: failed to load releases list.",
            file=sys.stderr,
        )
        return []

    snapshots: List[Dict[str, Any]] = []
    for release in releases:
        if not isinstance(release, Mapping):
            continue
        download_url = _find_models_asset(release)
        if download_url is None:
            tag_name = release.get("tag_name") or release.get("name") or "<unknown>"
            print(
                f"Skipping release {tag_name}: models.json asset not found.",
                file=sys.stderr,
            )
            continue

        payload = _github_get_json(
            download_url,
            token=token,
            accept="application/octet-stream",
        )
        if not isinstance(payload, Mapping):
            tag_name = release.get("tag_name") or release.get("name") or "<unknown>"
            print(
                f"Skipping release {tag_name}: failed to parse models.json asset.",
                file=sys.stderr,
            )
            continue

        timestamp = (
            release.get("published_at")
            or release.get("created_at")
            or release.get("updated_at")
        )
        snapshots.append(
            {
                "payload": payload,
                "timestamp": timestamp,
                "metadata": {
                    "release_tag": release.get("tag_name"),
                    "release_name": release.get("name"),
                    "release_url": release.get("html_url"),
                },
            }
        )

    snapshots.sort(key=lambda item: item.get("timestamp") or "")
    return snapshots


def resolve_repository() -> Optional[str]:
    candidates = (
        os.getenv("POE_MODELS_RELEASES_REPOSITORY"),
        os.getenv("POE_MODELS_GITHUB_REPOSITORY"),
        os.getenv("GITHUB_REPOSITORY"),
    )
    for candidate in candidates:
        if candidate:
            value = candidate.strip()
            if value:
                return value
    remote_repo = _repository_from_git_remote()
    if remote_repo:
        return remote_repo
    return None


def resolve_github_token() -> Optional[str]:
    candidates = (
        os.getenv("POE_MODELS_GITHUB_TOKEN"),
        os.getenv("GH_TOKEN"),
        os.getenv("GITHUB_TOKEN"),
    )
    for candidate in candidates:
        if candidate:
            value = candidate.strip()
            if value:
                return value
    return None


def _github_get_json(
    url: str,
    *,
    token: Optional[str],
    accept: str = "application/vnd.github+json",
) -> Optional[Any]:
    body = _github_request(url, token=token, accept=accept)
    if body is None:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        print(f"Failed to decode JSON from {url}", file=sys.stderr)
        return None


def _github_request(
    url: str,
    *,
    token: Optional[str],
    accept: str,
) -> Optional[str]:
    headers = {
        "Accept": accept,
        "User-Agent": "poe-v1-models/1.0 (+https://github.com/poe-v1-models)",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=REMOTE_TIMEOUT) as response:  # nosec: B310
            if response.status != 200:
                print(
                    f"GitHub API request failed with status {response.status} for {url}",
                    file=sys.stderr,
                )
                return None
            raw = response.read()
            return raw.decode("utf-8", errors="replace")
    except (URLError, TimeoutError) as exc:
        print(f"GitHub API request failed for {url}: {exc}", file=sys.stderr)
        return None


def _find_models_asset(release: Mapping[str, Any]) -> Optional[str]:
    assets = release.get("assets")
    if not isinstance(assets, Sequence):
        return None
    for asset in assets:
        if not isinstance(asset, Mapping):
            continue
        name = asset.get("name")
        content_type = asset.get("content_type")
        download_url = asset.get("browser_download_url")
        if not isinstance(download_url, str):
            continue
        if name == "models.json":
            return download_url
        if isinstance(name, str) and name.endswith("models.json"):
            return download_url
        if content_type == "application/json":
            return download_url
    return None


def _repository_from_git_remote() -> Optional[str]:
    git_executable = os.getenv("GIT_EXECUTABLE") or "git"
    try:
        result = subprocess.run(
            [git_executable, "config", "--get", "remote.origin.url"],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return None

    if result.returncode != 0:
        return None

    remote = (result.stdout or "").strip()
    if not remote:
        return None

    # Handle SSH URLs like git@github.com:owner/repo.git
    if remote.startswith("git@"):
        _, _, path = remote.partition(":")
        owner_repo = path.rstrip("/")
        if owner_repo.endswith(".git"):
            owner_repo = owner_repo[:-4]
        if owner_repo.count("/") == 1:
            return owner_repo
        return None

    # Handle HTTPS/HTTP URLs.
    from urllib.parse import urlparse

    parsed = urlparse(remote)
    if not parsed.path:
        return None
    owner_repo = parsed.path.lstrip("/").rstrip("/")
    if owner_repo.endswith(".git"):
        owner_repo = owner_repo[:-4]
    if owner_repo.count("/") == 1:
        return owner_repo
    return None


if __name__ == "__main__":
    main()
