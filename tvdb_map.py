"""Map a streaming service's episode to TVDB numbering by air date.

Trackers (BLU, LST) name episodes by TVDB's default order, which often differs
from the service's own numbering (Crunchyroll's "Season 4" of Bleach TYBW is
TVDB S17). Run this helper before uploading:

    python tvdb_map.py --tmdb tv/30984 --episode 2026-10-18T15:00:00Z "THE BLADE"

Prints one JSON line per --episode, in order: {"season": 17, "episode": 49,
"aired": "2026-10-19", "name": "THE BLADE"}, or {"error": "..."} when no
single TVDB episode matches. Uses UA's TVDB client and UA's TMDb key.
"""
import argparse
import asyncio
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

import httpx

from data.config import config
from src.tvdb import tvdb_data

MAX_DAYS_APART = 2  # service air date (UTC timestamp) vs TVDB's local air date


def _norm(text: Optional[str]) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def _air_dates(value: str) -> set[date]:
    """Calendar dates the air timestamp can fall on: as given (UTC) and in Japan time."""
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        return {stamp.date()}
    return {stamp.astimezone(timezone.utc).date(), stamp.astimezone(timezone(timedelta(hours=9))).date()}


def _tvdb_series_id(tmdb: Optional[str], imdb: Optional[str]) -> Optional[int]:
    key = config["DEFAULT"]["tmdb_api"]
    with httpx.Client(timeout=20) as client:
        if not tmdb and imdb:
            found = client.get(f"https://api.themoviedb.org/3/find/{imdb}",
                               params={"api_key": key, "external_source": "imdb_id"}).json()
            results = found.get("tv_results") or []
            tmdb = f"tv/{results[0]['id']}" if results else None
        if not tmdb or not tmdb.startswith("tv/"):
            return None
        ids = client.get(f"https://api.themoviedb.org/3/{tmdb}/external_ids", params={"api_key": key}).json()
        return ids.get("tvdb_id")


def match_episode(episodes: list[dict[str, Any]], aired: str, title: Optional[str]) -> dict[str, Any]:
    days = _air_dates(aired)
    candidates = []
    for ep in episodes:
        if not ep.get("aired") or not ep.get("seasonNumber"):  # skip specials (season 0)
            continue
        apart = min(abs((date.fromisoformat(ep["aired"]) - d).days) for d in days)
        if apart <= MAX_DAYS_APART:
            candidates.append((apart, ep))
    if title:
        by_title = [ep for _, ep in candidates if _norm(ep.get("name")) == _norm(title)]
        if len(by_title) == 1:
            candidates = [(0, by_title[0])]
    if not candidates:
        return {"error": f"no TVDB episode aired within {MAX_DAYS_APART} days of {aired}"}
    best = min(apart for apart, _ in candidates)
    closest = [ep for apart, ep in candidates if apart == best]
    if len(closest) > 1:
        return {"error": "ambiguous: " + ", ".join(f"S{e['seasonNumber']:02d}E{e['number']:02d}" for e in closest)}
    ep = closest[0]
    return {"season": ep["seasonNumber"], "episode": ep["number"], "aired": ep["aired"], "name": ep.get("name")}


async def main() -> None:
    parser = argparse.ArgumentParser(description="Map service episodes to TVDB season/episode by air date.")
    parser.add_argument("--tmdb", help="tv/30984")
    parser.add_argument("--imdb", help="tt0434665")
    parser.add_argument("--episode", nargs=2, action="append", metavar=("AIRED", "TITLE"), required=True,
                        help="Service air timestamp (ISO 8601) and episode title; repeatable")
    args = parser.parse_args()

    series_id = _tvdb_series_id(args.tmdb, args.imdb)
    if not series_id:
        for _ in args.episode:
            print(json.dumps({"error": "no TVDB series id for this TMDb/IMDb id"}))
        return
    data, _ = await tvdb_data(config).get_tvdb_episodes(series_id, base_dir=".")
    episodes = (data or {}).get("episodes") or []
    for aired, title in args.episode:
        print(json.dumps(match_episode(episodes, aired, title) if episodes else {"error": "no TVDB episodes"}))


if __name__ == "__main__":
    asyncio.run(main())
    sys.stdout.flush()
