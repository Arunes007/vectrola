"""Unit tests for Obsidian wiki generation."""

import pytest
from pathlib import Path
from unittest.mock import Mock

from vectrola.storage.wiki import WikiGenerator


class TestWikiGenerator:
    """Test wiki generation functionality."""

    def test_sanitize_filename(self):
        """Should sanitize filenames for cross-platform compatibility."""
        generator = WikiGenerator()

        # Test invalid characters
        assert generator._sanitize_filename('song<>name') == 'song--name'
        assert generator._sanitize_filename('path/to/file') == 'path-to-file'
        assert generator._sanitize_filename('song:name') == 'song-name'

        # Test whitespace
        assert generator._sanitize_filename('  spaced  ') == 'spaced'

        # Test dots
        assert generator._sanitize_filename('...dots...') == 'dots'

        # Test empty
        assert generator._sanitize_filename('') == 'Untitled'
        assert generator._sanitize_filename('   ') == 'Untitled'

        # Test length limit
        long_name = 'a' * 250
        assert len(generator._sanitize_filename(long_name)) == 200

    def test_directory_creation(self, tmp_path):
        """Should create wiki directory structure."""
        wiki_dir = tmp_path / "test_wiki"
        generator = WikiGenerator(wiki_dir)

        generator._create_directories()

        assert (wiki_dir / "Tracks").exists()
        assert (wiki_dir / "Artists").exists()
        assert (wiki_dir / "Moods").exists()
        assert (wiki_dir / "Themes").exists()
        assert (wiki_dir / "Movies").exists()

    def test_build_track_page(self):
        """Should build valid markdown track page."""
        generator = WikiGenerator()

        payload = {
            "title": "Test Song",
            "artists": ["Artist 1", "Artist 2"],
            "album": "Test Album",
            "movie": "Test Movie",
            "year": 2020,
            "composer": "Composer Name",
            "lyricist": "Lyricist Name",
            "moods": ["happy", "energetic"],
            "themes": ["celebration", "joy"],
            "narrative": "A happy celebration song",
            "lyrics": "La la la...",
        }

        content = generator._build_track_page(payload)

        # Check frontmatter
        assert content.startswith("---")
        assert "artists: ['Artist 1', 'Artist 2']" in content
        assert 'movie: "Test Movie"' in content
        assert "year: 2020" in content

        # Check title
        assert "# Test Song" in content

        # Check wikilinks
        assert "[[Artist 1]]" in content or "[[Artist-1]]" in content
        assert "[[Test Movie]]" in content or "[[Test-Movie]]" in content
        assert "[[happy]]" in content
        assert "[[celebration]]" in content

        # Check sections
        assert "## Credits" in content
        assert "## AI Semantic Analysis" in content
        assert "## Lyrics" in content

    def test_build_track_page_minimal(self):
        """Should handle minimal track data."""
        generator = WikiGenerator()

        payload = {
            "title": "Minimal Song",
        }

        content = generator._build_track_page(payload)

        assert "# Minimal Song" in content
        assert content.startswith("---")

    def test_generate_home_page(self, tmp_path):
        """Should generate home page with stats."""
        generator = WikiGenerator(tmp_path)
        generator._create_directories()

        # Mock tracks
        mock_tracks = [
            Mock(payload={
                "title": "Song 1",
                "artists": ["Artist A"],
                "moods": ["happy"],
                "themes": ["love"],
                "movie": "Movie 1",
            }),
            Mock(payload={
                "title": "Song 2",
                "artists": ["Artist B"],
                "moods": ["sad"],
                "themes": ["loss"],
                "movie": "Movie 2",
            }),
        ]

        generator._generate_home_page(mock_tracks)

        home_path = tmp_path / "README.md"
        assert home_path.exists()

        content = home_path.read_text()
        assert "# 🎧 Vectrola Music Library" in content
        assert "**Tracks:** 2" in content
        assert "**Artists:** 2" in content
        assert "**Movies:** 2" in content
        assert "**Moods:** 2" in content
        assert "**Themes:** 2" in content

    def test_wikilinks_format(self):
        """Wikilinks should use correct Obsidian format."""
        generator = WikiGenerator()

        payload = {
            "title": "Test",
            "artists": ["Artist Name"],
            "moods": ["happy"],
        }

        content = generator._build_track_page(payload)

        # Should use [[link]] format, not [link](url)
        assert "[[Artist Name]]" in content or "[[Artist-Name]]" in content
        assert "[[happy]]" in content
        assert "](http" not in content  # No HTTP links


@pytest.mark.integration
class TestWikiGeneratorIntegration:
    """Integration tests requiring Qdrant."""

    def test_generate_all(self, tmp_path):
        """Full wiki generation test."""
        pytest.skip("Requires Qdrant with indexed tracks")
