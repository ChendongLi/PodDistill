"""
Caption cleaner — strips VTT formatting to produce clean plain text.

WebVTT (Web Video Text Tracks) files contain timing information and
formatting tags that need to be removed before text processing.

Example VTT input:
    WEBVTT
    Kind: captions
    Language: en

    00:00:01.000 --> 00:00:03.000
    Hello, <c>welcome</c> to the podcast.

    00:00:03.000 --> 00:00:05.000
    Hello, welcome to the podcast.

Expected output:
    Hello, welcome to the podcast.
"""
from __future__ import annotations

import re


# Remove VTT inline tags: <c>, </c>, <b>, </b>, <i>, </i>, <u>, </u>
# and timestamp tags like <00:00:01.000>
_VTT_TAG_RE = re.compile(r"<[^>]+>")

# Remove timestamp cue lines: "00:00:01.000 --> 00:00:03.000" (with optional position info)
_TIMESTAMP_LINE_RE = re.compile(
    r"^\d{2}:\d{2}:\d{2}\.\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}\.\d{3}.*$",
    re.MULTILINE,
)

# Remove NOTE blocks (VTT comments)
_NOTE_RE = re.compile(r"^NOTE\b.*$", re.MULTILINE)

# Remove WEBVTT header and metadata lines (STYLE, REGION, Kind, Language, etc.)
_HEADER_RE = re.compile(r"^(WEBVTT|STYLE|REGION)\b.*$", re.MULTILINE)
_META_RE = re.compile(r"^(Kind|Language|X-TIMESTAMP-MAP).*$", re.MULTILINE)

# Remove cue identifiers (numeric or alphanumeric lines before timestamps)
_CUE_ID_RE = re.compile(r"^\w+\s*$", re.MULTILINE)


def clean_vtt(vtt_text: str) -> str:
    """
    Strip VTT formatting from caption text and return clean plain text.

    Processing steps:
    1. Remove WEBVTT header and metadata (Kind, Language, etc.)
    2. Remove timestamp cue lines (HH:MM:SS.mmm --> HH:MM:SS.mmm)
    3. Remove VTT inline tags (<c>, <b>, <00:00:01.000>, etc.)
    4. Remove NOTE blocks
    5. Deduplicate consecutive repeated lines (YouTube auto-captions repeat
       the current line as context for the next segment)
    6. Join remaining lines, stripping blank lines

    Args:
        vtt_text: Raw VTT caption text.

    Returns:
        Clean plain text with duplicate lines removed and content joined
        with spaces. Returns empty string if input is empty or None.
    """
    if not vtt_text:
        return ""

    text = vtt_text

    # Step 1: Remove WEBVTT header and VTT metadata
    text = _HEADER_RE.sub("", text)
    text = _META_RE.sub("", text)

    # Step 2: Remove timestamp cue lines
    text = _TIMESTAMP_LINE_RE.sub("", text)

    # Step 3: Remove VTT inline tags
    text = _VTT_TAG_RE.sub("", text)

    # Step 4: Remove NOTE blocks
    text = _NOTE_RE.sub("", text)

    # Step 5: Process lines — collect non-empty lines, deduplicate consecutive
    lines = []
    prev_line = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        # Skip empty lines and pure numeric/short cue IDs
        if not line:
            continue
        # Skip lines that look like cue sequence numbers (pure digits)
        if re.match(r"^\d+$", line):
            continue
        # Deduplicate consecutive identical lines
        if line == prev_line:
            continue
        lines.append(line)
        prev_line = line

    return " ".join(lines)
