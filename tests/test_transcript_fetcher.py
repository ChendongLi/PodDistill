"""Tests for TranscriptFetcher (TranscriptAPI.com integration)."""
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from poddistill.fetchers.transcript_fetcher import (
    TranscriptFetcher,
    TranscriptFetchError,
    TranscriptSegment,
    _parse_duration,
    _parse_segments,
)


# ── _parse_duration ───────────────────────────────────────────────────────────

def test_parse_duration_mm_ss():
    assert _parse_duration("23:45") == 23 * 60 + 45

def test_parse_duration_hh_mm_ss():
    assert _parse_duration("1:30:00") == 5400

def test_parse_duration_zero():
    assert _parse_duration("0:00") == 0

def test_parse_duration_invalid_returns_none():
    assert _parse_duration("live") is None
    assert _parse_duration("") is None


# ── _parse_segments ───────────────────────────────────────────────────────────

def test_parse_segments_basic():
    raw = [{"text": "Hello world", "offset": 0}, {"text": "Second", "offset": 5000}]
    segs = _parse_segments(raw)
    assert len(segs) == 2
    assert segs[0].text == "Hello world"
    assert segs[0].offset_seconds == 0.0
    assert segs[1].offset_seconds == 5.0  # 5000ms -> 5.0s

def test_parse_segments_skips_empty():
    raw = [{"text": "", "offset": 0}, {"text": "  ", "offset": 1000}, {"text": "ok", "offset": 2000}]
    segs = _parse_segments(raw)
    assert len(segs) == 1
    assert segs[0].text == "ok"

def test_parse_segments_skips_non_dict():
    raw = [{"text": "good", "offset": 0}, "bad", None, 42]
    segs = _parse_segments(raw)
    assert len(segs) == 1

def test_parse_segments_uses_start_fallback():
    # TranscriptAPI returns all offsets in ms; 10ms = 0.01s
    raw = [{"text": "hello", "start": 10}]
    segs = _parse_segments(raw)
    assert segs[0].offset_seconds == 0.01

def test_parse_segments_large_offset_treated_as_ms():
    raw = [{"text": "hi", "offset": 60000}]  # 60000 ms = 60 s
    segs = _parse_segments(raw)
    assert segs[0].offset_seconds == 60.0


# ── TranscriptSegment ─────────────────────────────────────────────────────────

def test_segment_timestamp_str():
    seg = TranscriptSegment("hello", 90.0)
    assert seg.timestamp_str == "1:30"

def test_segment_repr():
    seg = TranscriptSegment("hello world", 65.0)
    assert "1:05" in repr(seg)
    assert "hello" in repr(seg)


# ── TranscriptFetcher init ────────────────────────────────────────────────────

def test_init_requires_api_key():
    with pytest.raises(ValueError):
        TranscriptFetcher("")

def test_init_sets_auth_header():
    f = TranscriptFetcher("sk_test123")
    assert f.session.headers["Authorization"] == "Bearer sk_test123"


# ── get_channel_videos ────────────────────────────────────────────────────────

def _make_fetcher():
    return TranscriptFetcher("sk_test")

def test_get_channel_videos_returns_results():
    fetcher = _make_fetcher()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"results": [{"videoId": "abc", "title": "Ep 1"}]}
    mock_resp.raise_for_status.return_value = None
    with patch.object(fetcher.session, "get", return_value=mock_resp) as mock_get:
        videos = fetcher.get_channel_videos("UCtest")
        assert len(videos) == 1
        assert videos[0]["videoId"] == "abc"
        mock_get.assert_called_once()

def test_get_channel_videos_empty():
    fetcher = _make_fetcher()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {}
    mock_resp.raise_for_status.return_value = None
    with patch.object(fetcher.session, "get", return_value=mock_resp):
        assert fetcher.get_channel_videos("UCtest") == []


# ── find_latest_episode ───────────────────────────────────────────────────────

SAMPLE_VIDEOS = [
    {"videoId": "v1", "title": "#Shorts quick clip", "lengthText": "0:30"},
    {"videoId": "v2", "title": "The Close: Markets wrap", "lengthText": "1:25:00"},
    {"videoId": "v3", "title": "Stock Movers Today", "lengthText": "0:45"},
    {"videoId": "v4", "title": "Bloomberg Daybreak AM", "lengthText": "45:00"},
]

