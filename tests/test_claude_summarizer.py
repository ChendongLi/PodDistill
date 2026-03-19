"""
Tests for poddistill/summarizer/claude_summarizer.py

Levels:
  - Unit        — prompt building (load_prompts, build_prompt)
  - Integration — mocked HTTP (_call_claude, summarize_chunks)
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from poddistill.summarizer.claude_summarizer import (
    SummarizerError,
    _call_claude,
    build_prompt,
    load_prompts,
    summarize_chunks,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MINIMAL_PROMPTS = {
    "default": {
        "system": "You are a summarizer.",
        "user_template": "Show: {show_name} ({network})\nTitle: {title}\n{custom_instructions}\n{transcript}",
    },
}


def _make_mock_response(text: str, status_code: int = 200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = {
        "content": [{"type": "text", "text": text}],
        "model": "claude-haiku-4-5-20251001",
        "role": "assistant",
    }
    resp.text = text
    return resp


# ---------------------------------------------------------------------------
# Unit tests — load_prompts
# ---------------------------------------------------------------------------


def test_load_prompts_from_real_file(tmp_path):
    p = tmp_path / "prompts.yaml"
    p.write_text(yaml.dump(MINIMAL_PROMPTS))
    result = load_prompts(p)
    assert "default" in result


def test_load_prompts_missing_file(tmp_path):
    with pytest.raises(SummarizerError, match="not found"):
        load_prompts(tmp_path / "nonexistent.yaml")


def test_load_prompts_malformed_yaml(tmp_path):
    p = tmp_path / "prompts.yaml"
    p.write_text(": bad: yaml: [\n")
    with pytest.raises(SummarizerError, match="parse"):
        load_prompts(p)


def test_load_prompts_missing_default_key(tmp_path):
    p = tmp_path / "prompts.yaml"
    p.write_text(yaml.dump({"shows": {}}))
    with pytest.raises(SummarizerError, match="default"):
        load_prompts(p)


def test_load_prompts_env_var_override(tmp_path, monkeypatch):
    p = tmp_path / "custom_prompts.yaml"
    p.write_text(yaml.dump(MINIMAL_PROMPTS))
    monkeypatch.setenv("PROMPTS_FILE", str(p))
    result = load_prompts()  # no explicit path — should read env var
    assert "default" in result


# ---------------------------------------------------------------------------
# Unit tests — build_prompt
# ---------------------------------------------------------------------------


def test_build_prompt_includes_title():
    system, user = build_prompt("My Episode", "transcript text", prompts=MINIMAL_PROMPTS)
    assert "My Episode" in user


def test_build_prompt_includes_transcript():
    system, user = build_prompt("Title", "hello world content", prompts=MINIMAL_PROMPTS)
    assert "hello world content" in user


def test_build_prompt_includes_show_name():
    system, user = build_prompt("Title", "text", show_name="Mad Money", prompts=MINIMAL_PROMPTS)
    assert "Mad Money" in user


def test_build_prompt_includes_network():
    system, user = build_prompt("Title", "text", network="CNBC", prompts=MINIMAL_PROMPTS)
    assert "CNBC" in user


def test_build_prompt_per_show_custom_instructions():
    # custom_instructions now passed directly, not looked up by show name
    system, user = build_prompt(
        "Title",
        "text",
        show_name="Mad Money",
        custom_instructions="Focus on stock picks.",
        prompts=MINIMAL_PROMPTS,
    )
    assert "stock picks" in user


def test_build_prompt_no_custom_instructions_for_unknown_show():
    # No custom_instructions -> empty string, no error
    system, user = build_prompt("Title", "text", show_name="Unknown Show", prompts=MINIMAL_PROMPTS)
    assert "Unknown Show" in user


def test_build_prompt_returns_system_string():
    system, user = build_prompt("Title", "text", prompts=MINIMAL_PROMPTS)
    assert "summarizer" in system.lower()


# ---------------------------------------------------------------------------
# Integration tests — _call_claude
# ---------------------------------------------------------------------------


def test_call_claude_success():
    with patch("poddistill.summarizer.claude_summarizer.requests.post") as mock_post:
        mock_post.return_value = _make_mock_response("## Summary\n\n- Point 1")
        result = _call_claude("system", "user message", api_key="sk-fake")
        assert "Summary" in result
        assert "Point 1" in result


def test_call_claude_passes_system_prompt():
    with patch("poddistill.summarizer.claude_summarizer.requests.post") as mock_post:
        mock_post.return_value = _make_mock_response("ok")
        _call_claude("my system prompt", "user msg", api_key="sk-fake")
        payload = mock_post.call_args[1]["json"]
        assert payload["system"] == "my system prompt"


def test_call_claude_api_error():
    with patch("poddistill.summarizer.claude_summarizer.requests.post") as mock_post:
        mock_post.return_value = _make_mock_response("Unauthorized", status_code=401)
        with pytest.raises(SummarizerError, match="401"):
            _call_claude("sys", "user", api_key="bad-key")


def test_call_claude_empty_response():
    with patch("poddistill.summarizer.claude_summarizer.requests.post") as mock_post:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"content": []}
        mock_post.return_value = resp
        with pytest.raises(SummarizerError, match="empty"):
            _call_claude("sys", "user", api_key="sk-fake")


def test_call_claude_network_error():
    with patch("poddistill.summarizer.claude_summarizer.requests.post") as mock_post:
        mock_post.side_effect = Exception("Connection refused")
        with pytest.raises(SummarizerError, match="failed"):
            _call_claude("sys", "user", api_key="sk-fake")


# ---------------------------------------------------------------------------
# Integration tests — summarize_chunks
# ---------------------------------------------------------------------------


def test_summarize_chunks_success():
    chunks = [
        {"title": "Intro", "startSeconds": 0, "text": "Welcome to the show."},
        {"title": "Main Topic", "startSeconds": 300, "text": "Today we discuss AI."},
    ]
    with patch("poddistill.summarizer.claude_summarizer.requests.post") as mock_post:
        mock_post.return_value = _make_mock_response("## Summary\n\n- Key point")
        results = summarize_chunks(chunks, api_key="sk-fake", prompts=MINIMAL_PROMPTS)
        assert len(results) == 2
        for r in results:
            assert "title" in r
            assert "startSeconds" in r
            assert "summary_md" in r


def test_summarize_chunks_passes_show_context():
    chunks = [{"title": "Ep", "startSeconds": 0, "text": "Content here."}]
    with patch("poddistill.summarizer.claude_summarizer.requests.post") as mock_post:
        mock_post.return_value = _make_mock_response("ok")
        summarize_chunks(
            chunks,
            api_key="sk-fake",
            show_name="Mad Money",
            network="CNBC",
            prompts=MINIMAL_PROMPTS,
        )
        payload = mock_post.call_args[1]["json"]
        # show_name and network should appear in the user message
        assert "Mad Money" in payload["messages"][0]["content"]
        assert "CNBC" in payload["messages"][0]["content"]


def test_summarize_chunks_per_show_instructions_injected():
    chunks = [{"title": "Ep", "startSeconds": 0, "text": "Content."}]
    with patch("poddistill.summarizer.claude_summarizer.requests.post") as mock_post:
        mock_post.return_value = _make_mock_response("ok")
        summarize_chunks(
            chunks,
            api_key="sk-fake",
            show_name="Mad Money",
            custom_instructions="Focus on stock picks.",
            prompts=MINIMAL_PROMPTS,
        )
        payload = mock_post.call_args[1]["json"]
        assert "stock picks" in payload["messages"][0]["content"]


def test_summarize_chunks_empty_text_skipped():
    chunks = [
        {"title": "Intro", "startSeconds": 0, "text": ""},
        {"title": "Main", "startSeconds": 300, "text": "Real content here."},
    ]
    with patch("poddistill.summarizer.claude_summarizer.requests.post") as mock_post:
        mock_post.return_value = _make_mock_response("## Summary\n\n- Point")
        results = summarize_chunks(chunks, api_key="sk-fake", prompts=MINIMAL_PROMPTS)
        assert len(results) == 2
        assert "No transcript" in results[0]["summary_md"]
        assert mock_post.call_count == 1  # only called for non-empty chunk


def test_summarize_chunks_preserves_metadata():
    chunks = [{"title": "Test Chapter", "startSeconds": 150, "text": "Content"}]
    with patch("poddistill.summarizer.claude_summarizer.requests.post") as mock_post:
        mock_post.return_value = _make_mock_response("## Summary")
        results = summarize_chunks(chunks, api_key="sk-fake", prompts=MINIMAL_PROMPTS)
        assert results[0]["title"] == "Test Chapter"
        assert results[0]["startSeconds"] == 150


def test_summarize_chunks_empty_list():
    results = summarize_chunks([], api_key="sk-fake", prompts=MINIMAL_PROMPTS)
    assert results == []
