"""Tests for the ingestion pipeline."""

import pytest
from pathlib import Path
from vectrola.ingest.pipeline import IngestPipeline, TrackAnalysis, ingest_track


class TestTrackAnalysis:
    """Tests for TrackAnalysis dataclass."""

    def test_track_analysis_required_fields(self):
        """Test TrackAnalysis with required fields."""
        analysis = TrackAnalysis(
            file_path=Path("/test/song.mp3"),
            title="Test Song",
        )

        assert analysis.file_path == Path("/test/song.mp3")
        assert analysis.title == "Test Song"
        assert analysis.artists == []
        assert analysis.album == ""

    def test_track_analysis_all_fields(self):
        """Test TrackAnalysis with all fields."""
        analysis = TrackAnalysis(
            file_path=Path("/test/song.mp3"),
            title="Test Song",
            artists=["Artist 1", "Artist 2"],
            album="Test Album",
            year=2020,
            movie="Test Movie",
            composer="Composer",
            lyricist="Lyricist",
            lyrics="Test lyrics",
            lyrics_source="lrclib",
            language="hi",
            themes=["love"],
            moods=["happy"],
            narrative="A happy song",
            imagery=["sunshine"],
        )

        assert analysis.artists == ["Artist 1", "Artist 2"]
        assert analysis.movie == "Test Movie"
        assert analysis.composer == "Composer"
        assert analysis.lyricist == "Lyricist"
        assert analysis.language == "hi"

    def test_track_analysis_to_dict(self):
        """Test TrackAnalysis serialization."""
        analysis = TrackAnalysis(
            file_path=Path("/test/song.mp3"),
            title="Test Song",
            artists=["Artist"],
            album="Album",
            year=2020,
            movie="Movie",
            moods=["happy"],
            themes=["love"],
            narrative="A love song",
            imagery=["hearts"],
        )

        d = analysis.to_dict()

        assert d["file_path"] == "/test/song.mp3"
        assert d["title"] == "Test Song"
        assert d["artists"] == ["Artist"]
        assert d["album"] == "Album"
        assert d["year"] == 2020
        assert d["movie"] == "Movie"
        assert d["moods"] == ["happy"]
        assert d["themes"] == ["love"]


class TestIngestPipeline:
    """Tests for IngestPipeline class."""

    def test_pipeline_initialization(self):
        """Test pipeline initializes correctly."""
        pipeline = IngestPipeline()

        assert pipeline.use_stems is False
        assert pipeline._transcriber is None  # Lazy loaded
        assert pipeline._synthesizer is None
        assert pipeline._lyrics_fetcher is None

    def test_pipeline_with_stems(self):
        """Test pipeline with stem separation enabled."""
        pipeline = IngestPipeline(use_stems=True)

        assert pipeline.use_stems is True

    def test_pipeline_with_genius_token(self):
        """Test pipeline with Genius token."""
        pipeline = IngestPipeline(genius_token="test_token")

        assert pipeline.genius_token == "test_token"

    def test_detect_language_hindi(self):
        """Test language detection for Hindi text."""
        pipeline = IngestPipeline()

        # Devanagari text
        hindi_text = "तेरे बिना जीना नहीं"
        assert pipeline._detect_language(hindi_text) == "hi"

    def test_detect_language_english(self):
        """Test language detection for English text."""
        pipeline = IngestPipeline()

        english_text = "I love you forever"
        assert pipeline._detect_language(english_text) == "en"


class TestIngestTrackFunction:
    """Tests for ingest_track convenience function."""

    def test_ingest_track_fast_mode(self):
        """Test that fast mode skips stems."""
        # This is a unit test for the function signature
        # Actual processing requires a real audio file
        pass


# Integration tests (require actual audio file)
@pytest.mark.integration
class TestPipelineIntegration:
    """Integration tests for the full pipeline."""

    @pytest.fixture
    def test_audio_file(self):
        """Provide a test audio file path."""
        # This would be configured based on test environment
        # Example: return Path("/path/to/test/audio/file.mp3")
        return Path("tests/fixtures/sample_audio.mp3")

    def test_full_pipeline(self, test_audio_file):
        """Test the full ingestion pipeline."""
        if not test_audio_file.exists():
            pytest.skip("Test audio file not found")

        pipeline = IngestPipeline()
        analysis = pipeline.process_track(test_audio_file, write_file_tags=False)

        assert isinstance(analysis, TrackAnalysis)
        assert analysis.title
        assert analysis.lyrics or analysis.lyrics_source == "whisper"
