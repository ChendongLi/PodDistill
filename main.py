#!/usr/bin/env python3
"""
PodDistill — Daily podcast summarizer with timestamp deep-links.

Pipeline:
    1. Load podcast registry (podcasts.yaml)
    2. Check for new episodes (state.json)
    3. Fetch transcript via TranscriptAPI (primary) or yt-dlp/Whisper (fallback)
    4. Parse timestamps & clean text
    5. Summarize with Claude
    6. Format summary with YouTube timestamp deep-links
    7. Upload to GCS (if configured)
    8. Send email digest via AgentMail
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from pathlib import Path

import yaml  # type: ignore
from dotenv import load_dotenv

from poddistill.email.digest import DigestError, send_digest
from poddistill.fetchers.transcript_fetcher import TranscriptFetcher, TranscriptFetchError
from poddistill.fetchers.update_checker import (
    is_new_episode,
    load_state,
    mark_processed,
    save_state,
)
from poddistill.storage.gcs import StorageError, episode_gcs_paths, upload_to_gcs
from poddistill.summarizer.claude_summarizer import SummarizerError, summarize_chunks
from poddistill.summarizer.formatter import format_summary_with_links

load_dotenv()

log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


def _get_env(key: str, required: bool = False) -> str | None:
    val = os.environ.get(key)
    if required and not val:
        raise RuntimeError(f"Required environment variable not set: {key}")
    return val


def _load_podcasts_yaml(path: Path) -> list[dict]:
    """Load podcasts.yaml and return list of podcast dicts."""
    with open(path) as f:
        data = yaml.safe_load(f)
    return data.get("podcasts", [])


def process_podcast_transcriptapi(
    podcast: dict,
    state: dict,
    transcript_api_key: str,
    anthropic_api_key: str,
    gcs_bucket: str | None,
) -> dict | None:
    """
    Process a single podcast using TranscriptAPI as the transcript source.

    Args:
        podcast: Dict with keys: name, channel_id, playlist_id, keywords, network, first_match
        state: Mutable state dict for dedup tracking
        transcript_api_key: TranscriptAPI.com key
        anthropic_api_key: Anthropic Claude key
        gcs_bucket: Optional GCS bucket name

    Returns:
        Episode result dict or None if skipped/errored.
    """
    name = podcast["name"]
    channel_id = podcast.get("channel_id")
    playlist_id = podcast.get("playlist_id")
    keywords = podcast.get("keywords", [])
    first_match = podcast.get("first_match", False)
    network = podcast.get("network", "")

    if not channel_id and not playlist_id:
        log.warning("Skipping %s — missing channel_id and playlist_id", name)
        return None

    fetcher = TranscriptFetcher(api_key=transcript_api_key)

    # Find latest episode: playlist takes priority over channel search
    if playlist_id:
        log.info("[%s] Looking for latest episode in playlist %s", name, playlist_id)
        video_id, ep_title = fetcher.find_latest_from_playlist(playlist_id)
    elif first_match:
        log.info("[%s] Looking for latest episode (first_match=True)", name)
        video_id, ep_title = fetcher.find_latest_episode(channel_id, first_match=True)
    else:
        if not keywords:
            log.warning("Skipping %s — missing keywords (and first_match not set)", name)
            return None
        log.info("[%s] Looking for latest episode (keywords=%s)", name, keywords)
        video_id, ep_title = fetcher.find_latest_episode(channel_id, keywords)

    if not video_id:
        log.warning("[%s] No matching episode found in recent channel videos", name)
        return None

    log.info("[%s] Found: %s — %s", name, video_id, ep_title)

    # Dedup check
    if not is_new_episode(name, video_id, state):
        log.info("[%s] Already processed %s — skipping", name, video_id)
        return None

    # Fetch transcript
    try:
        segments = fetcher.fetch_transcript(video_id)
    except TranscriptFetchError as e:
        log.error("[%s] Transcript fetch failed: %s", name, e)
        return None

    if not segments:
        log.warning("[%s] Empty transcript for %s", name, video_id)
        return None

    log.info("[%s] Fetched %d transcript segments", name, len(segments))

    # Build transcript text with timestamps for Claude
    transcript_text = fetcher.transcript_to_text(
        segments,
        include_timestamps=True,
        max_words=10000,
    )

    # Summarize with Claude
    chunks = [
        {
            "title": ep_title,
            "text": transcript_text,
            "startSeconds": 0,
        }
    ]

    custom_instructions = podcast.get("custom_instructions", "") or ""

    try:
        summarized = summarize_chunks(
            chunks,
            api_key=anthropic_api_key,
            show_name=name,
            network=network,
            custom_instructions=custom_instructions,
        )
    except SummarizerError as e:
        log.error("[%s] Summarization failed: %s", name, e)
        return None

    final_markdown = format_summary_with_links(summarized, video_id)

    # GCS upload (optional)
    if gcs_bucket:
        date_str = datetime.now(UTC).strftime("%Y-%m-%d")
        slug = name.lower().replace(" ", "-").replace("/", "-")
        paths = episode_gcs_paths(date_str, slug, video_id)
        try:
            upload_to_gcs(gcs_bucket, paths["summary"], final_markdown, "text/markdown")
            log.info("[%s] Uploaded summary to GCS", name)
        except StorageError as e:
            log.warning("[%s] GCS upload failed (non-fatal): %s", name, e)

    mark_processed(name, video_id, state)

    return {
        "podcast_name": name,
        "network": network,
        "episode_title": ep_title,
        "video_id": video_id,
        "summary_md": final_markdown,
    }


def main():
    log.info("PodDistill starting…")

    anthropic_api_key = _get_env("ANTHROPIC_API_KEY", required=True)
    transcript_api_key = _get_env("TRANSCRIPT_API_KEY")
    gcs_bucket = _get_env("GCS_BUCKET")
    agentmail_api_key = _get_env("AGENTMAIL_API_KEY")
    digest_recipient = _get_env("DIGEST_RECIPIENT")

    # Load podcast list
    podcasts_config = Path(_get_env("PODCASTS_CONFIG") or "podcasts.yaml")
    if not podcasts_config.exists():
        log.error("podcasts.yaml not found at: %s", podcasts_config)
        return
    podcasts = _load_podcasts_yaml(podcasts_config)
    log.info("Loaded %d podcasts from %s", len(podcasts), podcasts_config)

    state = load_state()
    episodes_processed = []

    # Process each podcast
    for podcast in podcasts:
        name = podcast.get("name", "?")
        try:
            # TranscriptAPI path (primary — all shows with channel_id + keywords or first_match)
            if transcript_api_key and (podcast.get("channel_id") or podcast.get("playlist_id")):
                result = process_podcast_transcriptapi(
                    podcast=podcast,
                    state=state,
                    transcript_api_key=transcript_api_key,
                    anthropic_api_key=anthropic_api_key,
                    gcs_bucket=gcs_bucket,
                )
                if result:
                    episodes_processed.append(result)
            else:
                log.warning("Skipping %s — no channel_id or TRANSCRIPT_API_KEY not set", name)
        except Exception as e:
            log.exception("Unexpected error processing %s: %s", name, e)

    save_state(state)
    log.info("State saved. %d new episodes processed.", len(episodes_processed))

    # Send digest
    if episodes_processed and agentmail_api_key and digest_recipient:
        try:
            sent = send_digest(
                episodes=episodes_processed,
                recipient=digest_recipient,
                api_key=agentmail_api_key,
            )
            if sent:
                log.info(
                    "Digest sent to %s (%d episodes)", digest_recipient, len(episodes_processed)
                )
        except DigestError as e:
            log.error("Failed to send digest: %s", e)
    elif episodes_processed:
        log.info(
            "Processed %d episodes — AGENTMAIL/RECIPIENT not set, skipping email",
            len(episodes_processed),
        )
    else:
        log.info("No new episodes to process today.")

    log.info("PodDistill done.")


if __name__ == "__main__":
    main()
