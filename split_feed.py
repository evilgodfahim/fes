import feedparser
from feedgen.feed import FeedGenerator
import requests
import re
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone, timedelta
import os

# --- Config ---
SOURCE_URLS = [
    "https://politepaul.com/fd/BNnVF6SFDNH6.xml",
    "https://evilgodfahim.github.io/tbs/articles.xml",
]
MAX_ARTICLES = 500
MAX_AGE_HOURS = 3

# --- Bangla character detector ---
bangla_re = re.compile(r'[\u0980-\u09FF]')

# ============================================================
# NEGATIVE / LOW-VALUE FILTER
#
# PASS THROUGH (never block):
#   * Ongoing war reporting (Gaza, Ukraine, Middle East, etc.)
#   * Trade war, tariffs, sanctions, geopolitics, diplomacy
#   * Economic policy, markets, business, agriculture
#   * Political analysis, governance, international relations
#
# BLOCK:
#   * BD local accidents (road, gas, drowning, fire, structural)
#   * BD local court drama (remand, bail, petty arrests, ACC)
#   * Local police ops, drug busts, small-time crime
#   * Murder, sexual violence, child abuse
#   * Celebrity gossip (Epstein-type), sensationalism
#
# KEY DESIGN RULE:
#   Ambiguous single words — attack, bomb, war, losses, crash,
#   blast, militant, combat, hostile — are REMOVED entirely.
#   Only compound phrases or genuinely unambiguous standalone
#   terms are kept. BD-specific local patterns are added
#   explicitly to catch noise global wordlists miss.
# ============================================================

