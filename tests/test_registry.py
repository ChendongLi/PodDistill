"""
Tests for poddistill/fetchers/registry.py

Levels:
  - Unit        — pure logic, no I/O
  - Integration — mocked HTTP calls
  - E2E         — real API calls (marked @pytest.mark.e2e, run manually)
"""
from __future__ import annotations

import json
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from poddistill.fetchers.registry import (
    PodcastSource,
    build_registry,
    load_podcasts_yaml,
    load_registry,
    resolve_rss_via_itunes,
    resolve_youtube_channel,
    save_registry,
)


# ---------------------------------------------------------------------------
# Unit tests — PodcastSource
# ---------------------------------------------------------------------------

class TestPodcastSource:
    def test_has_source_with_rss(self):
        src = PodcastSource(name="Test", rss_url="https://example.com/feed")
        assert src.has_source()

    def test_has_source_with_youtube(self):
        src = PodcastSource(name="Test", youtube_channel_url="https://youtube.com/@test")
        assert src.has_source()

    def test_has_source_empty(self):
        src = PodcastSource(name="Test")
        assert not src.has_source()

    def test_roundtrip_serialization(self):
        src = PodcastSource(
            name="Lex Fridman Podcast",
            rss_url="https://lexfridman.com/feed",
            youtube_channel_id="UCSHZKyawb77ixDdsGog4iWA",
            youtube_channel_url="https://www.youtube.com/@lexfridman",
        )
        assert PodcastSource.from_dict(src.to_dict()).name == src.name
        assert PodcastSource.from_dict(src.to_dict()).rss_url == src.rss_url
        assert PodcastSource.from_dict(src.to_dict()).youtube_channel_id == src.youtube_channel_id

    def test_from_dict_missing_optional_fields(self):
        src = PodcastSource.from_dict({"name": "Minimal"})
        assert src.rss_url is None
        assert src.youtube_channel_id is None


# ---------------------------------------------------------------------------
# Unit tests — file I/O helpers
# ---------------------------------------------------------------------------

class TestRegistryIO:
    def test_load_podcasts_yaml(self, tmp_path):
        f = tmp_path / "podcasts.yaml"
        f.write_text(textwrap.dedent("""\
            podcasts:
              - name: Lex Fridman Podcast
              - name: My First Million
        """))
        names = load_podcasts_yaml(f)
        assert names == ["Lex Fridman Podcast", "My First Million"]

    def test_load_podcasts_yaml_empty(self, tmp_path):
        f = tmp_path / "podcasts.yaml"
        f.write_text("podcasts: []\n")
        assert load_podcasts_yaml(f) == []

    def test_load_registry_missing_file(self, tmp_path):
        assert load_registry(tmp_path / "nonexistent.json") == {}

    def test_save_and_load_registry(self, tmp_path):
        path = tmp_path / "registry.json"
        reg = {
            "Test Show": PodcastSource(
                name="Test Show",
                rss_url="https://example.com/feed",
                youtube_channel_id="UCtest",
                youtube_channel_url="https://youtube.com/channel/UCtest",
            )
        }
        save_registry(reg, path)
        loaded = load_registry(path)
        assert "Test Show" in loaded
        assert loaded["Test Show"].rss_url == "https://example.com/feed"


# ---------------------------------------------------------------------------
# Integration tests — mocked HTTP
# ---------------------------------------------------------------------------

ITUNES_RESPONSE = {
    "results": [
        {
            "collectionName": "Lex Fridman Podcast",
            "feedUrl": "https://lexfridman.com/feed/podcast/",
        }
    ]
}

YOUTUBE_HTML_SNIPPET = (
    '"channelId":"UCSHZKyawb77ixDdsGog4iWA"'
    '"canonicalBaseUrl":"/@lexfridman"'
)


