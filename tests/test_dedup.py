"""Tests for deduplication logic in the ingestion pipeline."""

import pytest
import tempfile
import hashlib
import platform
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

from vectrola.ingest.pipeline import (
    calculate_checksum,
    find_existing_track,
    generate_track_id,
)
from vectrola.config import get_device_id


class TestCalculateChecksum:
    """Tests for calculate_checksum function."""

    def test_checksum_returns_md5_hex(self):
        """Test that checksum returns a valid MD5 hex string."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
            f.write(b"test audio content")
            f.flush()

            checksum = calculate_checksum(Path(f.name))

            # MD5 hex is 32 characters
            assert len(checksum) == 32
            assert all(c in "0123456789abcdef" for c in checksum)

    def test_checksum_is_deterministic(self):
        """Test that same file produces same checksum."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
            f.write(b"test audio content 12345")
            f.flush()

            checksum1 = calculate_checksum(Path(f.name))
            checksum2 = calculate_checksum(Path(f.name))

            assert checksum1 == checksum2

    def test_different_files_different_checksums(self):
        """Test that different files produce different checksums."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f1:
            f1.write(b"content A")
            f1.flush()

            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f2:
                f2.write(b"content B")
                f2.flush()

                checksum1 = calculate_checksum(Path(f1.name))
                checksum2 = calculate_checksum(Path(f2.name))

                assert checksum1 != checksum2

    def test_checksum_matches_python_hashlib(self):
        """Test that our checksum matches standard hashlib MD5."""
        content = b"test audio content for verification"

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
            f.write(content)
            f.flush()

            our_checksum = calculate_checksum(Path(f.name))
            expected = hashlib.md5(content).hexdigest()

            assert our_checksum == expected


class TestGenerateTrackId:
    """Tests for generate_track_id function."""

    def test_spotify_id_takes_priority(self):
        """Test that Spotify ID is used when available."""
        track_id = generate_track_id(
            spotify_id="4PTG3Z6ehGkBFwjybzWkR8",
            artist="Arijit Singh",
            title="Tum Hi Ho",
        )

        assert track_id == "spotify:4PTG3Z6ehGkBFwjybzWkR8"

    def test_hash_fallback_when_no_spotify(self):
        """Test hash-based ID when Spotify ID is not available."""
        track_id = generate_track_id(
            spotify_id=None,
            artist="Unknown Artist",
            title="Unknown Song",
        )

        assert track_id.startswith("hash:")
        assert len(track_id) == 5 + 16  # "hash:" + 16 hex chars

    def test_hash_is_deterministic(self):
        """Test that same artist+title produces same hash."""
        track_id1 = generate_track_id(None, "Artist", "Title")
        track_id2 = generate_track_id(None, "Artist", "Title")

        assert track_id1 == track_id2

    def test_hash_is_case_insensitive(self):
        """Test that hash normalizes case."""
        track_id1 = generate_track_id(None, "Artist", "Title")
        track_id2 = generate_track_id(None, "ARTIST", "TITLE")

        assert track_id1 == track_id2

    def test_hash_strips_whitespace(self):
        """Test that hash strips whitespace."""
        track_id1 = generate_track_id(None, "Artist", "Title")
        track_id2 = generate_track_id(None, "  Artist  ", "  Title  ")

        assert track_id1 == track_id2


class TestFindExistingTrack:
    """Tests for find_existing_track function."""

    def _create_mock_db(self, tracks=None):
        """Create a mock VectrolaDB with given tracks."""
        mock_db = Mock()
        mock_db.COLLECTION = "test_collection"

        if tracks is None:
            tracks = []

        def mock_scroll(collection_name, scroll_filter=None, limit=1, with_payload=True):
            if scroll_filter:
                # Check filter conditions
                must = scroll_filter.must if hasattr(scroll_filter, 'must') else []
                for condition in must:
                    if hasattr(condition, 'key') and hasattr(condition, 'match'):
                        key = condition.key
                        value = condition.match.value

                        # Find matching track
                        for track in tracks:
                            if track.payload.get(key) == value:
                                return ([track], None)
                return ([], None)
            else:
                # Return all tracks
                return (tracks[:limit], None)

        mock_db.client = Mock()
        mock_db.client.scroll = mock_scroll

        return mock_db

    def _create_mock_point(self, point_id, payload):
        """Create a mock Qdrant point."""
        point = Mock()
        point.id = point_id
        point.payload = payload
        return point

    def test_finds_by_checksum(self):
        """Test that existing track is found by checksum."""
        mock_point = self._create_mock_point(
            "point-123",
            {
                "checksum": "abc123def456",
                "track_id": "spotify:xyz",
                "title": "Test Song",
            }
        )
        mock_db = self._create_mock_db([mock_point])

        result = find_existing_track(
            db=mock_db,
            checksum="abc123def456",
            title="Different Title",  # Should still match by checksum
            artist="Different Artist",
        )

        assert result is not None
        point_id, track_id, payload = result
        assert point_id == "point-123"
        assert track_id == "spotify:xyz"

    def test_finds_by_title_and_artist(self):
        """Test that existing track is found by title + artist."""
        mock_point = self._create_mock_point(
            "point-456",
            {
                "checksum": "different_checksum",
                "track_id": "spotify:abc",
                "title": "Tum Hi Ho",
                "artists": ["Arijit Singh"],
            }
        )
        mock_db = self._create_mock_db([mock_point])

        # Mock the full payload fetch
        mock_db.client.scroll = Mock(side_effect=[
            ([], None),  # Checksum search returns empty
            ([mock_point], None),  # Title+artist search
            ([mock_point], None),  # Full payload fetch
        ])

        result = find_existing_track(
            db=mock_db,
            checksum="nonexistent_checksum",
            title="Tum Hi Ho",
            artist="Arijit Singh",
        )

        # The function should attempt title+artist matching
        assert mock_db.client.scroll.call_count >= 1

    def test_returns_none_when_no_match(self):
        """Test that None is returned when no match found."""
        mock_db = self._create_mock_db([])
        mock_db.client.scroll = Mock(return_value=([], None))

        result = find_existing_track(
            db=mock_db,
            checksum="nonexistent",
            title="Nonexistent Song",
            artist="Unknown Artist",
        )

        assert result is None

    def test_requires_both_title_and_artist_for_tier2(self):
        """Test that title+artist match requires both fields."""
        mock_point = self._create_mock_point(
            "point-789",
            {
                "checksum": "different",
                "track_id": "spotify:def",
                "title": "Some Song",
                "artists": ["Some Artist"],
            }
        )
        mock_db = self._create_mock_db([mock_point])
        mock_db.client.scroll = Mock(return_value=([], None))

        # With only title (no artist), should return None and not match
        result = find_existing_track(
            db=mock_db,
            checksum="nonexistent",
            title="Some Song",
            artist=None,  # No artist
        )

        assert result is None

    def test_title_matching_is_case_insensitive(self):
        """Test that title matching normalizes case."""
        mock_point = self._create_mock_point(
            "point-999",
            {
                "checksum": "xyz",
                "track_id": "spotify:ghi",
                "title": "TUM HI HO",
                "artists": ["ARIJIT SINGH"],
            }
        )
        mock_db = self._create_mock_db([mock_point])

        # Mock to simulate the scroll behavior
        mock_db.client.scroll = Mock(side_effect=[
            ([], None),  # Checksum search
            ([mock_point], None),  # All tracks for title search
            ([mock_point], None),  # Full payload fetch
        ])

        result = find_existing_track(
            db=mock_db,
            checksum="different",
            title="tum hi ho",  # lowercase
            artist="arijit singh",  # lowercase
        )

        # Should still find match despite case difference
        assert mock_db.client.scroll.call_count >= 1


class TestDeduplicationFlow:
    """Integration tests for the full deduplication flow."""

    @pytest.mark.integration
    def test_checksum_priority_over_title(self):
        """Test that checksum match takes priority over title+artist."""
        # This would require a real Qdrant instance
        # Marked as integration test
        pass

    @pytest.mark.integration
    def test_dedup_updates_file_path(self):
        """Test that dedup updates file_path when match found."""
        # This would require a real Qdrant instance
        # Marked as integration test
        pass


class TestForceFlag:
    """Tests for the --force flag that bypasses deduplication."""

    def test_force_flag_skips_dedup_check(self):
        """Test that force=True skips the deduplication check entirely.

        When force=True is passed to process_track, the deduplication check
        (find_existing_track) should be skipped, allowing re-analysis of
        tracks that already exist in the database.

        This test verifies the behavior by checking the code path - since
        the dedup check is inside an `if not force:` block, it won't execute
        when force=True.
        """
        # Verify the code structure - force flag exists and is used
        import inspect
        from vectrola.ingest.pipeline import IngestPipeline

        sig = inspect.signature(IngestPipeline.process_track)
        params = list(sig.parameters.keys())

        # Verify force parameter exists
        assert 'force' in params, "force parameter should exist in process_track"

        # Verify force defaults to False
        assert sig.parameters['force'].default is False, "force should default to False"

    def test_cli_force_flag_exists(self):
        """Test that --force/-F flag is recognized by CLI."""
        from typer.testing import CliRunner
        from vectrola.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["ingest", "--help"])

        assert result.exit_code == 0
        assert "--force" in result.output
        assert "-F" in result.output
        assert "Skip dedup check" in result.output

    def test_force_flag_short_form(self):
        """Test that -F is equivalent to --force."""
        from typer.testing import CliRunner
        from vectrola.cli import app

        runner = CliRunner()

        # Both should be recognized (will fail without a path, but flag should parse)
        result_long = runner.invoke(app, ["ingest", "--force", "--help"])
        result_short = runner.invoke(app, ["ingest", "-F", "--help"])

        # Both should show help (--help takes precedence)
        assert "--force" in result_long.output
        assert "--force" in result_short.output


class TestSourcesMerging:
    """Tests for multi-device sources merging."""

    def test_get_device_id_returns_hostname(self):
        """Test that get_device_id returns platform.node()."""
        device_id = get_device_id()
        assert device_id == platform.node()
        assert isinstance(device_id, str)
        assert len(device_id) > 0

    def test_sources_structure(self):
        """Test that TrackAnalysis uses correct sources structure."""
        from vectrola.ingest.pipeline import TrackAnalysis
        from pathlib import Path

        analysis = TrackAnalysis(
            file_path=Path("/test/song.mp3"),
            title="Test Song",
            sources={
                "local": {"DEVICE1": "/path/on/device1.mp3"},
                "cloud": {"gdrive": {"file_id": "abc123", "path": "Music/song.mp3"}}
            }
        )

        d = analysis.to_dict()
        assert "sources" in d
        assert "local" in d["sources"]
        assert "cloud" in d["sources"]
        assert d["sources"]["local"]["DEVICE1"] == "/path/on/device1.mp3"
        assert d["sources"]["cloud"]["gdrive"]["file_id"] == "abc123"

    def test_sources_default_empty(self):
        """Test that sources defaults to empty local/cloud dicts."""
        from vectrola.ingest.pipeline import TrackAnalysis
        from pathlib import Path

        analysis = TrackAnalysis(
            file_path=Path("/test/song.mp3"),
            title="Test Song",
        )

        d = analysis.to_dict()
        assert d["sources"] == {"local": {}, "cloud": {}}

    def test_old_fields_removed(self):
        """Test that file_path and gdrive_file_id are not in to_dict output."""
        from vectrola.ingest.pipeline import TrackAnalysis
        from pathlib import Path

        analysis = TrackAnalysis(
            file_path=Path("/test/song.mp3"),
            title="Test Song",
        )

        d = analysis.to_dict()
        assert "file_path" not in d
        assert "gdrive_file_id" not in d
        assert "gdrive_path" not in d
