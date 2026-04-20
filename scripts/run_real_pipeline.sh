#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$ROOT/src"
cd "$ROOT"
DATE="${1:-2026-03-13}"

/usr/bin/python3 scripts/download_hf_btc5m.py --source brock --date "$DATE" --out-dir data/hf_brock --manifest reports/hf_brock_download_manifest.json
/usr/bin/python3 scripts/download_hf_btc5m.py --source aliplayer-markets --out-dir data/hf_aliplayer --manifest reports/hf_aliplayer_download_manifest.json
/usr/bin/python3 scripts/build_candidates_from_hf.py --date "$DATE" --fetch-gamma --out "data/real_candidates_hf_brock_${DATE}.csv" 2>&1 | tee "reports/build_candidates_hf_brock_${DATE}.json"
/usr/bin/python3 scripts/calibrate_b_factor.py "data/real_candidates_hf_brock_${DATE}.csv" --out "reports/real_b_factor_calibration_hf_brock_${DATE}.csv" --summary "reports/real_backtest_summary_hf_brock_${DATE}.json" 2>&1 | tee "reports/calibrate_hf_brock_${DATE}.json"
