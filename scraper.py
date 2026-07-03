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
TIMEOUT = 20
TIMEOUT_SLOW = 30   # for vendor RSS feeds that are slow to respond
MAX_AGE_DAYS = 180  # ignore articles older than 6 months
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
    # Asia Gaming Brief (Asia-focused, Philippines, Macau, Singapore)
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
    # Pragmatic Play official news (game launch announcements) — slow, uses extended timeout
    "https://pragmaticplay.com/en/feed/",
    # Thunderkick (new game releases)
    "https://www.thunderkick.com/feed/",
    # Spinomenal (new game & partnership news)
    "https://spinomenal.com/feed/",
    # BonusFinder (casino & game news)
    "https://www.bonusfinder.com/feed",
    # European Gaming — covers vendor product releases across all major suppliers
    "https://europeangaming.eu/portal/feed/",
    # European Gaming SLOT TAG — specifically tagged slot/game release articles
    "https://europeangaming.eu/portal/tag/slot/feed/",
    # iGB Affiliate — covers game launches and provider partnerships
    "https://www.igbaffiliate.com/feed/",
    # AffPapa — B2B iGaming deals and partnerships
    "https://www.affpapa.com/feed/",
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
    # 2. New game releases — broad coverage of launch/release patterns
    (["new slot","new game","new title","launches new","new casino game",
      "unleashes","unearths","new release","slot launch","new addition to portfolio",
      "launches a new","new instant","new scratchcard",
      "releases new","release new","introduces new","presents new",
      "unveils new","reveals new","debuts","just released","goes live",
      "now live","just launched","game launch","new offering",
      "newly released","latest slot","latest game","fresh slot",
      "slot release","game release","drops new","brand new slot",
      "brand new game","new video slot","new table game","new live game",
      "new jackpot slot","world premiere","global launch","soft launch",
      "has released","has launched","studio releases","provider releases",
      "releases its latest","launches its","presents its","unveils its",
      "new fish game","new arcade","new crash game","new live dealer",
      # Single-verb release patterns (almost always game launches in iGaming context)
      " releases "," unveils "," introduces "," premieres ",
      "drops its ","drops a ","expands portfolio","adds to portfolio",
      "portfolio with new","collaboration launch","week slot games",
      "game of the week","slot games releases","casino game release",
      "powered by onetouch","exclusive release"], "新遊戲"),
    # 3. Named game suppliers (vendor-specific business/partnership/expansion news)
    (["pg soft","pgsoft","pocket games soft",
      "jili ","jili games",
      "jdb gaming","jdb ",
      "playtech","play tech",
      "microgaming","micro gaming",
      "cq9 ","cq9 gaming",
      "fa chai","fachai","fa-chai",
      "evolution gaming","evolution live","evo gaming",
      "pragmatic play","pragmatic live",
      "netent","net ent",
      "hacksaw gaming","hacksaw ",
      "nolimit city","no limit city",
      "wazdan",
      "spinomenal",
      "thunderkick",
      "yggdrasil",
      "play'n go","playngo","play n go",
      "relax gaming",
      "push gaming",
      "bgaming","b-gaming",
      "betsoft",
      "blueprint gaming",
      "quickspin",
      "iron dog studio",
      "red tiger","red tiger gaming",
      "elk studios",
      "3 oaks gaming",
      "kalamba",
      # Asian/B2B focused vendors
      "sa gaming","sa live casino",
      "wm casino","wm live","wm gaming",
      "spade gaming","spadegaming",
      "skywind group","skywind gaming",
      "tada gaming","tadagaming",
      "booming games",
      "playson",
      "endorphina",
      "habanero systems","habanero ",
      "isoftbet","isoft bet",
      "high 5 games","high5games",
      "gpk platform","gpk gaming",
      "topplay","top play gaming",
      "netgame","net game entertainment",
      "reelplay","reel play",
      "games global","games global ",
      "igt ","igt gaming",
      "aristocrat",
      "playago"], "熱門廠商"),
    # 4. Technology (specific AI/blockchain/crypto terms only)
    (["artificial intelligence","ai-powered","ai prediction","blockchain",
      "cryptocurrency","crypto casino","nft ","metaverse","virtual reality",
      "machine learning","chatgpt","generative ai","web3 ",
      "responsible ai","gambling tech","igaming tech","platform innovation",
      "data analytics","digital transformation","fintech gambling"], "科技應用"),
    # 5. Asia market — non-Philippines
    (["macau ","macao ","singapore casino","singapore integrated",
      "japan casino","japan ir","vietnam gambl","cambodia casino",
      "thailand casino","myanmar gambl","korea gambl","hong kong racing",
      "malaysia casino","indonesia gambl",
      "asian market","asia pacific gaming","apac gaming",
      "southeast asia","east asia gaming","china gambl"], "亞洲市場"),
    # 6. Global regulation — specific bodies/policies only
    (["gambling commission","ukgc","malta gaming authority"," mga ","alderney",
      "kahnawake","isle of man gambl","responsible gambling","harm prevention",
      "safer gambling","deposit limit","gambling act","betting levy",
      "financial intelligence centre","gaming control board",
      "gaming authority","gaming licence","gaming license",
      "gambling oversight","gambling regulation","gambling reform","gambling review",
      "betting regulation","betting act","gaming regulator","regulated market",
      "anti-money laundering","aml compliance",
      "self-exclusion","problem gambling","player protection"], "全球法規"),
    # 7. Industry events and major deals
    (["sigma ","igb live","g2e ","ice london","ice barcelona","sbc summit",
      "casinobeats summit","igb affiliate","acquisition ","acquires ",
      "merger ","takeover","joint venture","ipo ","gaming award",
      "industry award","billion dollar deal",
      "strategic partnership","landmark deal","exclusive agreement",
      "record revenue","record breaking","market leader",
      "enters into agreement","signs deal","signs agreement",
      "sign agreement","sign a deal","forms alliance","inks deal",
      "enters deal","new partnership","partnership agreement",
      "global expansion","new market entry","enters market"], "業界大事"),
    # 8. WG Platform
    (["wg包網","wg baowang","wgbaowang","wg platform","wg遊戲","wg api"], "平台動態"),
]

