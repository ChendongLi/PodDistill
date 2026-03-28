"""
Claude summarizer -- sends a timestamped transcript to Claude and asks it to
segment the episode by topic, returning structured JSON summaries with
start_seconds for YouTube deep-link generation.

No hardcoded chunk sizes -- Claude decides where topic breaks fall.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

import requests
import yaml

log = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 4096

DEFAULT_PROMPTS_FILE = Path(__file__).parent.parent.parent / "prompts.yaml"


class SummarizerError(Exception):
    """Raised when summarization fails."""


def load_prompts(prompts_file: Path | None = None) -> dict:
    """Load prompts.yaml and return the parsed dict."""
    env_path = os.environ.get("PROMPTS_FILE")
    path = Path(env_path) if env_path else (prompts_file or DEFAULT_PROMPTS_FILE)
    if not path.exists():
        raise SummarizerError(f"prompts.yaml not found at {path}")
    try:
        with path.open() as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise SummarizerError(f"Failed to parse {path}: {e}") from e
    if not isinstance(data, dict) or "default" not in data:
        raise SummarizerError(f"prompts.yaml must have a 'default' key -- got: {list(data)}")
    return data


def build_prompt(
    title: str,
    transcript: str,
    show_name: str = "",
    network: str = "",
    custom_instructions: str = "",
    prompts: dict | None = None,
) -> tuple[str, str]:
    """Build (system_prompt, user_message) for a single summarization call."""
    if prompts is None:
        prompts = load_prompts()
    default = prompts.get("default", {})
    system = default.get("system", "You are a helpful podcast summarizer.").strip()
    user_template = default.get("user_template", "{transcript}").strip()
    user_message = user_template.format(
        show_name=show_name or "Unknown Show",
        network=network or "Unknown Network",
        title=title,
        transcript=transcript,
        custom_instructions=custom_instructions.strip(),
    )
    return system, user_message


def _call_claude(
    system: str,
    user_message: str,
    api_key: str,
    model: str = DEFAULT_MODEL,
    max_tokens: int = MAX_TOKENS,
) -> str:
    """Make a single request to the Anthropic Messages API."""
    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_API_VERSION,
        "content-type": "application/json",
    }
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user_message}],
    }
    try:
        resp = requests.post(ANTHROPIC_API_URL, headers=headers, json=payload, timeout=60)
    except Exception as e:
        raise SummarizerError(f"Anthropic API request failed: {e}") from e
    if resp.status_code != 200:
        raise SummarizerError(f"Anthropic API returned {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    stop_reason = data.get("stop_reason", "")
    if stop_reason == "max_tokens":
        log.warning("Claude hit max_tokens limit — response may be truncated")
    content_blocks = data.get("content", [])
    if not content_blocks:
        raise SummarizerError("Anthropic API returned empty content")
    text_blocks = [b.get("text", "") for b in content_blocks if b.get("type") == "text"]
    result = "\n".join(text_blocks).strip()
    if not result:
        raise SummarizerError("Anthropic API returned no text content")
    if stop_reason == "max_tokens" and result:
        # Attempt to salvage truncated JSON by closing open structures
        result = _repair_truncated_json(result)
    return result


def _repair_truncated_json(text: str) -> str:
    """Best-effort repair of a JSON array truncated by max_tokens."""
    text = text.strip()
    # Strip markdown fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text).strip()
    # Find the last complete object (ends with })
    last_brace = text.rfind("}")
    if last_brace == -1:
        return text
    truncated = text[: last_brace + 1]
    # Ensure it closes as a valid JSON array
    if not truncated.rstrip().endswith("]"):
        truncated = truncated.rstrip().rstrip(",") + "\n]"
    return truncated


def _parse_segments_json(raw_text: str) -> list[dict]:
    """Extract and validate the JSON array from Claude's response."""
    text = raw_text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()
    try:
        segments = json.loads(text)
    except json.JSONDecodeError as e:
        raise SummarizerError(f"Claude returned invalid JSON: {e}\nRaw: {text[:500]}") from e
    if not isinstance(segments, list):
        raise SummarizerError(f"Expected JSON array, got {type(segments).__name__}")
    validated = []
    for i, seg in enumerate(segments):
        if not isinstance(seg, dict):
            log.warning("Skipping non-dict segment at index %d", i)
            continue
        validated.append(
            {
                "segment_title": str(seg.get("segment_title", f"Segment {i + 1}")),
                "start_seconds": int(seg.get("start_seconds", 0)),
                "tldr": str(seg.get("tldr", "")),
                "bullets": [str(b) for b in seg.get("bullets", [])],
                "tickers": str(seg.get("tickers", "None")),
            }
        )
    if not validated:
        raise SummarizerError("Claude returned an empty segments array")
    return validated


