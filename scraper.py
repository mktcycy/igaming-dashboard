#!/usr/bin/env python3
"""iGaming daily market news scraper — RSS feeds + translation to Traditional Chinese"""

import json, os, time, hashlib, re
from datetime import datetime, date, timezone, timedelta
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
    # ── 亞洲博彩專業媒體（加強亞洲市場/廠商覆蓋） ──
    # GGRAsia — 亞太博彩重量級媒體（澳門/菲律賓/日本/東南亞）
    "https://www.ggrasia.com/feed/",
    # Inside Asian Gaming (IAG) — 亞洲博彩產業深度報導
    "https://asgam.com/feed/",
    # Gambling Insider — 全球 B2B，含亞洲廠商/市場動態
    "https://www.gamblinginsider.com/feed",
    # ── 新產品追蹤 / 全球產業（亞洲到歐美洲） ──
    # SlotBeats — 專注 slot/遊戲新品發布（各家廠商新產品追蹤主力）
    "https://slotbeats.com/feed/",
    # G3 Newswire — 全球博彩產業（含亞洲/拉美/歐洲新品與合作）
    "https://g3newswire.com/feed/",
    # Yogonet International（拉丁美洲/全球，Americas 覆蓋主力）
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
    # Microgaming official news (game & product launches)
    "https://www.microgaming.co.uk/feed/",
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
    # ── 中文科技媒體（含博彩/遊戲相關報導） ──
    # 未來商務 — 數位時代旗下商務科技頻道
    "https://fc.bnext.com.tw/rss",
    # 科技報橘 TechOrange — 科技趨勢與新創報導
    "https://buzzorange.com/techorange/feed/",
    # TechNews 科技新報 — 科技與 AI 新聞
    "https://technews.tw/feed/",
    # IT之家 — 中國科技資訊媒體
    "https://www.ithome.com/rss/",
    # TechCrunch — 全球科技新創媒體
    "https://techcrunch.com/feed/",
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
    # 4. Technology & Marketing (AI, digital marketing, brand campaigns)
    (["artificial intelligence","ai-powered","ai prediction","blockchain",
      "cryptocurrency","crypto casino","nft ","metaverse","virtual reality",
      "machine learning","chatgpt","generative ai","web3 ",
      "responsible ai","gambling tech","igaming tech","platform innovation",
      "data analytics","digital transformation","fintech gambling",
      # Digital marketing / brand marketing
      "affiliate marketing","performance marketing","digital marketing",
      "brand campaign","brand awareness","marketing campaign","marketing strategy",
      "influencer","seo ","sem ","social media marketing","content marketing",
      "player acquisition","player retention","crm ","loyalty program",
      "gamification","user experience","ux design","conversion rate",
      "paid media","programmatic","email marketing","push notification",
      "media buy","media buying","media partnership",
      "brand ambassador","sponsorship deal","esports sponsor",
      # 品牌代言 / 體育贊助（行銷性質）
      "ambassador","global ambassador","brand ambassador",
      "sponsorship","title sponsor","kit partner","shirt sponsor",
      "training wear","sleeve sponsor","official partner of",
      "fan experience","fan engagement","fan activation"], "行銷科技"),
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
      "self-exclusion","problem gambling","player protection",
      # 監理處分 / 裁罰 / 稅務 / 新規（執法與法規動態）
      "banned by","gambling regulator"," regulator ","regulatory",
      "fined","penalty","settlement","settle probe","regulator probe",
      "aml ","anti-money","fatf","new rules for","adds new rules",
      "gambling tax","betting tax","tax on gambling","licence fee",
      "compliance"], "全球法規"),
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
      "global expansion","new market entry","enters market",
      # 併購 / 聯盟 / 人事 / 授權合作 / 市場擴張
      "alliance","to acquire"," acquires ","acquired by","merges with",
      "appoints","appointment","names new","new ceo","new chairman",
      "new chair","takes chair","steps down","resigns","joins as",
      "licensing deal","license deal","distribution deal","content deal",
      "aggregation deal","secures license","secures licence",
      "expands presence","expands into","expands its presence",
      "market entry","goes public","stock exchange listing",
      "profit guidance","lifts guidance"], "業界大事"),
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

