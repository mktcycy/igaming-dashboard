#!/usr/bin/env python3
"""iGaming daily market news scraper — RSS feeds + translation to Traditional Chinese"""

import json, os, time, hashlib, re
from datetime import datetime, date, timezone
from email.utils import parsedate_to_datetime

import requests
from bs4 import BeautifulSoup

try:
    from deep_translator import GoogleTranslator
    TRANSLATE = True
except ImportError:
    TRANSLATE = False
    print("deep_translator not installed, skipping translation")

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; iGaming-Monitor/1.0; RSS reader)"}
TIMEOUT = 15
BASE = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE, "data.json")

RSS_SOURCES = [
    # iGaming Business (4 channels)
    "https://igamingbusiness.com/feed/",
    "https://igamingbusiness.com/asia/feed/",
    "https://igamingbusiness.com/legal-compliance/feed/",
    "https://igamingbusiness.com/casino-games/feed/",
    # iGaming Future
    "https://igamingfuture.com/feed/",
    # Asia Gaming Brief
    "https://agbrief.com/feed/",
    # Yogonet International
    "https://www.yogonet.com/international/rss.xml",
    # Casino.org
    "https://casino.org/news/feed/",
    # EGR Global
    "https://egr.global/feed/",
    # SBC News (major B2B — covers vendor launches, regulation)
    "https://sbcnews.co.uk/feed/",
    # Casino Beats (excellent for new game releases)
    "https://casinobeats.com/feed/",
    # iGB (iGaming Business sister brand)
    "https://igamingbusiness.com/igaming/feed/",
    # Pragmatic Play official news (game launch announcements)
    "https://pragmaticplay.com/en/feed/",
    "https://pragmaticplay.com/en/news/rss/",
    # Thunderkick (new game releases)
    "https://www.thunderkick.com/feed/",
    # Spinomenal (new game & partnership news)
    "https://spinomenal.com/feed/",
    # BonusFinder (casino & game news)
    "https://www.bonusfinder.com/feed",
]

# Sites to monitor for page-content changes (no RSS available)
PAGE_MONITORS = [
    {
        "id": "wg-baowang",
        "name": "WG包網官網",
        "url": "https://www.wgbaowang.net/zh-TW.html",
        "vendor": "WG包網",
        "cat": "平台動態",
        "hash_file": "wg_page_hash.txt",
    },
]

CAT_RULES = [
    # 1. Philippines — ONLY with explicit PH entities
    (["pagcor","pogo ","philippine ","philippines ","pcso ","ceza "], "菲律賓市場"),
    # 2. New game releases — specific launch keywords
    (["new slot","new game","new title","launches new","new casino game",
      "unleashes","unearths","new release","slot launch","new addition to portfolio",
      "launches a ","new instant","new scratchcard"], "新遊戲"),
    # 3. Named game suppliers (business/partnership/expansion news)
    (["pg soft","pgsoft","jili ","jdb gaming","playtech","microgaming",
      "cq9 ","fa chai","fachai","evolution gaming","pragmatic play","netent",
      "hacksaw gaming","nolimit city","wazdan","spinomenal","thunderkick",
      "yggdrasil","play'n go","playngo","relax gaming","push gaming",
      "bgaming","betsoft","blueprint gaming","quickspin","iron dog studio",
      "red tiger","elk studios","3 oaks gaming","kalamba"], "熱門廠商"),
    # 4. Technology (specific AI/blockchain/crypto terms only)
    (["artificial intelligence","ai-powered","ai prediction","blockchain",
      "cryptocurrency","crypto casino","nft ","metaverse","virtual reality",
      "machine learning","chatgpt","generative ai","web3 "], "科技應用"),
    # 5. Asia market — non-Philippines
    (["macau ","macao ","singapore casino","singapore integrated",
      "japan casino","japan ir","vietnam gambl","cambodia casino",
      "thailand casino","myanmar gambl","korea gambl","hong kong racing",
      "malaysia casino","indonesia gambl"], "亞洲市場"),
    # 6. Global regulation — specific bodies/policies only
    (["gambling commission","ukgc","malta gaming authority"," mga ","alderney",
      "kahnawake","isle of man gambl","responsible gambling","harm prevention",
      "safer gambling","deposit limit","gambling act","betting levy",
      "financial intelligence centre","gaming control board",
      "gaming authority"], "全球法規"),
    # 7. Industry events and major deals
    (["sigma ","igb live","g2e ","ice london","ice barcelona","sbc summit",
      "casinobeats summit","igb affiliate","acquisition ","acquires ",
      "merger ","takeover","joint venture","ipo ","gaming award",
      "industry award","billion dollar deal"], "業界大事"),
    # 8. WG Platform
    (["wg包網","wg baowang","wgbaowang","wg platform","wg遊戲","wg api"], "平台動態"),
]

