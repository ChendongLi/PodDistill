"""
Tests for poddistill/fetchers/update_checker.py

Levels:
  - Unit        — pure logic, no I/O
  - Integration — file I/O with tmp_path
"""
from __future__ import annotations

import json
import sys
import os
from pathlib import Path

# Allow running directly with python3 (no pytest install needed)
sys.path.insert(0, str(Path(__file__).parent.parent))

from poddistill.fetchers.update_checker import (
    is_new_episode,
    load_state,
    mark_processed,
    save_state,
)


# ---------------------------------------------------------------------------
# Unit tests — pure logic
# ---------------------------------------------------------------------------

def test_is_new_episode_unknown_podcast():
    state = {}
    assert is_new_episode("New Show", "ep-001", state) is True


def test_is_new_episode_different_episode():
    state = {"My Podcast": {"last_episode_id": "ep-001", "last_checked": "2024-01-01T00:00:00+00:00"}}
    assert is_new_episode("My Podcast", "ep-002", state) is True


def test_is_new_episode_same_episode():
    state = {"My Podcast": {"last_episode_id": "ep-001", "last_checked": "2024-01-01T00:00:00+00:00"}}
    assert is_new_episode("My Podcast", "ep-001", state) is False


def test_mark_processed_adds_entry():
    state = {}
    result = mark_processed("My Podcast", "ep-001", state)
    assert "My Podcast" in result
    assert result["My Podcast"]["last_episode_id"] == "ep-001"
    assert "last_checked" in result["My Podcast"]


def test_mark_processed_updates_existing():
    state = {"My Podcast": {"last_episode_id": "ep-001", "last_checked": "2024-01-01T00:00:00+00:00"}}
    result = mark_processed("My Podcast", "ep-002", state)
    assert result["My Podcast"]["last_episode_id"] == "ep-002"


def test_mark_processed_returns_state():
    state = {}
    result = mark_processed("Show", "ep-1", state)
    assert result is state  # mutates and returns same dict


def test_mark_processed_last_checked_is_iso():
    state = {}
    mark_processed("Show", "ep-1", state)
    ts = state["Show"]["last_checked"]
    # Should be a valid ISO timestamp with UTC offset
    assert "T" in ts
    assert "+" in ts or "Z" in ts


# ---------------------------------------------------------------------------
# Integration tests — file I/O
# ---------------------------------------------------------------------------

def test_load_state_missing_file(tmp_path):
    result = load_state(tmp_path / "nonexistent.json")
    assert result == {}


def test_load_state_valid_file(tmp_path):
    p = tmp_path / "state.json"
    p.write_text(json.dumps({"Show A": {"last_episode_id": "ep-5", "last_checked": "2024-01-01T00:00:00+00:00"}}))
    state = load_state(p)
    assert state["Show A"]["last_episode_id"] == "ep-5"


def test_load_state_corrupt_file(tmp_path):
    p = tmp_path / "state.json"
    p.write_text("not valid json {{{{")
    result = load_state(p)
    assert result == {}


def test_save_and_load_roundtrip(tmp_path):
    p = tmp_path / "state.json"
    state = {"Podcast X": {"last_episode_id": "ep-99", "last_checked": "2024-06-01T12:00:00+00:00"}}
    save_state(state, p)
    loaded = load_state(p)
    assert loaded == state


def test_full_workflow(tmp_path):
    """Simulate a full update-check cycle."""
    p = tmp_path / "state.json"
    state = load_state(p)

    # First run — no state, all episodes are new
    assert is_new_episode("Lex Fridman", "ep-100", state) is True

    # After processing
    mark_processed("Lex Fridman", "ep-100", state)
    save_state(state, p)

    # Reload and check — same episode is NOT new
    state2 = load_state(p)
    assert is_new_episode("Lex Fridman", "ep-100", state2) is False

    # New episode IS new
    assert is_new_episode("Lex Fridman", "ep-101", state2) is True


# ---------------------------------------------------------------------------
# Run directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import traceback
    tests = [
        test_is_new_episode_unknown_podcast,
        test_is_new_episode_different_episode,
        test_is_new_episode_same_episode,
        test_mark_processed_adds_entry,
        test_mark_processed_updates_existing,
        test_mark_processed_returns_state,
        test_mark_processed_last_checked_is_iso,
    ]
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        file_tests = [
            lambda: test_load_state_missing_file(tmp_path),
            lambda: test_load_state_valid_file(tmp_path),
            lambda: test_load_state_corrupt_file(tmp_path),
            lambda: test_save_and_load_roundtrip(tmp_path),
            lambda: test_full_workflow(tmp_path),
        ]
        all_tests = tests + file_tests
        passed = 0
        failed = 0
        for t in all_tests:
            name = getattr(t, "__name__", repr(t))
            try:
                t()
                print(f"  PASS  {name}")
                passed += 1
            except Exception:
                print(f"  FAIL  {name}")
                traceback.print_exc()
                failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
