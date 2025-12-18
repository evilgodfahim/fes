import feedparser
from feedgen.feed import FeedGenerator
import requests
import re

# Source mixed feed
SOURCE_URL = "https://politepaul.com/fd/BNnVF6SFDNH6.xml"

# Regex to detect Bangla characters
bangla_re = re.compile(r'[\u0980-\u09FF]')

def is_bangla(text):
    return bool(bangla_re.search(text))

def make_feed(title, link, description, items):
    fg = FeedGenerator()
    fg.title(title)
    fg.link(href=link, rel="alternate")
    fg.description(description)
    fg.language("en")

    for entry in items:
        fe = fg.add_entry()
        fe.title(entry.get("title", ""))
        fe.link(href=entry.get("link", ""))
        fe.description(entry.get("summary", ""))
        if "published" in entry:
            fe.pubDate(entry.get("published"))

    return fg

def main():
    resp = requests.get(SOURCE_URL)
    feed = feedparser.parse(resp.content)

    bangla_items, english_items = [], []

    for entry in feed.entries:
        text = (entry.get("title", "") or "") + " " + (entry.get("summary", "") or "")
        if is_bangla(text):
            bangla_items.append(entry)
        else:
            english_items.append(entry)

    bangla_feed = make_feed("Bangla News", SOURCE_URL, "Filtered Bangla News", bangla_items)
    english_feed = make_feed("English News", SOURCE_URL, "Filtered English News", english_items)

    bangla_feed.rss_file("bangla.xml")
    english_feed.rss_file("english.xml")

if __name__ == "__main__":
    main()