# 排除詞：社會/刑案/天災/花邊等「不是產業情報」的雜訊。
# 即使文章含博彩關鍵字（如提到某賭場），只要命中這些詞就當作雜訊剔除。
EXCLUDE_TERMS_EN = [
    # 兇殺 / 刑案 / 法庭社會新聞
    "murder", "homicide", "manslaughter", " rape", "sexual assault",
    "stabb", "shooting", "shot dead", "gunman", "gunmen", "kidnap",
    "human traffick", "suicide", "overdose", "found dead", "body found",
    "on trial over", "goes on trial", "stands trial", "trial over",
    "obituary", "died aged", "passed away", "dies at",
    "sex scandal", "epstein", "sexual misconduct", "plead guilty",
    # 個人刑案花邊（高精準詞，避免誤傷「業者面臨刑責」類法規新聞）
    # 註：不用「monk」會誤傷 Monkeys/Monkey 遊戲名；僧侶案已由 僧侶/性勒索/sextortion 涵蓋
    "embezzl", "sextortion", "blackmail", "ponzi",
    # 天災 / 意外事故
    "earthquake", "hurricane", "wildfire", "tsunami", "plane crash",
    "typhoon", "landslide",
    # 純美國預測市場 / 金融話題（非博彩產業）
    "kalshi", "polymarket", "prediction market",
]
EXCLUDE_TERMS_ZH = [
    "謀殺", "兇殺", "命案", "性侵", "槍擊", "槍殺", "綁架", "自殺",
    "遺體", "屍體", "受審", "判刑", "入獄", "地震", "颱風", "海嘯", "山崩",
    # 個人刑案花邊（高精準詞；不放「入獄/監禁/判刑」等會誤傷法規新聞的泛詞）
    "性勒索", "僧侶", "僧人",
]

def is_excluded(title_en, summary_en="", text_zh=""):
    """命中排除詞（刑案/天災/花邊）即回傳 True，代表這篇是雜訊。"""
    en = (title_en + " " + summary_en).lower()
    if any(t in en for t in EXCLUDE_TERMS_EN):
        return True
    if any(t in text_zh for t in EXCLUDE_TERMS_ZH):
        return True
    return False


def is_relevant(title_en, summary_en="", summary_zh=""):
    """Check if an article is iGaming-related using English + Chinese text."""
    # 先剔除雜訊：即使含博彩關鍵字，命中排除詞就不算相關
    if is_excluded(title_en, summary_en, summary_zh):
        return False
    en = (title_en + " " + summary_en).lower()
    if any(t in en for t in IGAMING_TERMS_EN):
        return True
    if any(t in summary_zh for t in IGAMING_TERMS_ZH):
        return True
    return False


def is_english(text):
    """判斷是否仍為未翻譯英文。含任何中日韓文字即視為已翻譯（避免被品牌/人名等
    大量拉丁字母的『已翻譯標題』誤判為英文而重複翻譯）。"""
    if not text:
        return False
    if re.search(r'[一-鿿぀-ヿ]', text):
        return False
    ascii_count = sum(1 for c in text if ord(c) < 128)
    return ascii_count / len(text) > 0.65


def translate_zh(text, max_len=500):
    if not text or not TRANSLATE:
        return text
    if not is_english(text):
        return text
    chunk = text[:max_len]
    # 重試三次並拉長退避，避免整批被 Google 限流造成大量未翻譯
    for attempt in range(3):
        try:
            result = GoogleTranslator(source='auto', target='zh-TW').translate(chunk)
            # 只在明確錯誤字串時才拒收（避免翻譯結果內含數字 500 被誤判為 HTTP 500）
            low = (result or "").strip().lower()
            if result and not low.startswith('error') and not low.startswith('<'):
                return result.strip()
        except Exception:
            pass
        time.sleep(0.6 * (attempt + 1))
    return text


