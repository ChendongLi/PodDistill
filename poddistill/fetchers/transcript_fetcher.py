"""
TranscriptAPI fetcher — primary transcript source for PodDistill.

Uses transcriptapi.com to fetch YouTube transcripts and discover
the latest episode per show by searching channel video titles.

API docs: https://transcriptapi.com/openapi.json
Endpoint: https://transcriptapi.com/api/v2/youtube/
"""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

log = logging.getLogger(__name__)

TRANSCRIPT_API_BASE = "https://transcriptapi.com/api/v2/youtube"
DEFAULT_TIMEOUT_TRANSCRIPT = 90
DEFAULT_TIMEOUT_CHANNEL = 20
MIN_DURATION_SECONDS = 120  # ignore clips shorter than 2 min


class TranscriptFetchError(Exception):
    """Raised when transcript fetching fails."""


class TranscriptSegment:
    """A single transcript segment with text and timestamp."""

    def __init__(self, text: str, offset_seconds: float):
        self.text = text
        self.offset_seconds = offset_seconds

    @property
    def timestamp_str(self) -> str:
        mins, secs = divmod(int(self.offset_seconds), 60)
        return f"{mins}:{secs:02d}"

    def __repr__(self) -> str:
        return f"[{self.timestamp_str}] {self.text[:60]}"


class TranscriptFetcher:
    """
    Fetches YouTube transcripts via TranscriptAPI.com.

    Usage:
        fetcher = TranscriptFetcher(api_key="sk_...")
        segments = fetcher.fetch_transcript("dQw4w9WgXcQ")
        video_id, title = fetcher.find_latest_episode(channel_id, keywords=["the close"])
    """

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("TranscriptAPI key is required")
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {api_key}"})

    def _get(self, path: str, params: dict, timeout: int) -> dict:
        url = f"{TRANSCRIPT_API_BASE}/{path.lstrip('/')}"
        try:
            r = self.session.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except requests.Timeout:
            raise  # propagate so fetch_transcript can retry
        except requests.HTTPError as e:
            raise TranscriptFetchError(
                f"TranscriptAPI HTTP {e.response.status_code} for {url}: {e.response.text[:200]}"
            ) from e
        except requests.RequestException as e:
            raise TranscriptFetchError(f"TranscriptAPI request failed: {e}") from e

    def get_channel_videos(self, channel_id: str) -> list[dict[str, Any]]:
        """Return up to 100 recent videos from a YouTube channel."""
        data = self._get("channel/videos", {"channel": channel_id}, DEFAULT_TIMEOUT_CHANNEL)
        return data.get("results", [])

    def find_latest_episode(
        self,
        channel_id: str,
        keywords: list[str] | None = None,
        min_duration_seconds: int = MIN_DURATION_SECONDS,
        first_match: bool = False,
    ) -> tuple[str, str] | tuple[None, None]:
        """
        Find the most recent video in a channel whose title matches any keyword.
        Skips #Shorts and clips shorter than min_duration_seconds.

        Args:
            channel_id: YouTube channel ID.
            keywords: List of lowercase title substrings to match. Ignored when first_match=True.
            min_duration_seconds: Minimum episode length to accept (first pass).
            first_match: When True, skip keyword filtering and return the first non-Shorts
                video that meets the duration threshold (or the absolute first non-Shorts
                video if none meets it). Use for channels like Morgan Stanley where episode
                titles are topic-specific rather than show-name-containing.

        Returns:
            (video_id, title) or (None, None).
        """
        videos = self.get_channel_videos(channel_id)

        if first_match:
            # First pass: respect duration filter
            for video in videos:
                title = video.get("title", "")
                if "#shorts" in title.lower():
                    continue
                dur_text = video.get("lengthText", "")
                if dur_text:
                    total = _parse_duration(dur_text)
                    if total is not None and total < min_duration_seconds:
                        continue
                return video["videoId"], title

            # Second pass: skip duration filter (catch very short episodes)
            for video in videos:
                title = video.get("title", "")
                if "#shorts" in title.lower():
                    continue
                log.warning(
                    "find_latest_episode: first_match returned video without duration filter "
                    "(video=%s, title=%s)",
                    video["videoId"],
                    title[:60],
                )
                return video["videoId"], title

            return None, None

        if not keywords:
            log.warning(
                "find_latest_episode: no keywords provided and first_match=False — returning None"
            )
            return None, None

        # First pass: respect duration filter
        for video in videos:
            title = video.get("title", "")
            if "#shorts" in title.lower():
                continue
            dur_text = video.get("lengthText", "")
            if dur_text:
                total = _parse_duration(dur_text)
                if total is not None and total < min_duration_seconds:
                    continue
            for kw in keywords:
                if kw.lower() in title.lower():
                    return video["videoId"], title

        # Second pass: skip duration filter (catch short episodes like 4-min MS podcasts)
        for video in videos:
            title = video.get("title", "")
            if "#shorts" in title.lower():
                continue
            for kw in keywords:
                if kw.lower() in title.lower():
                    log.warning(
                        "find_latest_episode: matched without duration filter (video=%s, title=%s)",
                        video["videoId"],
                        title[:60],
                    )
                    return video["videoId"], title

        return None, None

    def fetch_transcript(
        self,
        video_id: str,
        retries: int = 3,
        retry_delay: float = 3.0,
    ) -> list[TranscriptSegment]:
        """
        Fetch transcript segments for a YouTube video.
        Returns list of TranscriptSegment objects ordered by time.
        Raises TranscriptFetchError if transcript cannot be fetched.
        """
        last_error: Exception | None = None
        for attempt in range(retries):
            try:
                data = self._get(
                    "transcript",
                    {"video_url": video_id, "format": "json"},
                    DEFAULT_TIMEOUT_TRANSCRIPT,
                )
                raw = data.get("transcript", [])
                return _parse_segments(raw)
            except requests.Timeout as e:
                last_error = e
                if attempt < retries - 1:
                    log.warning(
                        "Transcript fetch timeout for %s (attempt %d/%d), retrying...",
                        video_id,
                        attempt + 1,
                        retries,
                    )
                    time.sleep(retry_delay)
        raise TranscriptFetchError(
            f"Transcript fetch timed out after {retries} attempts for {video_id}"
        ) from last_error

    def transcript_to_text(
        self,
        segments: list[TranscriptSegment],
        include_timestamps: bool = False,
        max_words: int | None = None,
    ) -> str:
        """Convert transcript segments to plain text (optionally with timestamps)."""
        lines = []
        word_count = 0
        for seg in segments:
            text = seg.text.strip()
            if not text:
                continue
            line = f"[{seg.timestamp_str}] {text}" if include_timestamps else text
            lines.append(line)
            word_count += len(text.split())
            if max_words and word_count >= max_words:
                break
        return "\n".join(lines)


def _parse_duration(dur_text: str) -> int | None:
    """Parse '1:23:45' or '23:45' to total seconds. Returns None on error."""
    try:
        parts = [int(p) for p in dur_text.split(":")]
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
    except (ValueError, AttributeError):
        pass
    return None


def _parse_segments(raw: list[dict]) -> list[TranscriptSegment]:
    """Convert raw API segment dicts to TranscriptSegment objects.

    TranscriptAPI.com returns offset in milliseconds.
    """
    segments = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        text = item.get("text", "").strip()
        if not text:
            continue
        offset_ms = item.get("offset", item.get("start", 0))
        offset_sec = float(offset_ms) / 1000.0 if isinstance(offset_ms, int | float) else 0.0
        segments.append(TranscriptSegment(text=text, offset_seconds=offset_sec))
    return segments
