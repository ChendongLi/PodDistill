import os
import re
import time
from datetime import datetime

import requests

TRANSCRIPT_KEY = "sk_e7Ayv89yIFw2sRKgeCM_0dd-v6mHR2xiEkRuQial7lU"
ANTHROPIC_KEY = os.environ["ANTHROPIC_API_KEY"]
AGENTMAIL_KEY = os.environ["AGENTMAIL_API_KEY"]

TRANSCRIPT_BASE = "https://transcriptapi.com/api/v2/youtube"
TH = {"Authorization": "Bearer " + TRANSCRIPT_KEY}

BLOOMBERG = "UCIALMKvObZNtJ6AmdCLP7Lg"
GOLDMAN = "UCyz6-taovlaOkPsPtK4KNEg"
MORGAN = "UCz6RzD6KG_hH_oHb2kyW5jQ"

SHOWS = [
    ("Bloomberg The Opening Trade", BLOOMBERG, ["the opening trade", "opening trade"]),
    ("Bloomberg The Close", BLOOMBERG, ["the close"]),
    ("Bloomberg Businessweek", BLOOMBERG, ["businessweek"]),
    ("Bloomberg Daybreak", BLOOMBERG, ["daybreak"]),
    ("Goldman Sachs The Markets", GOLDMAN, ["the markets", "market stress", "opportunity"]),
    (
        "Morgan Stanley Thoughts on the Market",
        MORGAN,
        ["thoughts on the market", "market correction", "bottleneck"],
    ),
]


def get_channel_videos(channel_id):
    r = requests.get(
        TRANSCRIPT_BASE + "/channel/videos", params={"channel": channel_id}, headers=TH, timeout=20
    )
    r.raise_for_status()
    return r.json().get("results", [])


def find_video(videos, keywords, min_sec=120):
    for v in videos:
        if "#shorts" in v["title"].lower():
            continue
        dur = v.get("lengthText", "99:00")
        parts = dur.split(":")
        try:
            if len(parts) == 2:
                total = int(parts[0]) * 60 + int(parts[1])
            else:
                total = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            if total < min_sec:
                continue
        except Exception:
            pass
        for kw in keywords:
            if kw.lower() in v["title"].lower():
                return v
    return None


def get_transcript(video_id):
    for attempt in range(3):
        try:
            r = requests.get(
                TRANSCRIPT_BASE + "/transcript",
                params={"video_url": video_id, "format": "json"},
                headers=TH,
                timeout=90,
            )
            r.raise_for_status()
            return r.json()["transcript"]
        except requests.ReadTimeout:
            if attempt < 2:
                time.sleep(3)
                continue
            raise
    raise RuntimeError("timeout")


def summarize(show_name, ep_title, video_id, segments):
    lines = []
    total_words = 0
    for s in segments:
        text = s.get("text", "") if isinstance(s, dict) else str(s)
        ts = s.get("offset", s.get("start", 0)) if isinstance(s, dict) else 0
        if isinstance(ts, int | float) and ts > 10000:
            ts = int(ts / 1000)
        mins, secs = divmod(int(ts), 60)
        lines.append(f"[{mins}:{secs:02d}] {text}")
        total_words += len(text.split())
        if total_words > 6000:
            break
    transcript_text = "\n".join(lines)
    yt_base = "https://youtube.com/watch?v=" + video_id
    prompt = (
        "You are summarizing a financial markets podcast for a busy professional.\n"
        f"Show: {show_name}\nEpisode: {ep_title}\nVideo: {yt_base}\n\n"
        f"Transcript (with timestamps):\n{transcript_text}\n\n"
        "Write a crisp summary:\n"
        "**Key Takeaways** (3-5 bullets)\n"
        "**Markets and Numbers** (prices, levels, data points)\n"
        "**Notable Quote** (1 verbatim quote with timestamp link)\n"
        "**Topics Covered** (brief list)\n\n"
        f"Timestamp links: [M:SS]({yt_base}&t=SECONDS)\n"
        "Be specific, data-rich, max 280 words."
    )
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 600,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["content"][0]["text"]


