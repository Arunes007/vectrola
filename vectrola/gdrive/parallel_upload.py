"""
Parallel upload worker for Google Drive sync.

Uses multiprocessing to avoid thread-safety issues with Google API client.
Each process gets its own isolated client instance.
"""

import os
import time
from pathlib import Path
from typing import Optional

# Process-local client (initialized once per worker process)
_worker_client = None


def init_worker():
    """
    Initialize the Drive client for this worker process.
    Called once when each process is spawned.
    """
    global _worker_client
    from .client import DriveClient
    _worker_client = DriveClient()


def upload_single_file(args: tuple) -> tuple:
    """
    Upload a single file to Google Drive with exponential backoff retry.

    Args:
        args: Tuple of (local_path_str, rel_path, local_hash, parent_id)

    Returns:
        Tuple of (success, rel_path, local_hash, drive_file_id_or_error)
    """
    global _worker_client

    local_path_str, rel_path, local_hash, parent_id = args
    local_path = Path(local_path_str)

    max_retries = 5
    base_delay = 1.0

    for attempt in range(max_retries):
        try:
            drive_file_id = _worker_client.upload_or_update_file(local_path, parent_id)
            return (True, rel_path, local_hash, drive_file_id)
        except Exception as e:
            error_str = str(e)
            # Check for rate limit errors
            is_rate_limit = "403" in error_str or "429" in error_str or "Rate Limit" in error_str

            if attempt < max_retries - 1:
                # Exponential backoff: 1s, 2s, 4s, 8s, 16s
                delay = base_delay * (2 ** attempt)
                if is_rate_limit:
                    delay *= 2  # Double delay for rate limits
                time.sleep(delay)
            else:
                return (False, rel_path, local_hash, error_str)

    return (False, rel_path, local_hash, "Max retries exceeded")


def upload_single_file_with_id(args: tuple) -> tuple:
    """
    Upload a single file to Google Drive with track_id passthrough.

    Args:
        args: Tuple of (local_path_str, rel_path, local_hash, parent_id, track_id)

    Returns:
        Tuple of (success, rel_path, local_hash, drive_file_id_or_error, track_id)
    """
    global _worker_client

    local_path_str, rel_path, local_hash, parent_id, track_id = args
    local_path = Path(local_path_str)

    max_retries = 5
    base_delay = 1.0

    for attempt in range(max_retries):
        try:
            drive_file_id = _worker_client.upload_or_update_file(local_path, parent_id)
            return (True, rel_path, local_hash, drive_file_id, track_id)
        except Exception as e:
            error_str = str(e)
            is_rate_limit = "403" in error_str or "429" in error_str or "Rate Limit" in error_str

            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                if is_rate_limit:
                    delay *= 2
                time.sleep(delay)
            else:
                return (False, rel_path, local_hash, error_str, track_id)

    return (False, rel_path, local_hash, "Max retries exceeded", track_id)
