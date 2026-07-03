#!/usr/bin/env python3
"""Build index.html by injecting data.json into the template"""
import json, os, re, subprocess
from datetime import datetime

BASE = os.path.dirname(__file__)
DATA_FILE = os.path.join(BASE, "data.json")
TEMPLATE = os.path.join(BASE, "index_template.html")
OUTPUT = os.path.join(BASE, "index.html")

def build():
    if not os.path.exists(DATA_FILE):
        print("data.json not found, running scraper first...")
        subprocess.run(["python3", os.path.join(BASE, "scraper.py")], check=True)

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    with open(TEMPLATE, "r", encoding="utf-8") as f:
        html = f.read()

    # Inject data
    data_js = json.dumps(data, ensure_ascii=False)
    html = re.sub(r'const raw = \[.*?\];', f'const raw = {data_js};', html, flags=re.DOTALL)
    html = html.replace("{{BUILD_TIME}}", datetime.now().strftime("%Y-%m-%d %H:%M"))

    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ Built index.html with {len(data)} records")

if __name__ == "__main__":
    build()
