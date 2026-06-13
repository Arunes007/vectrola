"""
Tests for wiki sync cache functionality.
"""

import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from vectrola.gdrive.sync_cache import (
    compute_md5,
    load_sync_cache,
    save_sync_cache,
    get_cached_file,
    update_cached_file,
    remove_cached_file,
    file_needs_upload,
    get_files_to_delete,
    clear_cache,
    get_cache_stats,
    SYNC_CACHE_FILE,
)


class TestComputeMD5:
    """Tests for MD5 hash computation."""

    def test_compute_md5_simple(self, tmp_path):
        """Test MD5 computation for a simple file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        hash_result = compute_md5(test_file)

        # Known MD5 of "Hello, World!"
        assert hash_result == "65a8e27d8879283831b664bd8b7f0ad4"

    def test_compute_md5_empty_file(self, tmp_path):
        """Test MD5 computation for empty file."""
        test_file = tmp_path / "empty.txt"
        test_file.write_text("")

        hash_result = compute_md5(test_file)

        # Known MD5 of empty string
        assert hash_result == "d41d8cd98f00b204e9800998ecf8427e"

    def test_compute_md5_binary_file(self, tmp_path):
        """Test MD5 computation for binary file."""
        test_file = tmp_path / "binary.bin"
        test_file.write_bytes(b"\x00\x01\x02\x03\x04")

        hash_result = compute_md5(test_file)

        assert len(hash_result) == 32  # MD5 is always 32 hex chars
        assert all(c in "0123456789abcdef" for c in hash_result)

    def test_compute_md5_deterministic(self, tmp_path):
        """Test that MD5 is deterministic for same content."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Same content")

        hash1 = compute_md5(test_file)
        hash2 = compute_md5(test_file)

        assert hash1 == hash2

    def test_compute_md5_different_content(self, tmp_path):
        """Test that different content produces different hash."""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("Content A")
        file2.write_text("Content B")

        hash1 = compute_md5(file1)
        hash2 = compute_md5(file2)

        assert hash1 != hash2


class TestSyncCache:
    """Tests for sync cache operations."""

    @pytest.fixture
    def mock_cache_file(self, tmp_path, monkeypatch):
        """Mock the cache file location."""
        cache_file = tmp_path / "wiki_sync_cache.json"
        monkeypatch.setattr(
            "vectrola.gdrive.sync_cache.SYNC_CACHE_FILE", cache_file
        )
        return cache_file

    def test_load_sync_cache_empty(self, mock_cache_file):
        """Test loading cache when file doesn't exist."""
        cache = load_sync_cache()

        assert cache == {"files": {}, "version": 1}

    def test_load_sync_cache_existing(self, mock_cache_file):
        """Test loading existing cache."""
        cache_data = {
            "files": {"test.md": {"local_hash": "abc123"}},
            "version": 1,
        }
        mock_cache_file.write_text(json.dumps(cache_data))

        cache = load_sync_cache()

        assert cache == cache_data

    def test_load_sync_cache_corrupted(self, mock_cache_file):
        """Test loading corrupted cache file."""
        mock_cache_file.write_text("not valid json {{{")

        cache = load_sync_cache()

        assert cache == {"files": {}, "version": 1}

    def test_save_sync_cache(self, mock_cache_file):
        """Test saving cache."""
        cache = {
            "files": {"page.md": {"local_hash": "xyz789"}},
            "version": 1,
        }

        save_sync_cache(cache)

        loaded = json.loads(mock_cache_file.read_text())
        assert loaded == cache

    def test_save_sync_cache_creates_parent_dirs(self, tmp_path, monkeypatch):
        """Test that save creates parent directories."""
        cache_file = tmp_path / "subdir" / "cache.json"
        monkeypatch.setattr(
            "vectrola.gdrive.sync_cache.SYNC_CACHE_FILE", cache_file
        )

        save_sync_cache({"files": {}, "version": 1})

        assert cache_file.exists()


