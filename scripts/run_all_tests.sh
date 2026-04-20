#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$ROOT/src"
PYTHON_BIN="${PYTHON_BIN:-python3}"
cd "$ROOT"
"$PYTHON_BIN" -m unittest discover -s tests -v 2>&1 | tee reports/unittest_results.txt
"$PYTHON_BIN" scripts/build_fixture_and_backtest.py 2>&1 | tee reports/build_fixture_and_backtest_stdout.json
"$PYTHON_BIN" scripts/calibrate_b_factor.py data/fixtures/btc5m_tail_fixture.csv --out reports/b_factor_calibration.csv --summary reports/backtest_summary.json 2>&1 | tee reports/calibrate_stdout.json
