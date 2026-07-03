#!/usr/bin/env python3
"""iGaming daily market news scraper — uses RSS feeds for reliability"""

import json, os, time, hashlib, re
from datetime import datetime, date, timezone
from email.utils import parsedate_to_datetime

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; iGaming-Monitor/1.0; RSS reader)"}
TIMEOUT = 15
BASE = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE, "data.json")

RSS_SOURCES = [
    "https://igamingbusiness.com/feed/",
    "https://igamingfuture.com/feed/",
    "https://agbrief.com/feed/",
    "https://www.yogonet.com/international/rss.xml",
    "https://www.igamingbusiness.com/casino-games/feed/",
]

CAT_RULES = [
    (["pagcor","philippines","philippine","pogo","kyc","aml","anti-money","regulation","law","license","compliance"], "菲律賓法規"),
    (["ai ","artificial intelligence","blockchain","crypto","nft","vr ","ar ","metaverse","5g","technology","tech"], "全球科技應用"),
    (["pg soft","pgsoft","jili","jdb","playtech","microgaming","cq9","fa chai","fachai","evolution","pragmatic","netent","hacksaw","nolimit","push gaming","relax gaming","blueprint"], "熱門廠商"),
    (["sigma","igb live","g2e","ice barcelona","sbc summit","casinobeats","event","summit","expo","conference","award"], "業界大事"),
]

VENDOR_MAP = {
    "PG Soft": ["pg soft","pgsoft","pocket games"],
    "JILI Games": ["jili"],
    "JDB Gaming": ["jdb"],
    "MG（Microgaming）": ["microgaming"],
    "Playtech（PT）": ["playtech"],
    "CQ9 Gaming": ["cq9"],
    "Fa Chai Gaming（FG）": ["fa chai","fachai"],
    "Evolution": ["evolution gaming","evolution"],
    "Pragmatic Play": ["pragmatic play"],
    "NetEnt": ["netent"],
    "PAGCOR": ["pagcor"],
    "SiGMA": ["sigma"],
    "Hacksaw Gaming": ["hacksaw"],
    "Nolimit City": ["nolimit city"],
}

HIGH_WORDS = ["launch","launches","record","ban","banned","regulation","billion","major","first","exclusive","new law","merger","acquisition","deal","partnership","approved","license"]
LOW_WORDS = ["reminder","minor","opinion","column","analysis"]

def guess_category(text):
    t = text.lower()
    for keywords, cat in CAT_RULES:
        if any(k in t for k in keywords):
            return cat
    return "業界趨勢"

def guess_importance(text, cat):
    t = text.lower()
    score = 3
    for w in HIGH_WORDS:
        if w in t: score = min(5, score + 1)
    for w in LOW_WORDS:
        if w in t: score = max(1, score - 1)
    if cat in ("菲律賓法規", "業界大事"): score = min(5, score + 1)
    return score

def extract_vendor(text):
    t = text.lower()
    for vendor, kws in VENDOR_MAP.items():
        if any(k in t for k in kws):
            return vendor
    return "市場動態"

def uid(url, title):
    return hashlib.md5(f"{url}{title}".encode()).hexdigest()[:12]

def parse_rss_date(date_str):
    if not date_str: return date.today().isoformat()
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.astimezone(timezone.utc).date().isoformat()
    except Exception:
        m = re.search(r'\d{4}-\d{2}-\d{2}', date_str)
        return m.group() if m else date.today().isoformat()

def scrape_rss(feed_url):
    articles = []
    try:
        r = requests.get(feed_url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.content, "xml")
        items = soup.find_all("item")
        for item in items[:20]:
            title = item.find("title")
            link = item.find("link")
            pub_date = item.find("pubDate")
            description = item.find("description")

            title_text = title.get_text(strip=True) if title else ""
            url = link.get_text(strip=True) if link else ""
            art_date = parse_rss_date(pub_date.get_text(strip=True) if pub_date else "")
            desc = BeautifulSoup(description.get_text() if description else "", "lxml").get_text(strip=True)[:200] if description else ""

            if not title_text or not url or len(title_text) < 10: continue

            summary = desc if desc else title_text
            cat = guess_category(title_text + " " + summary)
            vendor = extract_vendor(title_text + " " + summary)

            articles.append({
                "id": uid(url, title_text),
                "date": art_date,
                "cat": cat,
                "vendor": vendor,
                "game": title_text,
                "summary": summary[:300],
                "stars": guess_importance(title_text + " " + summary, cat),
                "url": url,
            })
    except Exception as e:
        print(f"  ✗ {feed_url}: {e}")
    return articles

def load_existing():
    if not os.path.exists(DATA_FILE): return []
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(records):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

def run():
    today = date.today().isoformat()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] iGaming 爬蟲啟動 — {today}")

    existing = load_existing()
    existing_ids = {r.get("id") for r in existing}
    new_records = []

    for feed_url in RSS_SOURCES:
        print(f"  RSS: {feed_url}")
        arts = scrape_rss(feed_url)
        added = 0
        for a in arts:
            if a["id"] in existing_ids: continue
            new_records.append(a)
            existing_ids.add(a["id"])
            added += 1
        print(f"    → {len(arts)} 筆，新增 {added} 筆")
        time.sleep(0.5)

    if new_records:
        all_records = existing + new_records
        all_records.sort(key=lambda r: r["date"], reverse=True)
        save_data(all_records)
        print(f"\n✅ 新增 {len(new_records)} 筆，資料庫共 {len(all_records)} 筆")
    else:
        print("ℹ️  今日無新資料（可能已是最新）")

    return len(new_records)

if __name__ == "__main__":
    run()