NEGATIVE_WORDS = re.compile(r'\b(' + '|'.join([

    # ── DEATH — unambiguous crime/atrocity terms only ────────────────────
    r'murder(?:ed|s|ing|er|ers)?',
    r'homicide',
    r'manslaughter',
    r'decapitat(?:e|ed|ion)?',
    r'behead(?:ed|ing|s)?',
    r'massacr(?:e|ed|es)',
    r'assassination|assassinated',
    r'suicid(?:e|al|es|ed)?',
    r'hang(?:s|ed|ing)?\s+(?:himself|herself|themselves)',
    r'shot\s+dead',
    r'shot\s+and\s+killed',
    r'beaten\s+to\s+death',
    r'burned?\s+(?:alive|to\s+death)',
    r'hacked?\s+to\s+death',
    r'stabbed?\s+to\s+death',
    r'strangled?\s+to\s+death',
    r'killed\s+in\s+(?:road|highway|bus|truck|car|train|ferry|launch|boat)\s+(?:accident|crash|collision)',
    r'killed\s+(?:by|in)\s+(?:gas|fire|blast|explosion|flood|lightning|stampede|drowning)',
    r'killed\s+on\s+(?:the\s+)?spot',
    r'died?\s+on\s+(?:the\s+)?spot',
    r'dead\s+on\s+(?:the\s+)?spot',
    r'found\s+(?:dead|hanging|hanged)',
    r'body\s+(?:recovered|found|retrieved)\s+(?:from|in)\s+(?:river|pond|canal|lake|well|drain|ditch|water)',
    r'death\s+row',
    r'lethal\s+injection',
    r'capital\s+punishment',
    r'execution[-\s]?style',
    r'mass\s+(?:murder|killing|execution|grave)',
    r'double\s+(?:murder|homicide)',
    r'triple\s+(?:murder|homicide)',
    r'serial\s+kill(?:er|ing)',
    r'mob\s+kill(?:ing)?',
    r'targeted\s+kill(?:ing)?',
    r'extrajudicial\s+kill(?:ing)?',
    r'drove\s+off\s+(?:a\s+)?cliff',
    r'plunge[sd]?\s+to\s+(?:his|her|their\s+)?death',
    r'fell?\s+to\s+(?:his|her|their\s+)?death',
    r'postmortem|autopsy',
    r'obituary|obituaries',
    r'morgue(?:s)?',
    r'corpse(?:s)?',
    r'last\s+rites',

    # ── VIOLENT CRIME & ASSAULT ───────────────────────────────────────────
    r'maim(?:ed|s|ing)?',
    r'mutilat(?:e|ed|ion)?',
    r'disembowel(?:ed|ment)?',
    r'bludgeon(?:ed|ing|s)?',
    r'lynch(?:ed|ing)?|lynching',
    r'strangl(?:e|ed|ing|ation)?',
    r'suffocate?(?:d|s|ing)?|suffocation',
    r'tortur(?:e|ed|ing|ous)?',
    r'acid\s+attack(?:s)?',
    r'mob\s+(?:attack|beat|assault|violence|justice|lynching)',
    r'armed\s+robbery|armed\s+mugging',
    r'drive[-\s]?by\s+(?:shoot|shooting|kill)',
    r'gun(?:man|men)',
    r'gunshot(?:s)?(?:\s+wound)?',
    r'stabb(?:ed|ing)(?:\s+(?:victim|wound|attack))?',
    r'knife\s+(?:attack|wound|stab)',
    r'machete(?:s)?(?:\s+attack)?',
    r'hail\s+of\s+bullets',
    r'bullet[-\s]?riddled',
    r'body\s+bag(?:s)?',
    r'bloodshed',
    r'bloodbath',
    r'gruesome(?:\s+(?:murder|killing|crime|scene|discovery))?',
    r'grisly(?:\s+(?:murder|killing|crime|scene|discovery))?',
    r'perpetrator(?:s)?',
    r'assailant(?:s)?',
    r'pogrom(?:s)?',
    r'genocide(?:s)?|genocidal',
    r'ethnic\s+cleans(?:ing|e)?',
    r'war\s+crime(?:s)?',
    r'hate\s+(?:crime|speech)',

    # ── SEXUAL VIOLENCE — all terms (unambiguous) ─────────────────────────
    r'rape(?:d|s|ist|ists)?|raping',
    r'sexual\s+assault',
    r'sexual\s+violence',
    r'molestat(?:e|ed|ion|ing)?',
    r'molest(?:ed|ing|er|s)?',
    r'sexual\s+abuse(?:d|r|rs)?',
    r'sexual\s+exploitation',
    r'child\s+(?:abuse|molestation|sex(?:ual)?\s+abuse)',
    r'child(?:ren)?s?\s+porn(?:ography|o)?',
    r'pedophil(?:e|ia|es|ic)?',
    r'grooming\s+(?:minor|child|victim|girl|boy)',
    r'incest',
    r'statutory\s+rape',
    r'sexual\s+harass(?:ment|ed|ing)?',
    r'sexual\s+battery',
    r'date\s+rape',
    r'nonconsensual',
    r'voyeur(?:ism|ist)?',
    r'indecent\s+(?:assault|exposure)',
    r'sexual\s+(?:predator|offender|misconduct)',
    r'sex\s+crime(?:s)?',
    r'sexually\s+(?:abused|assaulted|harassed|exploited)',

    # ── FINANCIAL CRIME & CORRUPTION ─────────────────────────────────────
    r'kidnap(?:ped|ping|per|pers)?',
    r'abduct(?:ed|ion|s)?',
    r'hostage(?:s)?\s+(?:taken|held|situation|crisis)',
    r'ransom\s+(?:demand|paid|money|note)',
    r'extort(?:ion|ed|ing)?',
    r'blackmail(?:ed|ing)?',
    r'rob(?:bed|bery|beries|bing)?|robbery',
    r'burglary|burglar(?:y|ies|ize|ized)?',
    r'larceny|theft',
    r'pickpocket(?:ing|s)?',
    r'identity\s+theft',
    r'vandal(?:ize|ism|ized)?',
    r'arson(?:ist|ists)?',
    r'forgery',
    r'counterfeit(?:ing|ed)?\s+(?:currency|notes|documents|goods)',
    r'fraud(?:ulent)?\s+(?:case|scheme|ring|money|transaction)',
    r'scam(?:s|med|ming|mer|mers)?',
    r'fraudster(?:s)?',
    r'embezzl(?:e|ed|ment)?',
    r'brib(?:e|ed|ery|ing)?|kickback(?:s)?',
    r'graft\s+(?:case|charge|investigation)',
    r'money\s+launder(?:ing|ed)?',
    r'insider\s+trading',
    r'tax\s+evasion',
    r'ponzi(?:\s+scheme)?|pyramid\s+scheme',
    r'wire\s+fraud|securities\s+fraud|credit\s+card\s+fraud',
    r'cybercrime(?:s)?',
    r'malware|ransomware|spyware',
    r'phish(?:ing|ed)?',
    r'doxx(?:ing|ed)?',
    r'misappropriat(?:e|ed|ion)?',
    r'pilferage|pilfer(?:ed|ing)?',
    r'organized\s+crime',
    r'crime\s+(?:ring|syndicate|cartel)',
    r'mobster(?:s)?|crime\s+boss',
    r'money\s+mule(?:s)?',
    r'shell\s+compan(?:y|ies)',
    r'benami\s+(?:property|asset|account)',
    r'illegal\s+(?:arms|weapons?|guns?)',
    r'drug\s+(?:trafficking|smuggling|dealing|cartel)',
    r'narcotics\s+(?:trafficking|ring|bust|seizure)',
    r'human\s+trafficking|sex\s+trafficking',
    r'forced\s+(?:labor|marriage|prostitution)',
    r'child\s+labor\s+(?:case|violation|charge)',
    r'enslave(?:d|ment)?|slavery',

    # ── ARRESTS & LOCAL LEGAL DRAMA ───────────────────────────────────────
    r'arrest(?:ed|s|ing)?\s+(?:for|on|in|over|by|after)',
    r'remand(?:ed)?',
    r'detain(?:ed)?\s+(?:for|on|over|by)',
    r'apprehend(?:ed|s|ing)?',
    r'handcuff(?:ed|s)?',
    r'imprison(?:ed|ment)?',
    r'incarcer(?:ate|ated|ion)?',
    r'jail(?:ed)?\s+(?:for|over|after)',
    r'warrant\s+(?:issued|against|for|served)',
    r'search\s+warrant|arrest\s+warrant',
    r'suspect(?:ed)?\s+(?:arrested|detained|nabbed?|in|of)',
    r'accused\s+(?:of|in|over)',
    r'indict(?:ed|ment|s)?',
    r'convict(?:ed|ion|ions|s)?',
    r'plead(?:ed|ing)?\s+guilty',
    r'perjur(?:y|ed)?',
    r'subpoena(?:ed)?',
    r'contempt\s+of\s+court',
    r'obstruction\s+of\s+justice',
    r'parole\s+(?:violation|board|hearing|granted|denied)',
    r'probation\s+(?:violation|breach|revoked)',
    r'bail\s+(?:hearing|petition|granted|denied|refused|bond|jumping)',
    r'acquitt(?:al|ed)?',
    r'felony|felonies|misdemeanor(?:s)?',
    r'lawsuit(?:s)?\s+(?:filed|over|against)',
    r'sued?\s+(?:over|for)',
    r'(?:case|suit|complaint|FIR|charge)\s+(?:filed|lodged|registered)\s+(?:against|over|for)',
    r'FIR\s+(?:filed|lodged|registered)',
    r'charged\s+(?:with|over|for|in|under)',
    r'nabbed?\s+(?:for|with|over|in|by)',
    r'fugitive(?:s)?',
    r'manhunt\s+(?:for|launched|underway)',
    r'wanted\s+(?:by\s+police|for\s+(?:murder|rape|theft|robbery|kidnapping))',
    r'sealed\s+indictment',
    r'racketeer(?:ing)?',
    r'drug\s+(?:bust|raid|haul|seizure)',
    r'narcotics\s+(?:seized|recovered|busted)',
    r'gang\s+(?:member|leader|arrested|busted|nabbed?|crackdown)',

    # ── BD-SPECIFIC LOCAL POLITICAL & LEGAL NOISE ─────────────────────────
    r'RAB\s+(?:raid|operation|crackdown|arrest|detain|nab|killed?|recover)',
    r'detective\s+branch\s+(?:raid|arrest|operation|detain)',
    r'DB\s+police\s+(?:raid|arrest|operation)',
    r'police\s+(?:raided?|crackdown|drive|operation)\s+(?:in|at|on)\s+\w+',
    r'thana\s+(?:police|case|OC)',
    r'upazila\s+(?:police|chairman|parishad)\s+(?:arrest|sue|remand|kill|detain)',
    r'union\s+parishad\s+(?:chairman|member)\s+(?:arrested|sued|remanded|killed)',
    r'ex[-\s](?:minister|secretary|mp|sp|dc|uo|pdb|chairman|mayor|councillor)\s+(?:arrest|remand|jail|detain|sue|indict|convict|charge|kill)',
    r'former\s+(?:minister|secretary|mp|chairman|mayor)\s+(?:arrested|remanded|jailed|detained|sued|indicted|convicted)',
    r'acc\s+(?:case|suit|probe|charge|investigation)',
    r'disproportionate\s+(?:asset|wealth|income)',
    r'undisclosed\s+(?:asset|income|wealth)',
    r'Tk\s*\d+(?:\.\d+)?\s*(?:cr|crore|lac|lakh)\s+(?:launder|misappropriat|embezzl|siphon|loot|swindl)',
    r'laundering\s+Tk',

    # BD drug/crime-specific terms
    r'yaba(?:\s+(?:tablet|pill|dealer|peddler|seized|recovered|bust))?',
    r'phensedyl(?:\s+(?:seized|recovered|dealer|bust))?',
    r'ganja(?:\s+(?:seized|recovered|dealer|bust))?',
    r'dakait|dacoity',
    r'snatching\s+(?:case|gang|incident|victim)',

    # ── ROAD & TRANSPORT ACCIDENTS ────────────────────────────────────────
    r'road\s+(?:accident|crash|fatality)',
    r'highway\s+accident',
    r'bus\s+(?:accident|overturns?|plunge[sd]?|crash(?:es|ed)?|capsize)',
    r'truck\s+(?:accident|crash(?:es|ed)?|overturn)',
    r'motorcycle\s+accident|motorbike\s+accident',
    r'bike\s+(?:accident|crash(?:ed)?)',
    r'auto[-\s]?rickshaw\s+(?:accident|crash|collision|overturn)',
    r'three[-\s]?wheeler\s+(?:accident|crash|overturn)',
    r'microbus\s+(?:accident|crash(?:ed)?|collision|overturn)',
    r'vehicle\s+(?:accident|overturns?)',
    r'run\s+over\s+(?:by\s+)?(?:a\s+)?(?:bus|truck|car|lorry|vehicle|auto|motorcycle|train)',
    r'hit\s+by\s+(?:a\s+)?(?:bus|truck|car|lorry|vehicle|train|motorcycle|auto)',
    r'pedestrian\s+(?:killed|dead|mowed\s+down|run\s+over|crushed)',
    r'train\s+(?:accident|crash(?:ed)?|derail(?:ed)?)',
    r'level\s+crossing\s+(?:accident|crash|death)',
    r'ferry\s+(?:capsize[sd]?|sunk|sank|accident|overturn)',
    r'launch\s+(?:capsize[sd]?|sunk|sank|accident)',
    r'trawler\s+(?:capsize[sd]?|sunk|sank|accident)',
    r'speedboat\s+(?:capsize[sd]?|accident|crash)',
    r'boat\s+(?:capsize[sd]?|accident|sunk|sank)',
    r'bridge\s+collapse[sd]?',
    r'fell?\s+(?:from|off)\s+(?:a\s+)?(?:bridge|building|roof|tree|ladder|bike|rickshaw|motorcycle|scaffolding)',
    r'fell?\s+into\s+(?:a\s+)?(?:well|pond|canal|river|ditch|drain|lake)',
    r'plunged?\s+(?:into|off)\s+(?:river|canal|lake|pond|ditch|cliff)',

    # ── DROWNING ─────────────────────────────────────────────────────────
    r'drown(?:ed|ing|s)?',
    r'swept\s+away\s+(?:by|in)\s+(?:flood|current|river|tide|wave)',
    r'missing\s+(?:in|after)\s+(?:river|flood|sea|storm|cyclone)',

    # ── GAS EXPLOSIONS & LOCAL FIRE ACCIDENTS ────────────────────────────
    r'gas\s+(?:burst|cylinder\s+(?:blast|burst|explosion))',
    r'gas\s+cylinder\s+(?:blast|burst|explode[sd]?)',
    r'cylinder\s+(?:blast|burst|explosion)',
    r'boiler\s+(?:burst|explosion|blast)',
    r'LPG\s+(?:burst|explosion|fire|blast)',
    r'cooking\s+gas\s+(?:fire|blast|explosion|burst)',
    r'kitchen\s+fire',
    r'house\s+fire',
    r'building\s+fire',
    r'market\s+fire',
    r'factory\s+fire',
    r'slum\s+fire',
    r'shop(?:s)?\s+(?:gutted|burned|destroyed)\s+(?:in|by)\s+fire',
    r'gutted\s+(?:in|by)\s+(?:fire|blaze)',
    r'engulf(?:ed)?\s+(?:by|in)\s+(?:fire|flames?)',
    r'ravage(?:d)?\s+(?:by|in)\s+(?:fire|flames?)',
    r'fire\s+broke\s+out',
    r'fire\s+(?:gutted|kill(?:ed|s)?|claim(?:ed|s)?)',
    r'blaze\s+(?:kill(?:ed|s)?|destroy(?:ed|s)?|gut(?:ted)?|engulf|claim(?:ed|s)?)',
    r'inferno\s+(?:kill(?:ed|s)?|destroy)',

    # ── STRUCTURAL & ENVIRONMENTAL LOCAL ACCIDENTS ────────────────────────
    r'building\s+collapse[sd]?',
    r'wall\s+collapse[sd]?',
    r'roof\s+collapse[sd]?',
    r'construction\s+(?:accident|worker\s+(?:killed|dead))',
    r'electrocut(?:ed|ion)?',
    r'lightning\s+(?:kill(?:ed|s)?|struck|dead)',
    r'struck\s+by\s+lightning',
    r'snake\s+bite\s+(?:kill(?:ed|s)?|dead|fatal)',
    r'stampede\s+(?:kill(?:ed|s)?|dead|injur|casualt)',
    r'landslide\s+(?:kill(?:ed|s)?|dead|bury|claim)',
    r'flood\s+(?:kill(?:ed|s)?|dead|claim|bury)',

    # ── CELEBRITY & SENSATIONALIST NOISE ─────────────────────────────────
    r'epstein',
    r'weinstein',
    r'sex\s+tape',
    r'leaked?\s+(?:video|photo|footage|clip|nude)',
    r'nude\s+(?:photo|video|picture|image|clip)',
    r'OnlyFans',
    r'extramarital\s+(?:affair|relation)',
    r'love\s+triangle',
    r'celebrity\s+(?:scandal|divorce|breakup|feud|affair)',
    r'reality\s+(?:TV\s+)?star\s+(?:arrested|charged|sued|jailed)',
    r'scandal\s+(?:rocks?|hits?|grips?|engulfs?|shakes?)\s+\w+',

]) + r')\b', re.IGNORECASE)

