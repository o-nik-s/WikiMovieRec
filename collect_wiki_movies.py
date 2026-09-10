#!/usr/bin/env python3
"""Collect movie data from Wikipedia into NDJSON format compatible with WikiMovieRec.

Format of each record (matches wp_movies_10k.ndjson):
    [Name, Description(dict), Links(list), Rating1(str), Rating2(str)]

- Name: Wikipedia article title, e.g. "Deadpool (film)"
- Description: dict of infobox fields (plain text, wiki markup stripped)
- Links: list of outgoing wiki links (including "Category:" prefixed)
- Rating1: Rotten Tomatoes score as "NN%" (if available)
- Rating2: IMDb score as "N.N/10" (if available)

Design goals:
  - **Resumable / incremental**: the NDJSON output file is the single source
    of truth. On every run we load already-collected titles from it and skip
    them, so re-running never re-fetches the same pages and never duplicates.
    This survives cache loss (e.g. moving to a new PC) — just point --out at
    the existing file and it continues where it left off.
  - **Fresh-first**: year categories are processed newest -> oldest, so new
    movies are collected first.
  - **Auto-add new**: re-running with --new (or just re-running) picks up
    movies that appeared in categories since the last run.
  - **Polite rate limiting**: adaptive delay + retries with backoff on 429.

Usage:
    # First run: collect up to 20000 movies, newest first
    python collect_wiki_movies.py --max-movies 20000 --out wp_movies_extended.ndjson

    # Resume / add more old movies (continues from existing file)
    python collect_wiki_movies.py --max-movies 30000 --out wp_movies_extended.ndjson

    # Only refresh recent years (auto-add new movies)
    python collect_wiki_movies.py --years 2026 2025 2024 --out wp_movies_extended.ndjson

    # Collect specific years only
    python collect_wiki_movies.py --years 2020 2019 --max-movies 5000
"""
import argparse
import json
import os
import re
import sys
import time

import requests

API = "https://en.wikipedia.org/w/api.php"
HEADERS = {
    "User-Agent": "WikiMovieRec/1.0 (movie recommendation research; "
                  "contact: user@example.com)"
}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)

INFOBOX_FIELDS = [
    "name", "image", "alt", "caption", "director", "producer", "writer",
    "starring", "music", "cinematography", "editing", "studio", "distributor",
    "released", "runtime", "country", "language", "budget", "gross",
]

_MARKUP_RE = re.compile(
    r"\{\{[^{}]*\}\}"
    r"|\[\[(?:[^|\]]*\|)?([^\]]+)\]\]"
    r"|<ref[^>]*>.*?</ref>"
    r"|<ref[^>]*/>"
    r"|<[^>]+>"
    r"|'''|''"
)

_MIN_DELAY = 0.15
_MAX_DELAY = 5.0
_delay = _MIN_DELAY


def _clean_value(val: str) -> str:
    if not val:
        return ""
    val = _MARKUP_RE.sub(lambda m: m.group(1) if m.group(1) else "", val)
    val = val.replace("{{!}}", "|").replace("&amp;", "&").strip()
    return val


def _parse_infobox(wikitext: str) -> dict:
    m = re.search(r"\{\{Infobox film(.*?)\n\}\}", wikitext, re.S)
    if not m:
        return {}
    box = m.group(1)
    desc = {}
    for key, val in re.findall(r"\|\s*([a-zA-Z_ ]+)\s*=\s*(.+)", box):
        key = key.strip()
        if key in INFOBOX_FIELDS:
            desc[key] = _clean_value(val)
    return desc


def _extract_ratings(wikitext: str) -> tuple[str, str]:
    rating1 = ""
    rating2 = ""
    m = re.search(r"approval rating of \{\{RT data\|score\}\}", wikitext)
    if m:
        ctx = wikitext[m.start():m.start() + 200]
        num = re.search(r"(\d{1,3})%", ctx)
        if num:
            rating1 = num.group(1) + "%"
    return rating1, rating2


def _throttle():
    global _delay
    time.sleep(_delay)


def _on_429():
    global _delay
    _delay = min(_delay * 2, _MAX_DELAY)
    print(f"  [throttle] delay -> {_delay:.2f}s", flush=True)