def guess_category(text):
    t = " " + text.lower() + " "
    for keywords, cat in CAT_RULES:
        if any(k in t for k in keywords):
            return cat
    return "市場趨勢"


# 這些來源的分類由爬蟲權威決定，reclassify 不覆蓋
# （CQ9 用 category_id；PG Soft /games/ 頁本質即新遊戲）
_AUTHORITATIVE_CAT_DOMAINS = ["cq9gaming.com", "pgsoft.com/games/"]


def reclassify_all(records):
    """Re-run category classification using English fields (rules are English keywords)."""
    updated = 0
    for r in records:
        # Skip records from scrapers that set authoritative categories
        if any(d in r.get("url", "") for d in _AUTHORITATIVE_CAT_DOMAINS):
            continue
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


# 合法 vendor 標籤集合：VENDOR_MAP 正式名稱 + 特殊爬蟲設定值
_VALID_VENDORS = set(VENDOR_MAP.keys()) | {"市場動態"}


def normalize_vendors(records):
    """修正 vendor 欄位：舊資料殘留亂七八糟的標籤（如「反洗錢法」「AI應用」「市場規模」）
    重新以英文原文比對 VENDOR_MAP 正規化；比對不到就歸「市場動態」。
    已由官方爬蟲明確標記的（SA Gaming/WG包網）本就是合法值，會保留。"""
    fixed = 0
    for r in records:
        cur = r.get("vendor") or ""
        if cur in _VALID_VENDORS:
            continue
        text = (r.get("game_en") or r.get("game", "")) + " " + (r.get("summary_en") or "")
        new_vendor = extract_vendor(text)
        if new_vendor != cur:
            r["vendor"] = new_vendor
            fixed += 1
    return fixed


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
            # For Chinese articles, pass text as summary_zh so ZH keywords are checked
            if is_english(title_raw):
                if not is_relevant(title_raw, desc_raw):
                    continue
            else:
                if not is_relevant("", "", title_raw + " " + desc_raw):
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


_CQ9_CAT = {47: "新遊戲", 46: "熱門廠商", 48: "業界大事", 49: "科技應用", 50: "亞洲市場", 51: "市場趨勢"}


def scrape_cq9(existing_ids):
    """Scrape CQ9 Gaming news via embedded __NEXT_DATA__ JSON."""
    articles = []
    try:
        r = requests.get("https://cq9gaming.com/news", headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.DOTALL)
        if not match:
            raise ValueError("__NEXT_DATA__ not found")
        data = json.loads(match.group(1))
        items = data["props"]["pageProps"]["newsListData"]

        from datetime import timedelta
        cutoff = (date.today() - timedelta(days=MAX_AGE_DAYS)).isoformat()

        for item in items:
            art_date = (item.get("date") or "")[:10]
            if art_date < cutoff:
                continue

            title_raw = clean(item.get("title") or "")
            if not title_raw or len(title_raw) < 6:
                continue

            art_url = f"https://cq9gaming.com/news/{item['id']}"
            item_uid = uid(art_url, title_raw)
            if item_uid in existing_ids:
                continue

            # Extract plain text from editor_content HTML
            html_body = (item.get("data") or {}).get("editor_content") or ""
            summary_raw = clean(BeautifulSoup(html_body, "lxml").get_text())[:300] if html_body else title_raw

            if not is_relevant(title_raw, summary_raw):
                continue

            title_zh = translate_zh(title_raw)
            summary_zh = translate_zh(summary_raw)

            # Use CQ9's own category_id as the primary signal; fallback to keyword rules
            cat = _CQ9_CAT.get(item.get("category_id"), guess_category(title_raw + " " + summary_raw))
            vendor = extract_vendor("CQ9 Gaming " + title_raw + " " + summary_raw)

            articles.append({
                "id": item_uid,
                "date": art_date,
                "cat": cat,
                "vendor": vendor,
                "game": title_zh,
                "game_en": title_raw,
                "summary": summary_zh,
                "summary_en": summary_raw,
                "stars": guess_importance(title_raw + " " + summary_raw, cat),
                "url": art_url,
            })
            time.sleep(0.05)
    except Exception as e:
        print(f"  ✗ CQ9 Gaming: {e}")
    return articles


