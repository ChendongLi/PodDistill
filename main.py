#!/usr/bin/env python3
"""
PodDistill — Daily podcast summarizer with timestamp deep-links.

Pipeline:
    1. Load podcast registry (podcasts.yaml → registry.json)
    2. Check for new episodes (state.json)
    3. Fetch captions via yt-dlp OR transcribe via Whisper (fallback)
    4. Parse chapter timestamps from YouTube description
    5. Clean VTT captions to plain text
    6. Chunk transcript by chapters
    7. Summarize each chunk with Claude
    8. Format summary with YouTube timestamp deep-links
    9. Upload to GCS (if configured)
    10. Send email digest via AgentMail (if configured)
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


def _get_env(key: str, required: bool = False) -> str | None:
    val = os.environ.get(key)
    if required and not val:
        raise RuntimeError(f"Required environment variable not set: {key}")
    return val


def process_podcast(
    podcast_source,
    state: dict,
    anthropic_api_key: str,
    openai_api_key: str | None,
    gcs_bucket: str | None,
    agentmail_api_key: str | None,
    digest_recipient: str | None,
) -> dict | None:
    """
    Process a single podcast: fetch → clean → summarize → store.

    Returns episode dict for digest or None if skipped/errored.
    """
    from poddistill.fetchers.caption_fetcher import (
        CaptionFetchError,
        fetch_captions_ytdlp,
        get_latest_video_url,
    )
    from poddistill.fetchers.update_checker import is_new_episode, mark_processed
    from poddistill.captions.cleaner import clean_vtt
    from poddistill.captions.timestamp_parser import parse_timestamps, make_youtube_link
    from poddistill.captions.chunker import chunk_by_chapters
    from poddistill.summarizer.claude_summarizer import summarize_chunks, SummarizerError
    from poddistill.summarizer.formatter import format_summary_with_links

    podcast_name = podcast_source.name
    log.info("Processing podcast: %s", podcast_name)

    # Step 3a: Try YouTube caption path
    video_id = None
    raw_vtt = None

    if podcast_source.youtube_channel_url:
        try:
            video_url = get_latest_video_url(podcast_source.youtube_channel_url)
            # Extract video ID from URL
            if "v=" in video_url:
                video_id = video_url.split("v=")[-1].split("&")[0]
            elif "youtu.be/" in video_url:
                video_id = video_url.split("youtu.be/")[-1].split("?")[0]
            else:
                video_id = video_url  # fallback

            log.info("Latest video: %s (id=%s)", video_url, video_id)

            # Check if already processed
            if not is_new_episode(podcast_name, video_id, state):
                log.info("No new episode for %s (last: %s)", podcast_name, video_id)
                return None

            raw_vtt = fetch_captions_ytdlp(video_url)
            episode_title = f"Video {video_id}"

        except CaptionFetchError as e:
            log.warning("Caption fetch failed for %s: %s", podcast_name, e)
            raw_vtt = None

    # Step 3b: Whisper fallback for RSS-only podcasts
    if raw_vtt is None and podcast_source.rss_url:
        if not openai_api_key:
            log.warning("No OPENAI_API_KEY — skipping Whisper transcription for %s", podcast_name)
            return None

        from poddistill.fetchers.whisper_transcriber import transcribe_episode, WhisperError
        import feedparser  # type: ignore

        try:
            feed = feedparser.parse(podcast_source.rss_url)
            if not feed.entries:
                log.warning("No entries in RSS feed for %s", podcast_name)
                return None

            latest = feed.entries[0]
            episode_id = getattr(latest, "id", latest.get("link", ""))
            episode_title = getattr(latest, "title", "Untitled")

            if not is_new_episode(podcast_name, episode_id, state):
                log.info("No new episode for %s", podcast_name)
                return None

            # Find audio enclosure
            audio_url = None
            for enclosure in getattr(latest, "enclosures", []):
                if "audio" in enclosure.get("type", ""):
                    audio_url = enclosure.get("href") or enclosure.get("url")
                    break

            if not audio_url:
                log.warning("No audio enclosure found for %s", podcast_name)
                return None

            video_id = episode_id  # Use episode ID as identifier
            raw_vtt = transcribe_episode(audio_url, openai_api_key)

        except WhisperError as e:
            log.error("Whisper transcription failed for %s: %s", podcast_name, e)
            return None

    if raw_vtt is None:
        log.warning("Could not fetch transcript for %s — skipping", podcast_name)
        return None

    # Step 4: Parse timestamps (YouTube description only — skip for RSS)
    chapters = []
    # (Timestamp parsing from description requires additional API calls — skipping in MVP)

    # Step 5: Clean captions
    clean_text = clean_vtt(raw_vtt) if raw_vtt.startswith("WEBVTT") else raw_vtt
    log.info("Cleaned transcript: %d chars", len(clean_text))

    # Step 6: Chunk by chapters
    chunks = chunk_by_chapters(clean_text, chapters)
    log.info("Split into %d chunks", len(chunks))

    # Step 7: Summarize with Claude
    try:
        summarized = summarize_chunks(chunks, api_key=anthropic_api_key)
    except SummarizerError as e:
        log.error("Summarization failed for %s: %s", podcast_name, e)
        return None

    # Step 8: Format with timestamp deep-links
    final_markdown = format_summary_with_links(summarized, video_id or "")
    log.info("Generated %d chars of markdown summary", len(final_markdown))

    # Step 9: Upload to GCS (optional)
    if gcs_bucket and video_id:
        from poddistill.storage.gcs import upload_to_gcs, episode_gcs_paths, StorageError
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        podcast_slug = podcast_name.lower().replace(" ", "-").replace("/", "-")
        paths = episode_gcs_paths(date_str, podcast_slug, video_id)

        try:
            upload_to_gcs(gcs_bucket, paths["clean_captions"], clean_text, "text/plain")
            upload_to_gcs(gcs_bucket, paths["summary"], final_markdown, "text/markdown")
            log.info("Uploaded to GCS: gs://%s/%s", gcs_bucket, paths["summary"])
        except StorageError as e:
            log.warning("GCS upload failed (non-fatal): %s", e)

    # Mark as processed
    mark_processed(podcast_name, video_id or episode_title, state)

    return {
        "podcast_name": podcast_name,
        "episode_title": episode_title if "episode_title" in dir() else f"Episode {video_id}",
        "video_id": video_id or "",
        "summary_md": final_markdown,
    }


def main():
    log.info("PodDistill starting…")

    # Load config from environment
    anthropic_api_key = _get_env("ANTHROPIC_API_KEY", required=True)
    openai_api_key = _get_env("OPENAI_API_KEY")
    gcs_bucket = _get_env("GCS_BUCKET")
    agentmail_api_key = _get_env("AGENTMAIL_API_KEY")
    digest_recipient = _get_env("DIGEST_RECIPIENT")

    # Step 1: Load registry
    from poddistill.fetchers.registry import build_registry, load_podcasts_yaml

    podcasts_config = _get_env("PODCASTS_CONFIG") or "podcasts.yaml"
    try:
        podcast_names = load_podcasts_yaml(Path(podcasts_config))
    except FileNotFoundError:
        log.error("podcasts.yaml not found at: %s", podcasts_config)
        return

    registry = build_registry(podcast_names)
    log.info("Registry loaded: %d podcasts", len(registry))

    # Step 2: Load state
    from poddistill.fetchers.update_checker import load_state, save_state

    state = load_state()
    episodes_processed = []

    # Process each podcast
    for podcast_name, podcast_source in registry.items():
        if not podcast_source.has_source():
            log.warning("No source resolved for %s — skipping", podcast_name)
            continue

        result = process_podcast(
            podcast_source=podcast_source,
            state=state,
            anthropic_api_key=anthropic_api_key,
            openai_api_key=openai_api_key,
            gcs_bucket=gcs_bucket,
            agentmail_api_key=agentmail_api_key,
            digest_recipient=digest_recipient,
        )

        if result:
            episodes_processed.append(result)

    # Persist updated state
    save_state(state)
    log.info("State saved: %d podcasts tracked", len(state))

    # Step 10: Send email digest
    if episodes_processed and agentmail_api_key and digest_recipient:
        from poddistill.email.digest import send_digest, DigestError

        try:
            sent = send_digest(
                episodes=episodes_processed,
                recipient=digest_recipient,
                api_key=agentmail_api_key,
            )
            if sent:
                log.info("Digest sent to %s (%d episodes)", digest_recipient, len(episodes_processed))
        except DigestError as e:
            log.error("Failed to send digest: %s", e)
    elif episodes_processed:
        log.info(
            "Processed %d episodes but AGENTMAIL_API_KEY/DIGEST_RECIPIENT not set — "
            "skipping email",
            len(episodes_processed),
        )
    else:
        log.info("No new episodes to process today.")

    log.info("PodDistill done. %d episodes processed.", len(episodes_processed))


if __name__ == "__main__":
    main()
