import feedparser
from feedgen.feed import FeedGenerator
import requests
import re
from email.utils import parsedate_to_datetime

# --- Source feeds (list, not tuple) ---
SOURCE_URLS = [
    "https://politepaul.com/fd/BNnVF6SFDNH6.xml",
    "https://evilgodfahim.github.io/tbs/articles.xml",
]

# --- Bangla character detector ---
bangla_re = re.compile(r'[\u0980-\u09FF]')

# --- Comprehensive negative/dark news word list ---
NEGATIVE_WORDS = re.compile(r'\b(' + '|'.join([
    # Death & killing
    r'kill(?:ed|s|ing|er|ers)?', r'murder(?:ed|s|ing|er|ers)?',
    r'slaughter(?:ed|s|ing)?', r'massacre(?:d|s)?', r'assassin(?:ate|ated|ation|s)?',
    r'execut(?:e|ed|ion|ions)?', r'homicide', r'manslaughter',
    r'decapitat(?:e|ed|ion)?', r'behead(?:ed|ing|s)?',
    r'died?', r'dead', r'death(?:s)?', r'fatality', r'fatalities',
    r'casualt(?:y|ies)', r'corpse(?:s)?', r'bod(?:y|ies)', r'mort(?:uary|uarys)?',
    r'lifeless', r'perish(?:ed|es|ing)?', r'toll', r'slain', r'fallen', r'perished',
    r'killed\s?in', r'burn(?:ed|ing)?', r'charred', r'cremated', r'postmortem',
    r'autopsy', r'obituary', r'obituaries', r'bury', r'buried', r'burial',
    r'grave(?:s)?', r'cemetery', r'gravesite', r'ashes', r'laid\s?to\s?rest',
    r'killing\s?spree', r'atrocit(?:y|ies)?', r'genocide', r'ethnic\s?cleans(?:ing|e)?',
    r'pogrom(?:s)?', r'war\s?crime(?:s)?', r'combat\s?fatalit(?:y|ies)?', r'sniper(?:ed|s)?',
    r'ambush(?:ed|es|ing)?', r'targeted\s?killing', r'collateral\s?damage',
    r'friendly\s?fire', r'executioner', r'extra[-\s]?judicial', r'hit[-\s]?squad',
    r'assassination', r'assassinated', r'struck\s?down', r'mass[-\s]?fatalit(?:y|ies)?',
    r'plane\s?crash', r'air\s?crash', r'train\s?crash', r'pile[-\s]?up', r'collision',
    r'fatal\s?crash', r'crashed', r'derail(?:ed|ing)?', r'capsiz(?:e|ed|ing)?',
    r'sink(?:ing|ed)?', r'found\s?dead', r'discovered\s?dead', r'missing\s?and\s?dead',

    # Injury & violence
    r'injur(?:e|ed|y|ies|ing)?', r'wound(?:ed|s|ing)?', r'hurt(?:ing)?',
    r'maim(?:ed|s|ing)?', r'crippl(?:e|ed|ing)?', r'mutilat(?:e|ed|ion)?',
    r'disembowel(?:ed|ment)?', r'amputat(?:e|ed|ion)?', r'assault(?:ed|s|ing|er)?',
    r'attack(?:ed|s|ing|er|ers)?', r'beat(?:en|ing|s)?', r'batter(?:ed|ing|s)?',
    r'bludgeon(?:ed|ing|s)?', r'stab(?:bed|bing|s)?', r'shot', r'shoot(?:ing|ings|er|ers)?',
    r'gun(?:man|men|shot|shots|fire)?', r'shoot(?:out)?', r'grenade(?:s)?', r'landmine(?:s)?',
    r'ied', r'bomb(?:ed|ing|s)?', r'blast(?:ed|ing|s)?', r'explosion(?:s)?',
    r'car\s?bomb', r'vehicular\s?assault', r'run\s?over', r'drive-by', r'lynch(?:ed|ing)?',
    r'lacerat(?:e|ed|ion)?', r'fractur(?:e|ed|es)?', r'crush(?:ed|ing)?', r'compress(?:ed|ion)?',
    r'choke(?:d|ing)?', r'asphyx(?:ia|iate|iated)?', r'drown(?:ed|ing)?',
    r'electrocut(?:ed|ion)?', r'poison(?:ed|ing)?', r'overdose(?:d|s)?', r'acid\s?attack(?:s)?',
    r'ston(?:e|ing|ed)?', r'strangl(?:e|ed|ing)?', r'clash(?:es|ed|ing)?', r'riot(?:s|ed|ing)?',
    r'violenc(?:e|es)?', r'vicious(?:ly)?', r'bloodshed', r'bloodbath', r'gore', r'gruesome',
    r'brutal(?:ity|ities)?', r'savag(?:e|ery)', r'tortur(?:e|ed|ing)?', r'perpetrator(?:s)?',
    r'assailant(?:s)?', r'attacker(?:s)?', r'mob(?:s)?', r'siege(?:s)?', r'hostil(?:ity|ities)?',
    r'combat(?:ed|ing)?', r'explosion(?:al)?', r'detonate(?:d|ion)?', r'IED\s?attack', r'shrapnel',
    r'gunfire', r'rifle', r'pistol', r'bullet(?:s)?', r'bulletproof', r'bullet[-\s]?riddled',
    r'stomp(?:ed|ing)?', r'beaten\s?to\s?death', r'body\s?bag', r'medical\s?emergency',
    r'hemorrhag(?:e|ic)', r'internal\s?bleed(?:ing)?', r'bleed(?:ing)?', r'severe\s?injur(?:y|ies)?',

    # Crime & law enforcement
    r'arrest(?:ed|s|ing)?', r'detain(?:ed|s|ing|ee|ment)?', r'apprehend(?:ed|s|ing)?',
    r'imprison(?:ed|ment)?', r'jail(?:ed|s|ing)?', r'prison(?:er|ers|s)?',
    r'incarcer(?:ate|ated|ion)?', r'handcuff(?:ed|s)?', r'search\s?warrant', r'warrant(?:s)?',
    r'suspect(?:ed|s)?', r'accused', r'charg(?:e|ed|es|ing)?', r'indict(?:ed|ment|s)?',
    r'convict(?:ed|ion|ions|s)?', r'sentence(?:d|s|ing)?', r'verdict(?:s)?', r'trial(?:s)?',
    r'court(?:s)?', r'lawsuit(?:s)?', r'sue(?:d|s)?', r'suing', r'plead(?:ed|ing|s)?',
    r'guilty', r'acquitt(?:al|ed)?', r'parole', r'probation', r'obstruction(?:\s?of\s?justice)?',
    r'perjur(?:y|ed)?', r'subpoena(?:ed)?', r'contempt(?:\s?of\s?court)?', r'forgery',
    r'counterfeit(?:ing|ed)?', r'arson(?:ed|s)?', r'fraud(?:ulent)?', r'scam(?:s|med|ming)?',
    r'embezzl(?:e|ed|ment)?', r'brib(?:e|ed|ery|ing)?', r'corrupt(?:ion|ed)?', r'kickback(?:s)?',
    r'money\s?launder(?:ing|ed)?', r'insider\s?trading', r'hit[-\s]?and[-\s]?run', r'traffick(?:ed|ing|er|ers)?',
    r'smuggl(?:e|ed|ing|er|ers)?', r'kidnap(?:ped|ping|per|pers)?', r'abduct(?:ed|ion|s)?',
    r'hostage(?:s)?', r'ransom(?:ed|s)?', r'extort(?:ion|ed|ing)?', r'blackmail(?:ed|ing)?',
    r'larceny', r'theft', r'rob(?:bed|bery|beries|bing)?', r'burglary', r'burglar(?:y|ies|ize|ized)?',
    r'loot(?:ed|ing|s)?', r'pillage(?:d)?', r'vandal(?:ize|ism|ized)?', r'trespass(?:er|ing)?',
    r'pickpocket(?:ing|s)?', r'identity\s?theft', r'doxx(?:ing|ed)?', r'cybercrime(?:s)?',
    r'hacking', r'malware', r'ransomware', r'phish(?:ing|ed)?', r'credit\s?card\s?fraud',
    r'tax\s?evasion', r'evade(?:d|s|ing)?', r'scam(?:mer|mers)?', r'confidence\s?trick',
    r'con\s?man', r'con\s?men', r'cultivated\s?fraud', r'fraudster', r'felony', r'felonies',
    r'misdemeanor(?:s)?', r'breach\s?of\s?peace', r'seiz(?:e|ed|ure)?', r'asset\s?forfeit(?:ure|ures)?',
    r'forfeit(?:ed)?', r'sealed\s?indictment', r'racketeer(?:ing)?', r'racketeering', r'black\s?market',
    r'contraband', r'illicit\s?trade', r'possession\s?of\s?illegal', r'drug\s?bust', r'drug\s?raid',
    r'possession(?:s)?', r'distribution\s?of\s?narcotics', r'cult\s?activity', r'gang(?:s)?',
    r'organized\s?crime', r'mobster(?:s)?', r'crime\s?ring', r'perp(?:etrator)?', r'perp\s?name',
    r'asset\s?freeze', r'forfeiture', r'breach\s?of\s?probation', r'probation\s?violation', r'scantion(?:s)?',

    # Sexual violence
    r'rape(?:d|s|ist|ists)?', r'raping', r'sexual\s?assault', r'sexual\s?violence',
    r'molestation?', r'molest(?:ed|ing|er)?', r'sexual\s?abuse(?:d|s|r|rs)?', r'sexual\s?exploitation',
    r'child\s?abuse', r'child\s?molestation', r'child\s?porn(?:ography|o)?', r'pedophil(?:e|ia|es)?',
    r'grooming', r'incest', r'statutory\s?rape', r'sexual\s?harass(?:ed|ment|ing)?',
    r'sexual\s?battery', r'date\s?rape', r'rape\s?kit', r'rape\s?culture', r'assault\s?in\s?the\s?first\s?degree',
    r'assault\s?in\s?the\s?second\s?degree', r'sexual\s?exploitation', r'forced\s?sex', r'nonconsensual',
    r'voyeur(?:ism|ist)?', r'exposure(?:\s?to\s?sexual)?', r'indecent\s?assault', r'indecent\s?exposure',
    r'porno(?:graphy|graphic)?', r'child[-\s]?sex(?:ual)?\s?abuse', r'sexual\s?predator', r'sexual\s?offender',
    r'sex\s?crime(?:s)?', r'peadophilia', r'sexually\s?abused', r'sexual\s?misconduct', r'rape\s?survivor',

    # Abuse & oppression
    r'oppress(?:ion|ed|ing)?', r'discriminat(?:e|ed|ion|ory)?', r'persecutr?(?:e|ed|ion)?',
    r'ethnic\s?violenc(?:e)?', r'segregat(?:e|ed|ion)?', r'apartheid', r'torture(?:d|s)?',
    r'torment(?:ed|ing|s)?', r'humiliat(?:e|ed|ion)?', r'degrad(?:e|ed|ing|ation)?',
    r'exploit(?:ation|ed)?', r'enslave(?:d|ment)?', r'forced\s?labor', r'child\s?labor',
    r'slav(?:e|ery)?', r'serfdom', r'peonage', r'forced\s?marriage', r'fgm', r'female\s?genital\s?mutilation',
    r'cultural\s?erasure', r'systemic\s?rac(?:e|ism|ist)?', r'hate\s?crime(?:s)?', r'hate\s?speech',
    r'ethnic\s?cleansing', r'state[-\s]?sponsored\s?violence', r'political\s?persecution',
    r'genocidal', r'political\s?repression', r'blacklist(?:ed)?', r'suppression', r'coerc(?:e|ed|ion)?',
    r'ostracis(?:e|ed|m)?', r'repression', r'subjugat(?:e|ed|ion)?', r'denial\s?of\s?rights',
    r'civil\s?rights\s?violat(?:ion|ions)?', r'forced\s?displacement', r'ethnic\s?profiling',
    r'disenfranchis(?:e|ed|ment)?', r'marginaliz(?:e|ed|ation)?', r'colonial(?:ism|ist)?',
    r'cultural\s?suppression', r'repressive\s?regime', r'extrajudicial\s?detention', r'political\s?imprisonment',
    r'ideological\s?persecution', r'xenophob(?:e|ic|ia)?', r'sectarian\s?violence', r'communal\s?violence',
    r'state\s?terror(?:ism|ist)?', r'silent\s?genocide', r'forced\s?assimilation', r'ethnic\s?tension',

    # Additional cross-category terms and variants
    r'violator(?:s)?', r'victim(?:s)?', r'survivor(?:s)?', r'relat(?:ive|ives)?\s?killed',
    r'crash(?:es)?', r'incident(?:s)?', r'scandal(?:s)?', r'cover[-\s]?up', r'leak(?:ed|s)?',
    r'scuffle(?:s)?', r'altercat(?:ion|ions)?', r'fracas(?:es)?', r'brawl(?:s)?', r'riotous',
    r'mobbed', r'mobster', r'perpetrated', r'persecuted', r'victimized', r'victimisation',
    r'victimization', r'casualties', r'plunder(?:ed)?', r'raided', r'sack(?:ed)?',
    r'guns?ling(?:er|ed)?', r'proxy\s?war', r'terror(?:ist|ism|ist)?', r'terror(?:s)?',
    r'bombing(?:s)?', r'hostil(?:e|ity)', r'violator', r'abuser(?:s)?', r'abusive',
    r'inhumane', r'atrocious', r'savagery', r'barbaric', r'barbarism', r'brutality',
    r'heinous', r'heinousness', r'atrophy', r'incite(?:d|ment)?', r'incitement\s?to\s?violence',
    r'propaganda\s?of\s?violence', r'warfare', r'mass\s?violence', r'mass[-\s]?eviction',
    r'enfant', r'childrens?', r'rape?case', r'sexual?case', r'abduction', r'abducted',
]) + r')\b', re.IGNORECASE)

