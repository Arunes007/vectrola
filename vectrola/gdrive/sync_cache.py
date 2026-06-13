"""
Sync cache for efficient Google Drive uploads.

Tracks file hashes to skip unchanged files during sync.
Uses MD5 checksums (same as Google Drive) for comparison.
"""

import hashlib
import json
from pathlib import Path
from typing import Optional
from datetime import datetime


# Sync cache file location
VECTROLA_DIR = Path.home() / ".config" / "vectrola"
SYNC_CACHE_FILE = VECTROLA_DIR / "wiki_sync_cache.json"


def compute_md5(file_path: Path) -> str:
    """Compute MD5 hash of a file (matches Google Drive's md5Checksum)."""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def load_sync_cache() -> dict:
    """Load the sync cache from disk."""
    if SYNC_CACHE_FILE.exists():
        try:
            with open(SYNC_CACHE_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {"files": {}, "version": 1}
    return {"files": {}, "version": 1}


def save_sync_cache(cache: dict) -> None:
    """Save the sync cache to disk."""
    SYNC_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SYNC_CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)


def get_cached_file(cache: dict, rel_path: str) -> Optional[dict]:
    """Get cached info for a file path."""
    return cache.get("files", {}).get(rel_path)


def update_cached_file(
    cache: dict,
    rel_path: str,
    local_hash: str,
    drive_file_id: str,
    drive_hash: Optional[str] = None,
) -> None:
    """Update cache entry for a file."""
    if "files" not in cache:
        cache["files"] = {}

    cache["files"][rel_path] = {
        "local_hash": local_hash,
        "drive_file_id": drive_file_id,
        "drive_hash": drive_hash or local_hash,
        "last_synced": datetime.now().isoformat(),
    }


def remove_cached_file(cache: dict, rel_path: str) -> None:
    """Remove a file from cache (for deleted files)."""
    if "files" in cache and rel_path in cache["files"]:
        del cache["files"][rel_path]


def file_needs_upload(cache: dict, local_path: Path, rel_path: str) -> tuple[bool, str]:
    """
    Check if a file needs to be uploaded.

    Returns:
        (needs_upload, local_hash)
    """
    local_hash = compute_md5(local_path)
    cached = get_cached_file(cache, rel_path)

    if cached is None:
        # New file, not in cache
        return True, local_hash

    if cached.get("local_hash") != local_hash:
        # File changed since last sync
        return True, local_hash

    # File unchanged
    return False, local_hash


def get_files_to_delete(cache: dict, current_files: set[str]) -> list[str]:
    """
    Find files that were deleted locally but still in cache.

    Args:
        cache: The sync cache
        current_files: Set of current relative paths

    Returns:
        List of relative paths to delete from Drive
    """
    cached_files = set(cache.get("files", {}).keys())
    return list(cached_files - current_files)


def clear_cache() -> None:
    """Clear the entire sync cache."""
    if SYNC_CACHE_FILE.exists():
        SYNC_CACHE_FILE.unlink()


def get_cache_stats(cache: dict) -> dict:
    """Get statistics about the cache."""
    files = cache.get("files", {})
    return {
        "total_files": len(files),
        "cache_file": str(SYNC_CACHE_FILE),
    }