def test_find_latest_episode_matches_keyword():
    fetcher = _make_fetcher()
    with patch.object(fetcher, "get_channel_videos", return_value=SAMPLE_VIDEOS):
        vid, title = fetcher.find_latest_episode("UCtest", ["the close"])
        assert vid == "v2"
        assert "Close" in title

def test_find_latest_episode_skips_shorts():
    fetcher = _make_fetcher()
    with patch.object(fetcher, "get_channel_videos", return_value=SAMPLE_VIDEOS):
        vid, title = fetcher.find_latest_episode("UCtest", ["quick clip"])
        # The shorts video matches keyword but should be skipped; no fallback without duration filter either
        # because it is a #short
        assert vid is None

def test_find_latest_episode_skips_short_duration():
    fetcher = _make_fetcher()
    with patch.object(fetcher, "get_channel_videos", return_value=SAMPLE_VIDEOS):
        # "stock movers" matches v3 (0:45 = 45s < 120s), should skip in main pass
        # then retry without duration filter
        vid, title = fetcher.find_latest_episode("UCtest", ["stock movers"])
        assert vid == "v3"  # found in fallback pass

def test_find_latest_episode_no_match():
    fetcher = _make_fetcher()
    with patch.object(fetcher, "get_channel_videos", return_value=SAMPLE_VIDEOS):
        vid, title = fetcher.find_latest_episode("UCtest", ["mad money"])
        assert vid is None
        assert title is None

def test_find_latest_episode_case_insensitive():
    fetcher = _make_fetcher()
    with patch.object(fetcher, "get_channel_videos", return_value=SAMPLE_VIDEOS):
        vid, _ = fetcher.find_latest_episode("UCtest", ["DAYBREAK"])
        assert vid == "v4"


# ── fetch_transcript ──────────────────────────────────────────────────────────

def test_fetch_transcript_success():
    fetcher = _make_fetcher()
    raw_resp = {"transcript": [{"text": "Hello", "offset": 0}, {"text": "World", "offset": 3000}]}
    mock_resp = MagicMock()
    mock_resp.json.return_value = raw_resp
    mock_resp.raise_for_status.return_value = None
    with patch.object(fetcher.session, "get", return_value=mock_resp):
        segs = fetcher.fetch_transcript("abc123")
        assert len(segs) == 2
        assert segs[0].text == "Hello"
        assert segs[1].offset_seconds == 3.0  # 3000ms / 1000 = 3.0s  # 3000ms -> 3.0s

def test_fetch_transcript_http_error():
    import requests as _req
    fetcher = _make_fetcher()
    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.text = "Forbidden"
    http_err = _req.HTTPError(response=mock_resp)
    mock_resp.raise_for_status.side_effect = http_err
    with patch.object(fetcher.session, "get", return_value=mock_resp):
        with pytest.raises(TranscriptFetchError, match="403"):
            fetcher.fetch_transcript("abc123")

def test_fetch_transcript_timeout_retries():
    import requests as _req
    fetcher = _make_fetcher()
    with patch.object(fetcher.session, "get", side_effect=_req.Timeout()), \
         patch("time.sleep"):
        with pytest.raises(TranscriptFetchError, match="timed out"):
            fetcher.fetch_transcript("abc123", retries=2, retry_delay=0)


# ── transcript_to_text ────────────────────────────────────────────────────────

SAMPLE_SEGS = [
    TranscriptSegment("Hello world", 0.0),
    TranscriptSegment("Good morning", 30.0),
    TranscriptSegment("Markets open", 60.0),
]

def test_transcript_to_text_plain():
    fetcher = _make_fetcher()
    text = fetcher.transcript_to_text(SAMPLE_SEGS)
    assert "Hello world" in text
    assert "[" not in text  # no timestamps

def test_transcript_to_text_with_timestamps():
    fetcher = _make_fetcher()
    text = fetcher.transcript_to_text(SAMPLE_SEGS, include_timestamps=True)
    assert "[0:00]" in text
    assert "[0:30]" in text
    assert "[1:00]" in text

def test_transcript_to_text_max_words():
    fetcher = _make_fetcher()
    text = fetcher.transcript_to_text(SAMPLE_SEGS, max_words=2)
    # "Hello world" = 2 words, should stop after first segment
    assert "Good morning" not in text

def test_transcript_to_text_empty():
    fetcher = _make_fetcher()
    assert fetcher.transcript_to_text([]) == ""
