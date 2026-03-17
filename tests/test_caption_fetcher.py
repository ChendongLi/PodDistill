"""
Tests for poddistill/fetchers/caption_fetcher.py

Levels:
  - Unit        — pure logic (error handling paths)
  - Integration — mocked subprocess calls
"""
from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, str(Path(__file__).parent.parent))

from poddistill.fetchers.caption_fetcher import (
    CaptionFetchError,
    fetch_captions_ytdlp,
    get_latest_video_url,
)


# ---------------------------------------------------------------------------
# Integration tests — mocked subprocess
# ---------------------------------------------------------------------------

def test_fetch_captions_ytdlp_not_installed():
    """When yt-dlp is not installed, raise CaptionFetchError."""
    with patch("poddistill.fetchers.caption_fetcher.subprocess.run") as mock_run:
        mock_run.side_effect = FileNotFoundError("yt-dlp not found")
        try:
            fetch_captions_ytdlp("https://youtube.com/watch?v=test")
            assert False, "Should have raised CaptionFetchError"
        except CaptionFetchError as e:
            assert "not installed" in str(e).lower()


def test_fetch_captions_ytdlp_success():
    """Happy path — yt-dlp runs, VTT file created."""
    vtt_content = "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nHello world\n"

    with patch("poddistill.fetchers.caption_fetcher.subprocess.run") as mock_run, \
         patch("poddistill.fetchers.caption_fetcher.glob.glob") as mock_glob, \
         tempfile.TemporaryDirectory() as tmpdir:

        # First call: yt-dlp --version
        version_result = MagicMock()
        version_result.returncode = 0

        # Second call: actual caption fetch
        fetch_result = MagicMock()
        fetch_result.returncode = 0
        fetch_result.stderr = ""

        mock_run.side_effect = [version_result, fetch_result]

        # Create a real VTT file so the open() call works
        vtt_path = os.path.join(tmpdir, "captions.en.vtt")
        with open(vtt_path, "w") as f:
            f.write(vtt_content)
        mock_glob.return_value = [vtt_path]

        # Patch tempfile.TemporaryDirectory to use our tmpdir
        with patch("poddistill.fetchers.caption_fetcher.tempfile.TemporaryDirectory") as mock_td:
            mock_td.return_value.__enter__ = lambda s: tmpdir
            mock_td.return_value.__exit__ = MagicMock(return_value=False)

            result = fetch_captions_ytdlp("https://youtube.com/watch?v=abc123")
            assert result == vtt_content


def test_fetch_captions_ytdlp_no_vtt_file():
    """When yt-dlp runs but produces no VTT file, raise CaptionFetchError."""
    with patch("poddistill.fetchers.caption_fetcher.subprocess.run") as mock_run, \
         patch("poddistill.fetchers.caption_fetcher.glob.glob") as mock_glob, \
         patch("poddistill.fetchers.caption_fetcher.tempfile.TemporaryDirectory") as mock_td, \
         tempfile.TemporaryDirectory() as tmpdir:

        version_result = MagicMock(); version_result.returncode = 0
        fetch_result = MagicMock(); fetch_result.returncode = 0; fetch_result.stderr = ""
        mock_run.side_effect = [version_result, fetch_result]
        mock_glob.return_value = []  # No VTT files
        mock_td.return_value.__enter__ = lambda s: tmpdir
        mock_td.return_value.__exit__ = MagicMock(return_value=False)

        try:
            fetch_captions_ytdlp("https://youtube.com/watch?v=no_captions")
            assert False, "Should raise CaptionFetchError"
        except CaptionFetchError as e:
            assert "no vtt" in str(e).lower() or "captions" in str(e).lower()


def test_fetch_captions_ytdlp_yt_dlp_fails():
    """When yt-dlp exits non-zero, raise CaptionFetchError."""
    with patch("poddistill.fetchers.caption_fetcher.subprocess.run") as mock_run:
        version_result = MagicMock(); version_result.returncode = 0
        fetch_result = MagicMock(); fetch_result.returncode = 1; fetch_result.stderr = "ERROR: Video unavailable"
        mock_run.side_effect = [version_result, fetch_result]

        with patch("poddistill.fetchers.caption_fetcher.tempfile.TemporaryDirectory") as mock_td:
            mock_td.return_value.__enter__ = lambda s: "/tmp"
            mock_td.return_value.__exit__ = MagicMock(return_value=False)

            try:
                fetch_captions_ytdlp("https://youtube.com/watch?v=unavailable")
                assert False, "Should raise CaptionFetchError"
            except CaptionFetchError as e:
                assert "failed" in str(e).lower() or "exit" in str(e).lower()


def test_get_latest_video_url_success():
    """Happy path — returns full URL from yt-dlp output."""
    with patch("poddistill.fetchers.caption_fetcher.subprocess.run") as mock_run:
        version_result = MagicMock()
        version_result.returncode = 0

        url_result = MagicMock()
        url_result.returncode = 0
        url_result.stdout = "https://www.youtube.com/watch?v=dQw4w9WgXcQ\n"
        url_result.stderr = ""

        mock_run.side_effect = [version_result, url_result]

        url = get_latest_video_url("https://www.youtube.com/@SomeChannel")
        assert url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_get_latest_video_url_normalizes_id():
    """If yt-dlp returns just a video ID, it should be normalized to full URL."""
    with patch("poddistill.fetchers.caption_fetcher.subprocess.run") as mock_run:
        version_result = MagicMock(); version_result.returncode = 0
        url_result = MagicMock(); url_result.returncode = 0
        url_result.stdout = "dQw4w9WgXcQ\n"; url_result.stderr = ""
        mock_run.side_effect = [version_result, url_result]

        url = get_latest_video_url("https://www.youtube.com/@SomeChannel")
        assert "youtube.com" in url
        assert "dQw4w9WgXcQ" in url


def test_get_latest_video_url_not_installed():
    """When yt-dlp is not installed, raise CaptionFetchError."""
    with patch("poddistill.fetchers.caption_fetcher.subprocess.run") as mock_run:
        mock_run.side_effect = FileNotFoundError()
        try:
            get_latest_video_url("https://www.youtube.com/@channel")
            assert False, "Should raise CaptionFetchError"
        except CaptionFetchError as e:
            assert "not installed" in str(e).lower()


def test_get_latest_video_url_empty_output():
    """When yt-dlp returns empty output, raise CaptionFetchError."""
    with patch("poddistill.fetchers.caption_fetcher.subprocess.run") as mock_run:
        version_result = MagicMock(); version_result.returncode = 0
        url_result = MagicMock(); url_result.returncode = 0
        url_result.stdout = ""; url_result.stderr = ""
        mock_run.side_effect = [version_result, url_result]

        try:
            get_latest_video_url("https://www.youtube.com/@empty")
            assert False, "Should raise CaptionFetchError"
        except CaptionFetchError as e:
            assert "no videos" in str(e).lower() or "not found" in str(e).lower()


# ---------------------------------------------------------------------------
# Run directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        test_fetch_captions_ytdlp_not_installed,
        test_fetch_captions_ytdlp_success,
        test_fetch_captions_ytdlp_no_vtt_file,
        test_fetch_captions_ytdlp_yt_dlp_fails,
        test_get_latest_video_url_success,
        test_get_latest_video_url_normalizes_id,
        test_get_latest_video_url_not_installed,
        test_get_latest_video_url_empty_output,
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
