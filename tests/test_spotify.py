"""Tests for Spotify metadata fetcher."""

import pytest


class TestSpotifyTrack:
    """Tests for SpotifyTrack dataclass."""

    def test_spotify_track_defaults(self):
        """Test SpotifyTrack default values."""
        from vectrola.ingest.spotify import SpotifyTrack

        track = SpotifyTrack()
        assert track.title == ""
        assert track.artists == []
        assert track.album == ""
        assert track.year is None

    def test_spotify_track_to_dict(self):
        """Test SpotifyTrack serialization."""
        from vectrola.ingest.spotify import SpotifyTrack

        track = SpotifyTrack(
            title="Tum Hi Ho",
            artists=["Arijit Singh", "Mithoon"],
            album="Aashiqui 2",
            year=2013,
        )

        d = track.to_dict()
        assert d["title"] == "Tum Hi Ho"
        assert d["artists"] == ["Arijit Singh", "Mithoon"]
        assert d["album"] == "Aashiqui 2"
        assert d["year"] == 2013


@pytest.mark.network
class TestSpotifyFetcher:
    """Tests for SpotifyFetcher (requires network)."""

    @pytest.fixture
    def fetcher(self):
        """Create a SpotifyFetcher instance."""
        from vectrola.ingest.spotify import SpotifyFetcher
        return SpotifyFetcher()

    def test_search_bollywood_song(self, fetcher):
        """Test searching for a Bollywood song."""
        results = fetcher.search("Tum Hi Ho", limit=5)

        assert len(results) > 0
        # First result should be Arijit Singh version
        assert any("Arijit" in str(t.artists) for t in results)

    def test_search_with_artist(self, fetcher):
        """Test searching with artist name."""
        results = fetcher.search("Tum Hi Ho", artist="Arijit Singh", limit=5)

        assert len(results) > 0

    def test_get_best_match(self, fetcher):
        """Test getting best match."""
        track = fetcher.get_best_match("Tum Hi Ho", artist="Arijit Singh")

        assert track is not None
        assert "Arijit" in str(track.artists) or "Tum Hi Ho" in track.title

    def test_search_nonexistent(self, fetcher):
        """Test searching for nonexistent song."""
        results = fetcher.search("xyznonexistentsong12345", limit=5)

        # May return empty or unrelated results
        assert isinstance(results, list)

    def test_get_best_match_returns_album(self, fetcher):
        """Test that best match includes album info."""
        track = fetcher.get_best_match("Tum Hi Ho")

        assert track is not None
        # Aashiqui 2 should be in the album name
        assert track.album  # Should have some album
