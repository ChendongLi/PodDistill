"""
Claude summarizer — summarizes podcast transcript chunks using Claude via
the Anthropic Messages API (raw HTTP, no SDK required).

For each chapter chunk, Claude generates:
1. A one-line headline
2. 3-5 key bullet points
3. One notable quote if present

All formatted as Markdown.
"""
from __future__ import annotations

import logging
from typing import Optional

import requests

log = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-3-5-haiku-20241022"
MAX_TOKENS = 1024


class SummarizerError(Exception):
    """Raised when summarization fails."""


def _build_prompt(title: str, text: str) -> str:
    """Build the summarization prompt for a chapter."""
    return (
        f"Summarize this podcast segment titled '{title}'. "
        "Provide: 1) A one-line headline 2) 3-5 key bullet points "
        "3) One notable quote if present. Format as markdown.\n\n"
        f"Transcript:\n{text}"
    )


def _call_claude(
    prompt: str,
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
        "messages": [
            {"role": "user", "content": prompt}
        ],
    }

    try:
        resp = requests.post(
            ANTHROPIC_API_URL,
            headers=headers,
            json=payload,
            timeout=60,
        )
    except Exception as e:
        raise SummarizerError(f"Anthropic API request failed: {e}") from e

    if resp.status_code != 200:
        raise SummarizerError(
            f"Anthropic API returned {resp.status_code}: {resp.text[:300]}"
        )

    data = resp.json()
    # Response structure: {"content": [{"type": "text", "text": "..."}], ...}
    content_blocks = data.get("content", [])
    if not content_blocks:
        raise SummarizerError("Anthropic API returned empty content")

    text_blocks = [b.get("text", "") for b in content_blocks if b.get("type") == "text"]
    result = "\n".join(text_blocks).strip()
    if not result:
        raise SummarizerError("Anthropic API returned no text content")

    return result


def summarize_chunks(
    chunks: list[dict],
    api_key: str,
    model: str = DEFAULT_MODEL,
) -> list[dict]:
    """
    Summarize a list of transcript chunks using Claude.

    For each chunk, sends the transcript text to Claude and receives a
    Markdown summary. Chunks with empty text are skipped gracefully.

    Args:
        chunks: List of dicts with keys:
                  - title (str): Chapter title
                  - startSeconds (int): Chapter start time
                  - text (str): Transcript text for this chapter
        api_key: Anthropic API key.
        model: Claude model to use (default: claude-3-5-haiku-20241022).

    Returns:
        List of dicts with keys:
            - title (str): Chapter title
            - startSeconds (int): Chapter start time
            - summary_md (str): Markdown summary from Claude

    Raises:
        SummarizerError: If any API call fails.
    """
    results = []

    for i, chunk in enumerate(chunks):
        title = chunk.get("title", f"Chapter {i+1}")
        start_seconds = chunk.get("startSeconds", 0)
        text = chunk.get("text", "").strip()

        if not text:
            log.warning("Skipping empty chunk: %r", title)
            results.append({
                "title": title,
                "startSeconds": start_seconds,
                "summary_md": f"## {title}\n\n*No transcript available for this segment.*",
            })
            continue

        log.info("Summarizing chunk %d/%d: %r (%d chars)", i + 1, len(chunks), title, len(text))

        prompt = _build_prompt(title, text)
        summary_md = _call_claude(prompt, api_key, model)

        results.append({
            "title": title,
            "startSeconds": start_seconds,
            "summary_md": summary_md,
        })

    return results
