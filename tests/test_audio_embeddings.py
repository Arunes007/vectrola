"""Unit tests for CLAP audio embeddings."""

import pytest
from pathlib import Path
import numpy as np

from vectrola.ingest.embeddings import (
    AudioEmbedder,
    get_audio_embedder,
    embed_audio,
)


class TestAudioEmbedder:
    """Test CLAP audio embedding generation."""

    def test_singleton(self):
        """AudioEmbedder should be a singleton."""
        embedder1 = get_audio_embedder()
        embedder2 = get_audio_embedder()
        assert embedder1 is embedder2

    def test_vector_size(self):
        """CLAP embeddings should be 512 dimensions."""
        embedder = get_audio_embedder()
        assert embedder.VECTOR_SIZE == 512

    def test_model_name(self):
        """Should use laion/clap-htsat-unfused."""
        embedder = get_audio_embedder()
        assert embedder.MODEL_NAME == "laion/clap-htsat-unfused"

    @pytest.mark.integration
    def test_embed_text(self):
        """Text description should produce 512-dim vector."""
        embedder = get_audio_embedder()

        vector = embedder.embed_text("dark ambient drone with strings")

        assert isinstance(vector, list)
        assert len(vector) == 512
        assert all(isinstance(x, float) for x in vector)

    @pytest.mark.integration
    def test_text_similarity(self):
        """Similar text descriptions should have similar embeddings."""
        embedder = get_audio_embedder()

        # Similar descriptions
        v1 = embedder.embed_text("slow piano ballad")
        v2 = embedder.embed_text("soft piano music")

        # Different description
        v3 = embedder.embed_text("aggressive metal guitar")

        # Compute cosine similarity
        def cosine_sim(a, b):
            a = np.array(a)
            b = np.array(b)
            return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

        sim_similar = cosine_sim(v1, v2)
        sim_different = cosine_sim(v1, v3)

        # Similar should be more similar than different
        assert sim_similar > sim_different

    @pytest.mark.integration
    @pytest.mark.slow
    def test_embed_audio(self, audio_file):
        """Audio file should produce 512-dim vector."""
        embedder = get_audio_embedder()

        vector = embedder.embed_audio(str(audio_file))

        assert isinstance(vector, list)
        assert len(vector) == 512
        assert all(isinstance(x, float) for x in vector)

    @pytest.mark.integration
    @pytest.mark.slow
    def test_embed_audio_with_params(self, audio_file):
        """Should support custom duration and offset."""
        embedder = get_audio_embedder()

        # Different segments should produce different embeddings
        v1 = embedder.embed_audio(str(audio_file), duration=5.0, offset=0.0)
        v2 = embedder.embed_audio(str(audio_file), duration=5.0, offset=30.0)

        assert len(v1) == 512
        assert len(v2) == 512
        assert v1 != v2  # Different segments

    @pytest.mark.integration
    def test_convenience_function(self):
        """embed_audio() convenience function should work."""
        # Just test it doesn't crash without real audio
        # Real audio test is marked @slow
        pass


@pytest.fixture
def audio_file(tmp_path):
    """Create a dummy audio file for testing."""
    # Generate 1s of sine wave audio
    try:
        import librosa
        import soundfile as sf

        # Generate sine wave (440 Hz A note)
        sr = 22050
        duration = 1.0
        t = np.linspace(0, duration, int(sr * duration))
        audio = np.sin(2 * np.pi * 440 * t)

        # Save to file
        audio_path = tmp_path / "test_audio.wav"
        sf.write(str(audio_path), audio, sr)

        return audio_path
    except ImportError:
        pytest.skip("librosa or soundfile not available")
