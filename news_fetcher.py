# -*- coding: utf-8 -*-
"""Fetch global news RSS feeds and render a local HTML dashboard."""

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
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parent
SOURCES_PATH = ROOT / "sources.json"
DIST_DIR = ROOT / "dist"
OUTPUT_PATH = DIST_DIR / "index.html"
USER_AGENT = "GlobalNewsTracker/1.0 (+https://github.com/example/global-news-tracker)"

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


def clean_text(value: str | None, *, limit: int | None = None) -> str:
    text = html.unescape(value or "")
    text = re.sub(r"<[^>]+>", " ", text)
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
    for name in names:
        found = node.find(name)
        if found is not None and found.text:
            return found.text
    for child in node:
        local = child.tag.rsplit("}", 1)[-1].lower()
        if local in names and child.text:
            return child.text
    return ""


def find_atom_link(node: ET.Element) -> str:
    for child in node:
        local = child.tag.rsplit("}", 1)[-1].lower()
        if local == "link":
            href = child.attrib.get("href", "").strip()
            if href:
                return href
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

        link = find_atom_link(item)
        summary = clean_text(
            find_text(item, ["description", "summary", "content"]),
            limit=220,
        )
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


def collect_news(sources: list[Source], *, timeout: int = 15, limit: int = 60) -> tuple[list[Article], list[str]]:
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

    ranked = sorted(
        deduped.values(),
        key=lambda item: (item.score, item.published_iso),
        reverse=True,
    )
    return ranked[:limit], errors


def render_html(articles: list[Article], sources: list[Source], errors: list[str]) -> str:
    generated_at = dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
    regions = sorted({source.region for source in sources})
    source_names = sorted({source.name for source in sources})
    top_score = articles[0].score if articles else 0

    article_cards = "\n".join(render_article(article) for article in articles)
    region_options = "\n".join(f'<option value="{html.escape(region)}">{html.escape(region)}</option>' for region in regions)
    source_options = "\n".join(f'<option value="{html.escape(source)}">{html.escape(source)}</option>' for source in source_names)
    errors_html = "".join(f"<li>{html.escape(error)}</li>" for error in errors)

    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>全球热点新闻雷达</title>
    <link rel="stylesheet" href="../assets/styles.css" />
  </head>
  <body>
    <main class="shell">
      <header class="topbar">
        <div class="brand">
          <img src="../assets/news-mark.svg" alt="" class="brand-mark" />
          <div>
            <h1>全球热点新闻雷达</h1>
            <p>自动抓取公开 RSS 新闻源，按时效、来源权重和热点关键词排序。</p>
          </div>
        </div>
        <div class="updated">
          <span>Updated</span>
          <strong>{generated_at}</strong>
        </div>
      </header>

      <section class="metrics" aria-label="新闻统计">
        <article>
          <span>新闻数量</span>
          <strong>{len(articles)}</strong>
        </article>
        <article>
          <span>新闻源</span>
          <strong>{len(sources)}</strong>
        </article>
        <article>
          <span>最高热度</span>
          <strong>{top_score}</strong>
        </article>
      </section>

      <section class="toolbar" aria-label="筛选新闻">
        <label>
          <span>搜索</span>
          <input id="searchBox" type="search" placeholder="输入关键词" />
        </label>
        <label>
          <span>地区</span>
          <select id="regionFilter">
            <option value="">全部地区</option>
            {region_options}
          </select>
        </label>
        <label>
          <span>来源</span>
          <select id="sourceFilter">
            <option value="">全部来源</option>
            {source_options}
          </select>
        </label>
      </section>

      <section class="news-list" id="newsList" aria-live="polite">
        {article_cards or '<p class="empty">还没有抓到新闻。请检查网络或新闻源配置。</p>'}
      </section>

      {f'<section class="errors"><h2>抓取警告</h2><ul>{errors_html}</ul></section>' if errors else ''}
    </main>
    <script>
      const searchBox = document.querySelector("#searchBox");
      const regionFilter = document.querySelector("#regionFilter");
      const sourceFilter = document.querySelector("#sourceFilter");
      const cards = Array.from(document.querySelectorAll(".news-card"));

      function applyFilters() {{
        const query = searchBox.value.trim().toLowerCase();
        const region = regionFilter.value;
        const source = sourceFilter.value;

        for (const card of cards) {{
          const text = card.textContent.toLowerCase();
          const matchesQuery = !query || text.includes(query);
          const matchesRegion = !region || card.dataset.region === region;
          const matchesSource = !source || card.dataset.source === source;
          card.hidden = !(matchesQuery && matchesRegion && matchesSource);
        }}
      }}

      searchBox.addEventListener("input", applyFilters);
      regionFilter.addEventListener("change", applyFilters);
      sourceFilter.addEventListener("change", applyFilters);
    </script>
  </body>
</html>
"""


def render_article(article: Article) -> str:
    title = html.escape(article.title)
    link = html.escape(article.link or "#")
    summary = html.escape(article.summary or "暂无摘要")
    source = html.escape(article.source)
    region = html.escape(article.region)
    keywords = " ".join(f"<span>{html.escape(word)}</span>" for word in article.keywords)

    return f"""<article class="news-card" data-region="{region}" data-source="{source}">
  <div class="card-head">
    <span class="source">{source}</span>
    <span class="region">{region}</span>
  </div>
  <h2><a href="{link}" target="_blank" rel="noreferrer">{title}</a></h2>
  <p>{summary}</p>
  <div class="card-meta">
    <time>{html.escape(article.published)}</time>
    <span class="score">热度 {article.score}</span>
  </div>
  <div class="scorebar" aria-hidden="true"><i style="width: {article.score}%"></i></div>
  <div class="keywords">{keywords or '<span>latest</span>'}</div>
</article>"""


def write_outputs(articles: list[Article], sources: list[Source], errors: list[str]) -> None:
    DIST_DIR.mkdir(exist_ok=True)
    OUTPUT_PATH.write_text(render_html(articles, sources, errors), encoding="utf-8")
    (DIST_DIR / "latest.json").write_text(
        json.dumps([asdict(article) for article in articles], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch global RSS news and build a local HTML dashboard.")
    parser.add_argument("--limit", type=int, default=60, help="Maximum number of articles to render.")
    parser.add_argument("--timeout", type=int, default=15, help="Network timeout per source, in seconds.")
    parser.add_argument("--json", action="store_true", help="Print collected articles as JSON.")
    args = parser.parse_args(argv)

    sources = load_sources()
    articles, errors = collect_news(sources, timeout=args.timeout, limit=args.limit)
    write_outputs(articles, sources, errors)

    if args.json:
        print(json.dumps({"articles": [asdict(article) for article in articles], "errors": errors}, ensure_ascii=False, indent=2))
    else:
        print(f"Fetched {len(articles)} articles from {len(sources)} sources.")
        print(f"Dashboard: {OUTPUT_PATH}")
        if errors:
            print(f"Warnings: {len(errors)} source(s) failed.", file=sys.stderr)
    return 0 if articles else 1


if __name__ == "__main__":
    raise SystemExit(main())
