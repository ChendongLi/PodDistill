"""
Claude summarizer — summarizes podcast transcript chunks using Claude via
the Anthropic Messages API (raw HTTP, no SDK required).

Prompts are loaded from prompts.yaml (configurable via PROMPTS_FILE env var).
Each show can define custom_instructions that are injected into the template
as {custom_instructions}, allowing per-show tuning without touching Python.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import requests
import yaml

log = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 1024

# Default prompts.yaml lives next to main.py (repo root)
DEFAULT_PROMPTS_FILE = Path(__file__).parent.parent.parent / "prompts.yaml"


class SummarizerError(Exception):
    """Raised when summarization fails."""


# ── Prompt loading ────────────────────────────────────────────────────────────


def load_prompts(prompts_file: Path | None = None) -> dict:
    """
    Load prompts.yaml and return the parsed dict.

    Checks PROMPTS_FILE env var first, then the supplied path, then the
    default location (repo root/prompts.yaml).

    Raises:
        SummarizerError: If the file is missing or malformed.
    """
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
        raise SummarizerError(f"prompts.yaml must have a 'default' key — got: {list(data)}")

    return data


def build_prompt(
    title: str,
    transcript: str,
    show_name: str = "",
    network: str = "",
    prompts: dict | None = None,
) -> tuple[str, str]:
    """
    Build (system_prompt, user_message) for a single summarization call.

    Looks up show-specific custom_instructions in prompts['shows'][show_name].
    Falls back to an empty string if no per-show override exists.

    Args:
        title:      Episode title.
        transcript: Full transcript text.
        show_name:  Podcast show name (used for per-show lookup).
        network:    Network name (e.g. "CNBC").
        prompts:    Parsed prompts dict (from load_prompts). Loaded from disk
                    if not supplied.

    Returns:
        (system_prompt, user_message) tuple.
    """
    if prompts is None:
        prompts = load_prompts()

    default = prompts.get("default", {})
    system = default.get("system", "You are a helpful podcast summarizer.").strip()
    user_template = default.get("user_template", "{transcript}").strip()

    # Per-show custom instructions (empty string if not configured)
    shows = prompts.get("shows", {}) or {}
    show_config = shows.get(show_name, {}) or {}
    custom_instructions = (show_config.get("custom_instructions") or "").strip()

    # Format the user message
    user_message = user_template.format(
        show_name=show_name or "Unknown Show",
        network=network or "Unknown Network",
        title=title,
        transcript=transcript,
        custom_instructions=custom_instructions,
    )

    return system, user_message


# ── API call ──────────────────────────────────────────────────────────────────


def _call_claude(
    system: str,
    user_message: str,
    api_key: str,
    model: str = DEFAULT_MODEL,
    max_tokens: int = MAX_TOKENS,
) -> str:
    """
    Make a single request to the Anthropic Messages API.

    Returns the assistant's text response.

    Raises:
        SummarizerError: If the API call fails.
    """
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
    content_blocks = data.get("content", [])
    if not content_blocks:
        raise SummarizerError("Anthropic API returned empty content")

    text_blocks = [b.get("text", "") for b in content_blocks if b.get("type") == "text"]
    result = "\n".join(text_blocks).strip()
    if not result:
        raise SummarizerError("Anthropic API returned no text content")

    return result


# ── Public API ────────────────────────────────────────────────────────────────


def summarize_chunks(
    chunks: list[dict],
    api_key: str,
    model: str = DEFAULT_MODEL,
    show_name: str = "",
    network: str = "",
    prompts: dict | None = None,
) -> list[dict]:
    """
    Summarize a list of transcript chunks using Claude.

    Args:
        chunks:     List of dicts with keys:
                      - title (str): Chapter/segment title
                      - startSeconds (int): Segment start time in seconds
                      - text (str): Transcript text for this segment
        api_key:    Anthropic API key.
        model:      Claude model to use.
        show_name:  Podcast show name (used for per-show prompt lookup).
        network:    Network name (e.g. "CNBC").
        prompts:    Pre-loaded prompts dict. Loaded from disk if not supplied.

    Returns:
        List of dicts with keys:
            - title (str)
            - startSeconds (int)
            - summary_md (str): Markdown summary from Claude

    Raises:
        SummarizerError: If any API call fails.
    """
    if prompts is None:
        prompts = load_prompts()

    results = []

    for i, chunk in enumerate(chunks):
        title = chunk.get("title", f"Segment {i + 1}")
        start_seconds = chunk.get("startSeconds", 0)
        text = chunk.get("text", "").strip()

        if not text:
            log.warning("Skipping empty chunk: %r", title)
            results.append(
                {
                    "title": title,
                    "startSeconds": start_seconds,
                    "summary_md": f"## {title}\n\n*No transcript available for this segment.*",
                }
            )
            continue

        log.info(
            "Summarizing chunk %d/%d: %r (%d chars)",
            i + 1,
            len(chunks),
            title,
            len(text),
        )

        system, user_message = build_prompt(
            title=title,
            transcript=text,
            show_name=show_name,
            network=network,
            prompts=prompts,
        )
        summary_md = _call_claude(system, user_message, api_key, model)

        results.append(
            {
                "title": title,
                "startSeconds": start_seconds,
                "summary_md": summary_md,
            }
        )

    return results
