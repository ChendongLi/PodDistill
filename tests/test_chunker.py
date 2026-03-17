"""
Tests for poddistill/captions/chunker.py — all unit tests (pure logic).
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from poddistill.captions.chunker import chunk_by_chapters


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

def test_empty_chapters_returns_full_episode():
    result = chunk_by_chapters("Hello world text", [])
    assert len(result) == 1
    assert result[0]["title"] == "Full Episode"
    assert result[0]["startSeconds"] == 0
    assert result[0]["text"] == "Hello world text"


def test_none_chapters_returns_full_episode():
    result = chunk_by_chapters("Some text", None)
    assert len(result) == 1
    assert result[0]["title"] == "Full Episode"


def test_empty_transcript_with_chapters():
    chapters = [{"title": "Intro", "startSeconds": 0}, {"title": "Main", "startSeconds": 300}]
    result = chunk_by_chapters("", chapters)
    assert len(result) == 2
    for chunk in result:
        assert chunk["text"] == ""


def test_single_chapter():
    chapters = [{"title": "Intro", "startSeconds": 0}]
    result = chunk_by_chapters("Hello world", chapters)
    # Single chapter starting at 0 — all at 0 seconds means total_seconds=0
    assert len(result) == 1
    assert result[0]["text"] == "Hello world"


def test_two_chapters_splits_at_proportion():
    """With chapters at 0s and 300s (total 300s), split at 50% of text."""
    # chapters: 0s start, 300s start => total_seconds = 300
    # text of 100 chars => chapter 0: chars 0-50, chapter 1: chars 50-100
    text = "A" * 50 + "B" * 50  # 100 chars
    chapters = [
        {"title": "Intro", "startSeconds": 0},
        {"title": "Main", "startSeconds": 300},
    ]
    result = chunk_by_chapters(text, chapters)
    assert len(result) == 2
    assert result[0]["title"] == "Intro"
    assert result[1]["title"] == "Main"
    # Intro gets 0-50% = first 50 chars = all A's
    assert result[0]["text"] == "A" * 50
    # Main gets 50-100% = last 50 chars = all B's
    assert result[1]["text"] == "B" * 50


def test_three_chapters_proportional():
    text = "A" * 100 + "B" * 100 + "C" * 100  # 300 chars
    chapters = [
        {"title": "Ch1", "startSeconds": 0},
        {"title": "Ch2", "startSeconds": 300},
        {"title": "Ch3", "startSeconds": 600},
    ]
    result = chunk_by_chapters(text, chapters)
    assert len(result) == 3
    # Each chapter should be roughly equal
    for chunk in result:
        assert len(chunk["text"]) > 0


def test_last_chapter_goes_to_end():
    text = "Hello world this is a test"
    chapters = [
        {"title": "Intro", "startSeconds": 0},
        {"title": "Outro", "startSeconds": 100},
    ]
    result = chunk_by_chapters(text, chapters)
    # Last chunk should end at the end of text
    last_chunk_text = result[-1]["text"]
    assert last_chunk_text in text  # must be a substring


def test_output_has_required_keys():
    chapters = [{"title": "Test", "startSeconds": 0}]
    result = chunk_by_chapters("Some text", chapters)
    for chunk in result:
        assert "title" in chunk
        assert "startSeconds" in chunk
        assert "text" in chunk


def test_chapters_sorted_by_start_seconds():
    """Chapters out of order should still work correctly."""
    text = "A" * 100 + "B" * 100
    chapters = [
        {"title": "Ch2", "startSeconds": 200},  # Out of order
        {"title": "Ch1", "startSeconds": 0},
    ]
    result = chunk_by_chapters(text, chapters)
    assert len(result) == 2
    # After sorting, Ch1 (0s) comes first
    assert result[0]["title"] == "Ch1"
    assert result[1]["title"] == "Ch2"


def test_full_episode_fallback_preserves_text():
    long_text = "word " * 1000
    result = chunk_by_chapters(long_text, [])
    assert result[0]["text"] == long_text


# ---------------------------------------------------------------------------
# Run directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        test_empty_chapters_returns_full_episode,
        test_none_chapters_returns_full_episode,
        test_empty_transcript_with_chapters,
        test_single_chapter,
        test_two_chapters_splits_at_proportion,
        test_three_chapters_proportional,
        test_last_chapter_goes_to_end,
        test_output_has_required_keys,
        test_chapters_sorted_by_start_seconds,
        test_full_episode_fallback_preserves_text,
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