class TestCacheFileOperations:
    """Tests for individual file cache operations."""

    def test_get_cached_file_exists(self):
        """Test getting a cached file that exists."""
        cache = {
            "files": {
                "wiki/page.md": {
                    "local_hash": "abc123",
                    "drive_file_id": "drive_xyz",
                }
            }
        }

        result = get_cached_file(cache, "wiki/page.md")

        assert result["local_hash"] == "abc123"
        assert result["drive_file_id"] == "drive_xyz"

    def test_get_cached_file_not_exists(self):
        """Test getting a file that's not in cache."""
        cache = {"files": {}}

        result = get_cached_file(cache, "nonexistent.md")

        assert result is None

    def test_update_cached_file_new(self):
        """Test updating cache with a new file."""
        cache = {"files": {}}

        update_cached_file(cache, "new/page.md", "hash123", "drive_id_456")

        assert "new/page.md" in cache["files"]
        assert cache["files"]["new/page.md"]["local_hash"] == "hash123"
        assert cache["files"]["new/page.md"]["drive_file_id"] == "drive_id_456"
        assert "last_synced" in cache["files"]["new/page.md"]

    def test_update_cached_file_existing(self):
        """Test updating an existing cached file."""
        cache = {
            "files": {
                "page.md": {"local_hash": "old_hash", "drive_file_id": "old_id"}
            }
        }

        update_cached_file(cache, "page.md", "new_hash", "new_id")

        assert cache["files"]["page.md"]["local_hash"] == "new_hash"
        assert cache["files"]["page.md"]["drive_file_id"] == "new_id"

    def test_remove_cached_file(self):
        """Test removing a file from cache."""
        cache = {
            "files": {
                "keep.md": {"local_hash": "a"},
                "remove.md": {"local_hash": "b"},
            }
        }

        remove_cached_file(cache, "remove.md")

        assert "keep.md" in cache["files"]
        assert "remove.md" not in cache["files"]

    def test_remove_cached_file_not_exists(self):
        """Test removing a file that doesn't exist (no error)."""
        cache = {"files": {"other.md": {}}}

        remove_cached_file(cache, "nonexistent.md")

        assert "other.md" in cache["files"]


class TestFileNeedsUpload:
    """Tests for the file_needs_upload logic."""

    def test_file_needs_upload_new_file(self, tmp_path):
        """Test that new files need upload."""
        cache = {"files": {}}
        test_file = tmp_path / "new.md"
        test_file.write_text("New content")

        needs_upload, local_hash = file_needs_upload(cache, test_file, "new.md")

        assert needs_upload is True
        assert len(local_hash) == 32

    def test_file_needs_upload_unchanged(self, tmp_path):
        """Test that unchanged files don't need upload."""
        test_file = tmp_path / "unchanged.md"
        test_file.write_text("Same content")
        file_hash = compute_md5(test_file)

        cache = {
            "files": {
                "unchanged.md": {
                    "local_hash": file_hash,
                    "drive_file_id": "drive_123",
                }
            }
        }

        needs_upload, local_hash = file_needs_upload(
            cache, test_file, "unchanged.md"
        )

        assert needs_upload is False
        assert local_hash == file_hash

    def test_file_needs_upload_changed(self, tmp_path):
        """Test that changed files need upload."""
        test_file = tmp_path / "changed.md"
        test_file.write_text("New content")

        cache = {
            "files": {
                "changed.md": {
                    "local_hash": "old_hash_different",
                    "drive_file_id": "drive_123",
                }
            }
        }

        needs_upload, local_hash = file_needs_upload(
            cache, test_file, "changed.md"
        )

        assert needs_upload is True


class TestGetFilesToDelete:
    """Tests for finding deleted files."""

    def test_get_files_to_delete_none(self):
        """Test when no files deleted."""
        cache = {
            "files": {
                "a.md": {},
                "b.md": {},
            }
        }
        current_files = {"a.md", "b.md"}

        deleted = get_files_to_delete(cache, current_files)

        assert deleted == []

    def test_get_files_to_delete_some(self):
        """Test when some files deleted."""
        cache = {
            "files": {
                "a.md": {},
                "b.md": {},
                "deleted.md": {},
            }
        }
        current_files = {"a.md", "b.md"}

        deleted = get_files_to_delete(cache, current_files)

        assert deleted == ["deleted.md"]

    def test_get_files_to_delete_all(self):
        """Test when all cached files deleted."""
        cache = {
            "files": {
                "old1.md": {},
                "old2.md": {},
            }
        }
        current_files = {"new.md"}

        deleted = get_files_to_delete(cache, current_files)

        assert set(deleted) == {"old1.md", "old2.md"}


