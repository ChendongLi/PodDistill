"""
Timestamp parser — parses chapter timestamps from YouTube video descriptions.

YouTube creators often include chapter markers in video descriptions like:
    0:00 Introduction
    2:30 Topic 1
    1:23:45 Final thoughts

This module extracts those timestamps and converts them to seconds.
"""
from __future__ import annotations

import re
from typing import Optional

# Regex: match timestamp at start of line (with optional leading whitespace)
# Supports: 0:00, 00:00, 1:23:45, 01:23:45
_TIMESTAMP_RE = re.compile(
    r"^\s*"                           # optional leading whitespace
    r"(\d{1,2}:\d{2}(?::\d{2})?)"    # group 1: timestamp (MM:SS or HH:MM:SS)
    r"\s+"                            # one or more spaces
    r"(.+?)\s*$",                     # group 2: title (rest of line, stripped)
    re.MULTILINE,
)


def _parse_time_to_seconds(time_str: str) -> Optional[int]:
    """
    Convert a timestamp string to seconds.

    Args:
        time_str: "0:00", "1:23", "1:23:45", "01:23:45"

    Returns:
        Total seconds as int, or None if parse fails.
    """
    parts = time_str.strip().split(":")
    try:
        if len(parts) == 2:
            minutes, seconds = int(parts[0]), int(parts[1])
            return minutes * 60 + seconds
        elif len(parts) == 3:
            hours, minutes, seconds = int(parts[0]), int(parts[1]), int(parts[2])
            return hours * 3600 + minutes * 60 + seconds
        return None
    except (ValueError, IndexError):
        return None


def parse_timestamps(description_text: str) -> list[dict]:
    """
    Parse chapter timestamps from a YouTube video description.

    Looks for lines starting with a timestamp pattern (e.g. "0:00 Intro",
    "1:23:45 Final thoughts"). Leading whitespace is allowed.

    Args:
        description_text: Full video description text.

    Returns:
        List of dicts with keys:
            - title (str): Chapter title
            - startSeconds (int): Start time in seconds

        Returns [] if no timestamps found or input is empty/malformed.

    Examples:
        >>> parse_timestamps("0:00 Intro\\n2:30 Main Topic\\n1:00:00 Wrap Up")
        [
            {'title': 'Intro', 'startSeconds': 0},
            {'title': 'Main Topic', 'startSeconds': 150},
            {'title': 'Wrap Up', 'startSeconds': 3600},
        ]
    """
    if not description_text or not isinstance(description_text, str):
        return []

    chapters = []
    for match in _TIMESTAMP_RE.finditer(description_text):
        time_str = match.group(1)
        title = match.group(2).strip()

        seconds = _parse_time_to_seconds(time_str)
        if seconds is None:
            continue  # Skip malformed timestamps

        chapters.append({
            "title": title,
            "startSeconds": seconds,
        })

    return chapters


def make_youtube_link(video_id: str, start_seconds: int) -> str:
    """
    Generate a YouTube deep-link URL that starts playback at a given time.

    Args:
        video_id: YouTube video ID (e.g. "dQw4w9WgXcQ")
        start_seconds: Time offset in seconds

    Returns:
        Full YouTube URL with ?t= parameter, e.g.
        "https://youtube.com/watch?v=dQw4w9WgXcQ&t=150"

    Examples:
        >>> make_youtube_link("dQw4w9WgXcQ", 150)
        'https://youtube.com/watch?v=dQw4w9WgXcQ&t=150'
    """
    return f"https://youtube.com/watch?v={video_id}&t={start_seconds}"
