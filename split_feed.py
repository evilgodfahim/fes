"""
RSS Feed Splitter — Gemini AI Filter
Pipeline: Fetch → Age filter → Dedup → Gemini → Append to bangla.xml / english.xml
GitHub Actions secret: LU = Gemini API key
"""

import feedparser
from feedgen.feed import FeedGenerator
import requests
import re
import json
import os
import time
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone, timedelta

from google import genai

# ── CONFIG ────────────────────────────────────────────────────────────────────
SOURCE_URLS = [
    "https://politepaul.com/fd/BNnVF6SFDNH6.xml",
    "https://evilgodfahim.github.io/tbs/articles.xml",
]
MAX_ARTICLES   = 500
MAX_AGE_HOURS  = 5
GEMINI_MODEL   = "gemini-2.5-flash"
GEMINI_BATCH   = 100
GEMINI_RETRIES = 3
SEEN_FILE      = "seen.json"

# ── GEMINI PROMPT ─────────────────────────────────────────────────────────────
# NOTE: curly braces inside the prompt are doubled {{ }} to escape Python's
# str.format() — they render as single { } in the actual string sent to Gemini.

FILTER_PROMPT = """\
You are a news curator. Classify each article below as KEEP or SKIP, and if KEEP, identify its language.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
KEEP — these topics matter:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- International relations, diplomacy, geopolitics
- Ongoing wars and conflicts (Gaza, Ukraine, Iran, Middle East, etc.) and their economic or political consequences — even if casualties are mentioned
- Trade wars, tariffs, sanctions, economic blocs
- Global economy: oil prices, commodity markets, IMF/World Bank decisions, sovereign debt, currency crises
- Bangladesh economy: GDP, remittance, exports, RMG sector, FDI, budget, inflation, agriculture policy
- Bangladesh governance: major policy decisions, reform, infrastructure projects
- Science, technology, space, environment, climate policy
- International organizations: UN, WTO, ICC, ASEAN, SAARC — decisions with real consequences
- South Asia geopolitics: India-Bangladesh, India-Pakistan, China relations
- Public health policy at national or international scale
- Major corporate or tech developments with regional or global significance
- High-level corruption or crime that exposes systemic institutional failures

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SKIP — these have no significance:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Local Bangladesh accidents: road, bus, ferry, launch, boat, rickshaw, train crashes
- Drowning in rivers, ponds, canals
- Gas cylinder blasts, LPG fires, kitchen/house/market/factory/slum fires
- Building, wall, roof collapses; construction accidents
- Lightning strikes, snake bites, stampedes killing individuals
- Local crime: robbery, theft, chain snatching, dacoity, mugging
- Murder, rape, sexual assault, child abuse — individual criminal cases
- Local police operations: RAB raids, DB raids, thana-level drug busts
- Petty court drama: remand hearings, bail petitions, FIR filings for minor figures
- Routine arrests of former low-level officials for local corruption
- Union parishad, upazila-level political noise
- Suicide, self-harm incidents
- Celebrity gossip, sex scandals (Epstein-type), leaked videos, affairs
- Sports results, entertainment, reality TV, lifestyle, food, travel
- Obituaries, funeral notices, missing persons
- Monthly accident statistics summaries
- Court or Police related news related to Bangladesh and Bangladesh's.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BORDERLINE RULES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- War coverage: always KEEP even when it mentions killings, airstrikes, or casualties — the geopolitical and economic consequences are what matter
- Corruption: KEEP if it involves senior ministers, systemic policy failures, or international dimensions. SKIP if it is a routine remand/bail of a local ex-official
- International law enforcement (e.g. FBI arresting someone for a cross-border crime): KEEP
- Phone scams or cybercrime covered at a national policy level: KEEP. Individual fraud cases: SKIP
- Bangladesh fire/accident statistics reports (monthly summaries): SKIP

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LANGUAGE:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- BANGLA: title or description contains Bengali script or is clearly written in Bangla
- ENGLISH: everything else

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INPUT: numbered list — INDEX. [TITLE] | [DESCRIPTION]
OUTPUT: JSON array only — no markdown, no explanation.

Format exactly:
[
  {{"index": 0, "decision": "KEEP", "lang": "ENGLISH"}},
  {{"index": 1, "decision": "SKIP"}},
  {{"index": 2, "decision": "KEEP", "lang": "BANGLA"}}
]

Every input index must appear exactly once. Only include "lang" when decision is KEEP.

Articles:
{articles}
"""

# ── THUMBNAIL EXTRACTION ──────────────────────────────────────────────────────
IMG_SRC_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)

def extract_thumb_from_html(html):
    if not html:
        return None
    m = IMG_SRC_RE.search(html)
    return m.group(1) if m else None

