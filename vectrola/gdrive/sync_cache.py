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
                cache = json.load(f)
                # Migrate old format if needed
                if "files" in cache and "wiki_files" not in cache:
                    cache["wiki_files"] = cache.pop("files")
                if "wiki_files" not in cache:
                    cache["wiki_files"] = {}
                if "audio_files" not in cache:
                    cache["audio_files"] = {}
                return cache
        except (json.JSONDecodeError, IOError):
            return {"wiki_files": {}, "audio_files": {}, "version": 2}
    return {"wiki_files": {}, "audio_files": {}, "version": 2}


def save_sync_cache(cache: dict) -> None:
    """Save the sync cache to disk."""
    SYNC_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SYNC_CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)


def get_cached_file(cache: dict, rel_path: str, section: str = "wiki_files") -> Optional[dict]:
    """Get cached info for a file path."""
    return cache.get(section, {}).get(rel_path)


def update_cached_file(
    cache: dict,
    rel_path: str,
    local_hash: str,
    drive_file_id: str,
    section: str = "wiki_files",
    drive_hash: Optional[str] = None,
) -> None:
    """Update cache entry for a file."""
    if section not in cache:
        cache[section] = {}

    cache[section][rel_path] = {
        "local_hash": local_hash,
        "drive_file_id": drive_file_id,
        "drive_hash": drive_hash or local_hash,
        "last_synced": datetime.now().isoformat(),
    }


def remove_cached_file(cache: dict, rel_path: str, section: str = "wiki_files") -> None:
    """Remove a file from cache (for deleted files)."""
    if section in cache and rel_path in cache[section]:
        del cache[section][rel_path]


def file_needs_upload(cache: dict, local_path: Path, rel_path: str, section: str = "wiki_files") -> tuple[bool, str]:
    """
    Check if a file needs to be uploaded.

    Returns:
        (needs_upload, local_hash)
    """
    local_hash = compute_md5(local_path)
    cached = get_cached_file(cache, rel_path, section)

    if cached is None:
        # New file, not in cache
        return True, local_hash

    if cached.get("local_hash") != local_hash:
        # File changed since last sync
        return True, local_hash

    # File unchanged
    return False, local_hash


def get_files_to_delete(cache: dict, current_files: set[str], section: str = "wiki_files") -> list[str]:
    """
    Find files that were deleted locally but still in cache.

    Args:
        cache: The sync cache
        current_files: Set of current relative paths
        section: Cache section to check

    Returns:
        List of relative paths to delete from Drive
    """
    cached_files = set(cache.get(section, {}).keys())
    return list(cached_files - current_files)


def clear_cache() -> None:
    """Clear the entire sync cache."""
    if SYNC_CACHE_FILE.exists():
        SYNC_CACHE_FILE.unlink()


def get_cache_stats(cache: dict) -> dict:
    """Get statistics about the cache."""
    wiki_files = cache.get("wiki_files", {})
    audio_files = cache.get("audio_files", {})
    return {
        "wiki_files": len(wiki_files),
        "audio_files": len(audio_files),
        "total_files": len(wiki_files) + len(audio_files),
        "cache_file": str(SYNC_CACHE_FILE),
    }
