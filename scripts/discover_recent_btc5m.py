#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from btc5m_tail_flip.data_sources import btc5m_slug_for_ts, gamma_market_by_slug, extract_token_ids


def main() -> int:
    now = int(time.time())
    slugs = [btc5m_slug_for_ts(now - 300 * i) for i in range(6)]
    result = []
    for slug in slugs:
        try:
            m = gamma_market_by_slug(slug)
            result.append({
                "slug": slug,
                "id": m.get("id"),
                "conditionId": m.get("conditionId"),
                "tokens": extract_token_ids(m),
                "question": m.get("question"),
                "endDate": m.get("endDate"),
            })
        except Exception as e:
            result.append({"slug": slug, "error": repr(e)})
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
