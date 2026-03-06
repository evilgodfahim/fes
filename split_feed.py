import feedparser
from feedgen.feed import FeedGenerator
import requests
import re
from email.utils import parsedate_to_datetime

# --- Source feeds (list, not tuple) ---
SOURCE_URLS = [
    "https://politepaul.com/fd/BNnVF6SFDNH6.xml",
    "https://tbsnews.net/top-news/rss.xml",
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
    r'casualt(?:y|ies)', r'corpse(?:s)?', r'bod(?:y|ies)',
    r'lifeless', r'perish(?:ed|es|ing)?', r'toll',
    r'mourn(?:ed|ing|s)?', r'funeral(?:s)?', r'obituary', r'obituaries',
    r'bury', r'buried', r'burial', r'grave(?:s)?', r'cemetery',

    # Injury & violence
    r'injur(?:e|ed|y|ies|ing)?', r'wound(?:ed|s|ing)?',
    r'hurt(?:ing)?', r'maim(?:ed|s|ing)?', r'crippl(?:e|ed|ing)?',
    r'mutilat(?:e|ed|ion)?', r'disembowel(?:ed|ment)?',
    r'assault(?:ed|s|ing|er)?', r'attack(?:ed|s|ing|er|ers)?',
    r'beat(?:en|ing|s)?', r'batter(?:ed|ing|s)?',
    r'stab(?:bed|bing|s)?', r'shot', r'shoot(?:ing|ings|er|ers)?',
    r'gun(?:man|men|shot|shots|fire)?', r'shoot(?:out)?',
    r'bomb(?:ed|ing|ings|er|ers|blast)?', r'explo(?:sion|sions|de|ded|ding)?',
    r'blast(?:s|ed|ing)?', r'detonate(?:d|s)?', r'detonation',
    r'grenade(?:s)?', r'landmine(?:s)?', r'ied',
    r'clash(?:es|ed|ing)?', r'riot(?:s|ed|ing)?', r'violenc(?:e|es)?',
    r'aggression', r'brutal(?:ly|ity)?', r'savage(?:ly|ry)?',
    r'vicious(?:ly)?', r'bloodshed', r'bloodbath',

    # War & conflict
    r'war(?:fare|s)?', r'conflict(?:s)?', r'combat', r'battle(?:s|d)?',
    r'siege(?:s|d)?', r'invasion(?:s)?', r'invade(?:d|s)?',
    r'occupat(?:ion|ions)?', r'airstrike(?:s)?', r'air\s?raid(?:s)?',
    r'ceasefire', r'coup(?:s)?', r'insurgenc(?:y|ies)',
    r'insurgent(?:s)?', r'militia(?:s)?', r'guerrilla',
    r'terrorism?', r'terrorist(?:s)?', r'extremis(?:m|t|ts)',
    r'jihadist(?:s)?', r'militant(?:s)?', r'rebel(?:s|lion)?',
    r'uprising(?:s)?', r'genocide', r'ethnic\s?cleansing',
    r'refugee(?:s)?', r'displace(?:d|ment)?', r'fled',
    r'evacuate(?:d|s)?', r'evacuation',

    # Crime & law enforcement
    r'arrest(?:ed|s|ing)?', r'detain(?:ed|s|ing|ee|ment)?',
    r'imprison(?:ed|ment)?', r'jail(?:ed|s|ing)?', r'prison(?:er|ers|s)?',
    r'incarcer(?:ate|ated|ation)?', r'handcuff(?:ed|s)?',
    r'suspect(?:ed|s)?', r'accused', r'charg(?:e|ed|es|ing)?',
    r'indict(?:ed|ment|s)?', r'convict(?:ed|ion|ions|s)?',
    r'sentenc(?:e|ed|ing)?', r'verdict(?:s)?', r'trial(?:s)?',
    r'court(?:s)?', r'lawsuit(?:s)?', r'sue(?:d|s)?', r'suing',
    r'plead(?:ed|ing|s)?', r'guilty', r'acquitt(?:al|ed)?',
    r'parole', r'probation', r'warrant(?:s)?',
    r'crime(?:s)?', r'criminal(?:s)?', r'felony', r'felonies',
    r'misdemeanor(?:s)?', r'theft', r'rob(?:bed|bery|beries|bing)?',
    r'burglar(?:y|ies|ize|ized)?', r'loot(?:ed|ing|s)?', r'pillage(?:d)?',
    r'fraud(?:ulent)?', r'scam(?:s|med|ming)?', r'embezzl(?:e|ed|ment)?',
    r'brib(?:e|ed|ery|ing)?', r'corrupt(?:ion|ed)?',
    r'smuggl(?:e|ed|ing|er|ers)?', r'traffick(?:ed|ing|er|ers)?',
    r'kidnap(?:ped|ping|per|pers)?', r'abduct(?:ed|ion|s)?',
    r'hostage(?:s)?', r'ransom(?:ed|s)?',
    r'extort(?:ion|ed|ing)?', r'blackmail(?:ed|ing)?',
    r'stalk(?:ed|ing|er)?', r'harass(?:ed|ment|ing)?',

    # Sexual violence
    r'rape(?:d|s|ist|ists)?', r'raping', r'sexual\s?assault',
    r'molestation?', r'molest(?:ed|ing|er)?',
    r'abuse(?:d|s|r|rs)?', r'abusing',
    r'exploit(?:ed|ation|ation)?', r'grooming', r'pedophil(?:e|ia|es)?',

    # Disaster & accidents
    r'disaster(?:s)?', r'catastrophe(?:s)?', r'calamity',
    r'accident(?:s)?', r'crash(?:es|ed|ing)?', r'collide(?:d|s)?',
    r'collision(?:s)?', r'wreck(?:s|ed|ing)?', r'derail(?:ed|ment|s)?',
    r'capsize(?:d|s)?', r'shipwreck(?:s)?', r'drown(?:ed|ing|s)?',
    r'flood(?:s|ed|ing)?', r'earthquake(?:s)?', r'tsunami(?:s)?',
    r'cyclone(?:s)?', r'hurricane(?:s)?', r'tornado(?:es|s)?',
    r'wildfire(?:s)?', r'blaze(?:s|d)?', r'inferno',
    r'collapse(?:d|s|sing)?', r'landslide(?:s)?', r'avalanche(?:s)?',
    r'famine(?:s)?', r'drought(?:s)?', r'starv(?:e|ed|ing|ation)',

    # Health crisis
    r'epidemic(?:s)?', r'pandemic(?:s)?', r'outbreak(?:s)?',
    r'plague(?:s)?', r'contagion', r'contaminat(?:e|ed|ion)',
    r'poison(?:ed|ing|s)?', r'toxic(?:ity)?', r'overdos(?:e|ed|ing)?',
    r'suicide(?:s)?', r'suicidal', r'self.harm',

    # Political & economic turmoil
    r'sanction(?:s|ed)?', r'ban(?:ned|s|ning)?', r'embargo(?:es|ed)?',
    r'protest(?:s|ed|ing|er|ers)?', r'demonstrat(?:e|ed|ion|ions|or|ors)?',
    r'crackdown(?:s)?', r'suppres(?:s|sed|sion)?', r'censor(?:ed|ship|s)?',
    r'propaganda', r'disinformation', r'misinformation',
    r'impeach(?:ed|ment|s)?', r'resign(?:ed|ation|s)?',
    r'scandal(?:s)?', r'controversy', r'controversies',
    r'allegation(?:s)?', r'accus(?:e|ed|ation|ations)?',
    r'recession', r'depression', r'bankruptcy', r'bankruptcies',
    r'bankrupt(?:ed|s)?', r'default(?:ed|s|ing)?',
    r'collapse(?:d|s)?', r'crisis', r'crises',
    r'inflation', r'poverty', r'destitut(?:e|ion)',
    r'unemployment', r'layoff(?:s)?', r'retrench(?:ment|ed)?',
    r'strike(?:s|d)?', r'lockout(?:s)?',

    # Abuse & oppression
    r'oppress(?:ion|ed|ing)?', r'discriminat(?:e|ed|ion|ory)?',
    r'persecutr?(?:e|ed|ion)?', r'ethnic\s?violenc(?:e)?',
    r'segregat(?:e|ed|ion)?', r'apartheid', r'torture(?:d|s)?',
    r'torment(?:ed|ing|s)?', r'humiliat(?:e|ed|ion)?',
    r'degrad(?:e|ed|ing|ation)?', r'exploit(?:ation|ed)?',
    r'enslave(?:d|ment)?', r'forced\s?labor', r'child\s?labor',

    # Misc danger
    r'threat(?:s|ened|ening)?', r'danger(?:ous|ed)?',
    r'hazard(?:ous|s)?', r'risk(?:s)?', r'peril(?:ous|s)?',
    r'emergency', r'emergencies', r'crisis', r'crises',
    r'ultimatum(?:s)?', r'blackout(?:s)?', r'shutdown(?:s)?',
    r'quarantine(?:d|s)?', r'lockdown(?:s)?',
]) + r')\b', re.IGNORECASE)


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
        fe.description(entry.get("summary", ""))

        # Safely parse pubDate
        pub = entry.get("published") or entry.get("updated")
        if pub:
            try:
                fe.pubDate(parsedate_to_datetime(pub))
            except Exception:
                pass  # skip malformed dates

    return fg


