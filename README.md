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
                                              [Claude summarizer]
                                                        ↓
                                    [GCS storage] + [email digest]
```

## Setup

```bash
cp .env.example .env
# fill in API keys
pip install -r requirements.txt
python main.py
```

## Config

Add podcasts to `podcasts.yaml`. Sources (RSS feed + YouTube channel) are auto-resolved on first run and cached in `registry.json`.

## Deployment

Runs as a Cloud Run Job, triggered daily at 8am UTC via Cloud Scheduler. Secrets managed via GCP Secret Manager.

## Linear Project

[PodDistill on Linear](https://linear.app/agent-lens/project/poddistill-6ef21499)
