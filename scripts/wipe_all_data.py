#!/usr/bin/env python3
"""Wipe PostgreSQL contacts via the running API.

Requires the Python API running (BACKEND_BASE_URL from .env) and a valid JWT.

Usage:
  python scripts/wipe_all_data.py
  ACCESS_TOKEN=... python scripts/wipe_all_data.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.env_loader import load_env  # noqa: E402

load_env()

def main() -> int:
    api_base = (
        os.getenv("BACKEND_BASE_URL")
        or os.getenv("API_BASE_URL")
        or os.getenv("VITE_API_URL")
        or ""
    ).rstrip("/")
    if not api_base:
        print("Set BACKEND_BASE_URL (or API_BASE_URL) in .env", file=sys.stderr)
        return 1
    token = os.getenv("ACCESS_TOKEN", "").strip()

    payload = json.dumps({"confirm": True}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(
        f"{api_base}/admin/wipe-all-data",
        data=payload,
        headers=headers,
        method="POST",
    )

    print(f"Wiping backend data via {api_base}/admin/wipe-all-data …")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print("Backend wipe failed:", detail or exc.reason, file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"Backend not reachable at {api_base}: {exc.reason}", file=sys.stderr)
        print("Start the Python API: cd backend && python run.py", file=sys.stderr)
        return 1

    print(json.dumps(body, indent=2))
    print(
        "\nDone. Use Settings → Delete all data in the app to clear the browser queue/cache.",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