VENDOR_MAP = {
    "PG Soft": ["pg soft","pgsoft","pocket games soft"],
    "JILI Games": ["jili"],
    "JDB Gaming": ["jdb"],
    "MG（Microgaming）": ["microgaming"],
    "Playtech（PT）": ["playtech"],
    "CQ9 Gaming": ["cq9"],
    "Fa Chai Gaming（FG）": ["fa chai","fachai"],
    "Evolution": ["evolution gaming","evolution live"],
    "Pragmatic Play": ["pragmatic play"],
    "NetEnt": ["netent"],
    "PAGCOR": ["pagcor"],
    "WG包網": ["wg包網","wg baowang","wgbaowang","wg platform"],
    "SiGMA": ["sigma"],
    "Hacksaw Gaming": ["hacksaw"],
    "Nolimit City": ["nolimit city"],
    "Yggdrasil": ["yggdrasil"],
    "Play'n GO": ["play'n go","playngo"],
    "Red Tiger": ["red tiger"],
    "Wazdan": ["wazdan"],
    "Spinomenal": ["spinomenal"],
    "BGaming": ["bgaming"],
    "Betsoft": ["betsoft"],
    "Relax Gaming": ["relax gaming"],
}

HIGH_WORDS = ["launch","launches","record","ban","banned","regulation","billion","major","first","exclusive","new law","merger","acquisition","deal","partnership","approved","license","jackpot","milestone","breakthrough","surge","growth"]
LOW_WORDS = ["reminder","minor","opinion","column","analysis","roundup","preview"]


def is_english(text):
    """Simple heuristic: >65% ASCII chars = likely English."""
    if not text:
        return False
    ascii_count = sum(1 for c in text if ord(c) < 128)
    return ascii_count / len(text) > 0.65


def translate_zh(text, max_len=500):
    if not text or not TRANSLATE:
        return text
    if not is_english(text):
        return text
    try:
        chunk = text[:max_len]
        result = GoogleTranslator(source='auto', target='zh-TW').translate(chunk)
        if not result:
            return text
        # Discard if translation looks like an error page
        if result.strip().startswith('Error') or '500' in result[:30]:
            return text
        return result.strip()
    except Exception:
        return text


def guess_category(text):
    t = " " + text.lower() + " "
    for keywords, cat in CAT_RULES:
        if any(k in t for k in keywords):
            return cat
    return "市場趨勢"


def reclassify_all(records):
    """Re-run category classification on all existing records."""
    updated = 0
    for r in records:
        text = (r.get("game_en") or r.get("game", "")) + " " + r.get("summary", "")
        new_cat = guess_category(text)
        if new_cat != r.get("cat"):
            r["cat"] = new_cat
            updated += 1
    return updated


def guess_importance(text, cat):
    t = text.lower()
    score = 3
    for w in HIGH_WORDS:
        if w in t:
            score = min(5, score + 1)
    for w in LOW_WORDS:
        if w in t:
            score = max(1, score - 1)
    if cat in ("菲律賓市場", "業界大事", "全球法規", "新遊戲"):
        score = min(5, score + 1)
    return score


def extract_vendor(text):
    t = text.lower()
    for vendor, kws in VENDOR_MAP.items():
        if any(k in t for k in kws):
            return vendor
    return "市場動態"


def uid(url, title):
    return hashlib.md5(f"{url}{title}".encode()).hexdigest()[:12]


def clean(text):
    return re.sub(r'\s+', ' ', text or '').strip()


def parse_rss_date(date_str):
    if not date_str:
        return date.today().isoformat()
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.astimezone(timezone.utc).date().isoformat()
    except Exception:
        m = re.search(r'\d{4}-\d{2}-\d{2}', date_str)
        return m.group() if m else date.today().isoformat()


def scrape_rss(feed_url, existing_ids):
    articles = []
    try:
        r = requests.get(feed_url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.content, "xml")
        items = soup.find_all("item")
        for item in items[:30]:
            title_tag = item.find("title")
            link_tag = item.find("link")
            pub_date_tag = item.find("pubDate")
            description_tag = item.find("description")

            title_raw = clean(title_tag.get_text() if title_tag else "")
            url = clean(link_tag.get_text() if link_tag else "")
            art_date = parse_rss_date(clean(pub_date_tag.get_text() if pub_date_tag else ""))
            desc_html = description_tag.get_text() if description_tag else ""
            desc_raw = clean(BeautifulSoup(desc_html, "lxml").get_text())[:300]

            if not title_raw or not url or len(title_raw) < 10:
                continue

            item_uid = uid(url, title_raw)
            if item_uid in existing_ids:
                continue

            summary_raw = desc_raw if desc_raw else title_raw

            # Translate to Chinese
            title_zh = translate_zh(title_raw)
            summary_zh = translate_zh(summary_raw)

            cat = guess_category(title_raw + " " + summary_raw)
            vendor = extract_vendor(title_raw + " " + summary_raw)

            articles.append({
                "id": item_uid,
                "date": art_date,
                "cat": cat,
                "vendor": vendor,
                "game": title_zh,
                "game_en": title_raw,
                "summary": summary_zh,
                "stars": guess_importance(title_raw + " " + summary_raw, cat),
                "url": url,
            })
            time.sleep(0.05)  # small delay between translations
    except Exception as e:
        print(f"  ✗ {feed_url}: {e}")
    return articles


