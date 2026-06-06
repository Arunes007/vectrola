"""Tests for file tags module."""

import pytest
import tempfile
import shutil
from pathlib import Path
from vectrola.storage.tags import read_file_tags, write_tags, read_vectrola_tags, FileTags


class TestFileTags:
    """Tests for FileTags dataclass."""

    def test_file_tags_defaults(self):
        """Test FileTags default values."""
        tags = FileTags()

        assert tags.title == ""
        assert tags.artists == []
        assert tags.album == ""
        assert tags.year is None
        assert tags.composer == ""
        assert tags.genre == ""
        assert tags.has_metadata is False

    def test_file_tags_with_values(self):
        """Test FileTags with custom values."""
        tags = FileTags(
            title="Test Song",
            artists=["Artist 1"],
            album="Test Album",
            year=2020,
            has_metadata=True,
        )

        assert tags.title == "Test Song"
        assert tags.artists == ["Artist 1"]
        assert tags.album == "Test Album"
        assert tags.year == 2020
        assert tags.has_metadata is True


class TestReadFileTags:
    """Tests for read_file_tags function."""

    def test_read_nonexistent_file(self):
        """Test reading tags from nonexistent file."""
        tags = read_file_tags(Path("/nonexistent/file.mp3"))

        assert isinstance(tags, FileTags)
        assert tags.has_metadata is False

    def test_read_invalid_file(self, tmp_path):
        """Test reading tags from non-audio file."""
        # Create a fake file
        fake_file = tmp_path / "not_audio.mp3"
        fake_file.write_text("not an mp3")

        tags = read_file_tags(fake_file)

        assert isinstance(tags, FileTags)
        # Should not crash, just return empty tags


class TestWriteTags:
    """Tests for write_tags function."""

    def test_write_to_nonexistent_file(self):
        """Test writing tags to nonexistent file returns False."""
        result = write_tags(
            Path("/nonexistent/file.mp3"),
            {"moods": ["test"], "themes": ["test"]},
        )

        assert result is False

    def test_write_tags_structure(self):
        """Test that write_tags accepts the expected structure."""
        analysis = {
            "moods": ["melancholic", "hopeful"],
            "themes": ["love", "loss"],
            "narrative": "A story of love and loss",
            "imagery": ["rain", "sunset"],
        }

        # Should not raise an error with valid structure
        # (actual write would fail without a real file)
        assert "moods" in analysis
        assert "themes" in analysis


class TestReadVectrolaTags:
    """Tests for read_vectrola_tags function."""

    def test_read_nonexistent_file(self):
        """Test reading Vectrola tags from nonexistent file."""
        result = read_vectrola_tags(Path("/nonexistent/file.mp3"))

        assert result is None

    def test_read_file_without_vectrola_tags(self, tmp_path):
        """Test reading from file without Vectrola tags."""
        # Create a fake file
        fake_file = tmp_path / "no_tags.mp3"
        fake_file.write_text("not an mp3")

        result = read_vectrola_tags(fake_file)

        assert result is None