def build_html(summaries, today):
    parts = [
        '<html><body style="font-family:Georgia,serif;max-width:680px;margin:0 auto;padding:20px">',
        '<div style="background:#0a0a0a;padding:24px;border-radius:8px;margin-bottom:32px">',
        '<h1 style="color:#f0c040;margin:0">PodDistill</h1>',
        f'<p style="color:#999;margin:8px 0 0;font-size:14px">Daily Market Intelligence &mdash; {today}</p>',
        "</div>",
    ]
    for item in summaries:
        name, vid, title, summ = item["name"], item["video_id"], item["title"], item["summary"]
        h = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", summ)
        h = re.sub(
            r"\[([^\]]+)\]\((https?://[^\)]+)\)", r'<a href="\2" style="color:#0066cc">\1</a>', h
        )
        h = "<p>" + h.replace("\n\n", "</p><p>").replace("\n", "<br>") + "</p>"
        parts += [
            '<div style="background:#fff;border:1px solid #e0e0e0;border-radius:8px;padding:24px;margin-bottom:24px">',
            f'<div style="font-size:11px;text-transform:uppercase;color:#888;margin-bottom:4px">{name}</div>',
            f'<h2 style="margin:0 0 12px;font-size:17px"><a href="https://youtube.com/watch?v={vid}" style="color:#1a1a1a;text-decoration:none">{title}</a></h2>',
            f'<div style="font-size:15px;line-height:1.7">{h}</div>',
            f'<div style="margin-top:16px"><a href="https://youtube.com/watch?v={vid}" style="background:#cc0000;color:#fff;padding:8px 18px;border-radius:4px;text-decoration:none;font-size:13px">Watch on YouTube</a></div>',
            "</div>",
        ]
    parts.append("</body></html>")
    return "".join(parts)


def send_digest(summaries):
    today = datetime.now().strftime("%B %d, %Y")
    html = build_html(summaries, today)
    text = f"PodDistill - {today}\n\n"
    for item in summaries:
        clean = re.sub(
            r"\[([^\]]+)\]\([^\)]+\)", r"\1", re.sub(r"\*\*(.+?)\*\*", r"\1", item["summary"])
        )
        text += "=== {} ===\n{}\n{}\nhttps://youtube.com/watch?v={}\n\n".format(
            item["name"],
            item["title"],
            clean,
            item["video_id"],
        )
    r = requests.post(
        "https://api.agentmail.to/v0/inboxes/agentlens@agentmail.to/messages/send",
        headers={"Authorization": "Bearer " + AGENTMAIL_KEY, "Content-Type": "application/json"},
        json={
            "to": ["lichendong@gmail.com"],
            "subject": f"PodDistill - Market Intelligence Digest, {today}",
            "text": text,
            "html": html,
        },
        timeout=30,
    )
    return r.status_code, r.text[:200]


print("=" * 60)
print("PodDistill - End-to-End Run")
print(datetime.now().strftime("%Y-%m-%d %H:%M UTC"))
print("=" * 60)

print("\n[1/4] Channel video lists...")
channel_videos = {}
for label, cid in [
    ("Bloomberg", BLOOMBERG),
    ("Goldman Sachs", GOLDMAN),
    ("Morgan Stanley", MORGAN),
]:
    vids = get_channel_videos(cid)
    channel_videos[cid] = vids
    print(f"  {label}: {len(vids)} videos")

print("\n[2/4] Fetching transcripts...")
show_data = []
tcache = {}
for name, cid, keywords in SHOWS:
    vids = channel_videos.get(cid, [])
    video = find_video(vids, keywords) or find_video(vids, keywords, min_sec=0)
    if not video:
        print(f"  {name:<44}  NO MATCH")
        continue
    vid = video["videoId"]
    ep_title = video["title"]
    dur = video.get("lengthText", "?")
    if vid in tcache:
        print(f"  {name:<44}  [cached] {ep_title[:40]}")
        show_data.append(
            {"name": name, "video_id": vid, "title": ep_title, "transcript": tcache[vid]}
        )
        continue
    print(f"  {name:<44}  {vid} [{dur}]...", end="", flush=True)
    try:
        t = get_transcript(vid)
        tcache[vid] = t
        print(f" {len(t)} segs")
        show_data.append({"name": name, "video_id": vid, "title": ep_title, "transcript": t})
    except Exception as exc:
        print(f" FAILED: {str(exc)[:60]}")
    time.sleep(0.5)

print("\n[3/4] Claude summaries...")
summaries = []
for item in show_data:
    print("  {}...".format(item["name"]), end="", flush=True)
    try:
        s = summarize(item["name"], item["title"], item["video_id"], item["transcript"])
        summaries.append(
            {
                "name": item["name"],
                "video_id": item["video_id"],
                "title": item["title"],
                "summary": s,
            }
        )
        print(f" {len(s)} chars")
    except Exception as exc:
        print(f" FAILED: {str(exc)[:60]}")
    time.sleep(0.3)

print("\n[4/4] Sending email...")
if summaries:
    code, resp = send_digest(summaries)
    if code in (200, 201):
        print(f"  Sent! {len(summaries)} shows, status={code}")
    else:
        print(f"  FAILED status={code}: {resp}")
else:
    print("  Nothing to send.")

if summaries:
    s = summaries[0]
    print("\n=== SAMPLE: {} ===".format(s["name"]))
    print("Episode: {}".format(s["title"][:70]))
    print("https://youtube.com/watch?v={}\n".format(s["video_id"]))
    print(s["summary"])
