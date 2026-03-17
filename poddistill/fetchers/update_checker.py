"""
Update checker — tracks last seen episode per podcast in state.json.
On each run, compares latest episode ID vs state.json and only queues
new episodes for processing.

state.json structure:
{
    "podcast_name": {
        "last_episode_id": "...",
        "last_checked": "ISO timestamp"
    }
}
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

STATE_FILE = Path("state.json")


def load_state(path: Path = STATE_FILE) -> dict:
    """Load state.json. Returns empty dict if file doesn't exist."""
    if not path.exists():
        log.debug("state.json not found, starting fresh")
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log.warning("Failed to load state.json: %s — starting fresh", e)
        return {}


def save_state(state: dict, path: Path = STATE_FILE) -> None:
    """Persist state to state.json."""
    with open(path, "w") as f:
        json.dump(state, f, indent=2)
    log.debug("State saved: %d podcasts tracked", len(state))


def is_new_episode(podcast_name: str, episode_id: str, state: dict) -> bool:
    """
    Return True if episode_id differs from the last seen episode for
    podcast_name, or if podcast_name has never been seen before.
    """
    entry = state.get(podcast_name)
    if entry is None:
        return True
    return entry.get("last_episode_id") != episode_id


def mark_processed(podcast_name: str, episode_id: str, state: dict) -> dict:
    """
    Update state to record that episode_id was successfully processed for
    podcast_name. Updates last_checked to current UTC time.
    Returns the mutated state dict.
    """
    state[podcast_name] = {
        "last_episode_id": episode_id,
        "last_checked": datetime.now(timezone.utc).isoformat(),
    }
    return state
