"""
Tests for poddistill/fetchers/whisper_transcriber.py

Levels:
  - Unit        — MIME type guessing, pure logic
  - Integration — mocked HTTP calls
"""
from __future__ import annotations

import sys
import traceback
import tempfile
import os
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

sys.path.insert(0, str(Path(__file__).parent.parent))

from poddistill.fetchers.whisper_transcriber import (
    WhisperError,
    _guess_mime_type,
    transcribe_episode,
)


# ---------------------------------------------------------------------------
# Unit tests — pure logic
# ---------------------------------------------------------------------------

def test_guess_mime_mp3():
    assert _guess_mime_type("episode.mp3") == "audio/mpeg"

def test_guess_mime_m4a():
    assert _guess_mime_type("episode.m4a") == "audio/mp4"

def test_guess_mime_wav():
    assert _guess_mime_type("episode.wav") == "audio/wav"

def test_guess_mime_unknown():
    # Unknown extension falls back to audio/mpeg
    assert _guess_mime_type("episode.xyz") == "audio/mpeg"

def test_guess_mime_case_insensitive():
    assert _guess_mime_type("EPISODE.MP3") == "audio/mpeg"


# ---------------------------------------------------------------------------
# Integration tests — mocked HTTP
# ---------------------------------------------------------------------------

def test_transcribe_episode_success():
    """Happy path: download + transcription both succeed."""
    audio_content = b"fake audio bytes"
    transcript_text = "Hello, this is a podcast episode."

    with patch("poddistill.fetchers.whisper_transcriber.requests.get") as mock_get, \
         patch("poddistill.fetchers.whisper_transcriber.requests.post") as mock_post, \
         patch("poddistill.fetchers.whisper_transcriber.tempfile.NamedTemporaryFile") as mock_tmp, \
         patch("builtins.open", mock_open(read_data=audio_content)), \
         patch("poddistill.fetchers.whisper_transcriber.os.path.exists", return_value=True), \
         patch("poddistill.fetchers.whisper_transcriber.os.unlink"):

        # Setup temp file mock
        mock_tmp_obj = MagicMock()
        mock_tmp_obj.name = "/tmp/fake_audio.mp3"
        mock_tmp.return_value.__enter__ = lambda s: mock_tmp_obj
        mock_tmp.return_value.__exit__ = MagicMock(return_value=False)
        mock_tmp.return_value = mock_tmp_obj

        # Download response
        download_resp = MagicMock()
        download_resp.raise_for_status = MagicMock()
        download_resp.iter_content.return_value = [audio_content]
        mock_get.return_value = download_resp

        # Transcription response
        transcribe_resp = MagicMock()
        transcribe_resp.status_code = 200
        transcribe_resp.json.return_value = {"text": transcript_text}
        mock_post.return_value = transcribe_resp

        result = transcribe_episode(
            "https://example.com/episode.mp3",
            api_key="sk-fake",
        )
        assert result == transcript_text


def test_transcribe_episode_download_fails():
    """When download fails, raise WhisperError."""
    with patch("poddistill.fetchers.whisper_transcriber.requests.get") as mock_get, \
         patch("poddistill.fetchers.whisper_transcriber.tempfile.NamedTemporaryFile") as mock_tmp:

        mock_tmp_obj = MagicMock()
        mock_tmp_obj.name = "/tmp/fake_audio.mp3"
        mock_tmp.return_value = mock_tmp_obj

        mock_get.side_effect = Exception("Connection refused")

        try:
            transcribe_episode("https://example.com/episode.mp3", api_key="sk-fake")
            assert False, "Should raise WhisperError"
        except WhisperError as e:
            assert "download" in str(e).lower() or "failed" in str(e).lower()


def test_transcribe_episode_api_error():
    """When Whisper API returns error, raise WhisperError."""
    with patch("poddistill.fetchers.whisper_transcriber.requests.get") as mock_get, \
         patch("poddistill.fetchers.whisper_transcriber.requests.post") as mock_post, \
         patch("poddistill.fetchers.whisper_transcriber.tempfile.NamedTemporaryFile") as mock_tmp, \
         patch("builtins.open", mock_open(read_data=b"fake audio")), \
         patch("poddistill.fetchers.whisper_transcriber.os.path.exists", return_value=True), \
         patch("poddistill.fetchers.whisper_transcriber.os.unlink"):

        mock_tmp_obj = MagicMock()
        mock_tmp_obj.name = "/tmp/fake_audio.mp3"
        mock_tmp.return_value = mock_tmp_obj

        download_resp = MagicMock()
        download_resp.raise_for_status = MagicMock()
        download_resp.iter_content.return_value = [b"fake audio bytes"]
        mock_get.return_value = download_resp

        transcribe_resp = MagicMock()
        transcribe_resp.status_code = 401
        transcribe_resp.text = "Unauthorized"
        mock_post.return_value = transcribe_resp

        try:
            transcribe_episode("https://example.com/episode.mp3", api_key="sk-invalid")
            assert False, "Should raise WhisperError"
        except WhisperError as e:
            assert "401" in str(e) or "api" in str(e).lower()


def test_transcribe_episode_empty_transcription():
    """When API returns empty text, raise WhisperError."""
    with patch("poddistill.fetchers.whisper_transcriber.requests.get") as mock_get, \
         patch("poddistill.fetchers.whisper_transcriber.requests.post") as mock_post, \
         patch("poddistill.fetchers.whisper_transcriber.tempfile.NamedTemporaryFile") as mock_tmp, \
         patch("builtins.open", mock_open(read_data=b"fake audio")), \
         patch("poddistill.fetchers.whisper_transcriber.os.path.exists", return_value=True), \
         patch("poddistill.fetchers.whisper_transcriber.os.unlink"):

        mock_tmp_obj = MagicMock()
        mock_tmp_obj.name = "/tmp/fake_audio.mp3"
        mock_tmp.return_value = mock_tmp_obj

        download_resp = MagicMock()
        download_resp.raise_for_status = MagicMock()
        download_resp.iter_content.return_value = [b"fake audio bytes"]
        mock_get.return_value = download_resp

        transcribe_resp = MagicMock()
        transcribe_resp.status_code = 200
        transcribe_resp.json.return_value = {"text": ""}
        mock_post.return_value = transcribe_resp

        try:
            transcribe_episode("https://example.com/episode.mp3", api_key="sk-fake")
            assert False, "Should raise WhisperError"
        except WhisperError as e:
            assert "empty" in str(e).lower()


# ---------------------------------------------------------------------------
# Run directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        test_guess_mime_mp3,
        test_guess_mime_m4a,
        test_guess_mime_wav,
        test_guess_mime_unknown,
        test_guess_mime_case_insensitive,
        test_transcribe_episode_success,
        test_transcribe_episode_download_fails,
        test_transcribe_episode_api_error,
        test_transcribe_episode_empty_transcription,
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