def _on_success():
    global _delay
    _delay = max(_MIN_DELAY, _delay * 0.9)


def _get(params: dict, retries: int = 4) -> dict:
    for attempt in range(retries):
        try:
            r = SESSION.get(API, params=params, timeout=30)
            if r.status_code == 429:
                _on_429()
                time.sleep(_delay * (attempt + 1))
                continue
            r.raise_for_status()
            _on_success()
            return r.json()
        except requests.exceptions.RequestException as e:
            if attempt == retries - 1:
                raise
            time.sleep(_delay * (attempt + 1))
    raise RuntimeError("unreachable")


def get_category_members(category: str, limit: int = 500) -> list[str]:
    titles = []
    params = {
        "action": "query",
        "list": "categorymembers",
        "cmtitle": category,
        "cmlimit": str(limit),
        "cmtype": "page",
        "format": "json",
    }
    while True:
        data = _get(params)
        members = data.get("query", {}).get("categorymembers", [])
        titles.extend(m["title"] for m in members)
        if "continue" in data:
            params["cmcontinue"] = data["continue"]["cmcontinue"]
        else:
            break
        _throttle()
    return titles


def get_page_data(title: str) -> tuple[dict, list, str]:
    params = {
        "action": "parse",
        "page": title,
        "prop": "links|wikitext",
        "format": "json",
        "redirects": 1,
    }
    data = _get(params)
    parse = data.get("parse", {})
    if not parse:
        return {}, [], ""
    links = [l.get("*", "") for l in parse.get("links", [])]
    links = [l for l in links
             if not l.startswith(("Wikipedia:", "File:", "Help:", "Template:",
                                  "Category talk:", "Talk:", "Portal:"))]
    wikitext = parse.get("wikitext", {}).get("*", "")
    infobox = _parse_infobox(wikitext)
    return infobox, links, wikitext


def load_existing(out_path: str) -> set[str]:
    """Load already-collected titles from the NDJSON file (if it exists).

    The output file is the source of truth, so state survives cache loss.
    """
    if not os.path.exists(out_path):
        return set()
    seen = set()
    with open(out_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                name = rec[0] if isinstance(rec, list) else rec.get("Name")
                if name:
                    seen.add(name)
            except (json.JSONDecodeError, IndexError, AttributeError):
                continue
    return seen


def collect_movies(years: list[int], max_movies: int, out_path: str) -> None:
    seen = load_existing(out_path)
    print(f"Already collected: {len(seen)} movies (resuming)", flush=True)

    mode = "a" if os.path.exists(out_path) else "w"
    count = len(seen)
    with open(out_path, mode, encoding="utf-8") as f:
        for year in years:
            if count >= max_movies:
                break
            category = f"Category:{year} films"
            print(f"[{year}] Fetching {category} ...", flush=True)
            titles = get_category_members(category)
            print(f"  {len(titles)} titles, {len(seen)} already known", flush=True)
            for title in titles:
                if count >= max_movies:
                    break
                if title in seen:
                    continue
                seen.add(title)
                try:
                    infobox, links, wikitext = get_page_data(title)
                except Exception as e:
                    print(f"  skip {title}: {e}", flush=True)
                    continue
                if not links and not infobox:
                    continue
                rating1, rating2 = _extract_ratings(wikitext)
                record = [title, infobox, links, rating1, rating2]
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                f.flush()
                count += 1
                if count % 100 == 0:
                    print(f"  collected {count}/{max_movies}", flush=True)
                _throttle()
    print(f"\nDone. Total {count} movies -> {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Collect movies from Wikipedia")
    parser.add_argument("--max-movies", type=int, default=20000,
                        help="Target total number of movies")
    parser.add_argument("--out", default="wp_movies_extended.ndjson",
                        help="Output NDJSON path (also used as resume state)")
    parser.add_argument("--years", type=int, nargs="*", default=None,
                        help="Specific years (default: 2026 down to 1900)")
    parser.add_argument("--min-year", type=int, default=1900,
                        help="Oldest year to include")
    args = parser.parse_args()

    if args.years:
        years = sorted(set(args.years), reverse=True)
    else:
        years = list(range(2026, args.min_year - 1, -1))

    collect_movies(years, args.max_movies, args.out)


if __name__ == "__main__":
    main()