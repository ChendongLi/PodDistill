"""
Formatter — adds timestamp deep-links to summary output.

Transforms a list of summarized chunks into a single Markdown document
where each chapter heading links directly to the corresponding timestamp
in the YouTube video.

Example output:
    ## [▶ 0:00](https://youtube.com/watch?v=VIDEO_ID&t=0) Introduction
    *One-line headline*
    - Bullet 1
    - Bullet 2

    ## [▶ 2:30](https://youtube.com/watch?v=VIDEO_ID&t=150) Main Topic
    ...
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def _seconds_to_display(seconds: int) -> str:
    """
    Convert seconds to human-readable time display.

    Examples:
        0 → "0:00"
        90 → "1:30"
        3661 → "1:01:01"
    """
    seconds = max(0, int(seconds))
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_summary_with_links(
    summarized_chunks: list[dict],
    video_id: str,
) -> str:
    """
    Format summarized chunks into a final Markdown document with timestamp
    deep-links for each chapter heading.

    Args:
        summarized_chunks: List of dicts, each with:
                            - title (str): Chapter title
                            - startSeconds (int): Chapter start time in seconds
                            - summary_md (str): Markdown summary from Claude
        video_id: YouTube video ID (e.g. "dQw4w9WgXcQ")

    Returns:
        Full Markdown document as a string. Each chapter has a heading like:
            ## [▶ 2:30](https://youtube.com/watch?v=VIDEO_ID&t=150) Chapter Title

        Special case: if startSeconds == 0 and title == "Full Episode",
        no timestamp link is added (used when there are no chapters).

    Notes:
        - Each chunk's summary_md is appended as-is after the heading.
        - Sections are separated by a blank line.
    """
    if not summarized_chunks:
        return ""

    sections = []

    for chunk in summarized_chunks:
        title = chunk.get("title", "")
        start_seconds = chunk.get("startSeconds", 0)
        summary_md = chunk.get("summary_md", "").strip()

        # Special case: no timestamp link for "Full Episode" at 0s
        is_full_episode = (start_seconds == 0 and title == "Full Episode")

        if is_full_episode:
            heading = f"## {title}"
        else:
            display_time = _seconds_to_display(start_seconds)
            yt_url = f"https://youtube.com/watch?v={video_id}&t={start_seconds}"
            heading = f"## [▶ {display_time}]({yt_url}) {title}"

        section = f"{heading}\n\n{summary_md}"
        sections.append(section)

    return "\n\n---\n\n".join(sections)
