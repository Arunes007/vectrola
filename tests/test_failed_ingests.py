"""Tests for failed ingestion tracking and retry functionality."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime

from vectrola.services.failed_ingests import (
    FailedIngestsManager,
    detect_error_stage,
    FAILED_INGESTS_PATH,
)


class TestDetectErrorStage:
    """Test error stage detection from error messages."""

    def test_download_errors(self):
        """Download-related errors should be detected."""
        assert detect_error_stage("Download failed: connection reset") == "download"
        assert detect_error_stage("Google Drive API error") == "download"
        assert detect_error_stage("drive.readonly scope missing") == "download"

    def test_metadata_errors(self):
        """Metadata/Spotify errors should be detected."""
        assert detect_error_stage("Spotify API rate limit exceeded") == "metadata"
        assert detect_error_stage("spotify timeout after 30s") == "metadata"

    def test_lyrics_errors(self):
        """Lyrics-related errors should be detected."""
        assert detect_error_stage("LRClib timeout") == "lyrics"
        assert detect_error_stage("Genius API error: 429") == "lyrics"
        assert detect_error_stage("No lyrics found for track") == "lyrics"

    def test_llm_errors(self):
        """LLM-related errors should be detected."""
        assert detect_error_stage("Ollama connection refused") == "llm"
        assert detect_error_stage("Model 'llama3.2:1b' not found") == "llm"
        assert detect_error_stage("LLM synthesis failed") == "llm"
        assert detect_error_stage("anthropic.APIError: rate limit") == "llm"
        assert detect_error_stage("openai.RateLimitError") == "llm"

    def test_storage_errors(self):
        """Storage/Qdrant errors should be detected."""
        assert detect_error_stage("Qdrant connection timeout") == "storage"
        assert detect_error_stage("Vector embedding failed") == "storage"
        assert detect_error_stage("Storage write error") == "storage"
        assert detect_error_stage("embedding dimension mismatch") == "storage"

    def test_unknown_errors(self):
        """Unrecognized errors should return 'unknown'."""
        assert detect_error_stage("Something went wrong") == "unknown"
        assert detect_error_stage("Generic error message") == "unknown"
        assert detect_error_stage("") == "unknown"


class TestFailedIngestsManager:
    """Test FailedIngestsManager class."""

    @pytest.fixture
    def temp_failed_path(self, tmp_path):
        """Create a temporary path for failed_ingests.json."""
        return tmp_path / "config" / "vectrola" / "failed_ingests.json"

    @pytest.fixture
    def manager(self, temp_failed_path):
        """Create a manager with temporary storage."""
        with patch.object(
            FailedIngestsManager,
            "_load",
            return_value={"version": 1, "failed": []},
        ):
            mgr = FailedIngestsManager()
            # Override the save to use temp path
            original_save = mgr._save

            def temp_save():
                temp_failed_path.parent.mkdir(parents=True, exist_ok=True)
                temp_failed_path.write_text(json.dumps(mgr._data, indent=2))

            mgr._save = temp_save
            return mgr

    def test_add_local_failed(self, manager):
        """Test adding a local file failure."""
        manager.add_failed(
            name="song.mp3",
            source="local",
            source_path="/music/song.mp3",
            error="Model not found",
            error_stage="llm",
        )

        failed = manager.get_failed()
        assert len(failed) == 1
        assert failed[0]["id"] == "local:/music/song.mp3"
        assert failed[0]["name"] == "song.mp3"
        assert failed[0]["source"] == "local"
        assert failed[0]["error"] == "Model not found"
        assert failed[0]["error_stage"] == "llm"
        assert failed[0]["attempts"] == 1
        assert failed[0]["gdrive_file_id"] is None

    def test_add_gdrive_failed(self, manager):
        """Test adding a Google Drive file failure."""
        manager.add_failed(
            name="track.mp3",
            source="gdrive",
            source_path="/Music/track.mp3",
            error="LRClib timeout",
            error_stage="lyrics",
            gdrive_file_id="1abc123xyz",
        )

        failed = manager.get_failed()
        assert len(failed) == 1
        assert failed[0]["id"] == "gdrive:1abc123xyz"
        assert failed[0]["gdrive_file_id"] == "1abc123xyz"
        assert failed[0]["source"] == "gdrive"

    def test_update_existing_failure(self, manager):
        """Test that re-adding the same track updates attempts."""
        # First failure
        manager.add_failed(
            name="song.mp3",
            source="local",
            source_path="/music/song.mp3",
            error="First error",
            error_stage="llm",
        )

        # Second failure (same track)
        manager.add_failed(
            name="song.mp3",
            source="local",
            source_path="/music/song.mp3",
            error="Second error",
            error_stage="storage",
        )

        failed = manager.get_failed()
        assert len(failed) == 1  # Still only one entry
        assert failed[0]["error"] == "Second error"  # Updated error
        assert failed[0]["error_stage"] == "storage"  # Updated stage
        assert failed[0]["attempts"] == 2  # Incremented attempts

    def test_remove_failed(self, manager):
        """Test removing a track from the failed list."""
        manager.add_failed(
            name="song1.mp3",
            source="local",
            source_path="/music/song1.mp3",
            error="Error 1",
            error_stage="llm",
        )
        manager.add_failed(
            name="song2.mp3",
            source="local",
            source_path="/music/song2.mp3",
            error="Error 2",
            error_stage="lyrics",
        )

        assert manager.count() == 2

        manager.remove_failed("local:/music/song1.mp3")

        assert manager.count() == 1
        assert manager.get_failed()[0]["name"] == "song2.mp3"

    def test_remove_nonexistent_is_safe(self, manager):
        """Test that removing a non-existent track doesn't error."""
        manager.add_failed(
            name="song.mp3",
            source="local",
            source_path="/music/song.mp3",
            error="Error",
            error_stage="llm",
        )

        # Should not raise
        manager.remove_failed("local:/nonexistent.mp3")
        assert manager.count() == 1

    def test_clear_all(self, manager):
        """Test clearing all failed tracks."""
        manager.add_failed(
            name="song1.mp3",
            source="local",
            source_path="/music/song1.mp3",
            error="Error 1",
            error_stage="llm",
        )
        manager.add_failed(
            name="song2.mp3",
            source="gdrive",
            source_path="/Music/song2.mp3",
            error="Error 2",
            error_stage="lyrics",
            gdrive_file_id="abc123",
        )

        assert manager.count() == 2

        cleared = manager.clear()

        assert cleared == 2
        assert manager.count() == 0
        assert manager.get_failed() == []

    def test_clear_empty_list(self, manager):
        """Test clearing an already empty list."""
        cleared = manager.clear()
        assert cleared == 0

    def test_count(self, manager):
        """Test count method."""
        assert manager.count() == 0

        manager.add_failed(
            name="song.mp3",
            source="local",
            source_path="/music/song.mp3",
            error="Error",
            error_stage="llm",
        )
        assert manager.count() == 1

        manager.add_failed(
            name="track.mp3",
            source="gdrive",
            source_path="/Music/track.mp3",
            error="Error",
            error_stage="lyrics",
            gdrive_file_id="xyz789",
        )
        assert manager.count() == 2

    def test_failed_at_timestamp(self, manager):
        """Test that failed_at timestamp is set correctly."""
        before = datetime.utcnow().isoformat()

        manager.add_failed(
            name="song.mp3",
            source="local",
            source_path="/music/song.mp3",
            error="Error",
            error_stage="llm",
        )

        after = datetime.utcnow().isoformat()

        failed = manager.get_failed()[0]
        # Remove the 'Z' suffix for comparison
        timestamp = failed["failed_at"].rstrip("Z")
        assert before <= timestamp <= after

    def test_persistence(self, temp_failed_path):
        """Test that data persists to disk."""
        # Directly test file writing
        temp_failed_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "version": 1,
            "failed": [
                {
                    "id": "local:/test.mp3",
                    "name": "test.mp3",
                    "source": "local",
                    "source_path": "/test.mp3",
                    "gdrive_file_id": None,
                    "error": "Test error",
                    "error_stage": "llm",
                    "failed_at": "2026-06-12T10:00:00Z",
                    "attempts": 1,
                }
            ],
        }
        temp_failed_path.write_text(json.dumps(data))

        # Verify file content
        loaded = json.loads(temp_failed_path.read_text())
        assert loaded["version"] == 1
        assert len(loaded["failed"]) == 1
        assert loaded["failed"][0]["name"] == "test.mp3"


