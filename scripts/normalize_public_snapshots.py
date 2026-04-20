#!/usr/bin/env python3
"""Inspect/normalize public Parquet orderbook snapshots.

Because third-party snapshot schemas can evolve, this script first prints the
schema and writes a JSONL inspection file. Extend `normalize_row()` after seeing
actual column names in your downloaded data.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from glob import glob

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("path_glob", help="e.g. data/public_snapshots/*.parquet")
    p.add_argument("--out", default="reports/public_snapshot_inspection.jsonl")
    args = p.parse_args()
    try:
        import pyarrow.parquet as pq
    except Exception as e:
        raise SystemExit("pyarrow required: pip install pyarrow") from e
    files = glob(args.path_glob if os.path.isabs(args.path_glob) else os.path.join(ROOT, args.path_glob))
    out_path = args.out if os.path.isabs(args.out) else os.path.join(ROOT, args.out)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as out:
        for file in files:
            table = pq.read_table(file)
            record = {
                "file": file,
                "num_rows": table.num_rows,
                "columns": table.column_names,
                "schema": str(table.schema),
            }
            # Write first row preview if available.
            if table.num_rows:
                record["first_row"] = table.slice(0, 1).to_pylist()[0]
            out.write(json.dumps(record, default=str, ensure_ascii=False) + "\n")
            print(json.dumps(record, default=str, ensure_ascii=False, indent=2)[:4000])
    print(f"wrote {out_path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
