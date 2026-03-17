"""
Email digest via AgentMail.

Sends a daily PodDistill digest email containing summaries of all newly
processed podcast episodes.

AgentMail API:
    POST https://api.agentmail.to/v0/inboxes/{inbox_id}/messages/send
    Authorization: Bearer {api_key}
    Body: {
        "to": ["recipient@email.com"],
        "subject": "...",
        "text": "...",
        "html": "..."
    }

Usage:
    from poddistill.email.digest import send_digest

    success = send_digest(
        episodes=[
            {
                "podcast_name": "Lex Fridman Podcast",
                "episode_title": "Episode #400",
                "video_id": "dQw4w9WgXcQ",
                "summary_md": "## Summary\n\n- Point 1",
            }
        ],
        recipient="user@example.com",
        api_key="your-agentmail-api-key",
    )
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Optional

import requests

log = logging.getLogger(__name__)

AGENTMAIL_API_BASE = "https://api.agentmail.to/v0"
DEFAULT_INBOX = "agentlens@agentmail.to"


class DigestError(Exception):
    """Raised when the digest email fails to send."""


def _md_to_html(md_text: str) -> str:
    """Convert Markdown to simple HTML for email."""
    lines = md_text.split("\n")
    html_lines = []
    in_list = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("### "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h3>{stripped[4:]}</h3>")
        elif stripped.startswith("## "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h2>{stripped[3:]}</h2>")
        elif stripped.startswith("# "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h1>{stripped[2:]}</h1>")
        elif stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            html_lines.append(f"<li>{stripped[2:]}</li>")
        elif stripped.startswith("> "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<blockquote><em>{stripped[2:]}</em></blockquote>")
        elif stripped in ("---", "***", "___"):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append("<hr>")
        elif not stripped:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append("")
        else:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<p>{stripped}</p>")

    if in_list:
        html_lines.append("</ul>")

    html = "\n".join(html_lines)
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = re.sub(r"\*(.+?)\*", r"<em>\1</em>", html)
    html = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', html)
    return html


def _build_email_body(episodes: list[dict]) -> tuple[str, str]:
    """Build (text_body, html_body) for the digest email."""
    text_parts = []
    html_parts = [
        "<html><body>",
        "<h1>🎙️ PodDistill Daily Digest</h1>",
        "<p>Your podcast summaries for today:</p>",
        "<hr>",
    ]

    for ep in episodes:
        podcast_name = ep.get("podcast_name", "Unknown Podcast")
        episode_title = ep.get("episode_title", "Untitled Episode")
        video_id = ep.get("video_id", "")
        summary_md = ep.get("summary_md", "")

        text_parts.append("=" * 60)
        text_parts.append(f"{podcast_name}: {episode_title}")
        if video_id:
            text_parts.append(f"Watch: https://youtube.com/watch?v={video_id}")
        text_parts.append("")
        text_parts.append(summary_md)
        text_parts.append("")

        html_parts.append(f"<h2>{podcast_name}: {episode_title}</h2>")
        if video_id:
            yt_url = f"https://youtube.com/watch?v={video_id}"
            html_parts.append(f'<p><a href="{yt_url}">▶ Watch on YouTube</a></p>')
        html_parts.append(_md_to_html(summary_md))
        html_parts.append("<hr>")

    html_parts.append("<p><em>Delivered by PodDistill 🎙️</em></p>")
    html_parts.append("</body></html>")

    return "\n".join(text_parts), "\n".join(html_parts)


def send_digest(
    episodes: list[dict],
    recipient: str,
    api_key: str,
    inbox: str = DEFAULT_INBOX,
    date_str: Optional[str] = None,
) -> bool:
    """
    Send a PodDistill digest email via AgentMail.

    Args:
        episodes:  List of episode dicts with keys:
                     podcast_name, episode_title, video_id, summary_md
        recipient: Destination email address.
        api_key:   AgentMail API key (used as Bearer token).
        inbox:     AgentMail inbox ID (default: agentlens@agentmail.to)
        date_str:  Date string for subject (default: today UTC, e.g. "March 17, 2026")

    Returns:
        True if sent, False if no episodes (nothing to send).

    Raises:
        DigestError: If the API call fails.
    """
    if not episodes:
        log.info("No episodes to digest, skipping email")
        return False

    if date_str is None:
        date_str = datetime.now(timezone.utc).strftime("%B %d, %Y")

    subject = f"PodDistill Digest — {date_str}"
    text_body, html_body = _build_email_body(episodes)

    payload = {
        "to": [recipient],
        "subject": subject,
        "text": text_body,
        "html": html_body,
    }

    url = f"{AGENTMAIL_API_BASE}/inboxes/{inbox}/messages/send"
    log.info("Sending digest to %s via %s (%d episodes)", recipient, inbox, len(episodes))

    try:
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        )
    except Exception as e:
        raise DigestError(f"AgentMail request failed: {e}") from e

    if resp.status_code not in (200, 201, 202):
        raise DigestError(
            f"AgentMail returned {resp.status_code}: {resp.text[:300]}"
        )

    log.info("Digest sent (status %d)", resp.status_code)
    return True
