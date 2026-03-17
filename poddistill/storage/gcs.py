"""
GCS storage layer — upload summarized content to Google Cloud Storage.

Uses the google-cloud-storage SDK with import guard so the rest of the
pipeline works without GCS installed.

Usage:
    from poddistill.storage.gcs import upload_to_gcs, episode_gcs_paths

    paths = episode_gcs_paths("2024-01-15", "lex-fridman", "dQw4w9WgXcQ")
    uri = upload_to_gcs(
        bucket_name="my-bucket",
        blob_path=paths["summary"],
        content="# Summary\\n...",
        content_type="text/markdown",
    )
    # Returns: "gs://my-bucket/2024-01-15/lex-fridman/dQw4w9WgXcQ/summary.md"
"""
from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger(__name__)


class StorageError(Exception):
    """Raised when GCS operations fail (SDK not available or upload error)."""


try:
    from google.cloud import storage as gcs_lib  # type: ignore
    _GCS_AVAILABLE = True
except ImportError:
    _GCS_AVAILABLE = False
    gcs_lib = None  # type: ignore


def upload_to_gcs(
    bucket_name: str,
    blob_path: str,
    content: str,
    content_type: str = "text/plain",
) -> str:
    """
    Upload text content to Google Cloud Storage.

    Idempotent: if the blob already exists, skips the upload and returns
    the existing gs:// URI.

    Args:
        bucket_name: GCS bucket name (e.g. "my-poddistill-bucket")
        blob_path:   Path within bucket (e.g. "2024-01-15/lex-fridman/ep/summary.md")
        content:     Text content to upload
        content_type: MIME type (default: "text/plain")

    Returns:
        gs:// URI of the uploaded blob, e.g.
        "gs://my-poddistill-bucket/2024-01-15/lex-fridman/ep/summary.md"

    Raises:
        StorageError: If google-cloud-storage is not installed or upload fails.
    """
    if not _GCS_AVAILABLE:
        raise StorageError(
            "google-cloud-storage is not installed. "
            "Install with: pip install google-cloud-storage"
        )

    try:
        client = gcs_lib.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_path)

        # Idempotency check: skip if blob already exists
        if blob.exists():
            log.info("Blob already exists, skipping upload: gs://%s/%s", bucket_name, blob_path)
            return f"gs://{bucket_name}/{blob_path}"

        blob.upload_from_string(content, content_type=content_type)
        uri = f"gs://{bucket_name}/{blob_path}"
        log.info("Uploaded to %s", uri)
        return uri

    except StorageError:
        raise
    except Exception as e:
        raise StorageError(f"GCS upload failed for gs://{bucket_name}/{blob_path}: {e}") from e


def episode_gcs_paths(date_str: str, podcast_slug: str, video_id: str) -> dict:
    """
    Generate standard GCS blob paths for all episode artifacts.

    Args:
        date_str:     ISO date string (e.g. "2024-01-15")
        podcast_slug: URL-friendly podcast name (e.g. "lex-fridman")
        video_id:     YouTube video ID or episode identifier

    Returns:
        Dict with keys:
            - raw_captions:   path for raw VTT file
            - clean_captions: path for cleaned plain-text captions
            - summary:        path for final Markdown summary

    Example:
        >>> episode_gcs_paths("2024-01-15", "lex-fridman", "dQw4w9WgXcQ")
        {
            "raw_captions":   "2024-01-15/lex-fridman/dQw4w9WgXcQ/captions.vtt",
            "clean_captions": "2024-01-15/lex-fridman/dQw4w9WgXcQ/captions_clean.txt",
            "summary":        "2024-01-15/lex-fridman/dQw4w9WgXcQ/summary.md",
        }
    """
    base = f"{date_str}/{podcast_slug}/{video_id}"
    return {
        "raw_captions":   f"{base}/captions.vtt",
        "clean_captions": f"{base}/captions_clean.txt",
        "summary":        f"{base}/summary.md",
    }
