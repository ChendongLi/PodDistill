"""
Whisper transcriber — fallback transcription for RSS-only podcasts.

For podcasts with no YouTube source (no auto-generated captions available),
this module downloads the audio from the RSS enclosure URL and transcribes
it using the OpenAI Whisper API.

This is the FALLBACK path. Prefer caption_fetcher.py (yt-dlp) when a
YouTube channel URL is available, as it is faster and free.

Usage:
    from poddistill.fetchers.whisper_transcriber import transcribe_episode
    text = transcribe_episode(audio_url="https://example.com/episode.mp3",
                              api_key="sk-...")
"""
from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

import requests

log = logging.getLogger(__name__)

WHISPER_API_URL = "https://api.openai.com/v1/audio/transcriptions"
WHISPER_MODEL = "whisper-1"
# Max file size OpenAI Whisper accepts (25 MB)
MAX_AUDIO_BYTES = 25 * 1024 * 1024


class WhisperError(Exception):
    """Raised when transcription fails."""


def _download_audio(audio_url: str, dest_path: str, timeout: int = 300) -> None:
    """
    Download audio from URL to dest_path.
    Streams to avoid loading entire file into memory.

    Raises:
        WhisperError: if download fails or file exceeds size limit.
    """
    log.info("Downloading audio: %s", audio_url)
    try:
        resp = requests.get(audio_url, stream=True, timeout=timeout)
        resp.raise_for_status()
    except Exception as e:
        raise WhisperError(f"Failed to download audio from {audio_url}: {e}") from e

    downloaded = 0
    with open(dest_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                if downloaded > MAX_AUDIO_BYTES:
                    raise WhisperError(
                        f"Audio file exceeds {MAX_AUDIO_BYTES // (1024*1024)} MB limit "
                        f"(downloaded {downloaded // (1024*1024)} MB so far). "
                        "Consider splitting the episode or using a different transcription method."
                    )

    log.info("Downloaded %.1f MB to %s", downloaded / (1024 * 1024), dest_path)


def _transcribe_file(file_path: str, api_key: str, model: str = WHISPER_MODEL) -> str:
    """
    Send audio file to OpenAI Whisper API and return transcribed text.

    Raises:
        WhisperError: if API call fails.
    """
    log.info("Transcribing %s with Whisper (%s)...", file_path, model)
    filename = os.path.basename(file_path)

    try:
        with open(file_path, "rb") as audio_file:
            resp = requests.post(
                WHISPER_API_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (filename, audio_file, _guess_mime_type(filename))},
                data={"model": model},
                timeout=600,  # Transcription can take a while
            )
    except Exception as e:
        raise WhisperError(f"Whisper API request failed: {e}") from e

    if resp.status_code != 200:
        raise WhisperError(
            f"Whisper API returned {resp.status_code}: {resp.text[:300]}"
        )

    data = resp.json()
    text = data.get("text", "")
    if not text:
        raise WhisperError("Whisper API returned empty transcription")

    log.info("Transcription complete: %d chars", len(text))
    return text


def _guess_mime_type(filename: str) -> str:
    """Guess MIME type from file extension for Whisper API multipart upload."""
    ext = Path(filename).suffix.lower()
    mime_map = {
        ".mp3": "audio/mpeg",
        ".mp4": "audio/mp4",
        ".m4a": "audio/mp4",
        ".wav": "audio/wav",
        ".ogg": "audio/ogg",
        ".flac": "audio/flac",
        ".webm": "audio/webm",
    }
    return mime_map.get(ext, "audio/mpeg")


def transcribe_episode(
    audio_url: str,
    api_key: str,
    model: str = WHISPER_MODEL,
    keep_audio: bool = False,
) -> str:
    """
    Download audio from RSS enclosure URL and transcribe via OpenAI Whisper API.

    This is the FALLBACK transcription path for RSS-only podcasts that don't
    have a YouTube channel with auto-generated captions.

    Args:
        audio_url: Direct URL to the podcast audio file (MP3, M4A, etc.)
                   Typically from the <enclosure> tag in an RSS feed.
        api_key:   OpenAI API key (sk-...).
        model:     Whisper model to use (default: "whisper-1").
        keep_audio: If True, don't delete the temp audio file after transcription.
                    Useful for debugging.

    Returns:
        Plain text transcription of the episode.

    Raises:
        WhisperError: If download or transcription fails.

    Note:
        Audio files are limited to 25 MB by the Whisper API. Long episodes
        may need to be split before transcription.
    """
    # Determine file extension from URL
    url_path = audio_url.split("?")[0]  # Strip query params
    ext = Path(url_path).suffix or ".mp3"
    if len(ext) > 5:  # Sanity check — unusually long ext
        ext = ".mp3"

    with tempfile.NamedTemporaryFile(suffix=ext, delete=not keep_audio) as tmp:
        tmp_path = tmp.name

    try:
        _download_audio(audio_url, tmp_path)
        text = _transcribe_file(tmp_path, api_key, model)
    finally:
        if not keep_audio and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    return text
