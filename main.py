#!/usr/bin/env python3
"""
PodDistill — Daily podcast summarizer with timestamp deep-links.
Fetches new episodes, transcribes/captions, summarizes via Claude,
and sends an email digest via AgentMail.
"""
import logging
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def main():
    log.info("PodDistill starting...")
    # TODO: wire up pipeline
    # 1. Load registry (AGE-29)
    # 2. Check for new episodes (AGE-30)
    # 3. Fetch captions via yt-dlp (AGE-31) or Whisper (AGE-32)
    # 4. Parse timestamps from description (AGE-38)
    # 5. Clean captions (AGE-33)
    # 6. Summarize with Claude (AGE-34)
    # 7. Generate timestamp deep-links (AGE-39, AGE-40)
    # 8. Upload to GCS (AGE-35)
    # 9. Send email digest (AGE-42)
    log.info("Done.")


if __name__ == "__main__":
    main()
