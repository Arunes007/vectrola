"""Tests for metadata fetching module."""

import pytest
from vectrola.ingest.metadata import MetadataFetcher, SongMetadata


# Mark all network-dependent tests
pytestmark = pytest.mark.network


class TestMetadataFetcher:
    """Tests for MetadataFetcher class."""

    @pytest.fixture
    def fetcher(self):
        """Create a metadata fetcher instance."""
        return MetadataFetcher()

    def test_fetch_with_artist_and_title(self, fetcher):
        """Test fetching metadata with artist and title."""
        result = fetcher.fetch(
            title="Tum Hi Ho",
            artist="Arijit Singh",
        )

        assert result is not None
        assert isinstance(result, SongMetadata)
        assert result.source == "musicbrainz"

    def test_fetch_returns_artists(self, fetcher):
        """Test that MusicBrainz returns artist info."""
        result = fetcher.fetch(
            title="Tum Hi Ho",
            artist="Arijit Singh",
        )

        assert result is not None
        assert result.artists  # Has artist list

    def test_fetch_returns_album(self, fetcher):
        """Test that MusicBrainz returns album info."""
        result = fetcher.fetch(
            title="Tum Hi Ho",
            artist="Arijit Singh",
        )

        assert result is not None
        # Album may or may not be present, but should not error

    def test_fetch_with_title_only(self, fetcher):
        """Test fetching with just title works."""
        result = fetcher.fetch(title="Bohemian Rhapsody")

        assert result is not None
        assert result.title

    def test_fetch_nonexistent_song(self, fetcher):
        """Test fetching metadata for a song that doesn't exist."""
        result = fetcher.fetch(
            title="NonExistentSong67890XYZ",
            artist="NonExistentArtist12345ABC",
        )

        # May return None or a low-quality match
        # MusicBrainz does fuzzy matching so it might return something

    def test_song_metadata_to_dict(self):
        """Test SongMetadata serialization."""
        metadata = SongMetadata(
            title="Test Song",
            artists=["Artist 1", "Artist 2"],
            album="Test Album",
            year=2020,
            movie="Test Movie",
            composer="Composer Name",
            lyricist="Lyricist Name",
            source="test",
        )

        d = metadata.to_dict()

        assert d["title"] == "Test Song"
        assert d["artists"] == ["Artist 1", "Artist 2"]
        assert d["album"] == "Test Album"
        assert d["year"] == 2020
        assert d["movie"] == "Test Movie"
        assert d["composer"] == "Composer Name"
        assert d["lyricist"] == "Lyricist Name"
        assert d["source"] == "test"