# --- Thumbnail extraction helpers ---
IMG_SRC_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)

def extract_thumbnail_from_summary(summary: str):
    if not summary:
        return None
    m = IMG_SRC_RE.search(summary)
    if m:
        return m.group(1)
    return None

def get_thumbnail(entry) -> str | None:
    mt = entry.get('media_thumbnail')
    if mt and isinstance(mt, (list, tuple)) and mt:
        url = mt[0].get('url') if isinstance(mt[0], dict) else mt[0]
        if url:
            return url
    if isinstance(mt, dict) and mt.get('url'):
        return mt.get('url')

    mc = entry.get('media_content')
    if mc and isinstance(mc, (list, tuple)) and mc:
        url = mc[0].get('url') if isinstance(mc[0], dict) else mc[0]
        if url:
            return url
    if isinstance(mc, dict) and mc.get('url'):
        return mc.get('url')

    links = entry.get('links') or []
    for l in links:
        rel = (l.get('rel') or '').lower()
        ltype = (l.get('type') or '').lower()
        href = l.get('href') or l.get('url')
        if not href:
            continue
        if rel == 'enclosure' and ltype.startswith('image'):
            return href
        if rel == 'thumbnail' or 'image' in ltype:
            return href

    for key in ('thumbnail', 'image', 'enclosure'):
        val = entry.get(key)
        if isinstance(val, dict) and val.get('url'):
            return val.get('url')
        if isinstance(val, str):
            return val

    summary = entry.get('summary') or entry.get('description') or ''
    thumb = extract_thumbnail_from_summary(summary)
    if thumb:
        return thumb

    sd = entry.get('summary_detail') or {}
    sd_val = sd.get('value') if isinstance(sd, dict) else None
    if sd_val:
        thumb = extract_thumbnail_from_summary(sd_val)
        if thumb:
            return thumb

    return None

