#!/usr/bin/env python3
"""Fetch recent papers from IACR Cryptology ePrint Archive Atom feeds.

ePrint is the primary preprint archive for cryptology research (ZKP, MPC,
homomorphic encryption, post-quantum crypto, etc.). Papers carry IDs of the
form ``{year}/{number}`` (e.g. ``2025/924``).

Usage:
    python3 tools/fetch_eprint.py              # output JSON to stdout
    python3 tools/fetch_eprint.py -o out.json  # output to file
    python3 tools/fetch_eprint.py --hours 48   # fetch last 48h (default: 24h)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from html import unescape as html_unescape
from urllib.parse import urlparse

try:
    import feedparser
except ImportError:
    class _FeedParserStub:
        @staticmethod
        def parse(*args, **kwargs):
            raise ImportError("feedparser not installed")

    feedparser = _FeedParserStub()

# ePrint does not use category codes like arXiv; instead it has a single
# global feed. Category-specific feeds use the ?category=NAME query param.
DEFAULT_FEED_URL = "https://eprint.iacr.org/rss/atom.xml"

_EPRINT_ID_RE = re.compile(r"/(\d{4}/\d+)(?:\.pdf)?$")


def fetch_recent(
    hours: int = 24,
    feed_url: str | None = None,
) -> list[dict]:
    """Fetch papers from the IACR ePrint Atom feed, filtered by recency.

    Args:
        hours: Only include papers published within this many hours.
        feed_url: Override the feed URL. Defaults to the global Atom feed.

    Returns:
        Deduplicated list of paper dicts, each with keys:
        ``title``, ``abstract``, ``authors``, ``eprint_url``,
        ``eprint_id``, ``published``.
    """
    url = feed_url or DEFAULT_FEED_URL
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    papers: list[dict] = []

    try:
        feed = feedparser.parse(url)
        if getattr(feed, "bozo", False) and not feed.entries:
            print(
                f"Warning: ePrint feed {url} returned an error, skipping.",
                file=sys.stderr,
            )
            return []
    except Exception as exc:
        print(
            f"Warning: failed to fetch ePrint feed {url}: {exc}",
            file=sys.stderr,
        )
        return []

    for entry in feed.entries:
        link = entry.get("link", "")
        eprint_id = _extract_id(link)

        # --- time filter ---
        published_str = entry.get("published", "") or entry.get("updated", "")
        if published_str:
            try:
                pub_dt = datetime.fromisoformat(
                    published_str.replace("Z", "+00:00")
                )
                if pub_dt < cutoff:
                    continue
            except (ValueError, TypeError):
                pass  # unparseable — keep the entry

        # Atom feed may put authors in dc:creator fields or atom:author
        raw_authors = entry.get("authors", [])
        author_names = [
            a.get("name", "")
            for a in raw_authors
            if isinstance(a, dict) and a.get("name")
        ]
        # Fallback: parse dc:creator if authors list is empty
        if not author_names:
            dc = entry.get("dc_creator") or entry.get("creator", "")
            if dc:
                author_names = [n.strip() for n in dc.split(",") if n.strip()]

        # Summary may contain HTML tags — strip them
        abstract = entry.get("summary", "").strip()
        abstract = re.sub(r"<[^>]+>", " ", abstract)
        abstract = html_unescape(abstract)
        abstract = " ".join(abstract.split())  # collapse whitespace

        title = entry.get("title", "").strip()
        title = re.sub(r"<[^>]+>", " ", title)
        title = html_unescape(title)
        title = " ".join(title.split())

        papers.append(
            {
                "title": title,
                "abstract": abstract,
                "authors": author_names,
                "eprint_url": link,
                "eprint_id": eprint_id,
                "published": published_str,
            }
        )

    # Deduplicate by eprint_id
    seen: set[str] = set()
    unique: list[dict] = []
    for p in papers:
        eid = p["eprint_id"]
        if eid and eid not in seen:
            seen.add(eid)
            unique.append(p)
        elif not eid:
            unique.append(p)
    return unique


def _extract_id(url: str) -> str:
    """Extract ePrint ID from URL like https://eprint.iacr.org/2025/924.

    Returns the ``{year}/{number}`` segment, or empty string.
    """
    path = urlparse(url).path.rstrip("/")
    m = _EPRINT_ID_RE.search(path)
    return m.group(1) if m else ""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch recent cryptology ePrint papers via Atom feed"
    )
    parser.add_argument(
        "-o", "--output", help="Output file path (default: stdout)"
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=24,
        help="Fetch papers from last N hours (default: 24)",
    )
    parser.add_argument(
        "--feed-url",
        help="Override feed URL (default: global Atom feed)",
    )
    parser.add_argument(
        "--category",
        help="ePrint category: APPLICATIONS, PROTOCOLS, FOUNDATIONS, IMPLEMENTATION, SECRETKEY, PUBLICKEY, ATTACKS",
    )
    args = parser.parse_args()

    feed_url = args.feed_url
    if args.category and not feed_url:
        feed_url = (
            f"https://eprint.iacr.org/rss/atom.xml?category={args.category}"
        )

    papers = fetch_recent(hours=args.hours, feed_url=feed_url)
    output = json.dumps(papers, indent=2, ensure_ascii=False)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(
            f"Fetched {len(papers)} ePrint papers → {args.output}",
            file=sys.stderr,
        )
    else:
        print(output)


if __name__ == "__main__":
    main()
