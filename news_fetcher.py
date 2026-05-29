# -*- coding: utf-8 -*-
"""Fetch public RSS feeds and build data for the public GitHub Pages app."""

from __future__ import annotations

import argparse
import datetime as dt
import email.utils
import html
import json
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parent
SOURCES_PATH = ROOT / "sources.json"
DIST_DIR = ROOT / "dist"
JSON_PATH = DIST_DIR / "latest.json"
LEGACY_HTML_PATH = DIST_DIR / "index.html"
USER_AGENT = "GlobalNewsTracker/2.0 (+https://github.com/001zxt/global-news-tracker)"

HOT_KEYWORDS = {
    "ai": r"(?<![a-z0-9])(?:ai|artificial intelligence)(?![a-z0-9])",
    "election": r"(?<![a-z0-9])elections?(?![a-z0-9])",
    "war": r"(?<![a-z0-9])war(?![a-z0-9])",
    "ceasefire": r"(?<![a-z0-9])cease[-\s]?fire(?![a-z0-9])",
    "climate": r"(?<![a-z0-9])climate(?![a-z0-9])",
    "earthquake": r"(?<![a-z0-9])earthquakes?(?![a-z0-9])",
    "flood": r"(?<![a-z0-9])floods?(?![a-z0-9])",
    "wildfire": r"(?<![a-z0-9])wildfires?(?![a-z0-9])",
    "market": r"(?<![a-z0-9])markets?(?![a-z0-9])",
    "inflation": r"(?<![a-z0-9])inflation(?![a-z0-9])",
    "cyber": r"(?<![a-z0-9])cyber(?:attack|security|crime|warfare)?(?![a-z0-9])",
    "security": r"(?<![a-z0-9])security(?![a-z0-9])",
    "pandemic": r"(?<![a-z0-9])pandemic(?![a-z0-9])",
    "energy": r"(?<![a-z0-9])energy(?![a-z0-9])",
    "china": r"(?<![a-z0-9])china(?![a-z0-9])",
    "us": r"(?<![a-z0-9])(?:u\.s\.|us|united states)(?![a-z0-9])",
    "europe": r"(?<![a-z0-9])europe(?:an)?(?![a-z0-9])",
    "russia": r"(?<![a-z0-9])russia(?:n)?(?![a-z0-9])",
    "ukraine": r"(?<![a-z0-9])ukraine(?:ian)?(?![a-z0-9])",
    "middle east": r"(?<![a-z0-9])middle east(?![a-z0-9])",
}

MOJIBAKE_REPLACEMENTS = {
    "â€™": "’",
    "â€˜": "‘",
    "â€œ": "“",
    "â€": "”",
    "â€“": "–",
    "â€”": "—",
    "â€¦": "…",
    "Â£": "£",
    "Â©": "©",
    "Â®": "®",
    "Â": "",
    "鈥檚": "’s",
    "鈥檛": "’t",
    "鈥檙": "’r",
    "鈥檝": "’v",
    "鈥檓": "’m",
    "鈥檒": "’l",
    "鈥榝": "‘f",
    "鈥榚": "‘e",
    "鈥榮": "‘s",
    "鈥榯": "‘t",
    "鈥榠": "‘i",
    "鈥?": "’",
    "鈥�": "’",
    "鈥嬧€?": "",
}


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    region: str
    weight: int = 50


@dataclass
class Article:
    title: str
    link: str
    summary: str
    source: str
    region: str
    published: str
    published_iso: str
    score: int
    keywords: list[str]


def repair_mojibake(value: str) -> str:
    text = value
    for bad, good in MOJIBAKE_REPLACEMENTS.items():
        text = text.replace(bad, good)
    return text


