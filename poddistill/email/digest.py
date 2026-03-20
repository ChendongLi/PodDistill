"""
Email digest via AgentMail — HTML email with inline CSS.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime

import requests

log = logging.getLogger(__name__)

AGENTMAIL_API_BASE = "https://api.agentmail.to/v0"
DEFAULT_INBOX = "agentlens@agentmail.to"

NETWORK_COLORS: dict[str, str] = {
    "Bloomberg": "#f26522",
    "Goldman Sachs": "#6699cc",
    "Morgan Stanley": "#003087",
    "CNBC": "#cc0000",
}


class DigestError(Exception):
    """Raised when the digest email fails to send."""


def _network_color(network: str) -> str:
    return NETWORK_COLORS.get(network, "#6366f1")


def _md_to_html(md_text: str) -> str:
    lines = md_text.split("\n")
    html_lines: list[str] = []
    in_list = False
    h2 = 'style="margin:20px 0 6px;font-size:16px;color:#0f3460;"'
    h3 = 'style="margin:16px 0 4px;font-size:14px;color:#374151;"'
    li = 'style="margin:4px 0;color:#374151;line-height:1.6;"'
    p = 'style="margin:8px 0;color:#374151;line-height:1.6;"'
    bq = 'style="margin:8px 0 8px 16px;padding:8px 12px;border-left:3px solid #d1d5db;color:#6b7280;font-style:italic;"'

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            html_lines.append("</ul>")
            in_list = False

    for line in lines:
        s = line.strip()
        if s.startswith("### "):
            close_list()
            html_lines.append(f"<h3 {h3}>{s[4:]}</h3>")
        elif s.startswith("## "):
            close_list()
            html_lines.append(f"<h2 {h2}>{s[3:]}</h2>")
        elif s.startswith("# "):
            close_list()
            html_lines.append(f"<h2 {h2}>{s[2:]}</h2>")
        elif s.startswith(("- ", "* ")):
            if not in_list:
                html_lines.append('<ul style="margin:8px 0;padding-left:20px;">')
                in_list = True
            html_lines.append(f"<li {li}>{s[2:]}</li>")
        elif s.startswith("> "):
            close_list()
            html_lines.append(f"<blockquote {bq}>{s[2:]}</blockquote>")
        elif s in ("---", "***", "___"):
            close_list()
            html_lines.append(
                '<hr style="border:none;border-top:1px solid #e5e7eb;margin:16px 0;">'
            )
        elif not s:
            close_list()
        else:
            close_list()
            html_lines.append(f"<p {p}>{s}</p>")

    close_list()
    html = "\n".join(html_lines)
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = re.sub(r"\*(.+?)\*", r"<em>\1</em>", html)
    html = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        r'<a href="\2" style="color:#6366f1;text-decoration:none;">\1</a>',
        html,
    )
    return html


def _segment_block(seg: dict, accent: str, vid: str) -> str:
    """Render a single Claude-identified segment with timestamp deep-link."""
    seg_title = seg.get("segment_title", "")
    timestamp_str = seg.get("timestamp_str", "")
    deep_link = seg.get("deep_link", f"https://youtube.com/watch?v={vid}" if vid else "")
    tldr = seg.get("tldr", "")
    bullets = seg.get("bullets", [])
    tickers = seg.get("tickers", "")

    bullet_html = "".join(
        f'<li style="margin:3px 0;color:#374151;line-height:1.6;">{b}</li>' for b in bullets
    )

    ticker_html = ""
    if tickers and tickers.lower() not in ("none", ""):
        ticker_html = (
            f'<p style="margin:8px 0 0;font-size:12px;color:#6b7280;">'
            f"<strong>Tickers:</strong> {tickers}</p>"
        )

    jump_btn = ""
    if deep_link and timestamp_str:
        jump_btn = (
            f'<a href="{deep_link}" style="display:inline-block;margin-top:10px;'
            f"padding:5px 14px;background:{accent}18;color:{accent};border:1px solid {accent}44;"
            f'text-decoration:none;border-radius:4px;font-size:12px;font-weight:600;">'
            f"&#9654; Jump to {timestamp_str}</a>"
        )

    return (
        f'<div style="margin:14px 0 0;padding:12px 14px;background:#f9fafb;border-radius:6px;'
        f'border-left:3px solid {accent}88;">'
        + (
            f'<p style="margin:0 0 4px;font-size:13px;font-weight:700;color:#1e293b;">{seg_title}</p>'
            if seg_title
            else ""
        )
        + (f'<p style="margin:0 0 8px;font-size:13px;color:#374151;">{tldr}</p>' if tldr else "")
        + (f'<ul style="margin:4px 0;padding-left:18px;">{bullet_html}</ul>' if bullet_html else "")
        + ticker_html
        + jump_btn
        + "</div>"
    )


def _episode_card(ep: dict) -> str:
    name = ep.get("podcast_name", "Unknown Podcast")
    title = ep.get("episode_title", "Untitled Episode")
    network = ep.get("network", "")
    vid = ep.get("video_id", "")
    segments = ep.get("segments", [])
    accent = _network_color(network)
    yt_url = f"https://youtube.com/watch?v={vid}" if vid else ""

    badge = (
        (
            f'<span style="display:inline-block;padding:2px 8px;background:{accent}22;'
            + f"color:{accent};border-radius:12px;font-size:11px;font-weight:700;"
            + f'letter-spacing:0.5px;margin-bottom:8px;text-transform:uppercase;">{network}</span><br>'
        )
        if network
        else ""
    )

    watch = (
        (
            f'<p style="margin:20px 0 0;"><a href="{yt_url}" style="display:inline-block;'
            + f"padding:8px 18px;background:{accent};color:#fff;text-decoration:none;"
            + 'border-radius:4px;font-size:13px;font-weight:600;">&#9654; Watch on YouTube</a></p>'
        )
        if yt_url
        else ""
    )

    # Render segments if available, otherwise fall back to legacy summary_md
    if segments:
        body = "".join(_segment_block(seg, accent, vid) for seg in segments)
    else:
        summary = ep.get("summary_md", "")
        body = _md_to_html(summary)

    return (
        '<table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:20px;">'
        + '<tr><td style="background:#fff;border-radius:8px;border:1px solid #e5e7eb;'
        + f'border-left:4px solid {accent};padding:20px 24px;">'
        + badge
        + f'<h2 style="margin:0 0 2px;font-size:18px;color:#0f3460;">{name}</h2>'
        + f'<p style="margin:0 0 14px;font-size:13px;color:#6b7280;">{title}</p>'
        + '<hr style="border:none;border-top:1px solid #f3f4f6;margin:0 0 4px;">'
        + body
        + watch
        + "</td></tr></table>"
    )


def _build_email_body(episodes: list[dict], date_str: str) -> tuple[str, str]:
    # Plain text
    lines = [f"PodDistill Digest \u2014 {date_str}", "=" * 50, ""]
    for ep in episodes:
        lines.append(f"## {ep.get('podcast_name', '')} \u2014 {ep.get('episode_title', '')}")
        if ep.get("video_id"):
            lines.append(f"Watch: https://youtube.com/watch?v={ep['video_id']}")
        segs = ep.get("segments", [])
        if segs:
            for seg in segs:
                lines.append(f"\n[{seg.get('timestamp_str', '')}] {seg.get('segment_title', '')}")
                lines.append(seg.get("tldr", ""))
                for b in seg.get("bullets", []):
                    lines.append(f"  - {b}")
                if seg.get("tickers") and seg["tickers"].lower() != "none":
                    lines.append(f"  Tickers: {seg['tickers']}")
                if seg.get("deep_link"):
                    lines.append(f"  \u25b6 {seg['deep_link']}")
        else:
            lines.append(ep.get("summary_md", ""))
        lines.append("\n" + "-" * 40 + "\n")
    lines.append("Delivered by PodDistill \u00b7 Weekdays")

    cards = "\n".join(_episode_card(ep) for ep in episodes)
    count = len(episodes)
    pl = "s" if count != 1 else ""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>PodDistill Digest &mdash; {date_str}</title></head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f3f4f6;">
<tr><td align="center" style="padding:24px 8px;">
<table width="680" cellpadding="0" cellspacing="0" style="max-width:680px;width:100%;">
<tr><td style="background:#0f3460;border-radius:8px 8px 0 0;padding:24px 24px;">
  <p style="margin:0;font-size:24px;font-weight:700;color:#fff;">&#127897; PodDistill</p>
  <p style="margin:4px 0 0;font-size:13px;color:#94a3b8;">{date_str} &middot; {count} new episode{pl}</p>
</td></tr>
<tr><td style="padding:20px 16px;background:#f3f4f6;">{cards}</td></tr>
<tr><td style="background:#e5e7eb;border-radius:0 0 8px 8px;padding:14px 16px;text-align:center;font-size:12px;color:#9ca3af;">
  Delivered by <strong style="color:#6b7280;">PodDistill</strong> &middot; Weekdays at 3&nbsp;PM&nbsp;PT
</td></tr>
</table></td></tr></table>
</body></html>"""

    return "\n".join(lines), html


