"""Unit tests for Obsidian wiki generation."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from vectrola.storage.wiki import WikiGenerator, calculate_era


# =============================================================================
# Era Calculation Tests
# =============================================================================


class TestCalculateEra:
    """Tests for calculate_era function."""

    def test_era_old_melodies_before_1990(self):
        """Test years before 1990 return 'Old Melodies'."""
        assert calculate_era(1985) == "Old Melodies"
        assert calculate_era(1960) == "Old Melodies"
        assert calculate_era(1989) == "Old Melodies"

    def test_era_90s_nostalgia(self):
        """Test 1990s return '90s Nostalgia'."""
        assert calculate_era(1990) == "90s Nostalgia"
        assert calculate_era(1995) == "90s Nostalgia"
        assert calculate_era(1999) == "90s Nostalgia"

    def test_era_y2k_vibes(self):
        """Test 2000s return 'Y2K Vibes'."""
        assert calculate_era(2000) == "Y2K Vibes"
        assert calculate_era(2005) == "Y2K Vibes"
        assert calculate_era(2009) == "Y2K Vibes"

    def test_era_2010s_rewind(self):
        """Test 2010s return '2010s Rewind'."""
        assert calculate_era(2010) == "2010s Rewind"
        assert calculate_era(2015) == "2010s Rewind"
        assert calculate_era(2019) == "2010s Rewind"

    def test_era_fresh_hits(self):
        """Test 2020+ return 'Fresh Hits'."""
        assert calculate_era(2020) == "Fresh Hits"
        assert calculate_era(2023) == "Fresh Hits"
        assert calculate_era(2025) == "Fresh Hits"

    def test_era_timeless_for_none(self):
        """Test None year returns 'Timeless'."""
        assert calculate_era(None) == "Timeless"

    def test_era_timeless_for_invalid(self):
        """Test invalid year returns 'Timeless'."""
        assert calculate_era("invalid") == "Timeless"
        assert calculate_era("") == "Timeless"

    def test_era_handles_string_year(self):
        """Test string year is converted to int."""
        assert calculate_era("2015") == "2010s Rewind"
        assert calculate_era("1995") == "90s Nostalgia"


# =============================================================================
# Wiki Generator Tests
# =============================================================================
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


# =============================================================================
# Era Page Generation Tests
# =============================================================================


class TestWikiGeneratorEraPages:
    """Tests for era page generation."""

    def test_era_directory_created(self, tmp_path):
        """Test that Eras directory is created."""
        generator = WikiGenerator(tmp_path)
        generator._create_directories()

        assert (tmp_path / "Eras").exists()

    def test_era_pages_created(self, tmp_path):
        """Test that era pages are created."""
        generator = WikiGenerator(tmp_path)
        generator._create_directories()

        mock_tracks = [
            Mock(payload={
                "title": "Song 90s",
                "artists": ["Artist A"],
                "year": 1995,
                "moods": [],
                "themes": [],
            }),
            Mock(payload={
                "title": "Song 2020s",
                "artists": ["Artist B"],
                "year": 2022,
                "moods": [],
                "themes": [],
            }),
        ]

        generator._generate_era_pages(mock_tracks)

        # Check era pages were created
        assert (tmp_path / "Eras" / "90s Nostalgia.md").exists()
        assert (tmp_path / "Eras" / "Fresh Hits.md").exists()

    def test_era_calculated_from_year_when_not_stored(self, tmp_path):
        """Test era is calculated from year if not stored in payload."""
        generator = WikiGenerator(tmp_path)
        generator._create_directories()

        # Track without 'era' field, only 'year'
        mock_tracks = [
            Mock(payload={
                "title": "Old Song",
                "artists": ["Artist"],
                "year": 1985,
                "moods": [],
                "themes": [],
                # No 'era' field
            }),
        ]

        generator._generate_era_pages(mock_tracks)

        # Should calculate era from year
        assert (tmp_path / "Eras" / "Old Melodies.md").exists()

    def test_era_uses_stored_value_when_available(self, tmp_path):
        """Test stored era value takes precedence."""
        generator = WikiGenerator(tmp_path)
        generator._create_directories()

        # Track with explicit 'era' field
        mock_tracks = [
            Mock(payload={
                "title": "Custom Era Song",
                "artists": ["Artist"],
                "year": 2000,  # Would normally be "Y2K Vibes"
                "era": "Custom Era",  # But we stored a custom era
                "moods": [],
                "themes": [],
            }),
        ]

        generator._generate_era_pages(mock_tracks)

        # Should use stored era, not calculated
        assert (tmp_path / "Eras" / "Custom Era.md").exists()

    def test_home_page_includes_eras_stats(self, tmp_path):
        """Test home page includes era stats."""
        generator = WikiGenerator(tmp_path)
        generator._create_directories()

        mock_tracks = [
            Mock(payload={
                "title": "Song 1",
                "artists": ["Artist A"],
                "year": 1995,
                "moods": [],
                "themes": [],
            }),
            Mock(payload={
                "title": "Song 2",
                "artists": ["Artist B"],
                "year": 2022,
                "moods": [],
                "themes": [],
            }),
        ]

        generator._generate_home_page(mock_tracks)

        content = (tmp_path / "README.md").read_text()
        assert "**Eras:**" in content
        assert "[[Eras/|By Era]]" in content

    def test_track_page_includes_era_link(self):
        """Test track page includes era wikilink."""
        generator = WikiGenerator()

        payload = {
            "title": "Test Song",
            "artists": ["Artist"],
            "year": 2015,
        }

        content = generator._build_track_page(payload)

        # Should have era in frontmatter
        assert 'era: "2010s Rewind"' in content
        # Should have era wikilink
        assert "**Era:**" in content
        assert "[[Eras/" in content


# =============================================================================
# GDrive Playback Tests (Day 7)
# =============================================================================


class TestWikiGeneratorGDrivePlayback:
    """Tests for GDrive playback support in wiki."""

    def test_playlist_includes_gdrive_id(self):
        """Test playlist JSON includes gdrive_id when available."""
        generator = WikiGenerator()

        # Mock library that returns GDrive ID
        mock_library = MagicMock()
        mock_library.get_gdrive_id.return_value = "gdrive_file_123"
        generator._library = mock_library

        tracks = [
            {
                "title": "Test Song",
                "artists": ["Artist"],
                "file_path": "/local/path.mp3",
                "track_id": "spotify:abc123",
            }
        ]

        script = generator._get_audio_player_script(tracks, "Test Page")

        # Check that gdrive_id is in the playlist
        assert '"gdrive_id": "gdrive_file_123"' in script

    def test_playlist_fallback_to_local_path(self):
        """Test playlist uses local path when no GDrive ID."""
        generator = WikiGenerator()

        # Mock library that returns None (no GDrive)
        mock_library = MagicMock()
        mock_library.get_gdrive_id.return_value = None
        generator._library = mock_library

        tracks = [
            {
                "title": "Local Song",
                "artists": ["Artist"],
                "file_path": "/music/song.mp3",
                "track_id": "hash:xyz",
            }
        ]

        script = generator._get_audio_player_script(tracks, "Test Page")

        # Should include local path
        assert '"path": "/music/song.mp3"' in script
        # gdrive_id should be null
        assert '"gdrive_id": null' in script

    def test_playlist_uses_stored_gdrive_file_id(self):
        """Test playlist uses gdrive_file_id from payload if library unavailable."""
        generator = WikiGenerator()
        generator._library = None  # No library service

        tracks = [
            {
                "title": "GDrive Song",
                "artists": ["Artist"],
                "file_path": "/local/path.mp3",
                "gdrive_file_id": "stored_gdrive_id",  # Stored in payload
                "track_id": "spotify:xyz",
            }
        ]

        script = generator._get_audio_player_script(tracks, "Test Page")

        # Should use gdrive_file_id from payload
        assert '"gdrive_id": "stored_gdrive_id"' in script

    def test_source_indicator_cloud_for_gdrive(self):
        """Test source indicator shows cloud icon for GDrive tracks."""
        generator = WikiGenerator()

        mock_library = MagicMock()
        mock_library.get_gdrive_id.return_value = "gdrive_123"
        generator._library = mock_library

        tracks = [
            {
                "title": "Cloud Song",
                "artists": ["Artist"],
                "file_path": "",
                "track_id": "spotify:cloud",
            }
        ]

        script = generator._get_audio_player_script(tracks, "Test")

        # Script should handle gdrive_id for source indicator
        assert "gdrive_id" in script

    def test_source_indicator_local_for_file(self):
        """Test source indicator shows local icon for file-only tracks."""
        generator = WikiGenerator()
        generator._library = None

        tracks = [
            {
                "title": "Local Song",
                "artists": ["Artist"],
                "file_path": "/music/local.mp3",
                "track_id": "hash:local",
            }
        ]

        script = generator._get_audio_player_script(tracks, "Test")

        # Script should contain the local path
        assert '"/music/local.mp3"' in script

    def test_audio_player_script_has_gdrive_playback_code(self):
        """Test audio player script includes GDrive streaming code."""
        generator = WikiGenerator()
        generator._library = None

        tracks = [
            {
                "title": "Test",
                "artists": ["Artist"],
                "file_path": "/test.mp3",
                "track_id": "test",
            }
        ]

        script = generator._get_audio_player_script(tracks, "Test")

        # Check GDrive playback code is present
        assert "googleapis.com/drive/v3/files" in script
        assert "gdrive_token.json" in script
        assert "alt=media" in script
