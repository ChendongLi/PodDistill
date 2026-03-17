# PodDistill 🎙️

AI-powered podcast & video summarizer with timestamp deep-links. Runs daily, delivers summaries as an email digest.

## Architecture

```
podcasts.yaml → [registry] → [update checker] → [caption fetcher / whisper]
                                                        ↓
                                              [timestamp parser]
                                                        ↓
                                              [caption cleaner]
                                                        ↓
                                              [chunker (by chapter)]
                                                        ↓
                                              [Claude summarizer]
                                                        ↓
                                    [formatter (timestamp deep-links)]
                                                        ↓
                                    [GCS storage] + [email digest]
```

## Modules

| Module | Location | Description |
|--------|----------|-------------|
| Registry | `poddistill/fetchers/registry.py` | Loads `podcasts.yaml`, auto-discovers RSS + YouTube sources, caches in `registry.json` |
| Update Checker | `poddistill/fetchers/update_checker.py` | Tracks last-seen episode per podcast in `state.json`; skips already-processed episodes |
| Caption Fetcher | `poddistill/fetchers/caption_fetcher.py` | Fetches auto-generated YouTube captions via yt-dlp; `get_latest_video_url()` for channel lookup |
| Whisper Transcriber | `poddistill/fetchers/whisper_transcriber.py` | **Fallback**: downloads RSS audio and transcribes via OpenAI Whisper API |
| Timestamp Parser | `poddistill/captions/timestamp_parser.py` | Parses YouTube chapter timestamps from video descriptions; generates deep-links |
| Caption Cleaner | `poddistill/captions/cleaner.py` | Strips VTT formatting (headers, timestamps, tags) and deduplicates repeated lines |
| Chunker | `poddistill/captions/chunker.py` | Splits transcript into chapter-aligned chunks using proportional character splitting |
| Claude Summarizer | `poddistill/summarizer/claude_summarizer.py` | Summarizes chunks via Claude API (raw HTTP); returns Markdown with headline + bullets + quote |
| Formatter | `poddistill/summarizer/formatter.py` | Adds YouTube timestamp deep-links to each chapter heading in the final Markdown doc |
| GCS Storage | `poddistill/storage/gcs.py` | Uploads raw/clean captions and summary to Google Cloud Storage; idempotent |
| Email Digest | `poddistill/email/digest.py` | Sends daily digest email via AgentMail API with Markdown-to-HTML conversion |

## Setup

### Prerequisites

```bash
# Install system dependencies
apt-get install ffmpeg yt-dlp  # or: pip install yt-dlp

# Install Python dependencies
pip install -r requirements.txt
```

### Configuration

```bash
cp .env.example .env
# Edit .env with your API keys
```

Add podcasts to `podcasts.yaml`:

```yaml
podcasts:
  - name: Lex Fridman Podcast
    youtube_channel: https://www.youtube.com/@lexfridman
  - name: My RSS Podcast
    rss_feed: https://example.com/feed.xml
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Claude API key for summarization |
| `OPENAI_API_KEY` | No | OpenAI Whisper API key (fallback transcription for RSS-only podcasts) |
| `GCS_BUCKET` | No | Google Cloud Storage bucket for archiving |
| `AGENTMAIL_API_KEY` | No | AgentMail API key for email digest |
| `DIGEST_RECIPIENT` | No | Email address to send the daily digest to |

### Run Locally

```bash
python main.py
```

## State Management

`state.json` tracks the last processed episode per podcast to avoid re-processing. This file is **not committed** to git and persists between runs on the host.

## Deployment

PodDistill is designed to run as a **Cloud Run Job** triggered daily by Cloud Scheduler.

### Build & Deploy

```bash
# Build and push image
docker build -t gcr.io/YOUR_PROJECT/poddistill .
docker push gcr.io/YOUR_PROJECT/poddistill

# Create Cloud Run Job
gcloud run jobs create poddistill-job \
  --image gcr.io/YOUR_PROJECT/poddistill \
  --region us-central1 \
  --set-secrets ANTHROPIC_API_KEY=anthropic-api-key:latest \
  --set-secrets AGENTMAIL_API_KEY=agentmail-api-key:latest \
  --set-env-vars DIGEST_RECIPIENT=you@example.com

# Set up Cloud Scheduler (runs daily at 8 AM UTC)
# See deploy/cloud-scheduler.yaml for full config
gcloud scheduler jobs create http poddistill-daily \
  --schedule="0 8 * * *" \
  --location=us-central1 \
  --time-zone=UTC
```

### CI/CD with Cloud Build

Push to `main` triggers `cloudbuild.yaml` which:
1. Builds the Docker image
2. Pushes to Artifact Registry
3. Updates the Cloud Run Job with the new image

### Files

- `Dockerfile` — container definition with Python 3.11, ffmpeg, yt-dlp
- `cloudbuild.yaml` — Cloud Build CI/CD pipeline
- `deploy/cloud-scheduler.yaml` — Cloud Scheduler configuration

## Linear Project

[PodDistill on Linear](https://linear.app/agent-lens/project/poddistill-6ef21499)
