#!/usr/bin/env python3
"""CI version: rebuild index.html embedding data.json inline (no external fetch needed)"""
import json, os, re
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(BASE, "data.json"), "r", encoding="utf-8") as f:
    data = json.load(f)

with open(os.path.join(BASE, "index.html"), "r", encoding="utf-8") as f:
    html = f.read()

data_js = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
html = re.sub(r'const raw = \[.*?\];', f'const raw = {data_js};', html, flags=re.DOTALL)
html = re.sub(r'最新更新.*?<\/b>', f'最新更新 <b id="statLatest">{data[0]["date"] if data else "-"}</b>', html)

with open(os.path.join(BASE, "index.html"), "w", encoding="utf-8") as f:
    f.write(html)

print(f"Built index.html with {len(data)} records, latest: {data[0]['date'] if data else 'N/A'}")
