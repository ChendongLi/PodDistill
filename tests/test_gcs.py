"""
Tests for poddistill/storage/gcs.py

Levels:
  - Unit        — episode_gcs_paths pure logic
  - Integration — mocked GCS SDK
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from poddistill.storage.gcs import (
    StorageError,
    episode_gcs_paths,
    upload_to_gcs,
)


# ---------------------------------------------------------------------------
# Unit tests — episode_gcs_paths
# ---------------------------------------------------------------------------

def test_gcs_paths_structure():
    paths = episode_gcs_paths("2024-01-15", "lex-fridman", "dQw4w9WgXcQ")
    assert "raw_captions" in paths
    assert "clean_captions" in paths
    assert "summary" in paths

def test_gcs_paths_contain_date():
    paths = episode_gcs_paths("2024-01-15", "podcast", "vid123")
    for path in paths.values():
        assert "2024-01-15" in path

def test_gcs_paths_contain_slug():
    paths = episode_gcs_paths("2024-01-15", "my-podcast", "vid123")
    for path in paths.values():
        assert "my-podcast" in path

def test_gcs_paths_contain_video_id():
    paths = episode_gcs_paths("2024-01-15", "podcast", "abc999")
    for path in paths.values():
        assert "abc999" in path

def test_gcs_paths_file_extensions():
    paths = episode_gcs_paths("2024-01-15", "pod", "vid")
    assert paths["raw_captions"].endswith(".vtt")
    assert paths["clean_captions"].endswith(".txt")
    assert paths["summary"].endswith(".md")

def test_gcs_paths_base_structure():
    paths = episode_gcs_paths("2024-01-15", "lex-fridman", "dQw4w9WgXcQ")
    expected_base = "2024-01-15/lex-fridman/dQw4w9WgXcQ"
    for path in paths.values():
        assert path.startswith(expected_base)


# ---------------------------------------------------------------------------
# Integration tests — mocked GCS SDK
# ---------------------------------------------------------------------------

def _make_mock_client(blob_exists=False):
    """Create a mock GCS client."""
    mock_blob = MagicMock()
    mock_blob.exists.return_value = blob_exists

    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob

    mock_client = MagicMock()
    mock_client.bucket.return_value = mock_bucket

    return mock_client, mock_bucket, mock_blob


def test_upload_to_gcs_success():
    mock_client, mock_bucket, mock_blob = _make_mock_client(blob_exists=False)

    with patch("poddistill.storage.gcs._GCS_AVAILABLE", True), \
         patch("poddistill.storage.gcs.gcs_lib") as mock_gcs_lib:

        mock_gcs_lib.Client.return_value = mock_client

        uri = upload_to_gcs("my-bucket", "path/to/file.md", "# Content", "text/markdown")
        assert uri == "gs://my-bucket/path/to/file.md"
        mock_blob.upload_from_string.assert_called_once()


def test_upload_to_gcs_idempotent():
    """If blob already exists, should skip upload and return URI."""
    mock_client, mock_bucket, mock_blob = _make_mock_client(blob_exists=True)

    with patch("poddistill.storage.gcs._GCS_AVAILABLE", True), \
         patch("poddistill.storage.gcs.gcs_lib") as mock_gcs_lib:

        mock_gcs_lib.Client.return_value = mock_client

        uri = upload_to_gcs("my-bucket", "path/to/file.md", "# Content")
        assert uri == "gs://my-bucket/path/to/file.md"
        # Should NOT have uploaded since blob exists
        mock_blob.upload_from_string.assert_not_called()


def test_upload_to_gcs_not_available():
    """When GCS SDK not installed, raise StorageError."""
    with patch("poddistill.storage.gcs._GCS_AVAILABLE", False):
        try:
            upload_to_gcs("bucket", "path", "content")
            assert False, "Should raise StorageError"
        except StorageError as e:
            assert "not installed" in str(e).lower() or "google-cloud-storage" in str(e)


def test_upload_to_gcs_upload_fails():
    """When GCS upload fails, raise StorageError."""
    mock_client, mock_bucket, mock_blob = _make_mock_client(blob_exists=False)
    mock_blob.upload_from_string.side_effect = Exception("Network error")

    with patch("poddistill.storage.gcs._GCS_AVAILABLE", True), \
         patch("poddistill.storage.gcs.gcs_lib") as mock_gcs_lib:

        mock_gcs_lib.Client.return_value = mock_client

        try:
            upload_to_gcs("bucket", "path", "content")
            assert False, "Should raise StorageError"
        except StorageError as e:
            assert "gcs upload failed" in str(e).lower()


def test_upload_returns_gs_uri():
    mock_client, mock_bucket, mock_blob = _make_mock_client()

    with patch("poddistill.storage.gcs._GCS_AVAILABLE", True), \
         patch("poddistill.storage.gcs.gcs_lib") as mock_gcs_lib:

        mock_gcs_lib.Client.return_value = mock_client
        uri = upload_to_gcs("test-bucket", "folder/file.txt", "text")
        assert uri.startswith("gs://")
        assert "test-bucket" in uri
        assert "folder/file.txt" in uri


# ---------------------------------------------------------------------------
# Run directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        test_gcs_paths_structure,
        test_gcs_paths_contain_date,
        test_gcs_paths_contain_slug,
        test_gcs_paths_contain_video_id,
        test_gcs_paths_file_extensions,
        test_gcs_paths_base_structure,
        test_upload_to_gcs_success,
        test_upload_to_gcs_idempotent,
        test_upload_to_gcs_not_available,
        test_upload_to_gcs_upload_fails,
        test_upload_returns_gs_uri,
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