VENDOR_MAP = {
    # ── 主要亞洲廠商 ──
    "PG Soft": ["pg soft","pgsoft","pocket games soft"],
    "JILI Games": ["jili games","jili "],
    "JDB Gaming": ["jdb gaming","jdb "],
    "CQ9 Gaming": ["cq9 gaming","cq9 "],
    "Fa Chai Gaming (FG)": ["fa chai","fachai","fa-chai"],
    "SA Gaming": ["sa gaming","sa live casino"],
    "WM Casino": ["wm casino","wm live","wm gaming"],
    "Spade Gaming (SG)": ["spade gaming","spadegaming"],
    "Skywind (SW)": ["skywind group","skywind gaming","skywind "],
    "Tada Gaming": ["tada gaming","tadagaming"],
    "GPK / TopPlay (TP)": ["gpk platform","gpk gaming"," gpk ","topplay","top play gaming"],
    # ── 主要歐美廠商 ──
    "Microgaming (MG)": ["microgaming","micro gaming"],
    "Playtech (PT)": ["playtech","play tech"],
    "Evolution (EVO)": ["evolution gaming","evolution live","evo gaming"],
    "Pragmatic Play (PP)": ["pragmatic play","pragmatic live"],
    "NetEnt": ["netent","net ent"],
    "Hacksaw Gaming": ["hacksaw gaming","hacksaw "],
    "Nolimit City": ["nolimit city","no limit city"],
    "Yggdrasil": ["yggdrasil"],
    "Play'n GO": ["play'n go","playngo","play n go"],
    "Red Tiger": ["red tiger","red tiger gaming"],
    "Wazdan": ["wazdan"],
    "Spinomenal": ["spinomenal"],
    "BGaming (BG)": ["bgaming","b-gaming"],
    "Betsoft": ["betsoft"],
    "Relax Gaming": ["relax gaming"],
    "Thunderkick": ["thunderkick"],
    "Push Gaming": ["push gaming"],
    "Blueprint Gaming": ["blueprint gaming"],
    "Quickspin": ["quickspin"],
    "Booming Games": ["booming games"],
    "Habanero": ["habanero systems","habanero "],
    "Endorphina": ["endorphina"],
    "iSoftBet": ["isoftbet","isoft bet"],
    "3 Oaks Gaming": ["3 oaks gaming"],
    "Games Global": ["games global"],
    # ── 其他機構 ──
    "PAGCOR": ["pagcor"],
    "WG包網": ["wg包網","wg baowang","wgbaowang","wg platform"],
    "SiGMA": ["sigma "],
}

HIGH_WORDS = ["launch","launches","record","ban","banned","regulation","billion","major","first","exclusive","new law","merger","acquisition","deal","partnership","approved","license","jackpot","milestone","breakthrough","surge","growth"]
LOW_WORDS = ["reminder","minor","opinion","column","analysis","roundup","preview"]

