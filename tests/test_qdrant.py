"""Tests for Qdrant storage module."""

import pytest
from unittest.mock import MagicMock, patch


class TestVectrolaDB:
    """Tests for VectrolaDB class."""

    def test_generate_id_deterministic(self):
        """Test that ID generation is deterministic."""
        from vectrola.storage.qdrant import VectrolaDB

        db = VectrolaDB.__new__(VectrolaDB)

        id1 = db._generate_id("/path/to/song.mp3")
        id2 = db._generate_id("/path/to/song.mp3")
        id3 = db._generate_id("/path/to/other.mp3")

        assert id1 == id2  # Same path = same ID
        assert id1 != id3  # Different path = different ID

    def test_generate_id_format(self):
        """Test that generated ID is a valid UUID string."""
        from vectrola.storage.qdrant import VectrolaDB
        import uuid

        db = VectrolaDB.__new__(VectrolaDB)
        generated_id = db._generate_id("/test/path.mp3")

        # Should be a valid UUID
        uuid.UUID(generated_id)


@pytest.mark.integration
class TestVectrolaDBIntegration:
    """Integration tests requiring Qdrant to be running."""

    @pytest.fixture
    def db(self):
        """Create a test database connection."""
        from vectrola.storage.qdrant import VectrolaDB

        db = VectrolaDB(url="http://localhost:6333")
        return db

    def test_is_connected(self, db):
        """Test connection check."""
        # This will fail if Qdrant is not running
        assert db.is_connected()

    def test_count(self, db):
        """Test track count."""
        count = db.count()
        assert isinstance(count, int)
        assert count >= 0

    def test_upsert_and_retrieve(self, db):
        """Test upserting and retrieving a track."""
        test_path = "/test/integration_test_track.mp3"
        test_vector = [0.1] * 384  # 384-dim vector
        test_payload = {
            "title": "Test Track",
            "artists": ["Test Artist"],
            "moods": ["happy"],
            "themes": ["testing"],
        }

        # Upsert
        point_id = db.upsert_track(
            file_path=test_path,
            lyrics_vector=test_vector,
            payload=test_payload,
        )

        assert point_id is not None

        # Retrieve
        track = db.get_track(test_path)
        assert track is not None
        assert track.payload["title"] == "Test Track"

        # Cleanup
        db.delete_track(test_path)

    def test_search_by_lyrics(self, db):
        """Test lyrics search returns results."""
        # Search with a random vector
        query_vector = [0.1] * 384
        results = db.search_by_lyrics(query_vector, limit=5)

        assert isinstance(results, list)
        # Results may be empty if DB is empty, that's ok

    def test_update_payload(self, db):
        """Test updating payload fields without changing vectors."""
        test_path = "/test/update_payload_test.mp3"
        test_vector = [0.1] * 384
        test_payload = {
            "title": "Test Track",
            "artists": ["Test Artist"],
        }

        # Insert track
        db.upsert_track(
            file_path=test_path,
            lyrics_vector=test_vector,
            payload=test_payload,
        )

        # Update payload with YouTube ID
        success = db.update_payload(test_path, {"youtube_id": "dQw4w9WgXcQ"})
        assert success is True

        # Retrieve and verify
        track = db.get_track(test_path)
        assert track is not None
        assert track.payload["title"] == "Test Track"  # Original field preserved
        assert track.payload["youtube_id"] == "dQw4w9WgXcQ"  # New field added

        # Cleanup
        db.delete_track(test_path)
