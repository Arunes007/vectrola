"""Tests for embeddings module."""

import pytest


class TestTextEmbedder:
    """Tests for TextEmbedder class."""

    @pytest.fixture
    def embedder(self):
        """Create embedder instance (slow - loads model)."""
        from vectrola.ingest.embeddings import TextEmbedder
        return TextEmbedder()

    def test_vector_size(self, embedder):
        """Test that embeddings have correct dimensions."""
        vec = embedder.embed("test sentence")
        assert len(vec) == 384

    def test_embed_empty_string(self, embedder):
        """Test embedding empty string returns zero vector."""
        vec = embedder.embed("")
        assert len(vec) == 384
        assert all(v == 0.0 for v in vec)

    def test_embed_whitespace(self, embedder):
        """Test embedding whitespace returns zero vector."""
        vec = embedder.embed("   ")
        assert len(vec) == 384
        assert all(v == 0.0 for v in vec)

    def test_embed_hindi_text(self, embedder):
        """Test that Hindi text can be embedded."""
        hindi_text = "यादों की कैद में गिरफ्तार हो गया दिल"
        vec = embedder.embed(hindi_text)

        assert len(vec) == 384
        # Should NOT be all zeros
        assert not all(v == 0.0 for v in vec)

    def test_embed_english_text(self, embedder):
        """Test that English text can be embedded."""
        vec = embedder.embed("This is a sad melancholic song")

        assert len(vec) == 384
        assert not all(v == 0.0 for v in vec)

    def test_similar_texts_have_similar_embeddings(self, embedder):
        """Test that similar texts produce similar embeddings."""
        import numpy as np

        vec1 = embedder.embed("sad melancholic song about heartbreak")
        vec2 = embedder.embed("melancholic sad music about lost love")
        vec3 = embedder.embed("happy upbeat party dance music")

        # Cosine similarity
        def cosine_sim(a, b):
            return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

        sim_12 = cosine_sim(vec1, vec2)  # Similar texts
        sim_13 = cosine_sim(vec1, vec3)  # Different texts

        assert sim_12 > sim_13  # Similar texts should be more similar

    def test_embed_batch(self, embedder):
        """Test batch embedding."""
        texts = ["hello world", "goodbye world", ""]
        vecs = embedder.embed_batch(texts)

        assert len(vecs) == 3
        assert len(vecs[0]) == 384
        assert len(vecs[1]) == 384
        assert len(vecs[2]) == 384
        # Empty text should be zero vector
        assert all(v == 0.0 for v in vecs[2])

    def test_embed_batch_empty(self, embedder):
        """Test batch embedding with empty list."""
        vecs = embedder.embed_batch([])
        assert vecs == []


class TestMultilingualSupport:
    """Tests for multilingual embedding support."""

    @pytest.fixture
    def embedder(self):
        from vectrola.ingest.embeddings import TextEmbedder
        return TextEmbedder()

    def test_hindi_english_similarity(self, embedder):
        """Test that Hindi lyrics match English mood queries."""
        import numpy as np

        # Hindi lyrics about sadness/longing
        hindi = "यादों की कैद में गिरफ्तार हो गया दिल दरबदर इश्क में तार तार हो गया दिल"
        english_query = "sad melancholic song about memories and love"

        hindi_vec = embedder.embed(hindi)
        eng_vec = embedder.embed(english_query)

        similarity = np.dot(hindi_vec, eng_vec) / (np.linalg.norm(hindi_vec) * np.linalg.norm(eng_vec))

        # Multilingual model should give reasonable similarity
        assert similarity > 0.3, f"Hindi-English similarity too low: {similarity}"