def _og(soup, prop):
    tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
    return clean(tag.get("content", "")) if tag else ""


def scrape_sa_gaming(existing_ids):
    """SA Gaming 官網新聞稿：sitemap 取 /press/ 連結，逐頁抓 og:title（靜態可讀）。

    PG/JILI/Tada 等官網為 JS SPA 靜態抓不到（保留方案 B）；SA 的新聞稿頁有
    server-side og 標籤，故可直接爬取，作為亞洲廠商第一手來源之一。
    """
    articles = []
    try:
        r = requests.get("https://www.sa-gaming.com/sitemap.xml", headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.content, "xml")
        press_urls = [clean(loc.get_text()) for loc in soup.find_all("loc")
                      if "/press/" in loc.get_text() or "/blog/" in loc.get_text()]
        for art_url in press_urls[:20]:
            title_slug = art_url.rstrip("/").split("/")[-1].replace("-", " ")
            item_uid = uid(art_url, title_slug)
            if item_uid in existing_ids:
                continue
            try:
                pr = requests.get(art_url, headers=HEADERS, timeout=TIMEOUT)
                pr.raise_for_status()
                psoup = BeautifulSoup(pr.content, "lxml")
                title_raw = _og(psoup, "og:title") or clean(psoup.title.get_text() if psoup.title else "")
                desc_raw = _og(psoup, "og:description")[:300]
            except Exception:
                continue
            # 去掉品牌前綴「SA Gaming | 」讓標題乾淨
            title_raw = re.sub(r'^SA ?Gaming\s*[|｜:-]\s*', '', title_raw).strip()
            if not title_raw or len(title_raw) < 6:
                continue
            summary_raw = desc_raw or title_raw
            title_zh = translate_zh(title_raw)
            summary_zh = translate_zh(summary_raw)
            cat = guess_category("SA Gaming " + title_raw + " " + summary_raw)
            articles.append({
                "id": item_uid,
                "date": date.today().isoformat(),
                "cat": cat,
                "vendor": "SA Gaming",
                "game": title_zh,
                "game_en": title_raw,
                "summary": summary_zh,
                "summary_en": summary_raw,
                "stars": guess_importance(title_raw + " " + summary_raw, cat),
                "url": art_url,
            })
            time.sleep(0.1)
    except Exception as e:
        print(f"  ✗ SA Gaming: {e}")
    return articles


def _nuxt_field(blob, key):
    """從 Nuxt 內嵌物件 window.__NUXT__（key 未加引號）抓取字串欄位值。"""
    m = re.search(r'[,{]' + key + r':"((?:[^"\\]|\\.)*)"', blob)
    return m.group(1) if m else ""


