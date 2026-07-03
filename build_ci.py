#!/usr/bin/env python3
"""CI: clean data.json strings only — index.html loads data via fetch(), no injection needed."""
import json, os, re

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE, "data.json")

with open(DATA_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)

cleaned = 0
for r in data:
    for k in ("game", "summary", "vendor", "cat"):
        if k in r and isinstance(r[k], str):
            orig = r[k]
            r[k] = re.sub(r'\s+', ' ', r[k]).strip()
            if r[k] != orig:
                cleaned += 1

with open(DATA_FILE, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"data.json cleaned ({cleaned} fields fixed), {len(data)} records, latest: {data[0]['date'] if data else 'N/A'}")
