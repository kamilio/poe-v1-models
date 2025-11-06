#!/usr/bin/env python3
"""Publish the generated models.json as a timestamped GitHub release."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.update_models import (  # noqa: E402
    MODELS_OUTPUT_PATH,
    resolve_github_token,
    resolve_repository,
)


def main() -> int:
    repository = resolve_repository()
    if not repository or "/" not in repository:
        print("Unable to resolve GitHub repository (expected owner/repo).", file=sys.stderr)
        return 1

    owner, repo = repository.split("/", 1)
    token = resolve_github_token()
    if not token:
        print("Publishing requires a GitHub token (set POE_MODELS_GITHUB_TOKEN, GH_TOKEN, or GITHUB_TOKEN).", file=sys.stderr)
        return 1

    models_path = MODELS_OUTPUT_PATH
    if not models_path.exists():
        print(f"models.json not found at {models_path}; run scripts/update_models.py first.", file=sys.stderr)
        return 1

    models_payload = _load_models(models_path)
    if models_payload is None:
        return 1

    timestamp = datetime.now(timezone.utc)
    tag_suffix = timestamp.strftime("%Y%m%d-%H%M%S")
    release_tag = f"models-{tag_suffix}"
    release_name = f"Models Snapshot {tag_suffix}"

    existing_release = _fetch_release_by_tag(owner, repo, release_tag, token)
    if existing_release:
        print(f"Release {release_tag} already exists; skipping creation.")
        _write_github_output(existing_release.get("html_url"), release_tag)
        return 0

    print(f"Creating release {release_tag} …")
    release = _create_release(owner, repo, release_tag, release_name, timestamp, token, models_payload)
    if release is None:
        return 1

    upload_url = (release.get("upload_url") or "").split("{", 1)[0]
    if not upload_url:
        print("Release created but upload URL missing.", file=sys.stderr)
        return 1

    print("Uploading models.json asset …")
    if not _upload_asset(upload_url, token, models_path.read_bytes(), "models.json"):
        return 1

    release_url = release.get("html_url")
    if release_url:
        print(f"Release published: {release_url}")
    else:
        print("Release published.")
    _write_github_output(release_url, release_tag)
    return 0


def _api_base() -> str:
    return (os.getenv("GITHUB_API_URL") or "https://api.github.com").rstrip("/")


def _uploads_base() -> str:
    return (os.getenv("GITHUB_UPLOAD_URL") or "https://uploads.github.com").rstrip("/")


def _load_models(path: Path) -> Optional[Dict[str, Any]]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"Failed to read {path}: {exc}", file=sys.stderr)
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"Failed to parse {path}: {exc}", file=sys.stderr)
        return None
    if not isinstance(payload, dict):
        print(f"{path} root element must be an object.", file=sys.stderr)
        return None
    return payload


def _fetch_release_by_tag(owner: str, repo: str, tag: str, token: str) -> Optional[Dict[str, Any]]:
    url = f"{_api_base()}/repos/{owner}/{repo}/releases/tags/{tag}"
    return _github_json_request(url, token=token)


def _create_release(
    owner: str,
    repo: str,
    tag: str,
    name: str,
    timestamp: datetime,
    token: str,
    models_payload: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    url = f"{_api_base()}/repos/{owner}/{repo}/releases"
    body_lines = [
        f"Snapshot generated at {timestamp.isoformat()}",
    ]
    total_models = _count_models(models_payload)
    if total_models is not None:
        body_lines.append("")
        body_lines.append(f"Total models: {total_models}")

    payload = {
        "tag_name": tag,
        "name": name,
        "body": "\n".join(body_lines),
        "prerelease": False,
        "draft": False,
    }

    response = _github_json_request(url, token=token, method="POST", json_body=payload)
    if response is None:
        print("Failed to create release.", file=sys.stderr)
    return response


def _upload_asset(
    upload_url: str,
    token: str,
    content: bytes,
    filename: str,
) -> bool:
    uploads_base = upload_url or ""
    if not uploads_base.startswith("http"):
        uploads_base = f"{_uploads_base()}{uploads_base}"

    query = urlencode({"name": filename})
    url = f"{uploads_base}?{query}"

    headers = {
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "User-Agent": "poe-v1-models/1.0 (+https://github.com/poe-v1-models)",
        "Authorization": f"Bearer {token}",
        "Content-Length": str(len(content)),
    }

    request = Request(url, data=content, headers=headers, method="POST")
    try:
        with urlopen(request) as response:  # nosec: B310
            if response.status not in (200, 201):
                print(f"Asset upload failed with status {response.status}", file=sys.stderr)
                return False
            return True
    except HTTPError as exc:
        if exc.code == 422:
            print("models.json asset already exists on this release.", file=sys.stderr)
        else:
            print(f"Asset upload failed: HTTP {exc.code}", file=sys.stderr)
        return False
    except URLError as exc:
        print(f"Asset upload failed: {exc}", file=sys.stderr)
        return False


def _github_json_request(
    url: str,
    *,
    token: str,
    method: str = "GET",
    json_body: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "poe-v1-models/1.0 (+https://github.com/poe-v1-models)",
        "Authorization": f"Bearer {token}",
    }

    data: Optional[bytes] = None
    if json_body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(json_body).encode("utf-8")

    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request) as response:  # nosec: B310
            if response.status >= 400:
                print(f"GitHub API request failed with status {response.status}", file=sys.stderr)
                return None
            raw = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        if exc.code != 404:
            print(f"GitHub API request failed: HTTP {exc.code}", file=sys.stderr)
        return None
    except URLError as exc:
        print(f"GitHub API request failed for {url}: {exc}", file=sys.stderr)
        return None

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"Failed to decode GitHub response JSON: {exc}", file=sys.stderr)
        return None

    if not isinstance(payload, dict):
        return None
    return payload


def _count_models(models_payload: Dict[str, Any]) -> Optional[int]:
    data = models_payload.get("data")
    if isinstance(data, list):
        return len(data)
    return None


def _write_github_output(release_url: Optional[str], release_tag: str) -> None:
    output_path = os.getenv("GITHUB_OUTPUT")
    if not output_path:
        return
    try:
        with open(output_path, "a", encoding="utf-8") as handle:
            if release_url:
                handle.write(f"release_url={release_url}\n")
            handle.write(f"release_tag={release_tag}\n")
    except OSError as exc:
        print(f"Failed to write GitHub output: {exc}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
