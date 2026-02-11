"""
Supabase Storage service — upload, download, signed URLs, delete.
All PDF file I/O goes through this module.
"""

import os
import tempfile
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)

RESUMES_BUCKET = "resumes"
TAILORED_BUCKET = "tailored"

# Lazy-init Supabase client (service role for full bucket access)
_supabase_client = None


def _get_supabase():
    """Get or create the Supabase client using the service key."""
    global _supabase_client
    if _supabase_client is None:
        from supabase import create_client
        url = os.getenv("SUPABASE_URL", "")
        service_key = os.getenv("SUPABASE_SERVICE_KEY", "")
        if not url or not service_key:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set for storage operations"
            )
        _supabase_client = create_client(url, service_key)
    return _supabase_client


def is_local_path(path: str) -> bool:
    """Check if a file_path is a local filesystem path (legacy) vs Supabase storage key."""
    return path.startswith("/") or path.startswith("\\") or (len(path) > 1 and path[1] == ":")


async def upload_file(
    bucket: str,
    storage_path: str,
    file_bytes: bytes,
    content_type: str = "application/pdf",
) -> str:
    """Upload file bytes to Supabase Storage. Returns the storage_path."""
    client = _get_supabase()
    client.storage.from_(bucket).upload(
        path=storage_path,
        file=file_bytes,
        file_options={"content-type": content_type, "upsert": "true"},
    )
    logger.info(f"Uploaded {len(file_bytes)} bytes to {bucket}/{storage_path}")
    return storage_path


async def download_file(bucket: str, storage_path: str) -> bytes:
    """Download file bytes from Supabase Storage."""
    client = _get_supabase()
    data = client.storage.from_(bucket).download(storage_path)
    logger.info(f"Downloaded {len(data)} bytes from {bucket}/{storage_path}")
    return data


@contextmanager
def download_to_tempfile(bucket: str, storage_path: str, suffix: str = ".pdf"):
    """
    Context manager: download from Supabase to a temp file, yield the path,
    then clean up. Use this for PyMuPDF operations that need a local file.

    Usage:
        with download_to_tempfile("resumes", path) as tmp_path:
            doc = fitz.open(tmp_path)
    """
    data = _get_supabase().storage.from_(bucket).download(storage_path)
    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    try:
        os.write(fd, data)
        os.close(fd)
        logger.info(f"Downloaded {bucket}/{storage_path} to temp {tmp_path}")
        yield tmp_path
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def get_signed_url(bucket: str, storage_path: str, expires_in: int = 3600) -> str:
    """Get a signed URL for direct browser download (expires in N seconds)."""
    client = _get_supabase()
    result = client.storage.from_(bucket).create_signed_url(storage_path, expires_in)
    return result["signedURL"]


async def delete_file(bucket: str, storage_path: str) -> None:
    """Delete a file from Supabase Storage."""
    client = _get_supabase()
    client.storage.from_(bucket).remove([storage_path])
    logger.info(f"Deleted {bucket}/{storage_path}")


def ensure_buckets_exist():
    """Create storage buckets if they don't exist. Call once at startup."""
    try:
        client = _get_supabase()
        existing = [b.name for b in client.storage.list_buckets()]
        for bucket_name in [RESUMES_BUCKET, TAILORED_BUCKET]:
            if bucket_name not in existing:
                client.storage.create_bucket(
                    bucket_name,
                    options={"public": False},
                )
                logger.info(f"Created storage bucket: {bucket_name}")
            else:
                logger.info(f"Storage bucket exists: {bucket_name}")
    except Exception as e:
        logger.error(f"Failed to ensure storage buckets: {e}")