def get_thumbnail(entry):
    for enc in (entry.get('enclosures') or []):
        href = enc.get('href') or enc.get('url')
        if href and 'image' in (enc.get('type') or '').lower():
            return href
    mt = entry.get('media_thumbnail')
    if mt:
        if isinstance(mt, list) and mt:
            url = mt[0].get('url') if isinstance(mt[0], dict) else mt[0]
            if url: return url
        elif isinstance(mt, dict) and mt.get('url'):
            return mt['url']
    mc = entry.get('media_content')
    if mc:
        if isinstance(mc, list) and mc:
            url = mc[0].get('url') if isinstance(mc[0], dict) else mc[0]
            if url: return url
        elif isinstance(mc, dict) and mc.get('url'):
            return mc['url']
    for lnk in (entry.get('links') or []):
        href = lnk.get('href') or lnk.get('url')
        rel  = (lnk.get('rel') or '').lower()
        typ  = (lnk.get('type') or '').lower()
        if href and ((rel == 'enclosure' and 'image' in typ) or rel == 'thumbnail' or 'image' in typ):
            return href
    for key in ('thumbnail', 'image', 'enclosure'):
        val = entry.get(key)
        if isinstance(val, dict) and val.get('url'): return val['url']
        if isinstance(val, str) and val:             return val
    for field in ('summary', 'description', 'content'):
        text = entry.get(field)
        if isinstance(text, list):
            text = text[0].get('value', '') if text else ''
        thumb = extract_thumb_from_html(text or '')
        if thumb: return thumb
    return None

# ── DATE HELPERS ──────────────────────────────────────────────────────────────
def get_pub_datetime(entry):
    pub = entry.get('published') or entry.get('updated')
    if pub:
        try: return parsedate_to_datetime(pub)
        except Exception: pass
    pp = entry.get('published_parsed') or entry.get('updated_parsed')
    if pp:
        try: return datetime(*pp[:6], tzinfo=timezone.utc)
        except Exception: pass
    return None

def is_too_old(entry):
    dt = get_pub_datetime(entry)
    if dt is None: return False
    if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt) > timedelta(hours=MAX_AGE_HOURS)

# ── SEEN.JSON ─────────────────────────────────────────────────────────────────
def load_seen():
    if not os.path.exists(SEEN_FILE):
        return set()
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        seen = set(data) if isinstance(data, list) else set()
        print(f"[SEEN] Loaded {len(seen)} previously processed URLs from {SEEN_FILE}")
        return seen
    except Exception as e:
        print(f"[WARN] Could not load {SEEN_FILE}: {e}")
        return set()

def save_seen(seen: set):
    try:
        with open(SEEN_FILE, "w", encoding="utf-8") as f:
            json.dump(sorted(seen), f, indent=2)
        print(f"[SEEN] Saved {len(seen)} URLs to {SEEN_FILE}")
    except Exception as e:
        print(f"[WARN] Could not save {SEEN_FILE}: {e}")

# ── FETCH ─────────────────────────────────────────────────────────────────────
def fetch_feed(url):
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        print(f"[OK]   {url} — {len(feed.entries)} entries")
        return feed.entries
    except Exception as e:
        print(f"[FAIL] {url} — {e}")
        return []

# ── GEMINI ────────────────────────────────────────────────────────────────────
def extract_json_array(text):
    text = re.sub(r'```(?:json)?', '', text).replace('```', '').strip()
    match = re.search(r'\[.*\]', text, flags=re.DOTALL)
    if not match:
        return None
    arr_text = match.group(0)
    try:
        return json.loads(arr_text)
    except Exception:
        fixed = re.sub(r',\s*]', ']', arr_text)
        try:
            return json.loads(fixed)
        except Exception:
            return None

def call_gemini(articles_batch):
    api_key = os.environ.get("LU")
    if not api_key:
        print("[WARN] No API key in LU — passing through unfiltered")
        return [{"index": a["index"], "decision": "KEEP", "lang": "ENGLISH"} for a in articles_batch]

    client = genai.Client(api_key=api_key)

    lines = []
    for a in articles_batch:
        desc = (a.get("description") or "").strip()[:200].replace('\n', ' ')
        lines.append(f"{a['index']}. [{a['title']}] | [{desc}]")
    articles_text = "\n".join(lines)

    prompt = FILTER_PROMPT.format(articles=articles_text)

    for attempt in range(GEMINI_RETRIES):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
            )
            response_text = getattr(response, "text", None) or str(response)
            result = extract_json_array(response_text)
            if isinstance(result, list):
                return result
            print(f"[GEMINI] Attempt {attempt+1}: unexpected response format")
        except Exception as e:
            print(f"[GEMINI] Attempt {attempt+1} failed: {e}")
        if attempt < GEMINI_RETRIES - 1:
            time.sleep(3)

    print("[GEMINI] All retries failed — passing batch through unfiltered")
    return [{"index": a["index"], "decision": "KEEP", "lang": "ENGLISH"} for a in articles_batch]