# Relevance filter — keeps only iGaming-related articles
IGAMING_TERMS_EN = [
    # Core product terms
    "casino","slot","gaming","gambl","bet ","poker","lottery","wagering",
    "igaming","i-gaming","sportsbook","sportbook","online game",
    "jackpot","roulette","blackjack","baccarat","live dealer","live casino",
    # Regulatory bodies
    "pagcor","ceza","mga ","ukgc","gambling commission",
    "gaming authority","gaming control","gaming regulator",
    # Major vendors (appear in partnership/launch news without "slot")
    "pragmatic play","pg soft","pgsoft","playtech","microgaming","evolution ",
    "jili ","jdb ","cq9 ","netent","yggdrasil","hacksaw","nolimit city",
    "spinomenal","thunderkick","wazdan","bgaming","betsoft","spade gaming",
    "sa gaming","wm casino","skywind","tada gaming","relax gaming",
    "ela games","ainsworth","zitro ","igt ","aristocrat","light & wonder",
    "scientific games","konami gaming",
    # Major operators / media companies
    "draftkings","fanduel","flutter","entain","888 ","evoke plc","betmgm",
    "william hill","ladbrokes","betfair","paddy power","bet365","pointsbet",
    "hard rock casino","mgm resort","wynn resort","las vegas sands",
    "melco resort","galaxy entertainment","sands corp",
    # Prediction markets (gambling-adjacent)
    "kalshi","prediction market","polymarket",
    # Industry media / events / trade terms
    "igb ","egr ","sbc ","sigma ","casinobeats","agbrief","calvinayre",
    "gross gaming revenue","ggr ","ngr ","handle ","revenue gambling",
    "iGaming affiliate","sports betting","online betting","online wagering",
    "operator revenue","casino revenue","gaming revenue","gaming market",
]
IGAMING_TERMS_ZH = [
    "遊戲", "賭場", "老虎機", "娛樂城", "彩票", "博彩", "廠商", "電子遊藝",
    "運動彩券", "彩券", "博奕", "賭博", "押注", "賠率",
]

def is_relevant(title_en, summary_en="", summary_zh=""):
    """Check if an article is iGaming-related using English + Chinese text."""
    en = (title_en + " " + summary_en).lower()
    if any(t in en for t in IGAMING_TERMS_EN):
        return True
    if any(t in summary_zh for t in IGAMING_TERMS_ZH):
        return True
    return False


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
    """Re-run category classification using English fields (rules are English keywords)."""
    updated = 0
    for r in records:
        # Prefer English fields so keyword rules match correctly
        en_title = r.get("game_en") or r.get("game", "")
        en_summary = r.get("summary_en") or ""  # may be empty for legacy records
        text = en_title + " " + en_summary
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
    # Use extended timeout for known slow vendor feeds
    timeout = TIMEOUT_SLOW if "pragmaticplay.com" in feed_url else TIMEOUT
    try:
        r = requests.get(feed_url, headers=HEADERS, timeout=timeout)
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

            # Skip articles with no iGaming relevance
            if not is_relevant(title_raw, desc_raw):
                continue

            # Skip articles older than MAX_AGE_DAYS
            try:
                from datetime import timedelta
                cutoff = (date.today() - timedelta(days=MAX_AGE_DAYS)).isoformat()
                if art_date < cutoff:
                    continue
            except Exception:
                pass

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
                "summary_en": summary_raw,  # keep English for future reclassification
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
                "summary_en": desc_raw,
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


def purge_irrelevant(records):
    """Remove records with no iGaming relevance (checks English title + summary + Chinese summary)."""
    before = len(records)
    cleaned = []
    for r in records:
        if is_relevant(
            r.get("game_en") or r.get("game", ""),
            r.get("summary_en") or "",
            r.get("summary") or "",
        ):
            cleaned.append(r)
    return cleaned, before - len(cleaned)


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

    # Remove off-topic records (casino.org crime/sports articles etc.)
    all_records, purged = purge_irrelevant(all_records)
    if purged:
        print(f"  → 移除非相關內容 {purged} 筆")

    all_records.sort(key=lambda r: r["date"], reverse=True)
    save_data(all_records)
    print(f"\n✅ 新增 {len(new_records)} 筆，資料庫共 {len(all_records)} 筆")

    return len(new_records)


if __name__ == "__main__":
    run()