# --- Thumbnail helpers ---
IMG_SRC_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)

def extract_thumbnail_from_summary(summary: str):
    if not summary:
        return None
    m = IMG_SRC_RE.search(summary)
    return m.group(1) if m else None

def get_thumbnail(entry) -> str | None:
    # 1. feedparser enclosures — handles RSS <enclosure> tags (TBS fix)
    enclosures = entry.get('enclosures') or []
    for enc in enclosures:
        href = enc.get('href') or enc.get('url')
        etype = (enc.get('type') or '').lower()
        if href and 'image' in etype:
            return href

    # 2. media:thumbnail
    mt = entry.get('media_thumbnail')
    if mt:
        if isinstance(mt, (list, tuple)) and mt:
            url = mt[0].get('url') if isinstance(mt[0], dict) else mt[0]
            if url:
                return url
        elif isinstance(mt, dict) and mt.get('url'):
            return mt.get('url')

    # 3. media:content
    mc = entry.get('media_content')
    if mc:
        if isinstance(mc, (list, tuple)) and mc:
            url = mc[0].get('url') if isinstance(mc[0], dict) else mc[0]
            if url:
                return url
        elif isinstance(mc, dict) and mc.get('url'):
            return mc.get('url')

    # 4. links (rel=enclosure or image type)
    links = entry.get('links') or []
    for lnk in links:
        rel = (lnk.get('rel') or '').lower()
        ltype = (lnk.get('type') or '').lower()
        href = lnk.get('href') or lnk.get('url')
        if not href:
            continue
        if rel == 'enclosure' and ltype.startswith('image'):
            return href
        if rel == 'thumbnail' or 'image' in ltype:
            return href

    # 5. misc keys
    for key in ('thumbnail', 'image', 'enclosure'):
        val = entry.get(key)
        if isinstance(val, dict) and val.get('url'):
            return val.get('url')
        if isinstance(val, str) and val:
            return val

    # 6. img tag in summary/description
    for field in ('summary', 'description', 'content'):
        text = entry.get(field)
        if isinstance(text, list):
            text = text[0].get('value', '') if text else ''
        thumb = extract_thumbnail_from_summary(text or '')
        if thumb:
            return thumb

    return None

