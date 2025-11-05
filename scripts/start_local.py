#!/usr/bin/env python3
"""Generate pricing outputs locally and serve the dist directory."""

from __future__ import annotations

import argparse
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = ROOT / "dist"

# Ensure project root is on sys.path so absolute imports find sibling scripts.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build pricing artifacts and serve them locally.")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind (default: 127.0.0.1)")
    parser.add_argument("--port", default=8000, type=int, help="Port for the HTTP server (default: 8000)")
    parser.add_argument(
        "--skip-update",
        action="store_true",
        help="Skip regenerating dist/ before starting the server.",
    )
    return parser.parse_args()


def regenerate_outputs() -> None:
    from scripts import update_models

    update_models.main()


def serve_directory(host: str, port: int) -> None:
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    handler = partial(SimpleHTTPRequestHandler, directory=str(DIST_DIR))
    try:
        with ThreadingHTTPServer((host, port), handler) as httpd:
            base_url = f"http://{host}:{port}"
            print(f"\nServing reports from {DIST_DIR}")
            print("Available pages:")
            for page in ("index.html", "checks.html", "changelog.html"):
                print(f" • {base_url}/{page}")
            print("\nPress Ctrl+C to stop.\n")
            httpd.serve_forever()
    except OSError as exc:
        print(f"Failed to start server on {host}:{port}: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nStopping server…")


def main() -> None:
    args = parse_args()
    if not args.skip_update:
        print("Regenerating pricing outputs…")
        regenerate_outputs()
    serve_directory(args.host, args.port)


if __name__ == "__main__":
    main()
