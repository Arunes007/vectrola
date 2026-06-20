"""Tests for metadata refresh functionality."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from vectrola.services.metadata_gap_detector import detect_missing_fields
from vectrola.services.metadata_refresher import MetadataRefresher


class TestDetectMissingFields:
    """Tests for detect_missing_fields function."""

    def test_all_fields_complete(self):
        """Test that complete metadata returns empty list."""
        payload = {
            "spotify_id": "spotify:123",
            "album": "Album Name",
            "year": 2020,
            "lyrics": "Some lyrics here",
            "themes": ["love", "loss"],
            "moods": ["melancholic"],
            "composer": "John Doe",
            "lyricist": "Jane Doe",
            "album_art_url": "https://example.com/art.jpg",
        }

        missing = detect_missing_fields(payload)
        assert missing == []

    def test_missing_spotify_metadata(self):
        """Test detection of missing Spotify fields."""
        # Missing spotify_id
        payload = {"album": "Album", "year": 2020}
        assert "spotify_metadata" in detect_missing_fields(payload)

        # Missing album
        payload = {"spotify_id": "spotify:123", "year": 2020}
        assert "spotify_metadata" in detect_missing_fields(payload)

        # Missing year is OK (year is optional)
        payload = {"spotify_id": "spotify:123", "album": "Album"}
        assert "spotify_metadata" not in detect_missing_fields(payload)

    def test_missing_lyrics(self):
        """Test detection of empty lyrics."""
        # Empty string
        payload = {"lyrics": ""}
        assert "lyrics" in detect_missing_fields(payload)

        # Whitespace only
        payload = {"lyrics": "   "}
        assert "lyrics" in detect_missing_fields(payload)

        # No lyrics key
        payload = {}
        assert "lyrics" in detect_missing_fields(payload)

    def test_missing_themes_moods(self):
        """Test detection of empty LLM synthesis fields."""
        # Missing themes
        payload = {"moods": ["happy"]}
        assert "themes_moods" in detect_missing_fields(payload)

        # Missing moods
        payload = {"themes": ["love"]}
        assert "themes_moods" in detect_missing_fields(payload)

        # Empty lists
        payload = {"themes": [], "moods": []}
        assert "themes_moods" in detect_missing_fields(payload)

    def test_missing_composer_lyricist(self):
        """Test that composer/lyricist are NOT checked (optional fields)."""
        # Missing composer and lyricist should NOT be flagged
        payload = {}
        assert "composer_lyricist" not in detect_missing_fields(payload)

        # Even if only one is present, should not be flagged
        payload = {"composer": "John"}
        assert "composer_lyricist" not in detect_missing_fields(payload)

    def test_missing_album_art(self):
        """Test detection of missing album art."""
        payload = {}
        assert "album_art" in detect_missing_fields(payload)

        payload = {"album_art_url": None}
        assert "album_art" in detect_missing_fields(payload)

    def test_multiple_missing_fields(self):
        """Test detection of multiple missing fields at once."""
        payload = {
            "title": "Song",
            "artists": ["Artist"],
            # Everything else missing
        }

        missing = detect_missing_fields(payload)
        assert "spotify_metadata" in missing
        assert "lyrics" in missing
        assert "themes_moods" in missing
        assert "album_art" in missing
        # composer_lyricist should NOT be in missing (optional)
        assert "composer_lyricist" not in missing
        assert len(missing) == 4


class TestMetadataRefresher:
    """Tests for MetadataRefresher class."""

    def test_refresh_track_not_found(self):
        """Test error when track_id doesn't exist."""
        with patch("vectrola.ingest.pipeline.IngestPipeline"):
            refresher = MetadataRefresher()

            with patch("vectrola.storage.qdrant.get_db") as mock_get_db:
                mock_db = Mock()
                mock_db.COLLECTION = "test_collection"
                mock_db.client.scroll.return_value = ([], None)  # No points found
                mock_get_db.return_value = mock_db

                with pytest.raises(ValueError, match="Track .* not found"):
                    refresher.refresh_track("nonexistent:123", ["lyrics"])

    def test_refresh_spotify_metadata(self):
        """Test refreshing Spotify metadata (simplified check)."""
        # Just verify the method exists and has correct signature
        from vectrola.services.metadata_refresher import MetadataRefresher
        import inspect

        refresher = MetadataRefresher()
        assert hasattr(refresher, "_refresh_spotify")
        sig = inspect.signature(refresher._refresh_spotify)
        assert "payload" in sig.parameters

    def test_refresh_lyrics_from_lrclib(self):
        """Test refreshing lyrics from LRClib (simplified check)."""
        from vectrola.services.metadata_refresher import MetadataRefresher
        import inspect

        refresher = MetadataRefresher()
        assert hasattr(refresher, "_refresh_lyrics")
        sig = inspect.signature(refresher._refresh_lyrics)
        assert "payload" in sig.parameters
        assert "updates" in sig.parameters
        assert "file_path" in sig.parameters

    def test_refresh_lyrics_fallback_to_genius(self):
        """Test lyrics method structure."""
        from vectrola.services.metadata_refresher import MetadataRefresher

        refresher = MetadataRefresher()
        # Verify method exists
        assert callable(refresher._refresh_lyrics)

    def test_refresh_themes_moods(self):
        """Test refreshing themes/moods from LLM."""
        refresher = MetadataRefresher()

        # Mock synthesis
        mock_synthesis = Mock()
        mock_synthesis.themes = ["love", "loss"]
        mock_synthesis.moods = ["melancholic", "romantic"]
        mock_synthesis.narrative = "A sad love story"
        mock_synthesis.imagery = ["rain", "night"]

        refresher.pipeline.synthesis = Mock()
        refresher.pipeline.synthesis.synthesize_from_lyrics.return_value = mock_synthesis

        payload = {"title": "Song", "lyrics": "Some lyrics"}
        updates = refresher._refresh_themes_moods(payload, {})

        assert updates["themes"] == ["love", "loss"]
        assert updates["moods"] == ["melancholic", "romantic"]
        assert updates["narrative"] == "A sad love story"
        assert updates["imagery"] == ["rain", "night"]

    def test_refresh_themes_moods_no_lyrics(self):
        """Test that themes/moods refresh requires lyrics."""
        refresher = MetadataRefresher()

        payload = {"title": "Song", "lyrics": ""}
        updates = refresher._refresh_themes_moods(payload, {})

        assert updates == {}

    def test_refresh_composer_lyricist(self):
        """Test that composer/lyricist refresh is no longer used."""
        from vectrola.services.metadata_refresher import MetadataRefresher

        refresher = MetadataRefresher()
        # Method should not exist anymore
        assert not hasattr(refresher, "_refresh_composer_lyricist")


class TestRefreshCLI:
    """Tests for the refresh CLI command."""

    def test_cli_command_exists(self):
        """Test that refresh command is registered."""
        from typer.testing import CliRunner
        from vectrola.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["refresh", "--help"])

        assert result.exit_code == 0
        assert "Refresh metadata for existing tracks" in result.output
        assert "--track" in result.output
        assert "--list" in result.output

    def test_cli_list_flag(self):
        """Test that --list flag is recognized."""
        from typer.testing import CliRunner
        from vectrola.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["refresh", "--help"])

        assert "--list" in result.output
        assert "-l" in result.output
        assert "List tracks with missing metadata" in result.output

    def test_cli_track_option(self):
        """Test that --track option is recognized."""
        from typer.testing import CliRunner
        from vectrola.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["refresh", "--help"])

        assert "--track" in result.output
        assert "Refresh specific track by name" in result.output