class TestResolveRSS:
    @patch("poddistill.fetchers.registry.requests.get")
    def test_exact_name_match(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = ITUNES_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        url = resolve_rss_via_itunes("Lex Fridman Podcast")
        assert url == "https://lexfridman.com/feed/podcast/"

    @patch("poddistill.fetchers.registry.requests.get")
    def test_falls_back_to_first_result(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "results": [
                {"collectionName": "Something Else", "feedUrl": "https://first.com/feed"}
            ]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        url = resolve_rss_via_itunes("Lex Fridman Podcast")
        assert url == "https://first.com/feed"

    @patch("poddistill.fetchers.registry.requests.get")
    def test_no_results_returns_none(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"results": []}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        assert resolve_rss_via_itunes("Unknown Podcast") is None

    @patch("poddistill.fetchers.registry.requests.get")
    def test_network_error_returns_none(self, mock_get):
        mock_get.side_effect = Exception("network error")
        assert resolve_rss_via_itunes("Lex Fridman Podcast") is None


class TestResolveYouTube:
    @patch("poddistill.fetchers.registry.requests.get")
    def test_extracts_channel_id_and_url(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.text = YOUTUBE_HTML_SNIPPET
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        channel_id, channel_url = resolve_youtube_channel("Lex Fridman Podcast")
        assert channel_id == "UCSHZKyawb77ixDdsGog4iWA"
        assert channel_url == "https://www.youtube.com/@lexfridman"

    @patch("poddistill.fetchers.registry.requests.get")
    def test_no_channel_returns_none(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.text = "<html>nothing here</html>"
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        channel_id, channel_url = resolve_youtube_channel("Unknown Show")
        assert channel_id is None
        assert channel_url is None

    @patch("poddistill.fetchers.registry.requests.get")
    def test_network_error_returns_none(self, mock_get):
        mock_get.side_effect = Exception("timeout")
        channel_id, channel_url = resolve_youtube_channel("Lex Fridman Podcast")
        assert channel_id is None
        assert channel_url is None


class TestBuildRegistry:
    @patch("poddistill.fetchers.registry.resolve_youtube_channel")
    @patch("poddistill.fetchers.registry.resolve_rss_via_itunes")
    def test_discovers_new_podcasts(self, mock_rss, mock_yt, tmp_path):
        mock_rss.return_value = "https://example.com/feed"
        mock_yt.return_value = ("UCtest123456789012345678", "https://youtube.com/@test")

        podcasts_file = tmp_path / "podcasts.yaml"
        podcasts_file.write_text("podcasts:\n  - name: Test Podcast\n")
        registry_file = tmp_path / "registry.json"

        reg = build_registry(podcasts_file, registry_file, discover_delay=0)
        assert "Test Podcast" in reg
        assert reg["Test Podcast"].rss_url == "https://example.com/feed"
        assert registry_file.exists()

    @patch("poddistill.fetchers.registry.resolve_youtube_channel")
    @patch("poddistill.fetchers.registry.resolve_rss_via_itunes")
    def test_skips_already_resolved(self, mock_rss, mock_yt, tmp_path):
        podcasts_file = tmp_path / "podcasts.yaml"
        podcasts_file.write_text("podcasts:\n  - name: Cached Podcast\n")
        registry_file = tmp_path / "registry.json"
        registry_file.write_text(json.dumps({
            "Cached Podcast": {
                "name": "Cached Podcast",
                "rss_url": "https://cached.com/feed",
                "youtube_channel_id": None,
                "youtube_channel_url": None,
            }
        }))

        reg = build_registry(podcasts_file, registry_file, discover_delay=0)
        mock_rss.assert_not_called()
        mock_yt.assert_not_called()
        assert reg["Cached Podcast"].rss_url == "https://cached.com/feed"


# ---------------------------------------------------------------------------
# E2E tests — real API calls (run with: pytest -m e2e)
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestE2EResolution:
    def test_itunes_resolves_lex_fridman(self):
        url = resolve_rss_via_itunes("Lex Fridman Podcast")
        assert url is not None
        assert url.startswith("http")

    def test_itunes_resolves_my_first_million(self):
        url = resolve_rss_via_itunes("My First Million")
        assert url is not None
        assert url.startswith("http")

    def test_youtube_resolves_lex_fridman(self):
        channel_id, channel_url = resolve_youtube_channel("Lex Fridman Podcast")
        assert channel_id is not None
        assert channel_id.startswith("UC")
        assert channel_url is not None

    def test_full_build_registry_e2e(self, tmp_path):
        podcasts_file = tmp_path / "podcasts.yaml"
        podcasts_file.write_text(
            "podcasts:\n  - name: Lex Fridman Podcast\n  - name: Huberman Lab\n"
        )
        registry_file = tmp_path / "registry.json"

        reg = build_registry(podcasts_file, registry_file, discover_delay=1.0)
        assert len(reg) == 2
        for name, src in reg.items():
            assert src.has_source(), f"{name!r} has no source resolved"
