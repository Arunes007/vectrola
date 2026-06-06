"""Unit tests for Qdrant named vectors and hybrid search support."""

import pytest
from unittest.mock import Mock, patch
from qdrant_client import models

from vectrola.storage.qdrant import VectrolaDB


class TestQdrantNamedVectors:
    """Test Qdrant collection with named vectors for multimodal search."""

    def test_collection_has_correct_vector_sizes(self):
        """Collection should have correct dimensions for named vectors."""
        db = VectrolaDB()

        assert db.LYRICS_VECTOR_SIZE == 384
        assert db.ACOUSTIC_VECTOR_SIZE == 512

    def test_upsert_with_lyrics_only(self):
        """Should allow upserting with only lyrics vector (Day 2 compat)."""
        db = VectrolaDB()

        client_mock = Mock()
        db._client = client_mock

        lyrics_vector = [0.1] * 384
        payload = {"title": "Test Song", "artists": ["Test Artist"]}

        db.upsert_track(
            file_path="/path/to/song.mp3",
            lyrics_vector=lyrics_vector,
            payload=payload,
        )

        # Should call upsert with only lyrics_dense vector
        assert client_mock.upsert.called
        call_args = client_mock.upsert.call_args
        point = call_args.kwargs["points"][0]
        assert "lyrics_dense" in point.vector
        assert "acoustic_clap" not in point.vector

    def test_upsert_with_both_vectors(self):
        """Should support upserting with both lyrics and audio vectors."""
        db = VectrolaDB()

        client_mock = Mock()
        db._client = client_mock

        lyrics_vector = [0.1] * 384
        audio_vector = [0.2] * 512
        payload = {"title": "Test Song"}

        db.upsert_track(
            file_path="/path/to/song.mp3",
            lyrics_vector=lyrics_vector,
            audio_vector=audio_vector,
            payload=payload,
        )

        # Should call upsert with both vectors
        assert client_mock.upsert.called
        point = client_mock.upsert.call_args.kwargs["points"][0]
        assert "lyrics_dense" in point.vector
        assert "acoustic_clap" in point.vector
        assert len(point.vector["lyrics_dense"]) == 384
        assert len(point.vector["acoustic_clap"]) == 512

    def test_search_by_audio(self):
        """Should support searching by audio vector."""
        db = VectrolaDB()

        client_mock = Mock()
        db._client = client_mock
        mock_result = Mock()
        mock_result.points = []
        client_mock.query_points.return_value = mock_result

        audio_vector = [0.2] * 512
        db.search_by_audio(audio_vector, limit=10)

        # Should query using acoustic_clap vector
        assert client_mock.query_points.called
        call_args = client_mock.query_points.call_args
        assert call_args.kwargs["using"] == "acoustic_clap"
        assert call_args.kwargs["query"] == audio_vector

    def test_hybrid_search(self):
        """Should support hybrid RRF search with both vectors."""
        db = VectrolaDB()

        client_mock = Mock()
        db._client = client_mock
        mock_result = Mock()
        mock_result.points = []
        client_mock.query_points.return_value = mock_result

        lyrics_vector = [0.1] * 384
        audio_vector = [0.2] * 512

        db.hybrid_search(lyrics_vector, audio_vector, limit=10)

        # Should use prefetch + RRF fusion
        assert client_mock.query_points.called
        call_args = client_mock.query_points.call_args
        assert "prefetch" in call_args.kwargs
        assert "query" in call_args.kwargs

        prefetch = call_args.kwargs["prefetch"]
        assert len(prefetch) == 2  # Two prefetch queries

        # Check prefetch contains both vector types
        prefetch_vectors = [p.using for p in prefetch]
        assert "lyrics_dense" in prefetch_vectors
        assert "acoustic_clap" in prefetch_vectors

        # Check RRF fusion
        query = call_args.kwargs["query"]
        assert isinstance(query, models.FusionQuery)
        assert query.fusion == models.Fusion.RRF

    def test_get_track_with_vectors(self):
        """get_track should return vectors."""
        db = VectrolaDB()

        client_mock = Mock()
        db._client = client_mock
        mock_record = Mock()
        mock_record.vector = {
            "lyrics_dense": [0.1] * 384,
            "acoustic_clap": [0.2] * 512,
        }
        client_mock.retrieve.return_value = [mock_record]

        track = db.get_track("/path/to/song.mp3")

        # Should retrieve with vectors
        assert client_mock.retrieve.called
        call_args = client_mock.retrieve.call_args
        assert call_args.kwargs["with_vectors"] is True

        # Should return record with vectors
        assert track is not None
        assert "lyrics_dense" in track.vector
        assert "acoustic_clap" in track.vector


@pytest.mark.integration
class TestQdrantNamedVectorsIntegration:
    """Integration tests for Qdrant with real connection."""

    def test_create_collection_with_named_vectors(self):
        """Should create collection with both named vectors."""
        pytest.skip("Requires Qdrant running")
        # Test would verify actual collection creation

    def test_upsert_and_retrieve_both_vectors(self):
        """Should store and retrieve both vectors correctly."""
        pytest.skip("Requires Qdrant running")

    def test_hybrid_search_returns_results(self):
        """Hybrid search should return RRF-fused results."""
        pytest.skip("Requires Qdrant with indexed tracks")
