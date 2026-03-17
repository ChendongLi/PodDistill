# PodDistill — Cloud Run Job Dockerfile
#
# Environment variables (set via Cloud Run / Secret Manager):
#   ANTHROPIC_API_KEY   — Claude API key (required)
#   OPENAI_API_KEY      — OpenAI Whisper API key (optional, for RSS-only fallback)
#   GCS_BUCKET          — Google Cloud Storage bucket name (optional)
#   AGENTMAIL_API_KEY   — AgentMail API key for email digest (optional)
#   DIGEST_RECIPIENT    — Email address for the daily digest (optional)
#   PODCASTS_CONFIG     — Path to podcasts.yaml (default: /app/podcasts.yaml)

FROM python:3.11-slim

# Install system dependencies
# yt-dlp requires ffmpeg for some audio processing
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        yt-dlp \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Run the pipeline
CMD ["python", "main.py"]