def scrape_vendor_html(source, existing_ids):
    """Scrape vendor press release pages that lack RSS."""
    articles = []
    try:
        r = requests.get(source["url"], headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.content, "lxml")
        items = soup.select(source["item_sel"])[:15]
        for item in items:
            title_tag = item.select_one(source["title_sel"])
            link_tag = item.select_one(source["link_sel"])
            desc_tag = item.select_one(source["desc_sel"])

            title_raw = clean(title_tag.get_text() if title_tag else "")
            href = link_tag.get("href", "") if link_tag else ""
            if href and not href.startswith("http"):
                from urllib.parse import urljoin
                href = urljoin(source["url"], href)
            desc_raw = clean(desc_tag.get_text() if desc_tag else "")[:300]

            if not title_raw or not href or len(title_raw) < 10:
                continue

            item_uid = uid(href, title_raw)
            if item_uid in existing_ids:
                continue

            summary_raw = desc_raw if desc_raw else title_raw
            title_zh = translate_zh(title_raw)
            summary_zh = translate_zh(summary_raw)

            cat = guess_category(title_raw + " " + summary_raw)
            vendor = extract_vendor(source["name"] + " " + title_raw + " " + summary_raw)

            articles.append({
                "id": item_uid,
                "date": date.today().isoformat(),
                "cat": cat,
                "vendor": vendor,
                "game": title_zh,
                "game_en": title_raw,
                "summary": summary_zh,
                "stars": guess_importance(title_raw + " " + summary_raw, cat),
                "url": href,
            })
    except Exception as e:
        print(f"  ✗ {source['name']}: {e}")
    return articles


def monitor_page(source, existing_ids):
    """Detect content changes on a static page with no RSS."""
    results = []
    hash_path = os.path.join(BASE, source["hash_file"])
    try:
        r = requests.get(source["url"], headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.content, "lxml")
        # Extract main text content (strip scripts/styles)
        for tag in soup(["script", "style", "meta", "head"]):
            tag.decompose()
        text = clean(soup.get_text())
        content_hash = hashlib.md5(text.encode()).hexdigest()

        prev_hash = ""
        if os.path.exists(hash_path):
            with open(hash_path) as f:
                prev_hash = f.read().strip()

        with open(hash_path, "w") as f:
            f.write(content_hash)

        if prev_hash and content_hash != prev_hash:
            today = date.today().isoformat()
            title = f"{source['name']} 內容有更新"
            item_uid = uid(source["url"], today + content_hash[:6])
            if item_uid not in existing_ids:
                summary_zh = f"{source['name']}官網於 {today} 偵測到頁面內容變動，請前往確認最新資訊。"
                results.append({
                    "id": item_uid,
                    "date": today,
                    "cat": source["cat"],
                    "vendor": source["vendor"],
                    "game": title,
                    "game_en": title,
                    "summary": summary_zh,
                    "stars": 4,
                    "url": source["url"],
                })
        elif not prev_hash:
            print(f"    → 首次紀錄 {source['name']} 基準值")
    except Exception as e:
        print(f"  ✗ {source['name']}: {e}")
    return results


def load_existing():
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_data(records):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def translate_existing(records):
    """Back-translate existing English records that haven't been translated yet."""
    updated = 0
    for r in records:
        if r.get("game_en"):
            continue  # already processed
        game = r.get("game", "")
        summary = r.get("summary", "")
        if is_english(game):
            r["game_en"] = game
            r["game"] = translate_zh(game)
            r["summary"] = translate_zh(summary)
            updated += 1
            time.sleep(0.05)
    return updated


def run():
    today = date.today().isoformat()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] iGaming 爬蟲啟動 — {today}")
    print(f"Translation: {'ON (zh-TW)' if TRANSLATE else 'OFF'}")

    existing = load_existing()
    existing_ids = {r.get("id") for r in existing}
    new_records = []

    # RSS sources
    for feed_url in RSS_SOURCES:
        print(f"  RSS: {feed_url}")
        arts = scrape_rss(feed_url, existing_ids)
        for a in arts:
            new_records.append(a)
            existing_ids.add(a["id"])
        print(f"    → {len(arts)} 新筆")
        time.sleep(0.5)

    # Page change monitors (sites without RSS)
    for src in PAGE_MONITORS:
        print(f"  監控: {src['name']}")
        arts = monitor_page(src, existing_ids)
        for a in arts:
            new_records.append(a)
            existing_ids.add(a["id"])
        if arts:
            print(f"    → ⚠️  偵測到頁面變動！")
        time.sleep(1)

    # Back-translate existing English records
    if TRANSLATE and existing:
        print("\n翻譯既有英文資料中...")
        updated = translate_existing(existing)
        print(f"  → 翻譯 {updated} 筆舊資料")

    # Re-classify ALL records with updated rules
    print("\n重新分類所有資料...")
    all_records = existing + new_records
    reclassified = reclassify_all(all_records)
    print(f"  → 更新分類 {reclassified} 筆")

    all_records.sort(key=lambda r: r["date"], reverse=True)
    save_data(all_records)
    print(f"\n✅ 新增 {len(new_records)} 筆，資料庫共 {len(all_records)} 筆")

    return len(new_records)


if __name__ == "__main__":
    run()
