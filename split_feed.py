"""
RSS Feed Splitter — Gemini AI Filter
=====================================
Pipeline:
  1. Fetch source feeds
  2. Age-filter (MAX_AGE_HOURS)
  3. Deduplicate by URL
  4. Send batches to Gemini — it decides what to keep and which language
  5. Append results to bangla.xml / english.xml (max MAX_ARTICLES, deduped)

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

import google.generativeai as genai

# ── CONFIG ────────────────────────────────────────────────────────────────────
SOURCE_URLS = [
    "https://politepaul.com/fd/BNnVF6SFDNH6.xml",
    "https://evilgodfahim.github.io/tbs/articles.xml",
]
MAX_ARTICLES   = 500
MAX_AGE_HOURS  = 5
GEMINI_MODEL   = "gemini-2.5-flash"
GEMINI_BATCH   = 40   # titles per API call
GEMINI_RETRIES = 3

# ── GEMINI PROMPT ─────────────────────────────────────────────────────────────
FILTER_PROMPT = """You are a news curator for a Bangladeshi competitive exam preparation platform (BCS and similar exams). Your job is to classify each article as KEEP or SKIP, and if KEEP, identify its language as BANGLA or ENGLISH.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ALWAYS KEEP — these topics have exam value:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• International relations, diplomacy, geopolitics
• Ongoing wars and conflicts (Gaza, Ukraine, Iran, Middle East, etc.) — their causes, consequences, global impact
• Trade wars, tariffs, sanctions, economic blocs
• Global economy: oil prices, commodity markets, currency moves, IMF/World Bank decisions
• Bangladesh economy: GDP, remittance, exports, RMG sector, FDI, budget, inflation, agriculture
• Bangladesh governance: major policy decisions, reform, infrastructure, development projects
• Science, technology, space, climate change, environment
• International organizations: UN, WTO, ICC, ASEAN, SAARC decisions
• South Asia geopolitics: India-Bangladesh, India-Pakistan, China relations
• Education, public health policy (not individual cases)
• Major corporate or tech developments with global/regional significance

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ALWAYS SKIP — no exam value:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Local Bangladesh accidents: road, bus, ferry, launch, boat, rickshaw, train crashes or overturns
• Drowning incidents in rivers, ponds, canals
• Gas cylinder blasts, LPG fires, kitchen/house/market/factory/slum fires
• Building, wall, roof collapses; construction accidents
• Lightning strikes, snake bites, floods killing individuals
• Local Bangladesh crime: robbery, theft, chain snatching, dacoity, mugging
• Murder, rape, sexual assault, child abuse (individual cases)
• Local police operations: RAB raids, DB raids, thana-level crackdowns
• Drug busts, yaba/phensedyl/ganja seizures at local level
• Petty court drama: remand hearings, bail petitions, FIR filings against minor figures
• Former/ex-officials' routine arrests for local corruption, money laundering of small sums
• ACC (Anti-Corruption Commission) cases against low-profile individuals
• Union parishad, upazila-level political drama
• Suicide, self-harm incidents
• Celebrity gossip: Epstein-type scandals, sex tapes, affairs, feuds
• Reality TV, entertainment news, sports results
• Obituaries, funeral rites, burial notices
• Individual missing person reports
• Local union disputes, minor strikes with no policy significance

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NUANCED RULES — read carefully:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• War reporting: KEEP. Even if an article mentions killings, airstrikes, or casualties in the context of an ongoing international conflict (Gaza, Ukraine, Iran war, etc.) — KEEP it. These have direct geopolitical and economic significance.
• Crime involving major figures or systemic issues: KEEP if it involves senior government officials, ministers, or reveals systemic corruption/policy failures. SKIP if it's a routine remand/bail of a local ex-official.
• Bangladesh fire/accident statistics reports (monthly summaries): SKIP — no individual incident has exam value even in aggregate form.
• Economic losses from trade/tariff disputes: KEEP. Economic losses from a local fire: SKIP.
• Phone scams, cybercrime at national policy level: KEEP. Individual fraud cases: SKIP.
• Child exploitation rings with international dimension (like FBI arrest): KEEP. Local molestation case: SKIP.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LANGUAGE DETECTION:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• BANGLA: title or description contains Bengali script (Unicode range \\u0980-\\u09FF) or the article is clearly written in Bangla
• ENGLISH: everything else

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INPUT FORMAT:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
A numbered list of articles. Each entry has:
  INDEX. [TITLE] | [DESCRIPTION SNIPPET]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT — strictly JSON, nothing else:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[
  {"index": 0, "decision": "KEEP", "lang": "ENGLISH"},
  {"index": 1, "decision": "SKIP"},
  {"index": 2, "decision": "KEEP", "lang": "BANGLA"}
]

Rules:
- Output ONLY the JSON array. No markdown, no explanation, no preamble.
- Only include "lang" field when decision is "KEEP".
- Every input index must appear in the output exactly once.

