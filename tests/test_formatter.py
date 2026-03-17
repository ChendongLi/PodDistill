"""
Tests for poddistill/summarizer/formatter.py — all unit tests (pure logic).
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from poddistill.summarizer.formatter import (
    _seconds_to_display,
    format_summary_with_links,
)


# ---------------------------------------------------------------------------
# Unit tests — _seconds_to_display
# ---------------------------------------------------------------------------

def test_seconds_zero():
    assert _seconds_to_display(0) == "0:00"

def test_seconds_sub_minute():
    assert _seconds_to_display(45) == "0:45"

def test_seconds_one_minute():
    assert _seconds_to_display(60) == "1:00"

def test_seconds_ninety():
    assert _seconds_to_display(90) == "1:30"

def test_seconds_one_hour():
    assert _seconds_to_display(3600) == "1:00:00"

def test_seconds_mixed():
    assert _seconds_to_display(3661) == "1:01:01"

def test_seconds_negative_clamped():
    assert _seconds_to_display(-10) == "0:00"


# ---------------------------------------------------------------------------
# Unit tests — format_summary_with_links
# ---------------------------------------------------------------------------

def test_empty_chunks():
    assert format_summary_with_links([], "vid123") == ""


def test_single_chunk_with_timestamp():
    chunks = [{"title": "Intro", "startSeconds": 0, "summary_md": "## Intro\n\n- Point 1"}]
    result = format_summary_with_links(chunks, "abc123")
    assert "▶" in result
    assert "abc123" in result
    assert "t=0" in result
    assert "Intro" in result
    assert "Point 1" in result


def test_timestamp_link_format():
    chunks = [{"title": "Main Topic", "startSeconds": 150, "summary_md": "Summary"}]
    result = format_summary_with_links(chunks, "dQw4w9WgXcQ")
    # Link should be: [▶ 2:30](https://youtube.com/watch?v=dQw4w9WgXcQ&t=150)
    assert "[▶ 2:30]" in result
    assert "https://youtube.com/watch?v=dQw4w9WgXcQ&t=150" in result


def test_full_episode_no_timestamp_link():
    chunks = [{"title": "Full Episode", "startSeconds": 0, "summary_md": "Summary text"}]
    result = format_summary_with_links(chunks, "vid123")
    # "Full Episode" at 0s should NOT have a timestamp link
    assert "▶" not in result
    assert "youtube.com" not in result
    assert "## Full Episode" in result
    assert "Summary text" in result


def test_multiple_chunks_separated():
    chunks = [
        {"title": "Intro", "startSeconds": 0, "summary_md": "Intro summary"},
        {"title": "Main", "startSeconds": 300, "summary_md": "Main summary"},
    ]
    result = format_summary_with_links(chunks, "vid123")
    assert "Intro summary" in result
    assert "Main summary" in result
    assert "---" in result  # sections separated


def test_multiple_chunks_order_preserved():
    chunks = [
        {"title": "Ch1", "startSeconds": 0, "summary_md": "First"},
        {"title": "Ch2", "startSeconds": 60, "summary_md": "Second"},
        {"title": "Ch3", "startSeconds": 120, "summary_md": "Third"},
    ]
    result = format_summary_with_links(chunks, "vid123")
    first_pos = result.index("First")
    second_pos = result.index("Second")
    third_pos = result.index("Third")
    assert first_pos < second_pos < third_pos


def test_heading_level_is_h2():
    chunks = [{"title": "Chapter", "startSeconds": 30, "summary_md": "Content"}]
    result = format_summary_with_links(chunks, "vid123")
    assert result.startswith("## ")


def test_summary_md_included_as_is():
    markdown = "# Headline\n\n- Bullet 1\n- Bullet 2\n\n> Notable quote"
    chunks = [{"title": "Test", "startSeconds": 10, "summary_md": markdown}]
    result = format_summary_with_links(chunks, "vid123")
    assert "Bullet 1" in result
    assert "Notable quote" in result


def test_one_hour_display():
    chunks = [{"title": "Late Chapter", "startSeconds": 3600, "summary_md": "Text"}]
    result = format_summary_with_links(chunks, "vid123")
    assert "▶ 1:00:00" in result


# ---------------------------------------------------------------------------
# Run directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        test_seconds_zero,
        test_seconds_sub_minute,
        test_seconds_one_minute,
        test_seconds_ninety,
        test_seconds_one_hour,
        test_seconds_mixed,
        test_seconds_negative_clamped,
        test_empty_chunks,
        test_single_chunk_with_timestamp,
        test_timestamp_link_format,
        test_full_episode_no_timestamp_link,
        test_multiple_chunks_separated,
        test_multiple_chunks_order_preserved,
        test_heading_level_is_h2,
        test_summary_md_included_as_is,
        test_one_hour_display,
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