# --- Filters ---
def is_bangla(text: str) -> bool:
    return bool(bangla_re.search(text or ""))

def get_negative_match(entry) -> str | None:
    """Returns the matched word/phrase if negative, else None. Used for filtering + debug."""
    text = " ".join(filter(None, [
        entry.get("title", "") or "",
        entry.get("summary", "") or "",
        (entry.get("tags") or [{}])[0].get("term", ""),
    ]))
    m = NEGATIVE_WORDS.search(text)
    return m.group(0) if m else None

def is_negative(entry) -> bool:
    return get_negative_match(entry) is not None

def get_pub_datetime(entry) -> datetime | None:
    pub = entry.get("published") or entry.get("updated")
    if pub:
        try:
            return parsedate_to_datetime(pub)
        except Exception:
            pass
    pp = entry.get("published_parsed") or entry.get("updated_parsed")
    if pp:
        try:
            return datetime(*pp[:6], tzinfo=timezone.utc)
        except Exception:
            pass
    return None

def is_too_old(entry) -> bool:
    dt = get_pub_datetime(entry)
    if dt is None:
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt) > timedelta(hours=MAX_AGE_HOURS)

# --- Persistence: load existing XML ---
def load_existing(filename: str) -> tuple[list, set]:
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

# --- Build & save feed ---
def save_feed(filename: str, title: str, feed_link: str, description: str,
              new_entries: list, existing_entries: list, seen_links: set):
    merged = []

    for e in new_entries:
        link = e.get('link', '')
        if link and link not in seen_links:
            seen_links.add(link)
            merged.append(e)

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

        summary = (entry.get("summary") or entry.get("description") or "")
        if isinstance(summary, list):
            summary = summary[0].get('value', '') if summary else ''
        summary = summary or ""

        thumb = get_thumbnail(entry)
        if thumb and not IMG_SRC_RE.search(summary):
            summary = f'<img src="{thumb}" alt="thumbnail" />' + summary

        fe.description(summary)

        if thumb:
            try:
                fe.enclosure(thumb, 0, 'image/jpeg')
            except Exception:
                pass

        pub = entry.get("published") or entry.get("updated")
        if pub:
            try:
                fe.pubDate(parsedate_to_datetime(pub))
            except Exception:
                pass

    fg.rss_file(filename)
    print(f"[SAVE] {filename} — {len(merged)} total ({len(new_entries)} new attempted)")

