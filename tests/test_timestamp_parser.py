"""
Tests for poddistill/captions/timestamp_parser.py — all unit tests (pure logic).
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from poddistill.captions.timestamp_parser import (
    _parse_time_to_seconds,
    make_youtube_link,
    parse_timestamps,
)


# ---------------------------------------------------------------------------
# Unit tests — _parse_time_to_seconds
# ---------------------------------------------------------------------------

def test_parse_mm_ss():
    assert _parse_time_to_seconds("0:00") == 0
    assert _parse_time_to_seconds("2:30") == 150
    assert _parse_time_to_seconds("59:59") == 3599

def test_parse_hh_mm_ss():
    assert _parse_time_to_seconds("1:00:00") == 3600
    assert _parse_time_to_seconds("1:23:45") == 5025
    assert _parse_time_to_seconds("0:01:30") == 90

def test_parse_leading_zeros():
    assert _parse_time_to_seconds("00:00") == 0
    assert _parse_time_to_seconds("01:30") == 90

def test_parse_invalid():
    assert _parse_time_to_seconds("notatime") is None
    assert _parse_time_to_seconds("") is None
    assert _parse_time_to_seconds("1:2:3:4") is None  # too many parts


# ---------------------------------------------------------------------------
# Unit tests — parse_timestamps
# ---------------------------------------------------------------------------

def test_parse_empty_string():
    assert parse_timestamps("") == []

def test_parse_none_like():
    assert parse_timestamps(None) == []  # type: ignore

def test_parse_no_timestamps():
    assert parse_timestamps("This is just a description with no timestamps.") == []

def test_parse_basic_mm_ss():
    desc = "0:00 Introduction\n2:30 Main Topic\n5:00 Outro"
    result = parse_timestamps(desc)
    assert len(result) == 3
    assert result[0] == {"title": "Introduction", "startSeconds": 0}
    assert result[1] == {"title": "Main Topic", "startSeconds": 150}
    assert result[2] == {"title": "Outro", "startSeconds": 300}

def test_parse_hh_mm_ss_timestamps():
    desc = "0:00 Intro\n1:23:45 Deep Dive\n2:00:00 Wrap Up"
    result = parse_timestamps(desc)
    assert len(result) == 3
    assert result[1] == {"title": "Deep Dive", "startSeconds": 5025}
    assert result[2] == {"title": "Wrap Up", "startSeconds": 7200}

def test_parse_leading_whitespace():
    desc = "  0:00 Intro\n  2:30 Topic"
    result = parse_timestamps(desc)
    assert len(result) == 2
    assert result[0]["title"] == "Intro"
    assert result[1]["startSeconds"] == 150

def test_parse_mixed_content():
    desc = """Welcome to the podcast!

Timestamps:
0:00 Intro
5:30 Guest Background
15:00 Main Discussion
1:02:30 Q&A Session
1:30:00 Wrap Up

Subscribe for more content!"""
    result = parse_timestamps(desc)
    assert len(result) == 5
    assert result[0]["title"] == "Intro"
    assert result[3]["startSeconds"] == 3750  # 1:02:30 = 3750s
    assert result[4]["title"] == "Wrap Up"

def test_parse_preserves_order():
    desc = "0:00 First\n10:00 Second\n20:00 Third"
    result = parse_timestamps(desc)
    assert [r["startSeconds"] for r in result] == [0, 600, 1200]

def test_parse_title_stripped():
    desc = "0:00  Title With Extra Space   "
    result = parse_timestamps(desc)
    assert result[0]["title"] == "Title With Extra Space"

def test_parse_timestamp_not_at_line_start_ignored():
    # Timestamps buried in text (not at start of line) should be ignored
    desc = "Check out 2:30 for the good part"
    result = parse_timestamps(desc)
    assert result == []


# ---------------------------------------------------------------------------
# Unit tests — make_youtube_link
# ---------------------------------------------------------------------------

def test_make_youtube_link_basic():
    url = make_youtube_link("dQw4w9WgXcQ", 0)
    assert url == "https://youtube.com/watch?v=dQw4w9WgXcQ&t=0"

def test_make_youtube_link_with_offset():
    url = make_youtube_link("abc123", 150)
    assert url == "https://youtube.com/watch?v=abc123&t=150"

def test_make_youtube_link_large_offset():
    url = make_youtube_link("vid001", 3600)
    assert "t=3600" in url


# ---------------------------------------------------------------------------
# Run directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        test_parse_mm_ss,
        test_parse_hh_mm_ss,
        test_parse_leading_zeros,
        test_parse_invalid,
        test_parse_empty_string,
        test_parse_none_like,
        test_parse_no_timestamps,
        test_parse_basic_mm_ss,
        test_parse_hh_mm_ss_timestamps,
        test_parse_leading_whitespace,
        test_parse_mixed_content,
        test_parse_preserves_order,
        test_parse_title_stripped,
        test_parse_timestamp_not_at_line_start_ignored,
        test_make_youtube_link_basic,
        test_make_youtube_link_with_offset,
        test_make_youtube_link_large_offset,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception:
            print(f"  FAIL  {t.__name__}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
