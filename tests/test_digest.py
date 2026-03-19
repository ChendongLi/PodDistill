"""
Tests for poddistill/email/digest.py

Levels:
  - Unit        — _md_to_html, _build_email_body
  - Integration — mocked HTTP for send_digest
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from poddistill.email.digest import (
    DigestError,
    _build_email_body,
    _md_to_html,
    send_digest,
)

# ---------------------------------------------------------------------------
# Unit tests — _md_to_html
# ---------------------------------------------------------------------------


def test_md_to_html_heading():
    html = _md_to_html("## Hello World")
    assert "Hello World" in html and "<h2" in html


def test_md_to_html_bullet_list():
    html = _md_to_html("- Point 1\n- Point 2")
    assert "<ul" in html
    assert "Point 1" in html
    assert "Point 2" in html
    assert "</ul>" in html


def test_md_to_html_bold():
    html = _md_to_html("This is **bold** text")
    assert "<strong>bold</strong>" in html


def test_md_to_html_italic():
    html = _md_to_html("This is *italic* text")
    assert "<em>italic</em>" in html


def test_md_to_html_link():
    html = _md_to_html("[Click here](https://example.com)")
    assert 'href="https://example.com"' in html
    assert ">Click here<" in html


def test_md_to_html_blockquote():
    html = _md_to_html("> Notable quote here")
    assert "Notable quote here" in html
    assert "<blockquote" in html


def test_md_to_html_hr():
    html = _md_to_html("---")
    assert "<hr" in html


def test_md_to_html_empty():
    assert _md_to_html("") == ""


# ---------------------------------------------------------------------------
# Unit tests — _build_email_body
# ---------------------------------------------------------------------------


def test_build_email_body_includes_podcast_name():
    episodes = [
        {
            "podcast_name": "Lex Fridman",
            "episode_title": "Ep 400",
            "video_id": "abc",
            "summary_md": "Summary",
        }
    ]
    text, html = _build_email_body(episodes, "March 19, 2026")
    assert "Lex Fridman" in text
    assert "Lex Fridman" in html


def test_build_email_body_includes_youtube_link():
    episodes = [
        {
            "podcast_name": "Pod",
            "episode_title": "Ep 1",
            "video_id": "dQw4w9WgXcQ",
            "summary_md": "",
        }
    ]
    text, html = _build_email_body(episodes, "March 19, 2026")
    assert "dQw4w9WgXcQ" in text
    assert "dQw4w9WgXcQ" in html


def test_build_email_body_html_structure():
    episodes = [
        {
            "podcast_name": "Pod",
            "episode_title": "Ep 1",
            "video_id": "vid",
            "summary_md": "## Point\n- Bullet",
        }
    ]
    _, html = _build_email_body(episodes, "March 19, 2026")
    assert "<html" in html
    assert "</html>" in html
    assert "<body" in html


def test_build_email_body_no_video_id():
    episodes = [
        {"podcast_name": "Pod", "episode_title": "Ep 1", "video_id": "", "summary_md": "Text"}
    ]
    text, html = _build_email_body(episodes, "March 19, 2026")
    assert "Text" in text


# ---------------------------------------------------------------------------
# Integration tests — mocked HTTP
# ---------------------------------------------------------------------------


def _make_episodes():
    return [
        {
            "podcast_name": "Lex Fridman Podcast",
            "episode_title": "AI Discussion #400",
            "video_id": "dQw4w9WgXcQ",
            "summary_md": "## Summary\n\n- Key insight 1\n- Key insight 2",
        }
    ]


def test_send_digest_empty_episodes_returns_false():
    result = send_digest([], "user@example.com", "fake-key")
    assert result is False


def test_send_digest_success():
    with patch("poddistill.email.digest.requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_post.return_value = mock_resp

        result = send_digest(_make_episodes(), "user@example.com", "fake-key")
        assert result is True
        mock_post.assert_called_once()


def test_send_digest_uses_correct_url():
    with patch("poddistill.email.digest.requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        send_digest(
            _make_episodes(), "user@example.com", "fake-key", inbox="agentlens@agentmail.to"
        )
        call_args = mock_post.call_args
        url = call_args[0][0] if call_args[0] else call_args[1].get("url", "")
        assert "agentlens@agentmail.to" in url or "agentmail.to" in url


def test_send_digest_subject_includes_date():
    with patch("poddistill.email.digest.requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        send_digest(_make_episodes(), "user@example.com", "fake-key", date_str="January 15, 2024")
        call_kwargs = mock_post.call_args[1]
        payload = call_kwargs.get("json", {})
        assert "January 15, 2024" in payload.get("subject", "")


def test_send_digest_api_error_raises():
    with patch("poddistill.email.digest.requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = "Forbidden"
        mock_post.return_value = mock_resp

        try:
            send_digest(_make_episodes(), "user@example.com", "bad-key")
            raise AssertionError("Should raise DigestError")
        except DigestError as e:
            assert "403" in str(e)


def test_send_digest_network_error_raises():
    with patch("poddistill.email.digest.requests.post") as mock_post:
        mock_post.side_effect = Exception("Network error")

        try:
            send_digest(_make_episodes(), "user@example.com", "key")
            raise AssertionError("Should raise DigestError")
        except DigestError as e:
            assert "failed" in str(e).lower()


def test_send_digest_includes_recipient():
    with patch("poddistill.email.digest.requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        send_digest(_make_episodes(), "test@example.com", "key")
        call_kwargs = mock_post.call_args[1]
        payload = call_kwargs.get("json", {})
        assert "test@example.com" in payload.get("to", [])


# ---------------------------------------------------------------------------
# Run directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        test_md_to_html_heading,
        test_md_to_html_bullet_list,
        test_md_to_html_bold,
        test_md_to_html_italic,
        test_md_to_html_link,
        test_md_to_html_blockquote,
        test_md_to_html_hr,
        test_md_to_html_empty,
        test_build_email_body_includes_podcast_name,
        test_build_email_body_includes_youtube_link,
        test_build_email_body_html_structure,
        test_build_email_body_no_video_id,
        test_send_digest_empty_episodes_returns_false,
        test_send_digest_success,
        test_send_digest_uses_correct_url,
        test_send_digest_subject_includes_date,
        test_send_digest_api_error_raises,
        test_send_digest_network_error_raises,
        test_send_digest_includes_recipient,
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
