"""
Caption fetcher (yt-dlp) — fetches auto-generated captions from YouTube.

For podcasts with a YouTube channel, uses yt-dlp CLI to fetch
auto-generated captions without downloading the full video.

Requires yt-dlp to be installed: pip install yt-dlp (or system package)
"""
from __future__ import annotations

import glob
import logging
import os
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)


class CaptionFetchError(Exception):
    """Raised when caption fetching fails (yt-dlp not installed or fetch error)."""


def fetch_captions_ytdlp(video_url: str, lang: str = "en") -> str:
    """
    Fetch auto-generated captions for a YouTube video using yt-dlp.

    Downloads VTT captions to a temp directory and returns the VTT text.
    Does not download the video.

    Args:
        video_url: Full YouTube video URL, e.g. https://www.youtube.com/watch?v=...
        lang: Caption language code (default: "en")

    Returns:
        VTT text as a string.

    Raises:
        CaptionFetchError: If yt-dlp is not installed or captions cannot be fetched.
    """
    # Check yt-dlp is available
    try:
        result = subprocess.run(
            ["yt-dlp", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            raise CaptionFetchError("yt-dlp returned non-zero on --version check")
    except FileNotFoundError:
        raise CaptionFetchError(
            "yt-dlp is not installed. Install with: pip install yt-dlp"
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        output_template = os.path.join(tmpdir, "captions")

        cmd = [
            "yt-dlp",
            "--write-auto-sub",
            "--skip-download",
            "--sub-lang", lang,
            "--sub-format", "vtt",
            "--output", output_template,
            "--no-playlist",
            "--quiet",
            "--js-runtimes", "node",
            video_url,
        ]

        log.info("Fetching captions for: %s (lang=%s)", video_url, lang)
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            raise CaptionFetchError(f"yt-dlp timed out fetching captions for {video_url}")

        if result.returncode != 0:
            log.error("yt-dlp stderr: %s", result.stderr)
            raise CaptionFetchError(
                f"yt-dlp failed (exit {result.returncode}) for {video_url}: {result.stderr[:200]}"
            )

        # Find the downloaded .vtt file
        vtt_files = glob.glob(os.path.join(tmpdir, "*.vtt"))
        if not vtt_files:
            raise CaptionFetchError(
                f"No VTT captions found for {video_url} (lang={lang}). "
                "Auto-captions may not be available for this video."
            )

        vtt_path = vtt_files[0]
        log.info("Caption file: %s", vtt_path)
        with open(vtt_path, encoding="utf-8") as f:
            return f.read()


def get_latest_video_url(channel_url: str) -> str:
    """
    Get the URL of the latest video from a YouTube channel using yt-dlp.

    Args:
        channel_url: YouTube channel URL, e.g. https://www.youtube.com/@channelname

    Returns:
        Full YouTube video URL of the most recent upload.

    Raises:
        CaptionFetchError: If yt-dlp is not installed or the channel cannot be accessed.
    """
    # Check yt-dlp is available
    try:
        subprocess.run(
            ["yt-dlp", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
    except FileNotFoundError:
        raise CaptionFetchError(
            "yt-dlp is not installed. Install with: pip install yt-dlp"
        )
    except subprocess.CalledProcessError:
        raise CaptionFetchError("yt-dlp returned non-zero on --version check")

    # Use yt-dlp to list the latest video URL without downloading
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--playlist-end", "1",
        "--print", "url",
        "--no-warnings",
        "--quiet",
        "--js-runtimes", "node",
        channel_url,
    ]

    log.info("Getting latest video URL from channel: %s", channel_url)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        raise CaptionFetchError(f"yt-dlp timed out fetching channel {channel_url}")

    if result.returncode != 0:
        log.error("yt-dlp stderr: %s", result.stderr)
        raise CaptionFetchError(
            f"yt-dlp failed (exit {result.returncode}) for channel {channel_url}: {result.stderr[:200]}"
        )

    url = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
    if not url:
        raise CaptionFetchError(f"No videos found for channel: {channel_url}")

    # Normalize to full URL if yt-dlp returned just a video ID
    if url.startswith("http"):
        return url
    return f"https://www.youtube.com/watch?v={url}"