# --- Fetch ---
def fetch_feed(url: str) -> list:
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)

        # ── DEBUG: structural sanity check ──────────────────────────────
        print(f"[OK]   {url}")
        print(f"       entries          : {len(feed.entries)}")
        print(f"       feed.bozo        : {feed.bozo}"
              + (f" ({feed.bozo_exception})" if feed.bozo else ""))
        if feed.entries:
            sample = feed.entries[0]
            print(f"       sample title     : {sample.get('title', '—')!r}")
            print(f"       sample published : {sample.get('published') or sample.get('updated') or '—'!r}")
            print(f"       sample has encl  : {bool(sample.get('enclosures'))}")
            print(f"       sample has media : {bool(sample.get('media_thumbnail') or sample.get('media_content'))}")
            print(f"       sample summary   : {repr((sample.get('summary') or '')[:80])}")
        # ────────────────────────────────────────────────────────────────

        return feed.entries
    except Exception as e:
        print(f"[FAIL] {url} — {e}")
        return []

# --- Main ---
def main():
    all_entries = []
    for url in SOURCE_URLS:
        entries = fetch_feed(url)
        # Tag each entry with its source URL for per-source debug later
        for e in entries:
            e['_source_url'] = url
        all_entries.extend(entries)

    print(f"\n{'='*60}")
    print(f"Total fetched : {len(all_entries)}")
    print(f"{'='*60}\n")

    bangla_new, english_new = [], []
    skipped_neg = skipped_old = skipped_no_date = 0

    # Per-source counters
    source_stats: dict[str, dict] = {url: {'total': 0, 'neg': 0, 'old': 0, 'bangla': 0, 'english': 0} for url in SOURCE_URLS}

    for entry in all_entries:
        src = entry.get('_source_url', 'unknown')
        title = entry.get('title', '(no title)')
        source_stats[src]['total'] += 1

        neg_match = get_negative_match(entry)
        if neg_match:
            skipped_neg += 1
            source_stats[src]['neg'] += 1
            print(f"  [NEG]  {title!r}")
            print(f"         matched: {neg_match!r}")
            continue

        if is_too_old(entry):
            skipped_old += 1
            source_stats[src]['old'] += 1
            pub = entry.get('published') or entry.get('updated') or '(no date)'
            dt = get_pub_datetime(entry)
            if dt:
                age_min = int((datetime.now(timezone.utc) - (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc))).total_seconds() / 60)
                print(f"  [OLD]  {title!r}  [{age_min}m old]")
            else:
                skipped_no_date += 1
                print(f"  [OLD?] {title!r}  [pub={pub!r}, could not parse date]")
            continue

        text = (entry.get("title", "") or "") + " " + (entry.get("summary", "") or "")
        has_thumb = bool(get_thumbnail(entry))
        if is_bangla(text):
            bangla_new.append(entry)
            source_stats[src]['bangla'] += 1
            print(f"  [BN]   {title!r}" + (" [img]" if has_thumb else ""))
        else:
            english_new.append(entry)
            source_stats[src]['english'] += 1
            print(f"  [EN]   {title!r}" + (" [img]" if has_thumb else ""))

    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    for url, s in source_stats.items():
        label = url.split('/')[-1] or url
        print(f"  {label}")
        print(f"    fetched   : {s['total']}")
        print(f"    blocked   : {s['neg']} negative  |  {s['old']} too old")
        print(f"    passed    : {s['bangla']} bangla  |  {s['english']} english")
    print()
    print(f"  Total skipped negative : {skipped_neg}")
    print(f"  Total skipped too old  : {skipped_old}  (of which {skipped_no_date} had no parseable date)")
    print(f"  New Bangla             : {len(bangla_new)}")
    print(f"  New English            : {len(english_new)}")
    print(f"{'='*60}\n")

    feeds = {
        "bangla.xml":  ("Bangla News",  "Filtered positive Bangla news",  bangla_new),
        "english.xml": ("English News", "Filtered positive English news", english_new),
    }

    for filename, (title, desc, new_items) in feeds.items():
        existing, seen = load_existing(filename)
        save_feed(filename, title, SOURCE_URLS[0], desc, new_items, existing, seen)

if __name__ == "__main__":
    main()
