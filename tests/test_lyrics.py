"""Tests for lyrics fetching module."""

import pytest
from vectrola.ingest.lyrics import LyricsFetcher, LyricsResult


# Mark all tests in this file as requiring network
pytestmark = pytest.mark.network


class TestLyricsFetcher:
    """Tests for LyricsFetcher class."""

    @pytest.fixture
    def fetcher(self):
        """Create a lyrics fetcher instance."""
        return LyricsFetcher()

    def test_fetch_with_artist_and_title(self, fetcher):
        """Test fetching lyrics with both artist and title."""
        result = fetcher.fetch(
            artist="Arijit Singh",
            title="Tum Hi Ho",
            use_whisper_fallback=False,
        )

        assert result is not None
        assert isinstance(result, LyricsResult)
        assert result.text  # Has lyrics
        assert result.source == "lrclib"
        assert result.artist  # Has artist info

    def test_fetch_with_title_only(self, fetcher):
        """Test fetching lyrics with just title (no artist)."""
        result = fetcher.fetch(
            artist="",
            title="Humnava",
            use_whisper_fallback=False,
        )

        assert result is not None
        assert result.text
        assert result.source == "lrclib"

    def test_fetch_returns_album_info(self, fetcher):
        """Test that LRClib returns album/movie info."""
        result = fetcher.fetch(
            artist="",
            title="Tere Naina",
            use_whisper_fallback=False,
        )

        assert result is not None
        assert result.album  # Should have album (movie name for Bollywood)

    def test_fetch_returns_duration(self, fetcher):
        """Test that LRClib returns duration."""
        result = fetcher.fetch(
            artist="Arijit Singh",
            title="Tum Hi Ho",
            use_whisper_fallback=False,
        )

        assert result is not None
        assert result.duration_seconds is not None
        assert result.duration_seconds > 0

    def test_fetch_synced_lyrics(self, fetcher):
        """Test fetching synced (timestamped) lyrics."""
        result = fetcher.fetch(
            artist="Arijit Singh",
            title="Tum Hi Ho",
            use_whisper_fallback=False,
        )

        assert result is not None
        if result.synced:
            assert result.segments is not None
            assert len(result.segments) > 0
            # Check segment structure
            seg = result.segments[0]
            assert "start" in seg
            assert "text" in seg

    def test_fetch_nonexistent_song(self, fetcher):
        """Test fetching lyrics for a song that doesn't exist."""
        result = fetcher.fetch(
            artist="NonExistentArtist12345",
            title="NonExistentSong67890",
            use_whisper_fallback=False,
        )

        assert result is None

    def test_clean_title(self, fetcher):
        """Test title cleaning removes file extensions and extras."""
        assert fetcher._clean_title("Song.mp3") == "Song"
        assert fetcher._clean_title("Song (Official Audio).mp3") == "Song"
        assert fetcher._clean_title("01 - Song") == "Song"
        assert fetcher._clean_title("Song [HD]") == "Song"

    def test_clean_artist(self, fetcher):
        """Test artist cleaning handles unknown values."""
        assert fetcher._clean_artist("Unknown Artist") == ""
        assert fetcher._clean_artist("unknown") == ""
        assert fetcher._clean_artist("Various") == ""
        assert fetcher._clean_artist("Arijit Singh") == "Arijit Singh"

    def test_hindi_lyrics_in_devanagari(self, fetcher):
        """Test that Hindi lyrics are returned in Devanagari script."""
        result = fetcher.fetch(
            artist="",
            title="Humnava",
            use_whisper_fallback=False,
        )

        assert result is not None
        # Check for Devanagari characters (Unicode range 0x0900-0x097F)
        has_devanagari = any(0x0900 <= ord(c) <= 0x097F for c in result.text)
        assert has_devanagari, "Hindi lyrics should be in Devanagari script"
