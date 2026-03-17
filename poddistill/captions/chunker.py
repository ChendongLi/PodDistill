"""
Chapter-segmented transcript chunker.

Splits a transcript into chunks aligned with chapter timestamps.
Used to feed focused text segments to the Claude summarizer.

Splitting strategy:
    Since we only have the transcript text (not timing info per word),
    we estimate chapter boundaries using character position proportional
    to the total episode duration.

    Total duration is estimated as:
        last_chapter_start + average_chapter_duration

    This ensures the last chapter gets a fair share of the text.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def chunk_by_chapters(transcript_text: str, chapters: list[dict]) -> list[dict]:
    """
    Split transcript text into chunks aligned with chapter timestamps.

    Args:
        transcript_text: Full episode transcript as plain text.
        chapters: List of chapter dicts, each with:
                    - title (str): Chapter title
                    - startSeconds (int): Start time in seconds

    Returns:
        List of dicts, each with:
            - title (str): Chapter title
            - startSeconds (int): Chapter start time in seconds
            - text (str): Transcript slice for this chapter

        Fallback: if chapters is empty or None, returns a single chunk
        covering the full episode:
            [{"title": "Full Episode", "startSeconds": 0, "text": transcript_text}]

    Notes:
        - Splitting uses character position proportional to duration.
        - Assumes chapters are sorted by startSeconds (ascending).
        - Last chapter extends to end of transcript.
        - Total duration estimated as: last_start + avg_chapter_duration
    """
    if not chapters:
        return [{"title": "Full Episode", "startSeconds": 0, "text": transcript_text}]

    if not transcript_text:
        return [
            {"title": ch["title"], "startSeconds": ch["startSeconds"], "text": ""}
            for ch in chapters
        ]

    # Sort chapters by startSeconds
    sorted_chapters = sorted(chapters, key=lambda c: c["startSeconds"])

    last_start = sorted_chapters[-1]["startSeconds"]

    # Single chapter or all chapters starting at 0 — no splitting needed
    if last_start == 0 or len(sorted_chapters) == 1:
        return [{"title": sorted_chapters[0]["title"], "startSeconds": 0, "text": transcript_text}]

    # Estimate total duration: last chapter start + average chapter duration
    # average_chapter_duration = last_start / (N - 1)
    n = len(sorted_chapters)
    avg_chapter_duration = last_start / (n - 1)
    total_seconds = last_start + avg_chapter_duration

    total_chars = len(transcript_text)

    def char_position_for_time(seconds: int) -> int:
        """Estimate character position for a given timestamp."""
        proportion = seconds / total_seconds
        proportion = max(0.0, min(1.0, proportion))
        return int(proportion * total_chars)

    chunks = []
    for i, chapter in enumerate(sorted_chapters):
        start_char = char_position_for_time(chapter["startSeconds"])

        if i + 1 < len(sorted_chapters):
            end_char = char_position_for_time(sorted_chapters[i + 1]["startSeconds"])
        else:
            end_char = total_chars  # Last chapter gets the rest

        text_slice = transcript_text[start_char:end_char].strip()

        chunks.append({
            "title": chapter["title"],
            "startSeconds": chapter["startSeconds"],
            "text": text_slice,
        })

    return chunks