Articles to classify:
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
    # 1. RSS <enclosure> — TBS feed uses this
    for enc in (entry.get('enclosures') or []):
        href = enc.get('href') or enc.get('url')
        if href and 'image' in (enc.get('type') or '').lower():
            return href

    # 2. media:thumbnail
    mt = entry.get('media_thumbnail')
    if mt:
        if isinstance(mt, list) and mt:
            url = mt[0].get('url') if isinstance(mt[0], dict) else mt[0]
            if url: return url
        elif isinstance(mt, dict) and mt.get('url'):
            return mt['url']

    # 3. media:content
    mc = entry.get('media_content')
    if mc:
        if isinstance(mc, list) and mc:
            url = mc[0].get('url') if isinstance(mc[0], dict) else mc[0]
            if url: return url
        elif isinstance(mc, dict) and mc.get('url'):
            return mc['url']

    # 4. links with image type
    for lnk in (entry.get('links') or []):
        href = lnk.get('href') or lnk.get('url')
        rel  = (lnk.get('rel') or '').lower()
        typ  = (lnk.get('type') or '').lower()
        if href and ((rel == 'enclosure' and 'image' in typ) or rel == 'thumbnail' or 'image' in typ):
            return href

    # 5. misc dict keys
    for key in ('thumbnail', 'image', 'enclosure'):
        val = entry.get(key)
        if isinstance(val, dict) and val.get('url'): return val['url']
        if isinstance(val, str) and val:             return val

    # 6. img tag inside summary/description/content
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
def call_gemini(articles_batch):
    """
    articles_batch: list of dicts with keys: index, title, description
    Returns: list of {index, decision, lang?}
    """
    api_key = os.environ.get("LU")
    if not api_key:
        print("[WARN] No Gemini API key found in env var LU — skipping AI filter")
        return [{"index": a["index"], "decision": "KEEP", "lang": "ENGLISH"} for a in articles_batch]

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(GEMINI_MODEL)

    lines = []
    for a in articles_batch:
        desc = (a.get("description") or "").strip()[:200].replace('\n', ' ')
        lines.append(f"{a['index']}. [{a['title']}] | [{desc}]")
    articles_text = "\n".join(lines)

    prompt = FILTER_PROMPT.format(articles=articles_text)

    for attempt in range(GEMINI_RETRIES):
        try:
            response = model.generate_content(prompt)
            raw = (getattr(response, "text", None) or "").strip()
            # Strip markdown code fences if present
            raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
            raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE)
            raw = raw.strip()
            result = json.loads(raw)
            if isinstance(result, list):
                return result
        except Exception as e:
            print(f"[GEMINI] Attempt {attempt+1} failed: {e}")
            if attempt < GEMINI_RETRIES - 1:
                time.sleep(3)

    print("[GEMINI] All retries failed — passing batch through unfiltered")
    return [{"index": a["index"], "decision": "KEEP", "lang": "ENGLISH"} for a in articles_batch]

def gemini_filter(entries):
    """
    Run entries through Gemini in batches.
    Returns: (bangla_entries, english_entries)
    """
    # Build flat list with stable indices
    batch_input = []
    for i, entry in enumerate(entries):
        title = entry.get('title', '') or ''
        desc  = entry.get('summary', '') or entry.get('description', '') or ''
        batch_input.append({"index": i, "title": title, "description": desc})

    decisions = {}
    for start in range(0, len(batch_input), GEMINI_BATCH):
        chunk = batch_input[start:start + GEMINI_BATCH]
        print(f"[GEMINI] Sending batch {start//GEMINI_BATCH + 1} ({len(chunk)} articles)...")
        results = call_gemini(chunk)
        for r in results:
            if isinstance(r, dict) and 'index' in r:
                decisions[r['index']] = r
        # Small delay between batches to avoid rate limits
        if start + GEMINI_BATCH < len(batch_input):
            time.sleep(1)

    bangla, english = [], []
    for i, entry in enumerate(entries):
        d = decisions.get(i, {})
        if d.get('decision') != 'KEEP':
            print(f"  [SKIP] {entry.get('title', '')[:80]}")
            continue
        lang = d.get('lang', 'ENGLISH').upper()
        print(f"  [KEEP/{lang}] {entry.get('title', '')[:80]}")
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
    # 1. Fetch
    all_entries = []
    for url in SOURCE_URLS:
        all_entries.extend(fetch_feed(url))

    print(f"\nTotal fetched: {len(all_entries)}")

    # 2. Age filter
    fresh = [e for e in all_entries if not is_too_old(e)]
    print(f"After age filter ({MAX_AGE_HOURS}h): {len(fresh)}")

    # 3. Deduplicate by URL (across sources)
    seen_urls = set()
    deduped = []
    for e in fresh:
        link = e.get('link', '')
        if link and link not in seen_urls:
            seen_urls.add(link)
            deduped.append(e)
    print(f"After dedup: {len(deduped)}")

    if not deduped:
        print("Nothing to process.")
        return

    # 4. Gemini filter
    print(f"\n[GEMINI] Filtering {len(deduped)} articles...\n")
    bangla_new, english_new = gemini_filter(deduped)

    print(f"\nNew Bangla  : {len(bangla_new)}")
    print(f"New English : {len(english_new)}\n")

    # 5. Append to XML feeds
    feeds = {
        "bangla.xml":  ("Bangla News",  "Filtered Bangla news",  bangla_new),
        "english.xml": ("English News", "Filtered English news", english_new),
    }
    for filename, (title, desc, new_items) in feeds.items():
        existing, seen = load_existing(filename)
        save_feed(filename, title, SOURCE_URLS[0], desc, new_items, existing, seen)

if __name__ == "__main__":
    main()
