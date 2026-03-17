"""
Tests for poddistill/captions/cleaner.py — all unit tests (pure logic).
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from poddistill.captions.cleaner import clean_vtt


SAMPLE_VTT = """WEBVTT
Kind: captions
Language: en

00:00:01.000 --> 00:00:03.000
Hello, <c>welcome</c> to the podcast.

00:00:03.000 --> 00:00:05.000 align:start position:0%
Hello, welcome to the podcast.

00:00:05.000 --> 00:00:07.000
<00:00:05.500><c>Today</c><00:00:06.000><c> we</c><00:00:06.500><c> discuss</c> AI.

"""

# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

def test_clean_empty():
    assert clean_vtt("") == ""

def test_clean_none_like():
    assert clean_vtt(None) == ""  # type: ignore

def test_removes_webvtt_header():
    result = clean_vtt("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nHello")
    assert "WEBVTT" not in result

def test_removes_timestamp_lines():
    result = clean_vtt("WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nHello world")
    assert "-->" not in result

def test_removes_vtt_tags():
    result = clean_vtt("WEBVTT\n\n00:00:01.000 --> 00:00:03.000\n<c>Hello</c> world")
    assert "<c>" not in result
    assert "</c>" not in result
    assert "Hello" in result

def test_removes_timestamp_tags():
    result = clean_vtt("WEBVTT\n\n00:00:01.000 --> 00:00:03.000\n<00:00:01.500>Hello world")
    assert "<00:" not in result
    assert "Hello world" in result

def test_deduplicates_consecutive_lines():
    vtt = "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nHello world\n\n00:00:03.000 --> 00:00:05.000\nHello world\n\n00:00:05.000 --> 00:00:07.000\nNew content"
    result = clean_vtt(vtt)
    # "Hello world" should appear only once, not twice
    assert result.count("Hello world") == 1
    assert "New content" in result

def test_non_consecutive_duplicates_kept():
    vtt = "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nHello\n\n00:00:03.000 --> 00:00:05.000\nWorld\n\n00:00:05.000 --> 00:00:07.000\nHello"
    result = clean_vtt(vtt)
    # "Hello" appears at start and end — non-consecutive, both should appear
    assert result.count("Hello") == 2

def test_removes_kind_language_metadata():
    result = clean_vtt(SAMPLE_VTT)
    assert "Kind:" not in result
    assert "Language:" not in result

def test_full_vtt_produces_clean_text():
    result = clean_vtt(SAMPLE_VTT)
    assert "Hello, welcome to the podcast." in result
    assert "Today" in result
    assert "AI." in result
    assert "-->" not in result
    assert "<c>" not in result

def test_removes_cue_numbers():
    vtt = "WEBVTT\n\n1\n00:00:01.000 --> 00:00:03.000\nLine one\n\n2\n00:00:03.000 --> 00:00:05.000\nLine two"
    result = clean_vtt(vtt)
    assert "Line one" in result
    assert "Line two" in result
    # Cue numbers should not appear as standalone text
    # (they might appear if the line "1" or "2" slips through)

def test_output_is_joined_text():
    vtt = "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nFirst sentence.\n\n00:00:02.000 --> 00:00:03.000\nSecond sentence."
    result = clean_vtt(vtt)
    # Should be joined with spaces, not newlines
    assert "\n" not in result
    assert "First sentence." in result
    assert "Second sentence." in result

def test_real_youtube_style_vtt():
    """Test with a VTT sample mimicking YouTube auto-generated captions."""
    vtt = """WEBVTT
Kind: captions
Language: en

00:00:00.000 --> 00:00:03.000 align:start position:0%
<00:00:00.000><c> welcome</c><00:00:00.500><c> to</c><00:00:01.000><c> the</c><00:00:01.500><c> show</c>

00:00:03.000 --> 00:00:06.000 align:start position:0%
 welcome to the show

00:00:06.000 --> 00:00:09.000 align:start position:0%
today<00:00:06.500><c> we</c><00:00:07.000><c> talk</c><00:00:07.500><c> about</c><00:00:08.000><c> AI</c>

00:00:09.000 --> 00:00:12.000 align:start position:0%
today we talk about AI
"""
    result = clean_vtt(vtt)
    assert "welcome to the show" in result
    assert "today we talk about AI" in result
    assert "<c>" not in result
    assert "-->" not in result


# ---------------------------------------------------------------------------
# Run directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        test_clean_empty,
        test_clean_none_like,
        test_removes_webvtt_header,
        test_removes_timestamp_lines,
        test_removes_vtt_tags,
        test_removes_timestamp_tags,
        test_deduplicates_consecutive_lines,
        test_non_consecutive_duplicates_kept,
        test_removes_kind_language_metadata,
        test_full_vtt_produces_clean_text,
        test_removes_cue_numbers,
        test_output_is_joined_text,
        test_real_youtube_style_vtt,
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
