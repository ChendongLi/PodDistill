"""
Tests for poddistill/summarizer/claude_summarizer.py

Levels:
  - Unit        — prompt building, output parsing
  - Integration — mocked HTTP
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from poddistill.summarizer.claude_summarizer import (
    SummarizerError,
    _build_prompt,
    _call_claude,
    summarize_chunks,
)


# ---------------------------------------------------------------------------
# Unit tests — prompt building
# ---------------------------------------------------------------------------

def test_build_prompt_includes_title():
    prompt = _build_prompt("Introduction", "Hello world text")
    assert "Introduction" in prompt

def test_build_prompt_includes_text():
    prompt = _build_prompt("Intro", "Hello world text")
    assert "Hello world text" in prompt

def test_build_prompt_includes_instructions():
    prompt = _build_prompt("Test", "text")
    assert "headline" in prompt.lower()
    assert "bullet" in prompt.lower()

def test_build_prompt_includes_markdown_instruction():
    prompt = _build_prompt("Test", "text")
    assert "markdown" in prompt.lower()


# ---------------------------------------------------------------------------
# Integration tests — mocked HTTP
# ---------------------------------------------------------------------------

def _make_mock_response(text: str, status_code: int = 200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = {
        "content": [{"type": "text", "text": text}],
        "model": "claude-3-5-haiku-20241022",
        "role": "assistant",
    }
    resp.text = text
    return resp


def test_call_claude_success():
    with patch("poddistill.summarizer.claude_summarizer.requests.post") as mock_post:
        mock_post.return_value = _make_mock_response("## Summary\n\n- Point 1")
        result = _call_claude("Summarize this", api_key="sk-fake")
        assert "Summary" in result
        assert "Point 1" in result


def test_call_claude_api_error():
    with patch("poddistill.summarizer.claude_summarizer.requests.post") as mock_post:
        mock_post.return_value = _make_mock_response("Unauthorized", status_code=401)
        try:
            _call_claude("Summarize this", api_key="bad-key")
            assert False, "Should raise SummarizerError"
        except SummarizerError as e:
            assert "401" in str(e)


def test_call_claude_empty_response():
    with patch("poddistill.summarizer.claude_summarizer.requests.post") as mock_post:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"content": []}
        mock_post.return_value = resp
        try:
            _call_claude("Summarize this", api_key="sk-fake")
            assert False, "Should raise SummarizerError"
        except SummarizerError as e:
            assert "empty" in str(e).lower()


def test_call_claude_network_error():
    with patch("poddistill.summarizer.claude_summarizer.requests.post") as mock_post:
        mock_post.side_effect = Exception("Connection refused")
        try:
            _call_claude("Summarize this", api_key="sk-fake")
            assert False, "Should raise SummarizerError"
        except SummarizerError as e:
            assert "failed" in str(e).lower()


def test_summarize_chunks_success():
    chunks = [
        {"title": "Intro", "startSeconds": 0, "text": "Welcome to the show."},
        {"title": "Main Topic", "startSeconds": 300, "text": "Today we discuss AI."},
    ]
    with patch("poddistill.summarizer.claude_summarizer.requests.post") as mock_post:
        mock_post.return_value = _make_mock_response("## Summary\n\n- Key point here")
        results = summarize_chunks(chunks, api_key="sk-fake")
        assert len(results) == 2
        for r in results:
            assert "title" in r
            assert "startSeconds" in r
            assert "summary_md" in r
            assert "Summary" in r["summary_md"]


def test_summarize_chunks_empty_text_skipped():
    chunks = [
        {"title": "Intro", "startSeconds": 0, "text": ""},
        {"title": "Main", "startSeconds": 300, "text": "Real content here."},
    ]
    with patch("poddistill.summarizer.claude_summarizer.requests.post") as mock_post:
        mock_post.return_value = _make_mock_response("## Summary\n\n- Point")
        results = summarize_chunks(chunks, api_key="sk-fake")
        assert len(results) == 2
        # Empty chunk gets a placeholder
        assert "No transcript" in results[0]["summary_md"] or results[0]["summary_md"] != ""
        # API called only once (for the non-empty chunk)
        assert mock_post.call_count == 1


def test_summarize_chunks_preserves_metadata():
    chunks = [{"title": "Test Chapter", "startSeconds": 150, "text": "Content"}]
    with patch("poddistill.summarizer.claude_summarizer.requests.post") as mock_post:
        mock_post.return_value = _make_mock_response("## Summary")
        results = summarize_chunks(chunks, api_key="sk-fake")
        assert results[0]["title"] == "Test Chapter"
        assert results[0]["startSeconds"] == 150


def test_summarize_chunks_empty_list():
    results = summarize_chunks([], api_key="sk-fake")
    assert results == []


# ---------------------------------------------------------------------------
# Run directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        test_build_prompt_includes_title,
        test_build_prompt_includes_text,
        test_build_prompt_includes_instructions,
        test_build_prompt_includes_markdown_instruction,
        test_call_claude_success,
        test_call_claude_api_error,
        test_call_claude_empty_response,
        test_call_claude_network_error,
        test_summarize_chunks_success,
        test_summarize_chunks_empty_text_skipped,
        test_summarize_chunks_preserves_metadata,
        test_summarize_chunks_empty_list,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception:
            print(f"  FAIL  {t.__name__}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