class TestCacheUtilities:
    """Tests for cache utility functions."""

    def test_clear_cache(self, tmp_path, monkeypatch):
        """Test clearing the cache."""
        cache_file = tmp_path / "cache.json"
        cache_file.write_text('{"files": {}}')
        monkeypatch.setattr(
            "vectrola.gdrive.sync_cache.SYNC_CACHE_FILE", cache_file
        )

        clear_cache()

        assert not cache_file.exists()

    def test_clear_cache_not_exists(self, tmp_path, monkeypatch):
        """Test clearing cache when file doesn't exist (no error)."""
        cache_file = tmp_path / "nonexistent.json"
        monkeypatch.setattr(
            "vectrola.gdrive.sync_cache.SYNC_CACHE_FILE", cache_file
        )

        clear_cache()  # Should not raise

    def test_get_cache_stats(self):
        """Test getting cache statistics."""
        cache = {
            "files": {
                "a.md": {},
                "b.md": {},
                "c.md": {},
            },
            "version": 1,
        }

        stats = get_cache_stats(cache)

        assert stats["total_files"] == 3
        assert "cache_file" in stats


class TestIntegration:
    """Integration tests for the sync cache workflow."""

    def test_full_sync_workflow(self, tmp_path, monkeypatch):
        """Test a complete sync workflow."""
        # Setup
        cache_file = tmp_path / "cache.json"
        monkeypatch.setattr(
            "vectrola.gdrive.sync_cache.SYNC_CACHE_FILE", cache_file
        )

        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir()
        (wiki_dir / "page1.md").write_text("Content 1")
        (wiki_dir / "page2.md").write_text("Content 2")

        # First sync: all files need upload
        cache = load_sync_cache()

        needs1, hash1 = file_needs_upload(cache, wiki_dir / "page1.md", "page1.md")
        needs2, hash2 = file_needs_upload(cache, wiki_dir / "page2.md", "page2.md")

        assert needs1 is True
        assert needs2 is True

        # Simulate successful upload
        update_cached_file(cache, "page1.md", hash1, "drive_id_1")
        update_cached_file(cache, "page2.md", hash2, "drive_id_2")
        save_sync_cache(cache)

        # Second sync: no files need upload (unchanged)
        cache = load_sync_cache()

        needs1, _ = file_needs_upload(cache, wiki_dir / "page1.md", "page1.md")
        needs2, _ = file_needs_upload(cache, wiki_dir / "page2.md", "page2.md")

        assert needs1 is False
        assert needs2 is False

        # Modify one file
        (wiki_dir / "page1.md").write_text("Modified content")

        # Third sync: only modified file needs upload
        needs1, new_hash1 = file_needs_upload(
            cache, wiki_dir / "page1.md", "page1.md"
        )
        needs2, _ = file_needs_upload(cache, wiki_dir / "page2.md", "page2.md")

        assert needs1 is True  # Changed
        assert needs2 is False  # Unchanged
        assert new_hash1 != hash1  # Different hash

    def test_deleted_files_workflow(self, tmp_path, monkeypatch):
        """Test handling of deleted files."""
        cache_file = tmp_path / "cache.json"
        monkeypatch.setattr(
            "vectrola.gdrive.sync_cache.SYNC_CACHE_FILE", cache_file
        )

        # Cache has 3 files
        cache = {
            "files": {
                "existing.md": {"local_hash": "a", "drive_file_id": "id1"},
                "deleted1.md": {"local_hash": "b", "drive_file_id": "id2"},
                "deleted2.md": {"local_hash": "c", "drive_file_id": "id3"},
            },
            "version": 1,
        }

        # Only one file exists now
        current_files = {"existing.md"}

        # Find deleted files
        deleted = get_files_to_delete(cache, current_files)
        assert set(deleted) == {"deleted1.md", "deleted2.md"}

        # Remove from cache
        for path in deleted:
            remove_cached_file(cache, path)

        # Verify cache is clean
        assert "existing.md" in cache["files"]
        assert "deleted1.md" not in cache["files"]
        assert "deleted2.md" not in cache["files"]
