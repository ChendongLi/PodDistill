"""
Podcast registry — loads podcasts.yaml, auto-resolves RSS + YouTube sources,
caches results in registry.json (discovery runs once per podcast).
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Optional

import requests
import yaml

log = logging.getLogger(__name__)

ITUNES_SEARCH_URL = "https://itunes.apple.com/search"
YOUTUBE_SEARCH_URL = "https://www.youtube.com/results"
REGISTRY_FILE = Path("registry.json")
PODCASTS_FILE = Path("podcasts.yaml")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class PodcastSource:
    def __init__(
        self,
        name: str,
        rss_url: Optional[str] = None,
        youtube_channel_id: Optional[str] = None,
        youtube_channel_url: Optional[str] = None,
    ):
        self.name = name
        self.rss_url = rss_url
        self.youtube_channel_id = youtube_channel_id
        self.youtube_channel_url = youtube_channel_url

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "rss_url": self.rss_url,
            "youtube_channel_id": self.youtube_channel_id,
            "youtube_channel_url": self.youtube_channel_url,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PodcastSource":
        return cls(
            name=d["name"],
            rss_url=d.get("rss_url"),
            youtube_channel_id=d.get("youtube_channel_id"),
            youtube_channel_url=d.get("youtube_channel_url"),
        )

    def has_source(self) -> bool:
        return bool(self.rss_url or self.youtube_channel_url)


# ---------------------------------------------------------------------------
# Discovery helpers
# ---------------------------------------------------------------------------

def resolve_rss_via_itunes(podcast_name: str, timeout: int = 10) -> Optional[str]:
    """Search iTunes API and return the feed URL for the best match."""
    try:
        resp = requests.get(
            ITUNES_SEARCH_URL,
            params={"term": podcast_name, "media": "podcast", "limit": 5},
            timeout=timeout,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            log.warning("iTunes: no results for %r", podcast_name)
            return None
        # Pick best match: prefer exact name match, else first result
        name_lower = podcast_name.lower()
        for r in results:
            if r.get("collectionName", "").lower() == name_lower:
                return r.get("feedUrl")
        return results[0].get("feedUrl")
    except Exception as e:
        log.error("iTunes lookup failed for %r: %s", podcast_name, e)
        return None


def resolve_youtube_channel(podcast_name: str, timeout: int = 10) -> tuple[Optional[str], Optional[str]]:
    """
    Scrape YouTube search results to find official channel.
    Returns (channel_id, channel_url) or (None, None).
    No API key required — uses public search page.
    """
    try:
        query = f"{podcast_name} official podcast"
        resp = requests.get(
            YOUTUBE_SEARCH_URL,
            params={"search_query": query},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=timeout,
        )
        resp.raise_for_status()
        # Extract channel handles / IDs from search results HTML
        channel_ids = re.findall(r'"channelId":"(UC[a-zA-Z0-9_-]{22})"', resp.text)
        channel_urls = re.findall(r'"canonicalBaseUrl":"(/(?:@|channel/)[^"]+)"', resp.text)
        if channel_ids and channel_urls:
            channel_id = channel_ids[0]
            channel_url = f"https://www.youtube.com{channel_urls[0]}"
            return channel_id, channel_url
        elif channel_ids:
            channel_id = channel_ids[0]
            return channel_id, f"https://www.youtube.com/channel/{channel_id}"
        log.warning("YouTube: no channel found for %r", podcast_name)
        return None, None
    except Exception as e:
        log.error("YouTube lookup failed for %r: %s", podcast_name, e)
        return None, None


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def load_podcasts_yaml(path: Path = PODCASTS_FILE) -> list[str]:
    """Load podcast names from podcasts.yaml."""
    with open(path) as f:
        data = yaml.safe_load(f)
    return [p["name"] for p in data.get("podcasts", [])]


def load_registry(path: Path = REGISTRY_FILE) -> dict[str, PodcastSource]:
    """Load cached registry.json, return dict keyed by podcast name."""
    if not path.exists():
        return {}
    with open(path) as f:
        raw = json.load(f)
    return {name: PodcastSource.from_dict(entry) for name, entry in raw.items()}


def save_registry(registry: dict[str, PodcastSource], path: Path = REGISTRY_FILE) -> None:
    """Persist registry to registry.json."""
    with open(path, "w") as f:
        json.dump({name: src.to_dict() for name, src in registry.items()}, f, indent=2)
    log.info("Registry saved: %d podcasts", len(registry))


def build_registry(
    podcasts_path: Path = PODCASTS_FILE,
    registry_path: Path = REGISTRY_FILE,
    discover_delay: float = 1.0,
) -> dict[str, PodcastSource]:
    """
    Load podcasts.yaml + cached registry.json. For any podcast not yet
    resolved, run auto-discovery (iTunes + YouTube). Save and return.
    """
    names = load_podcasts_yaml(podcasts_path)
    registry = load_registry(registry_path)
    changed = False

    for name in names:
        if name in registry and registry[name].has_source():
            log.info("Registry hit: %r", name)
            continue

        log.info("Discovering sources for %r...", name)
        rss_url = resolve_rss_via_itunes(name)
        channel_id, channel_url = resolve_youtube_channel(name)

        registry[name] = PodcastSource(
            name=name,
            rss_url=rss_url,
            youtube_channel_id=channel_id,
            youtube_channel_url=channel_url,
        )
        changed = True

        if discover_delay:
            time.sleep(discover_delay)  # be polite to external APIs

    if changed:
        save_registry(registry, registry_path)

    return registry
