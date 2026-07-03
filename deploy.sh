#!/bin/bash
# Daily scrape + push to GitHub
set -e
cd "$(dirname "$0")"

source "$(dirname "$0")/.env" 2>/dev/null || true
TOKEN="${GITHUB_TOKEN}"
REMOTE="https://mktcycy:${TOKEN}@github.com/mktcycy/igaming-dashboard.git"

echo "[$(date '+%Y-%m-%d %H:%M')] 開始每日爬蟲..."
python3 scraper.py

echo "重建 index.html..."
python3 build_ci.py

echo "推送至 GitHub..."
git remote set-url origin "$REMOTE"
git add data.json index.html
git diff --staged --quiet && echo "無新資料，跳過推送" && exit 0

git commit -m "chore: daily scrape $(date '+%Y-%m-%d')"
git push origin main

echo "✅ 完成！"
