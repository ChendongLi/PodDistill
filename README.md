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

## Setup

```bash
cp .env.example .env
# fill in API keys
pip install -r requirements.txt
python main.py
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Claude API key for summarization |
| `OPENAI_API_KEY` | No | OpenAI Whisper API key (fallback transcription) |
| `GCS_BUCKET` | No | Google Cloud Storage bucket for archiving |
| `AGENTMAIL_API_KEY` | No | AgentMail key for email digest |
| `DIGEST_RECIPIENT` | No | Email address to send digest to |

## Config

Add podcasts to `podcasts.yaml`. Sources (RSS feed + YouTube channel) are auto-resolved on first run and cached in `registry.json`.

## State

`state.json` tracks the last processed episode per podcast. This file is **not committed** — it persists between runs on the host.

## Deployment

Runs as a Cloud Run Job, triggered daily at 8am UTC via Cloud Scheduler. Secrets managed via GCP Secret Manager.

## Linear Project

[PodDistill on Linear](https://linear.app/agent-lens/project/poddistill-6ef21499)