def make_deep_link(video_id: str, start_seconds: int) -> str:
    """Return a YouTube deep-link URL."""
    return f"https://www.youtube.com/watch?v={video_id}&t={start_seconds}s"


def format_timestamp(seconds: int) -> str:
    """Convert seconds to M:SS or H:MM:SS string."""
    seconds = max(0, int(seconds))
    h, remainder = divmod(seconds, 3600)
    m, s = divmod(remainder, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def summarize_episode(
    title: str,
    transcript: str,
    video_id: str,
    api_key: str,
    model: str = DEFAULT_MODEL,
    show_name: str = "",
    network: str = "",
    custom_instructions: str = "",
    prompts: dict | None = None,
) -> list[dict]:
    """
    Send a full timestamped transcript to Claude.

    Claude segments the episode by topic and returns structured summaries.
    Each segment gets a YouTube deep-link based on its start_seconds.

    Returns list of segment dicts with keys:
        segment_title, start_seconds, timestamp_str, deep_link,
        tldr, bullets, tickers
    """
    if prompts is None:
        prompts = load_prompts()
    system, user_message = build_prompt(
        title=title,
        transcript=transcript,
        show_name=show_name,
        network=network,
        custom_instructions=custom_instructions,
        prompts=prompts,
    )
    log.info(
        "Summarizing %r (%d chars) -- asking Claude to segment by topic", title, len(transcript)
    )
    raw_response = _call_claude(system, user_message, api_key, model)
    segments = _parse_segments_json(raw_response)
    for seg in segments:
        seg["timestamp_str"] = format_timestamp(seg["start_seconds"])
        seg["deep_link"] = make_deep_link(video_id, seg["start_seconds"])
    log.info("Claude identified %d segments for %r", len(segments), title)
    return segments


def summarize_chunks(
    chunks: list[dict],
    api_key: str,
    model: str = DEFAULT_MODEL,
    show_name: str = "",
    network: str = "",
    custom_instructions: str = "",
    prompts: dict | None = None,
) -> list[dict]:
    """Legacy wrapper kept for test compatibility."""
    if not chunks:
        return []
    if prompts is None:
        prompts = load_prompts()
    results = []
    for chunk in chunks:
        title = chunk.get("title", "Episode")
        text = chunk.get("text", "").strip()
        start = chunk.get("startSeconds", 0)
        video_id = chunk.get("video_id", "unknown")
        if not text:
            results.append(
                {
                    "title": title,
                    "startSeconds": start,
                    "summary_md": f"## {title}\n\n*No transcript available.*",
                }
            )
            continue
        try:
            segments = summarize_episode(
                title=title,
                transcript=text,
                video_id=video_id,
                api_key=api_key,
                model=model,
                show_name=show_name,
                network=network,
                custom_instructions=custom_instructions,
                prompts=prompts,
            )
            md_parts = []
            for seg in segments:
                md_parts.append(f"### [{seg['timestamp_str']}] {seg['segment_title']}")
                md_parts.append(seg["tldr"])
                for b in seg["bullets"]:
                    md_parts.append(f"- {b}")
                if seg["tickers"] and seg["tickers"].lower() != "none":
                    md_parts.append(f"*Tickers: {seg['tickers']}*")
                md_parts.append(f"[>> Jump to {seg['timestamp_str']}]({seg['deep_link']})")
                md_parts.append("")
            results.append(
                {"title": title, "startSeconds": start, "summary_md": "\n".join(md_parts)}
            )
        except SummarizerError as e:
            log.error("Summarization failed for %r: %s", title, e)
            results.append(
                {
                    "title": title,
                    "startSeconds": start,
                    "summary_md": f"## {title}\n\n*Summarization failed: {e}*",
                }
            )
    return results