def is_bangla(text: str) -> bool:
    return bool(bangla_re.search(text or ""))

def is_negative(entry) -> bool:
    text = " ".join([
        entry.get("title", "") or "",
        entry.get("summary", "") or "",
        entry.get("tags", [{}])[0].get("term", "") if entry.get("tags") else "",
    ])
    return bool(NEGATIVE_WORDS.search(text))

def make_feed(title: str, link: str, description: str, items: list) -> FeedGenerator:
    fg = FeedGenerator()
    fg.title(title)
    fg.link(href=link, rel="alternate")
    fg.description(description)
    fg.language("en")

    for entry in items:
        fe = fg.add_entry()
        fe.title(entry.get("title", "No title"))
        fe.link(href=entry.get("link", ""))
        summary = entry.get("summary", "") or ""
        thumb = get_thumbnail(entry)
        if thumb and not IMG_SRC_RE.search(summary):
            summary = f'<img src="{thumb}" alt="thumbnail" />' + summary
            try:
                fe.enclosure(thumb, 0, 'image/*')
            except Exception:
                pass
        fe.description(summary)

        pub = entry.get("published") or entry.get("updated")
        if pub:
            try:
                fe.pubDate(parsedate_to_datetime(pub))
            except Exception:
                pass

    return fg

def fetch_feed(url: str) -> list:
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        print(f"[OK] {url} — {len(feed.entries)} entries")
        return feed.entries
    except Exception as e:
        print(f"[FAIL] {url} — {e}")
        return []

def main():
    all_entries = []
    for url in SOURCE_URLS:
        all_entries.extend(fetch_feed(url))

    print(f"\nTotal entries fetched: {len(all_entries)}")

    bangla_positive, english_positive = [], []

    for entry in all_entries:
        text = (entry.get("title", "") or "") + " " + (entry.get("summary", "") or "")
        if is_negative(entry):
            continue  # skip negative articles entirely
        if is_bangla(text):
            bangla_positive.append(entry)
        else:
            english_positive.append(entry)

    print(f"Bangla saved: {len(bangla_positive)}")
    print(f"English saved: {len(english_positive)}")

    feeds = {
        "bangla.xml":  ("Bangla News",  "Filtered positive Bangla news",   bangla_positive),
        "english.xml": ("English News", "Filtered positive English news",   english_positive),
    }

    for filename, (title, desc, items) in feeds.items():
        fg = make_feed(title, SOURCE_URLS[0], desc, items)
        fg.rss_file(filename)
        print(f"Written: {filename} ({len(items)} items)")

if __name__ == "__main__":
    main()