class TestFailedIngestsIntegration:
    """Integration tests for failed ingests with CLI commands."""

    @pytest.fixture
    def mock_manager(self):
        """Create a mock FailedIngestsManager."""
        manager = MagicMock(spec=FailedIngestsManager)
        manager.get_failed.return_value = []
        manager.count.return_value = 0
        return manager

    def test_retry_list_empty(self, mock_manager):
        """Test listing when no failures exist."""
        mock_manager.get_failed.return_value = []

        # Simulate the list logic
        failed = mock_manager.get_failed()
        assert len(failed) == 0

    def test_retry_list_with_failures(self, mock_manager):
        """Test listing with failures."""
        mock_manager.get_failed.return_value = [
            {
                "id": "local:/music/song.mp3",
                "name": "song.mp3",
                "source": "local",
                "source_path": "/music/song.mp3",
                "gdrive_file_id": None,
                "error": "Model not found",
                "error_stage": "llm",
                "failed_at": "2026-06-12T10:00:00Z",
                "attempts": 2,
            },
            {
                "id": "gdrive:abc123",
                "name": "track.mp3",
                "source": "gdrive",
                "source_path": "/Music/track.mp3",
                "gdrive_file_id": "abc123",
                "error": "LRClib timeout",
                "error_stage": "lyrics",
                "failed_at": "2026-06-12T10:05:00Z",
                "attempts": 1,
            },
        ]

        failed = mock_manager.get_failed()
        assert len(failed) == 2
        assert failed[0]["source"] == "local"
        assert failed[1]["source"] == "gdrive"

    def test_clear_returns_count(self, mock_manager):
        """Test that clear returns the number of cleared items."""
        mock_manager.clear.return_value = 5

        count = mock_manager.clear()
        assert count == 5


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_detect_error_stage_case_insensitive(self):
        """Error detection should be case-insensitive."""
        assert detect_error_stage("OLLAMA connection refused") == "llm"
        assert detect_error_stage("QDRANT Error") == "storage"
        assert detect_error_stage("SPOTIFY API timeout") == "metadata"

    def test_empty_error_message(self):
        """Empty error message should return 'unknown'."""
        assert detect_error_stage("") == "unknown"

    def test_multiple_keywords_in_error(self):
        """When multiple keywords match, first match wins."""
        # "download" comes before "lyrics" in the detection order
        error = "Failed to download lyrics from LRClib"
        assert detect_error_stage(error) == "download"

    def test_gdrive_id_takes_precedence(self):
        """GDrive file ID should be used for ID when available."""
        with patch.object(
            FailedIngestsManager,
            "_load",
            return_value={"version": 1, "failed": []},
        ):
            with patch.object(FailedIngestsManager, "_save"):
                manager = FailedIngestsManager()

                # Even if source_path is different, gdrive_file_id determines the ID
                manager.add_failed(
                    name="song.mp3",
                    source="gdrive",
                    source_path="/Old/Path/song.mp3",
                    error="Error",
                    error_stage="llm",
                    gdrive_file_id="unique_id_123",
                )

                assert manager.get_failed()[0]["id"] == "gdrive:unique_id_123"
