"""LLM-based semantic synthesis using Ollama."""

import json
from dataclasses import dataclass
from typing import Optional

from vectrola.config import get_config


@dataclass
class SynthesisResult:
    """Result of LLM semantic analysis."""

    themes: list[str]
    moods: list[str]
    narrative: str
    imagery: list[str]
    raw_response: str


SYNTHESIS_PROMPT = """Analyze these song lyrics and return a JSON object with:
- "themes": list of 3-5 abstract themes (e.g., "mortality", "urban isolation", "longing", "rebellion")
- "moods": list of 2-3 mood tags (e.g., "melancholic", "euphoric", "aggressive", "introspective")
- "narrative": one sentence describing the song's story arc or emotional journey
- "imagery": list of 2-3 visual images or scenes evoked by the lyrics

Lyrics:
{lyrics}

Return ONLY valid JSON, no explanation or markdown."""


class Synthesizer:
    """Extract semantic metadata from lyrics using Ollama."""

    def __init__(self, model: Optional[str] = None, host: Optional[str] = None):
        """
        Initialize the synthesizer.

        Args:
            model: Ollama model name (e.g., llama3, mistral)
            host: Ollama API host URL
        """
        config = get_config()
        self.model = model or config.ollama_model
        self.host = host or config.ollama_host

    def synthesize(self, lyrics: str, max_lyrics_length: int = 3000) -> SynthesisResult:
        """
        Extract themes, moods, and narrative from lyrics.

        Args:
            lyrics: Song lyrics text
            max_lyrics_length: Maximum characters of lyrics to send

        Returns:
            SynthesisResult with extracted semantic metadata
        """
        import ollama

        # Truncate lyrics if too long
        truncated_lyrics = lyrics[:max_lyrics_length]

        prompt = SYNTHESIS_PROMPT.format(lyrics=truncated_lyrics)

        try:
            response = ollama.generate(
                model=self.model,
                prompt=prompt,
                format="json",
            )
            raw_response = response["response"]

            # Parse JSON response
            data = json.loads(raw_response)

            return SynthesisResult(
                themes=data.get("themes", []),
                moods=data.get("moods", []),
                narrative=data.get("narrative", ""),
                imagery=data.get("imagery", []),
                raw_response=raw_response,
            )

        except json.JSONDecodeError:
            # If JSON parsing fails, return empty result with raw response
            return SynthesisResult(
                themes=[],
                moods=[],
                narrative=response.get("response", ""),
                imagery=[],
                raw_response=response.get("response", ""),
            )

        except Exception as e:
            # Handle connection errors, etc.
            error_msg = str(e)

            # If Ollama is not available, return a placeholder
            if "Connection" in error_msg or "refused" in error_msg.lower():
                return SynthesisResult(
                    themes=["[ollama-unavailable]"],
                    moods=["[ollama-unavailable]"],
                    narrative="Ollama LLM not available. Install and run 'ollama serve' then 'ollama pull llama3'",
                    imagery=[],
                    raw_response=error_msg,
                )

            return SynthesisResult(
                themes=[],
                moods=[],
                narrative=f"Error: {error_msg}",
                imagery=[],
                raw_response=error_msg,
            )


# Convenience function
def synthesize_lyrics(lyrics: str) -> SynthesisResult:
    """Synthesize semantic metadata from lyrics using default settings."""
    synthesizer = Synthesizer()
    return synthesizer.synthesize(lyrics)
