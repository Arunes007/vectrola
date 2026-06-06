"""Tests for semantic search module."""

import pytest


class TestSearchResult:
    """Tests for SearchResult dataclass."""

    def test_search_result_str(self):
        """Test SearchResult string representation."""
        from vectrola.search.semantic import SearchResult

        result = SearchResult(
            file_path="/path/to/song.mp3",
            title="Test Song",
            artists=["Artist 1", "Artist 2"],
            album="Test Album",
            movie="",
            score=0.85,
            moods=["happy"],
            themes=["love"],
            narrative="A happy song",
            lyrics_preview="La la la...",
        )

        str_repr = str(result)
        assert "Artist 1, Artist 2" in str_repr
        assert "Test Song" in str_repr
        assert "0.85" in str_repr

    def test_search_result_no_artists(self):
        """Test SearchResult with no artists."""
        from vectrola.search.semantic import SearchResult

        result = SearchResult(
            file_path="/path/to/song.mp3",
            title="Test Song",
            artists=[],
            album="",
            movie="",
            score=0.5,
            moods=[],
            themes=[],
            narrative="",
            lyrics_preview="",
        )

        str_repr = str(result)
        assert "Unknown" in str_repr


class TestSemanticSearch:
    """Tests for SemanticSearch class."""

    def test_search_initialization(self):
        """Test SemanticSearch can be initialized."""
        from vectrola.search.semantic import SemanticSearch

        searcher = SemanticSearch()
        assert searcher._db is None  # Lazy loaded
        assert searcher._text_embedder is None  # Lazy loaded


@pytest.mark.integration
class TestSemanticSearchIntegration:
    """Integration tests requiring Qdrant and embeddings model."""

    @pytest.fixture
    def searcher(self):
        """Create a searcher instance."""
        from vectrola.search.semantic import SemanticSearch
        return SemanticSearch()

    def test_search_returns_results(self, searcher):
        """Test that search returns results."""
        results = searcher.search("melancholic sad song", limit=5)

        assert isinstance(results, list)
        # May be empty if DB is empty

    def test_search_with_low_threshold(self, searcher):
        """Test search with low score threshold."""
        results = searcher.search(
            "test query",
            limit=10,
            score_threshold=0.1,  # Very low threshold
        )

        assert isinstance(results, list)

    def test_search_results_have_required_fields(self, searcher):
        """Test that search results have all required fields."""
        from vectrola.search.semantic import SearchResult

        results = searcher.search("love song", limit=1)

        if results:  # Only test if we have results
            result = results[0]
            assert isinstance(result, SearchResult)
            assert hasattr(result, 'title')
            assert hasattr(result, 'artists')
            assert hasattr(result, 'score')
            assert hasattr(result, 'moods')
            assert hasattr(result, 'themes')