def send_digest(
    episodes: list[dict],
    recipient: str | list[str],
    api_key: str,
    inbox: str = DEFAULT_INBOX,
    date_str: str | None = None,
) -> bool:
    """Send PodDistill digest email via AgentMail.

    recipient can be a single address string (comma-separated for multiple)
    or a list of address strings.
    """
    if not episodes:
        log.info("No episodes to digest, skipping email")
        return False

    if isinstance(recipient, str):
        recipients = [r.strip() for r in recipient.split(",") if r.strip()]
    else:
        recipients = [r.strip() for r in recipient if r.strip()]

    if not recipients:
        raise DigestError("No valid recipients provided")

    if date_str is None:
        date_str = datetime.now(UTC).strftime("%B %d, %Y")

    subject = f"\U0001f3a4 PodDistill \u2014 {date_str}"
    text_body, html_body = _build_email_body(episodes, date_str)

    url = f"{AGENTMAIL_API_BASE}/inboxes/{inbox}/messages/send"
    log.info("Sending digest to %s via %s (%d episodes)", recipients, inbox, len(episodes))

    try:
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"to": recipients, "subject": subject, "text": text_body, "html": html_body},
            timeout=30,
        )
    except Exception as e:
        raise DigestError(f"AgentMail request failed: {e}") from e

    if resp.status_code not in (200, 201, 202):
        raise DigestError(f"AgentMail returned {resp.status_code}: {resp.text[:300]}")

    log.info("Digest sent (status %d)", resp.status_code)
    return True