def clean_text(value: str | None, *, limit: int | None = None) -> str:
    text = html.unescape(value or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = repair_mojibake(text)
    text = re.sub(r"\s+", " ", text).strip()
    if limit and len(text) > limit:
        return text[: limit - 1].rstrip() + "..."
    return text


def normalize_key(title: str) -> str:
    key = re.sub(r"[^\w\s]", "", title.lower(), flags=re.UNICODE)
    return re.sub(r"\s+", " ", key).strip()


def parse_date(value: str | None) -> tuple[str, str, dt.datetime | None]:
    if not value:
        return "Unknown time", "", None

    text = value.strip()
    parsed: dt.datetime | None = None
    try:
        parsed = email.utils.parsedate_to_datetime(text)
    except (TypeError, ValueError):
        normalized = text.replace("Z", "+00:00")
        try:
            parsed = dt.datetime.fromisoformat(normalized)
        except ValueError:
            parsed = None

    if parsed is None:
        return clean_text(text, limit=40), "", None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    local = parsed.astimezone()
    return local.strftime("%Y-%m-%d %H:%M"), parsed.astimezone(dt.timezone.utc).isoformat(), parsed


def find_text(node: ET.Element, names: Iterable[str]) -> str:
    wanted = {name.lower() for name in names}
    for child in node.iter():
        local = child.tag.rsplit("}", 1)[-1].lower()
        if local in wanted and child.text:
            return child.text
    return ""


def find_atom_link(node: ET.Element) -> str:
    for child in node:
        local = child.tag.rsplit("}", 1)[-1].lower()
        if local == "link":
            href = child.attrib.get("href", "").strip()
            if href:
                return href
            if child.text:
                return child.text.strip()
    return find_text(node, ["link"])


def score_article(source: Source, title: str, summary: str, published_at: dt.datetime | None) -> tuple[int, list[str]]:
    now = dt.datetime.now(dt.timezone.utc)
    score = source.weight

    if published_at:
        age_hours = max((now - published_at.astimezone(dt.timezone.utc)).total_seconds() / 3600, 0)
        if age_hours <= 3:
            score += 45
        elif age_hours <= 12:
            score += 32
        elif age_hours <= 24:
            score += 22
        elif age_hours <= 72:
            score += 10

    haystack = f"{title} {summary}".lower()
    keywords = [word for word, pattern in HOT_KEYWORDS.items() if re.search(pattern, haystack)]
    score += min(len(keywords) * 7, 35)
    return min(score, 100), sorted(keywords)[:5]


def parse_feed(xml_bytes: bytes, source: Source) -> list[Article]:
    root = ET.fromstring(xml_bytes)
    items = root.findall("./channel/item")
    if not items:
        items = [node for node in root.iter() if node.tag.rsplit("}", 1)[-1].lower() == "entry"]

    articles: list[Article] = []
    for item in items:
        title = clean_text(find_text(item, ["title"]))
        if not title:
            continue

        link = clean_text(find_atom_link(item))
        summary = clean_text(find_text(item, ["description", "summary", "content", "encoded"]), limit=260)
        published_raw = find_text(item, ["pubDate", "published", "updated", "date"])
        published, published_iso, published_at = parse_date(published_raw)
        score, keywords = score_article(source, title, summary, published_at)

        articles.append(
            Article(
                title=title,
                link=link,
                summary=summary,
                source=source.name,
                region=source.region,
                published=published,
                published_iso=published_iso,
                score=score,
                keywords=keywords,
            )
        )
    return articles


def load_sources(path: Path = SOURCES_PATH) -> list[Source]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [Source(**entry) for entry in raw["sources"]]


def fetch_feed(source: Source, timeout: int) -> bytes:
    request = urllib.request.Request(
        source.url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def collect_news(sources: list[Source], *, timeout: int = 15, limit: int = 80) -> tuple[list[Article], list[str]]:
    articles: list[Article] = []
    errors: list[str] = []

    for source in sources:
        try:
            articles.extend(parse_feed(fetch_feed(source, timeout), source))
        except (urllib.error.URLError, TimeoutError, ET.ParseError, OSError) as exc:
            errors.append(f"{source.name}: {exc}")

    deduped: dict[str, Article] = {}
    for article in articles:
        key = normalize_key(article.title)
        if not key:
            continue
        existing = deduped.get(key)
        if existing is None or article.score > existing.score:
            deduped[key] = article

    ranked = sorted(deduped.values(), key=lambda item: (item.score, item.published_iso), reverse=True)
    return ranked[:limit], errors


def write_outputs(articles: list[Article], sources: list[Source], errors: list[str]) -> None:
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    generated_at = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    payload = {
        "generated_at": generated_at,
        "article_count": len(articles),
        "source_count": len(sources),
        "errors": errors,
        "articles": [asdict(article) for article in articles],
    }
    JSON_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    LEGACY_HTML_PATH.write_text(
        """<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta http-equiv="refresh" content="0; url=../" />
    <title>全球热点新闻追踪器</title>
  </head>
  <body>
    <a href="../">打开全球热点新闻追踪器</a>
  </body>
</html>
""",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch global RSS news and update GitHub Pages data.")
    parser.add_argument("--limit", type=int, default=80, help="Maximum number of articles to keep.")
    parser.add_argument("--timeout", type=int, default=15, help="Timeout per RSS source in seconds.")
    args = parser.parse_args(argv)

    sources = load_sources()
    articles, errors = collect_news(sources, timeout=args.timeout, limit=args.limit)
    write_outputs(articles, sources, errors)

    print(f"Wrote {len(articles)} articles to {JSON_PATH}")
    if errors:
        print("Some feeds failed:")
        for error in errors:
            print(f"- {error}")
    return 0 if articles else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
