"""Tests for Ollama synthesis module."""

import pytest
from vectrola.ingest.synthesis import Synthesizer, SynthesisResult


# Mark tests that require Ollama to be running
pytestmark = pytest.mark.ollama


class TestSynthesizer:
    """Tests for Synthesizer class."""

    @pytest.fixture
    def synthesizer(self):
        """Create a synthesizer instance."""
        return Synthesizer()

    def test_synthesize_returns_result(self, synthesizer):
        """Test that synthesize returns a SynthesisResult."""
        lyrics = """
        I'm walking down the street alone
        Rain is falling on my face
        Memories of you still haunt me
        In this cold and empty place
        """

        result = synthesizer.synthesize(lyrics)

        assert isinstance(result, SynthesisResult)

    def test_synthesize_extracts_themes(self, synthesizer):
        """Test that themes are extracted."""
        lyrics = """
        Time keeps on slipping away
        We grow old and fade to gray
        Nothing lasts forever they say
        But love remains, come what may
        """

        result = synthesizer.synthesize(lyrics)

        assert result.themes is not None
        assert isinstance(result.themes, list)
        # Should extract themes like mortality, time, love

    def test_synthesize_extracts_moods(self, synthesizer):
        """Test that moods are extracted."""
        lyrics = """
        Dancing in the moonlight
        Everything is feeling right
        Joy is filling up my heart
        Tonight we'll never be apart
        """

        result = synthesizer.synthesize(lyrics)

        assert result.moods is not None
        assert isinstance(result.moods, list)
        # Should be positive moods

    def test_synthesize_extracts_narrative(self, synthesizer):
        """Test that narrative summary is extracted."""
        lyrics = """
        Yesterday you were here
        Today you're gone
        I search for you everywhere
        But you've moved on
        """

        result = synthesizer.synthesize(lyrics)

        assert result.narrative is not None
        assert isinstance(result.narrative, str)
        assert len(result.narrative) > 10  # Should be a sentence

    def test_synthesize_extracts_imagery(self, synthesizer):
        """Test that imagery is extracted."""
        lyrics = """
        Standing by the ocean blue
        Watching waves crash on the shore
        Seagulls flying overhead
        Sunset painting sky with red
        """

        result = synthesizer.synthesize(lyrics)

        assert result.imagery is not None
        assert isinstance(result.imagery, list)

    def test_synthesize_handles_empty_lyrics(self, synthesizer):
        """Test that empty lyrics are handled gracefully."""
        result = synthesizer.synthesize("")

        assert isinstance(result, SynthesisResult)
        # Should return empty/default values, not crash

    def test_synthesize_handles_hindi_lyrics(self, synthesizer):
        """Test that Hindi lyrics are processed correctly."""
        lyrics = """
        तेरे बिना जीना नहीं
        तेरे बिना मरना नहीं
        तू ही मेरी दुनिया है
        तू ही मेरा सब कुछ है
        """

        result = synthesizer.synthesize(lyrics)

        assert isinstance(result, SynthesisResult)
        assert result.themes is not None or result.moods is not None

    def test_synthesis_result_dataclass(self):
        """Test SynthesisResult dataclass."""
        result = SynthesisResult(
            themes=["love", "longing"],
            moods=["melancholic", "hopeful"],
            narrative="A story of lost love",
            imagery=["rain", "empty streets"],
        )

        assert result.themes == ["love", "longing"]
        assert result.moods == ["melancholic", "hopeful"]
        assert result.narrative == "A story of lost love"
        assert result.imagery == ["rain", "empty streets"]
