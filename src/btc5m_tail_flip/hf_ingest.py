from __future__ import annotations

"""Hugging Face dataset download helpers for public Polymarket crypto data."""

import json
import os
from dataclasses import dataclass
from typing import Dict, Iterable, List

try:
    import requests
except Exception:  # pragma: no cover
    requests = None  # type: ignore


ALIPLAYER_REPO = "aliplayer1/polymarket-crypto-updown"
BROCK_REPO = "BrockMisner/polymarket-crypto-5m-15m"
HF_DATASET_API = "https://huggingface.co/api/datasets/{repo}"
HF_RESOLVE = "https://huggingface.co/datasets/{repo}/resolve/main/{path}"


@dataclass(frozen=True)
class DownloadedFile:
    repo: str
    remote_path: str
    local_path: str
    bytes_written: int


def _require_requests():
    if requests is None:
        raise RuntimeError("requests is required. Install with: pip install requests")
    return requests


def hf_resolve_url(repo: str, path: str) -> str:
    if path.startswith("/") or ".." in path.split("/"):
        raise ValueError("path must be a repository-relative file path")
    return HF_RESOLVE.format(repo=repo, path=path)


def fetch_dataset_api(repo: str, timeout: float = 30.0) -> Dict[str, object]:
    req = _require_requests()
    r = req.get(HF_DATASET_API.format(repo=repo), timeout=timeout)
    r.raise_for_status()
    return r.json()


def sibling_paths(repo: str, timeout: float = 30.0) -> List[str]:
    data = fetch_dataset_api(repo, timeout=timeout)
    return [str(item["rfilename"]) for item in data.get("siblings", []) if "rfilename" in item]


def download_file(repo: str, remote_path: str, local_path: str, timeout: float = 300.0) -> DownloadedFile:
    req = _require_requests()
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    url = hf_resolve_url(repo, remote_path)
    bytes_written = 0
    with req.get(url, stream=True, timeout=timeout) as r:
        r.raise_for_status()
        with open(local_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                f.write(chunk)
                bytes_written += len(chunk)
    return DownloadedFile(repo=repo, remote_path=remote_path, local_path=local_path, bytes_written=bytes_written)


def brock_remote_paths_for_date(date: str) -> List[str]:
    return [
        "markets/all.parquet",
        "resolutions/all.parquet",
        f"orderbooks/{date}.parquet",
        f"trades/{date}.parquet",
        f"crypto_prices/{date}.parquet",
        f"price_history/{date}.parquet",
    ]


def safe_local_name(remote_path: str) -> str:
    return remote_path.replace("/", "__")


def download_brock_day(date: str, out_dir: str) -> List[DownloadedFile]:
    files = []
    for remote_path in brock_remote_paths_for_date(date):
        local_path = os.path.join(out_dir, safe_local_name(remote_path))
        files.append(download_file(BROCK_REPO, remote_path, local_path))
    return files


def download_aliplayer_markets(out_dir: str) -> DownloadedFile:
    return download_file(ALIPLAYER_REPO, "data/markets.parquet", os.path.join(out_dir, "markets.parquet"))


def write_download_manifest(files: Iterable[DownloadedFile], path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump([file.__dict__ for file in files], f, indent=2, sort_keys=True)