def scrape_pgsoft(existing_ids):
    """PG Soft 官網（Nuxt.js SSR）：sitemap 取最新 /games/ 與 /news/，
    直接解析頁面內嵌的 window.__NUXT__ 物件抓標題/日期/說明（靜態可讀，無需瀏覽器）。

    方案 B 試點：PG 官網雖為 JS 框架（Nuxt），但 SSR 已把資料嵌在 __NUXT__，
    且無 Cloudflare 阻擋，故可靜態抓取，免用 Playwright。
    """
    articles = []
    BASE_URL = "https://www.pgsoft.com"
    cutoff = (date.today() - timedelta(days=MAX_AGE_DAYS)).isoformat()
    try:
        r = requests.get(f"{BASE_URL}/sitemap.xml", headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.content, "xml")
        games, news = [], []
        for u in soup.find_all("url"):
            loc = clean(u.loc.get_text()) if u.loc else ""
            lastmod = clean(u.lastmod.get_text()) if u.lastmod else ""
            if re.search(r"/games/\d+/?$", loc):
                games.append((loc, lastmod))
            elif re.search(r"/news/\d+/?$", loc):
                news.append((loc, lastmod))
        # 依 lastmod 由新到舊，各取最新一批（新品/新聞追蹤重點在最新）
        games.sort(key=lambda x: x[1], reverse=True)
        news.sort(key=lambda x: x[1], reverse=True)

        def fetch(loc):
            pr = requests.get(loc, headers=HEADERS, timeout=TIMEOUT)
            pr.raise_for_status()
            m = re.search(r'window\.__NUXT__=(.*?)</script>', pr.text, re.S)
            return m.group(1) if m else ""

        # 新遊戲（結構化：名稱 + RTP + 最大倍數 + 說明）
        for loc, _ in games[:18]:
            item_uid = uid(loc, "pg")
            if item_uid in existing_ids:
                continue
            try:
                blob = fetch(loc)
            except Exception:
                continue
            name = _nuxt_field(blob, "n") or _nuxt_field(blob, "t")
            ct = _nuxt_field(blob, "ct")[:10]
            if not name or not ct or ct < cutoff:
                continue
            ld = _nuxt_field(blob, "ld")[:300]
            rtp = _nuxt_field(blob, "rtp")
            me = _nuxt_field(blob, "me")
            spec = " ".join(x for x in [f"RTP {rtp}" if rtp else "",
                                        f"最大 {me}" if me else ""] if x)
            summary_en = (ld or name) + (f" ({spec})" if spec else "")
            articles.append({
                "id": item_uid,
                "date": ct,
                "cat": "新遊戲",
                "vendor": "PG Soft",
                "game": translate_zh(name),
                "game_en": name,
                "summary": (translate_zh(ld) if ld else translate_zh(name)) + (f"（{spec}）" if spec else ""),
                "summary_en": summary_en,
                "stars": guess_importance(name + " " + summary_en, "新遊戲"),
                "url": loc,
            })
            time.sleep(0.1)

        # 官網新聞（新品公告/活動）
        for loc, _ in news[:12]:
            item_uid = uid(loc, "pg")
            if item_uid in existing_ids:
                continue
            try:
                blob = fetch(loc)
            except Exception:
                continue
            title = _nuxt_field(blob, "t")
            ct = _nuxt_field(blob, "ct")[:10]
            if not title or not ct or ct < cutoff:
                continue
            # summary_en 帶入廠商名，讓後續 reclassify_all 也能判為「熱門廠商」而非落入 catch-all
            summary_en = "PG Soft — " + title
            cat = guess_category(summary_en)
            articles.append({
                "id": item_uid,
                "date": ct,
                "cat": cat,
                "vendor": "PG Soft",
                "game": translate_zh(title),
                "game_en": title,
                "summary": translate_zh(title),
                "summary_en": summary_en,
                "stars": guess_importance(title, cat),
                "url": loc,
            })
            time.sleep(0.1)
    except Exception as e:
        print(f"  ✗ PG Soft: {e}")
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


def fix_untranslated(records):
    """修補：已抓進來但標題/摘要仍是英文（先前翻譯失敗）的記錄，重新翻譯。"""
    fixed = 0
    for r in records:
        game = r.get("game", "")
        if game and is_english(game):
            # 確保保留英文原文供分類用
            if not r.get("game_en"):
                r["game_en"] = game
            zh = translate_zh(game)
            if zh and not is_english(zh):
                r["game"] = zh
                fixed += 1
        summ = r.get("summary", "")
        if summ and is_english(summ):
            if not r.get("summary_en"):
                r["summary_en"] = summ
            zh = translate_zh(summ)
            if zh and not is_english(zh):
                r["summary"] = zh
    return fixed


