"""Unit tests for hybrid search functionality."""

import pytest
from unittest.mock import Mock, patch
import numpy as np

from vectrola.search.semantic import SemanticSearch, SearchResult


class TestHybridSearch:
    """Test hybrid search with CLAP + text embeddings."""

    def test_search_modes(self):
        """Should support lyrics, audio, and hybrid modes."""
        searcher = SemanticSearch()

        # Mock the private attributes instead of properties
        text_mock = Mock()
        audio_mock = Mock()
        db_mock = Mock()

        searcher._text_embedder = text_mock
        searcher._audio_embedder = audio_mock
        searcher._db = db_mock

        text_mock.embed.return_value = [0.1] * 384
        audio_mock.embed_text.return_value = [0.2] * 512
        db_mock.search_by_lyrics.return_value = []
        db_mock.search_by_audio.return_value = []
        db_mock.hybrid_search.return_value = []

        # Lyrics mode
        searcher.search("test", mode="lyrics")
        assert text_mock.embed.called
        assert db_mock.search_by_lyrics.called
        assert not db_mock.hybrid_search.called

        # Reset
        text_mock.reset_mock()
        audio_mock.reset_mock()
        db_mock.reset_mock()

        # Audio mode
        searcher.search("test", mode="audio")
        assert audio_mock.embed_text.called
        assert db_mock.search_by_audio.called
        assert not db_mock.hybrid_search.called

        # Reset
        text_mock.reset_mock()
        audio_mock.reset_mock()
        db_mock.reset_mock()

        # Hybrid mode
        searcher.search("test", mode="hybrid")
        assert text_mock.embed.called
        assert audio_mock.embed_text.called
        assert db_mock.hybrid_search.called

    def test_find_similar_modes(self):
        """Should support audio and lyrics similarity modes."""
        searcher = SemanticSearch()

        # Mock track with both vectors
        mock_track = Mock()
        mock_track.vector = {
            "lyrics_dense": [0.1] * 384,
            "acoustic_clap": [0.2] * 512,
        }

        db_mock = Mock()
        searcher._db = db_mock
        db_mock.get_track.return_value = mock_track
        db_mock.search_by_audio.return_value = []
        db_mock.search_by_lyrics.return_value = []

        # Audio mode (default)
        searcher.find_similar("/path/to/song.mp3", mode="audio")
        assert db_mock.search_by_audio.called

        # Reset
        db_mock.reset_mock()
        db_mock.get_track.return_value = mock_track

        # Lyrics mode
        searcher.find_similar("/path/to/song.mp3", mode="lyrics")
        assert db_mock.search_by_lyrics.called

    def test_find_similar_filters_self(self):
        """find_similar should exclude the reference track."""
        searcher = SemanticSearch()

        # Mock track
        mock_track = Mock()
        mock_track.vector = {"acoustic_clap": [0.2] * 512}

        # Mock results including self
        mock_result1 = Mock()
        mock_result1.payload = {"file_path": "/path/to/song.mp3", "title": "Self"}
        mock_result1.score = 1.0

        mock_result2 = Mock()
        mock_result2.payload = {"file_path": "/path/to/other.mp3", "title": "Other"}
        mock_result2.score = 0.9

        db_mock = Mock()
        searcher._db = db_mock
        db_mock.get_track.return_value = mock_track
        db_mock.search_by_audio.return_value = [mock_result1, mock_result2]

        results = searcher.find_similar("/path/to/song.mp3", mode="audio")

        # Should only return "Other", not "Self"
        assert len(results) == 1
        assert results[0].title == "Other"

    def test_results_to_search_results(self):
        """Should convert Qdrant results to SearchResult objects."""
        searcher = SemanticSearch()

        # Mock Qdrant result
        mock_result = Mock()
        mock_result.payload = {
            "file_path": "/path/to/song.mp3",
            "title": "Test Song",
            "artists": ["Artist 1", "Artist 2"],
            "album": "Test Album",
            "movie": "Test Movie",
            "moods": ["happy", "energetic"],
            "themes": ["celebration", "joy"],
            "narrative": "A happy song",
            "lyrics": "La la la " * 100,  # Long lyrics
        }
        mock_result.score = 0.85

        results = searcher._results_to_search_results([mock_result])

        assert len(results) == 1
        r = results[0]
        assert isinstance(r, SearchResult)
        assert r.title == "Test Song"
        assert r.artists == ["Artist 1", "Artist 2"]
        assert r.score == 0.85
        assert r.moods == ["happy", "energetic"]
        assert len(r.lyrics_preview) <= 203  # 200 + "..."

    def test_empty_results(self):
        """Should handle empty search results gracefully."""
        searcher = SemanticSearch()

        text_mock = Mock()
        db_mock = Mock()
        searcher._text_embedder = text_mock
        searcher._db = db_mock

        text_mock.embed.return_value = [0.1] * 384
        db_mock.search_by_lyrics.return_value = []

        results = searcher.search("nonexistent query", mode="lyrics")

        assert results == []

    def test_missing_vectors(self):
        """find_similar should return empty if vectors missing."""
        searcher = SemanticSearch()

        # Track without acoustic_clap vector
        mock_track = Mock()
        mock_track.vector = {"lyrics_dense": [0.1] * 384}

        db_mock = Mock()
        searcher._db = db_mock
        db_mock.get_track.return_value = mock_track

        # Audio mode should fail gracefully
        results = searcher.find_similar("/path/to/song.mp3", mode="audio")
        assert results == []

    def test_track_not_found(self):
        """find_similar should return empty if track not found."""
        searcher = SemanticSearch()

        db_mock = Mock()
        searcher._db = db_mock
        db_mock.get_track.return_value = None

        results = searcher.find_similar("/nonexistent.mp3")
        assert results == []


@pytest.mark.integration
class TestHybridSearchIntegration:
    """Integration tests for hybrid search (requires Qdrant + models)."""

    def test_hybrid_search_full_stack(self):
        """End-to-end hybrid search test."""
        pytest.skip("Requires Qdrant running and indexed tracks")

    def test_acoustic_similarity_full_stack(self):
        """End-to-end acoustic similarity test."""
        pytest.skip("Requires Qdrant with audio embeddings")
