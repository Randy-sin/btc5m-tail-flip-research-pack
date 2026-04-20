#!/usr/bin/env python3
"""Read-only CLOB V2 preflight for the $1 live probe.

The check intentionally does not place or cancel orders. It verifies that:
  - required secret-bearing env vars exist without printing their values;
  - API credentials can be derived from the configured private key/funder;
  - Gamma discovery returns current/next BTC 5m IDs;
  - CLOB V2 market info can be fetched for those condition IDs.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import requests

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_ENV = [
    "POLY_HOST",
    "POLY_CHAIN_ID",
    "POLY_PRIVATE_KEY",
    "POLY_FUNDER_ADDRESS",
    "POLY_SIGNATURE_TYPE",
]


def _load_env() -> None:
    if load_dotenv:
        load_dotenv(dotenv_path=PACKAGE_ROOT / ".env")


def _redacted_env() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in REQUIRED_ENV + ["POLY_CLOB_API_KEY", "POLY_CLOB_SECRET", "POLY_CLOB_PASSPHRASE"]:
        value = os.getenv(key, "")
        if key in {"POLY_HOST", "POLY_CHAIN_ID", "POLY_SIGNATURE_TYPE"}:
            out[key] = value or "MISSING"
        else:
            out[key] = f"present_len={len(value)}" if value else "MISSING"
    return out


def _derive_creds_check() -> dict[str, Any]:
    from py_clob_client_v2 import ClobClient

    client = ClobClient(
        host=os.getenv("POLY_HOST", "https://clob-v2.polymarket.com"),
        chain_id=int(os.getenv("POLY_CHAIN_ID", "137")),
        key=os.getenv("POLY_PRIVATE_KEY"),
        signature_type=int(os.getenv("POLY_SIGNATURE_TYPE", "1")),
        funder=os.getenv("POLY_FUNDER_ADDRESS"),
    )
    creds = client.create_or_derive_api_key()
    return {
        "ok": True,
        "api_key_len": len(getattr(creds, "api_key", "") or ""),
        "api_secret_len": len(getattr(creds, "api_secret", "") or ""),
        "api_passphrase_len": len(getattr(creds, "api_passphrase", "") or ""),
    }


def _discover(window: str) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(PACKAGE_ROOT / "scripts" / "discover_btc5m_market.py"),
        "--window",
        window,
        "--with-clob-info",
    ]
    proc = subprocess.run(cmd, cwd=PACKAGE_ROOT, check=True, text=True, capture_output=True)
    return json.loads(proc.stdout)


def _geoblock_check() -> dict[str, Any]:
    resp = requests.get("https://polymarket.com/api/geoblock", timeout=10)
    resp.raise_for_status()
    data = resp.json()
    return {"ok": data.get("blocked") is False, "blocked": data.get("blocked")}


def main() -> int:
    _load_env()
    missing = [key for key in REQUIRED_ENV if not os.getenv(key)]
    report: dict[str, Any] = {
        "env": _redacted_env(),
        "missing_required_env": missing,
    }
    if missing:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 2

    try:
        report["geoblock"] = _geoblock_check()
    except Exception as exc:
        report["geoblock"] = {"ok": False, "error": type(exc).__name__, "message": str(exc)[:300]}

    try:
        report["api_creds"] = _derive_creds_check()
    except Exception as exc:
        report["api_creds"] = {"ok": False, "error": type(exc).__name__, "message": str(exc)[:300]}

    for window in ("current", "next"):
        try:
            report[f"{window}_market"] = _discover(window)
        except Exception as exc:
            report[f"{window}_market"] = {"ok": False, "error": type(exc).__name__, "message": str(exc)[:300]}

    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.get("api_creds", {}).get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