def dedupe_records(records):
    """移除重複標題（例：SA 官網 sitemap 的多語系同篇、跨來源轉載同一則）。
    以英文原標題正規化為鍵，保留日期最新的一筆。"""
    seen = set()
    out = []
    for r in sorted(records, key=lambda x: x.get("date", ""), reverse=True):
        key = re.sub(r'\s+', ' ', (r.get("game_en") or r.get("game", "")).strip().lower())
        if key and key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


# 第一方廠商爬蟲（官網直取）內容，定義上即為 iGaming，免關鍵字相關性測試，
# 但仍過濾刑案/天災花邊（is_excluded）
_FIRSTPARTY_VENDORS = {"PG Soft", "CQ9 Gaming", "SA Gaming", "WG包網"}


def purge_irrelevant(records):
    """Remove records with no iGaming relevance (checks English title + summary + Chinese summary)."""
    before = len(records)
    cleaned = []
    for r in records:
        # 中文檢查同時涵蓋標題與摘要（雜訊詞常只出現在標題）
        zh_text = (r.get("game") or "") + " " + (r.get("summary") or "")
        en_title = r.get("game_en") or r.get("game", "")
        en_summary = r.get("summary_en") or ""
        # 第一方廠商內容：只擋花邊，不要求含通用博彩關鍵字（遊戲名常無關鍵字）
        if r.get("vendor") in _FIRSTPARTY_VENDORS:
            if not is_excluded(en_title, en_summary, zh_text):
                cleaned.append(r)
            continue
        if is_relevant(en_title, en_summary, zh_text):
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

    # Vendor-specific HTML scrapers (no RSS available)
    print("  HTML: CQ9 Gaming News")
    cq9_arts = scrape_cq9(existing_ids)
    for a in cq9_arts:
        new_records.append(a)
        existing_ids.add(a["id"])
    print(f"    → {len(cq9_arts)} 新筆")

    # SA Gaming press releases (亞洲廠商第一手，sitemap + og:title)
    print("  HTML: SA Gaming Press")
    sa_arts = scrape_sa_gaming(existing_ids)
    for a in sa_arts:
        new_records.append(a)
        existing_ids.add(a["id"])
    print(f"    → {len(sa_arts)} 新筆")

    # PG Soft 官網（方案 B 試點：Nuxt SSR，新遊戲 + 新聞）
    print("  HTML: PG Soft (Nuxt)")
    pg_arts = scrape_pgsoft(existing_ids)
    for a in pg_arts:
        new_records.append(a)
        existing_ids.add(a["id"])
    print(f"    → {len(pg_arts)} 新筆")

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

    all_records = existing + new_records

    # 修補先前翻譯失敗、仍是英文的記錄
    if TRANSLATE:
        print("\n修補未翻譯的英文記錄...")
        fixed = fix_untranslated(all_records)
        print(f"  → 補翻 {fixed} 筆")

    # Re-classify ALL records with updated rules
    print("\n重新分類所有資料...")
    reclassified = reclassify_all(all_records)
    print(f"  → 更新分類 {reclassified} 筆")

    vendors_fixed = normalize_vendors(all_records)
    if vendors_fixed:
        print(f"  → 修正廠商標籤 {vendors_fixed} 筆")

    # Remove off-topic records (crime/tabloid/disaster/prediction-market noise)
    all_records, purged = purge_irrelevant(all_records)
    if purged:
        print(f"  → 移除非相關內容 {purged} 筆")

    before = len(all_records)
    all_records = dedupe_records(all_records)
    if before - len(all_records):
        print(f"  → 移除重複標題 {before - len(all_records)} 筆")

    all_records.sort(key=lambda r: r["date"], reverse=True)
    save_data(all_records)
    print(f"\n✅ 新增 {len(new_records)} 筆，資料庫共 {len(all_records)} 筆")

    return len(new_records)


if __name__ == "__main__":
    run()
