#!/usr/bin/env python3
"""
PodDistill — End-to-End Integration Test

Runs the full production pipeline against real APIs:
  1. Loads podcasts.yaml
  2. Fetches latest episode per show via TranscriptAPI
  3. Summarizes with Claude (topic segments + deep-links)
  4. Sends email digest via AgentMail

Usage:
    ANTHROPIC_API_KEY=... TRANSCRIPT_API_KEY=... AGENTMAIL_API_KEY=... \
    DIGEST_RECIPIENT=you@example.com python3 tests/test_e2e.py

Set FORCE_REPROCESS=1 to bypass the dedup state check (useful for testing).
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

# Ensure repo root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

from poddistill.email.digest import DigestError, send_digest
from poddistill.fetchers.transcript_fetcher import TranscriptFetcher, TranscriptFetchError
from poddistill.fetchers.update_checker import (
    is_new_episode,
    load_state,
    mark_processed,
    save_state,
)
from poddistill.summarizer.claude_summarizer import SummarizerError, summarize_episode

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("e2e")

SEP = "=" * 60


def _require(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        raise SystemExit(f"ERROR: required env var not set: {key}")
    return val


def main() -> None:
    print(SEP)
    print("PodDistill — End-to-End Run")
    print(datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"))
    print(SEP)

    anthropic_api_key = _require("ANTHROPIC_API_KEY")
    transcript_api_key = _require("TRANSCRIPT_API_KEY")
    agentmail_api_key = os.environ.get("AGENTMAIL_API_KEY")
    digest_recipient = os.environ.get("DIGEST_RECIPIENT")
    force_reprocess = os.environ.get("FORCE_REPROCESS") == "1"

    # Load podcasts.yaml from repo root
    podcasts_config = Path(__file__).parent.parent / "podcasts.yaml"
    if not podcasts_config.exists():
        raise SystemExit(f"ERROR: podcasts.yaml not found at {podcasts_config}")

    with open(podcasts_config) as f:
        podcasts = yaml.safe_load(f).get("podcasts", [])

    print(f"\nLoaded {len(podcasts)} podcasts from podcasts.yaml")

    state = load_state()
    fetcher = TranscriptFetcher(api_key=transcript_api_key)
    episodes_processed = []

    # ── 1. Discover + fetch transcripts ──────────────────────────────────────
    print("\n[1/3] Fetching transcripts...")
    for podcast in podcasts:
        name = podcast["name"]
        playlist_id = podcast.get("playlist_id")
        channel_id = podcast.get("channel_id")
        keywords = podcast.get("keywords", [])
        first_match = podcast.get("first_match", False)
        network = podcast.get("network", "")
        custom_instructions = podcast.get("custom_instructions", "") or ""

        print(f"  {name:<48}", end="", flush=True)

        try:
            if playlist_id:
                video_id, ep_title = fetcher.find_latest_from_playlist(playlist_id)
            elif first_match:
                video_id, ep_title = fetcher.find_latest_episode(channel_id, first_match=True)
            elif keywords and channel_id:
                video_id, ep_title = fetcher.find_latest_episode(channel_id, keywords)
            else:
                print(" SKIP (no playlist_id / keywords)")
                continue

            if not video_id:
                print(" NO MATCH")
                continue

            if not force_reprocess and not is_new_episode(name, video_id, state):
                print(f" already processed ({video_id})")
                continue

            segments = fetcher.fetch_transcript(video_id)
            if not segments:
                print(" EMPTY TRANSCRIPT")
                continue

            transcript_text = fetcher.transcript_to_text(
                segments, include_timestamps=True, max_words=10000
            )
            print(f" {len(segments)} segs — {ep_title[:50]}")

        except TranscriptFetchError as e:
            print(f" FETCH ERROR: {e}")
            continue
        except Exception as e:
            print(f" ERROR: {e}")
            continue

        # ── 2. Summarize ──────────────────────────────────────────────────────
        try:
            segments_summary = summarize_episode(
                title=ep_title,
                transcript=transcript_text,
                video_id=video_id,
                api_key=anthropic_api_key,
                show_name=name,
                network=network,
                custom_instructions=custom_instructions,
            )
            mark_processed(name, video_id, state)
            episodes_processed.append(
                {
                    "podcast_name": name,
                    "network": network,
                    "episode_title": ep_title,
                    "video_id": video_id,
                    "segments": segments_summary,
                }
            )
            seg_count = len(segments_summary) if isinstance(segments_summary, list) else 1
            print(f"    → {seg_count} topic segments")
        except SummarizerError as e:
            print(f"    → SUMMARIZE ERROR: {e}")

    save_state(state)

    # ── 3. Send digest ────────────────────────────────────────────────────────
    print(f"\n[2/3] Results: {len(episodes_processed)} new episodes processed")

    if not episodes_processed:
        print("  Nothing new — no email sent.")
        return

    if not agentmail_api_key or not digest_recipient:
        print("  AGENTMAIL_API_KEY / DIGEST_RECIPIENT not set — skipping email.")
        return

    print(f"\n[3/3] Sending email digest to {digest_recipient}...")
    try:
        sent = send_digest(
            episodes=episodes_processed,
            recipient=digest_recipient,
            api_key=agentmail_api_key,
        )
        if sent:
            print(f"  Sent! ({len(episodes_processed)} episodes)")
    except DigestError as e:
        print(f"  FAILED: {e}")

    # ── Sample output ─────────────────────────────────────────────────────────
    if episodes_processed:
        ep = episodes_processed[0]
        segs = ep["segments"]
        print(f"\n{SEP}")
        print(f"SAMPLE: {ep['podcast_name']}")
        print(f"Episode: {ep['episode_title'][:70]}")
        print(f"https://youtube.com/watch?v={ep['video_id']}")
        print(SEP)
        if isinstance(segs, list) and segs:
            for seg in segs[:2]:
                print(f"\n## {seg.get('segment_title', '?')}")
                print(f"   TL;DR: {seg.get('tldr', '')}")
                for b in seg.get("bullets", [])[:3]:
                    print(f"   - {b}")


if __name__ == "__main__":
    main()