def fetch_feed(url: str) -> list:
    """Fetch and parse a single RSS URL, return list of entries."""
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

    bangla_positive, bangla_negative = [], []
    english_positive, english_negative = [], []

    for entry in all_entries:
        text = (entry.get("title", "") or "") + " " + (entry.get("summary", "") or "")
        negative = is_negative(entry)
        bangla = is_bangla(text)

        if bangla:
            (bangla_negative if negative else bangla_positive).append(entry)
        else:
            (english_negative if negative else english_positive).append(entry)

    print(f"Bangla positive: {len(bangla_positive)} | negative: {len(bangla_negative)}")
    print(f"English positive: {len(english_positive)} | negative: {len(english_negative)}")

    # Write output feeds
    feeds = {
        "bangla_positive.xml":  ("Bangla Positive News",  "Filtered positive Bangla news",   bangla_positive),
        "bangla_negative.xml":  ("Bangla Negative News",  "Filtered negative Bangla news",    bangla_negative),
        "english_positive.xml": ("English Positive News", "Filtered positive English news",   english_positive),
        "english_negative.xml": ("English Negative News", "Filtered negative English news",   english_negative),
    }

    for filename, (title, desc, items) in feeds.items():
        fg = make_feed(title, SOURCE_URLS[0], desc, items)
        fg.rss_file(filename)
        print(f"Written: {filename} ({len(items)} items)")


if __name__ == "__main__":
    main()