def gemini_filter(entries):
    batch_input = []
    for i, entry in enumerate(entries):
        title = entry.get('title', '') or ''
        desc  = entry.get('summary', '') or entry.get('description', '') or ''
        batch_input.append({"index": i, "title": title, "description": desc})

    decisions = {}
    for start in range(0, len(batch_input), GEMINI_BATCH):
        chunk = batch_input[start:start + GEMINI_BATCH]
        print(f"[GEMINI] Batch {start // GEMINI_BATCH + 1}: {len(chunk)} articles...")
        results = call_gemini(chunk)
        for r in results:
            if isinstance(r, dict) and 'index' in r:
                decisions[r['index']] = r
        if start + GEMINI_BATCH < len(batch_input):
            time.sleep(1)

    bangla, english = [], []
    for i, entry in enumerate(entries):
        d = decisions.get(i, {})
        title = entry.get('title', '')[:80]
        if d.get('decision') != 'KEEP':
            print(f"  [SKIP] {title}")
            continue
        lang = (d.get('lang') or 'ENGLISH').upper()
        print(f"  [KEEP/{lang}] {title}")
        if lang == 'BANGLA':
            bangla.append(entry)
        else:
            english.append(entry)

    return bangla, english

# ── PERSISTENCE ───────────────────────────────────────────────────────────────
def load_existing(filename):
    entries, seen = [], set()
    if not os.path.exists(filename):
        return entries, seen
    try:
        feed = feedparser.parse(filename)
        for e in feed.entries:
            link = e.get('link', '')
            if link and link not in seen:
                seen.add(link)
                entries.append(e)
        print(f"[LOAD] {filename} — {len(entries)} existing entries")
    except Exception as ex:
        print(f"[WARN] Could not load {filename}: {ex}")
    return entries, seen

def save_feed(filename, title, feed_link, description, new_entries, existing_entries, seen_links):
    merged = []
    added = 0
    for e in new_entries:
        link = e.get('link', '')
        if link and link not in seen_links:
            seen_links.add(link)
            merged.append(e)
            added += 1
    merged.extend(existing_entries)
    merged = merged[:MAX_ARTICLES]

    fg = FeedGenerator()
    fg.title(title)
    fg.link(href=feed_link, rel="alternate")
    fg.description(description)
    fg.language("en")

    for entry in merged:
        fe = fg.add_entry()
        fe.title(entry.get("title", "No title"))
        fe.link(href=entry.get("link", ""))

        summary = entry.get("summary") or entry.get("description") or ""
        if isinstance(summary, list):
            summary = summary[0].get('value', '') if summary else ''
        summary = summary or ""

        thumb = get_thumbnail(entry)
        if thumb and not IMG_SRC_RE.search(summary):
            summary = f'<img src="{thumb}" alt="thumbnail" />' + summary
        fe.description(summary)

        if thumb:
            try: fe.enclosure(thumb, 0, 'image/jpeg')
            except Exception: pass

        pub = entry.get("published") or entry.get("updated")
        if pub:
            try: fe.pubDate(parsedate_to_datetime(pub))
            except Exception: pass

    fg.rss_file(filename)
    print(f"[SAVE] {filename} — {len(merged)} total (+{added} new)")

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    all_entries = []
    for url in SOURCE_URLS:
        all_entries.extend(fetch_feed(url))
    print(f"\nTotal fetched  : {len(all_entries)}")

    fresh = [e for e in all_entries if not is_too_old(e)]
    print(f"After age filter ({MAX_AGE_HOURS}h): {len(fresh)}")

    seen_urls = set()
    deduped = []
    for e in fresh:
        link = e.get('link', '')
        if link and link not in seen_urls:
            seen_urls.add(link)
            deduped.append(e)
    print(f"After dedup    : {len(deduped)}")

    # ── Skip articles already processed in a previous run ────────────────────
    gemini_seen = load_seen()
    unseen = [e for e in deduped if e.get('link', '') not in gemini_seen]
    print(f"After seen.json filter: {len(unseen)} new (skipping {len(deduped) - len(unseen)})")

    if not unseen:
        print("Nothing new to process.")
        return

    print(f"\n[GEMINI] Filtering {len(unseen)} articles...\n")
    bangla_new, english_new = gemini_filter(unseen)

    # Mark every article we just sent to Gemini as seen (regardless of KEEP/SKIP)
    for e in unseen:
        link = e.get('link', '')
        if link:
            gemini_seen.add(link)
    save_seen(gemini_seen)

    print(f"\nNew Bangla  : {len(bangla_new)}")
    print(f"New English : {len(english_new)}\n")

    feeds = {
        "bangla.xml":  ("Bangla News",  "Filtered Bangla news",  bangla_new),
        "english.xml": ("English News", "Filtered English news", english_new),
    }
    for filename, (ftitle, desc, new_items) in feeds.items():
        existing, seen = load_existing(filename)
        save_feed(filename, ftitle, SOURCE_URLS[0], desc, new_items, existing, seen)

if __name__ == "__main__":
    main()
