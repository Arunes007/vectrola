"""LLM-based semantic synthesis with multiple provider support."""

import json
from abc import ABC, abstractmethod
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


# =============================================================================
# LLM Client Abstraction
# =============================================================================


class LLMClient(ABC):
    """Abstract base class for LLM clients."""

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Generate a response for the given prompt."""
        pass


class OllamaClient(LLMClient):
    """Ollama LLM client (local, free)."""

    def __init__(self, model: str = "llama3.2:1b", host: str = "http://localhost:11434"):
        self.model = model
        self.host = host

    def generate(self, prompt: str) -> str:
        import ollama
        response = ollama.generate(model=self.model, prompt=prompt, format="json")
        return response["response"]


class OpenAIClient(LLMClient):
    """OpenAI LLM client (cloud, paid)."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        from openai import OpenAI
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def generate(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content


class AnthropicClient(LLMClient):
    """Anthropic LLM client (cloud, paid)."""

    def __init__(self, api_key: str, model: str = "claude-3-haiku-20240307"):
        import anthropic
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def generate(self, prompt: str) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text


def get_llm_client() -> Optional[LLMClient]:
    """
    Get LLM client based on config.

    Returns:
        LLMClient instance or None if LLM is disabled
    """
    config = get_config()

    if config.llm_provider == "ollama":
        return OllamaClient(model=config.llm_model or "llama3.2:1b", host=config.ollama_host)
    elif config.llm_provider == "openai":
        if not config.llm_api_key:
            raise ValueError("OpenAI API key not configured. Run 'vectrola setup' or set OPENAI_API_KEY.")
        return OpenAIClient(api_key=config.llm_api_key, model=config.llm_model or "gpt-4o-mini")
    elif config.llm_provider == "anthropic":
        if not config.llm_api_key:
            raise ValueError("Anthropic API key not configured. Run 'vectrola setup' or set ANTHROPIC_API_KEY.")
        return AnthropicClient(api_key=config.llm_api_key, model=config.llm_model or "claude-3-haiku-20240307")
    elif config.llm_provider == "none":
        return None
    else:
        # Default to Ollama for backwards compatibility
        return OllamaClient(model=config.ollama_model)


# =============================================================================
# Synthesizer
# =============================================================================


class Synthesizer:
    """Extract semantic metadata from lyrics using configurable LLM."""

    def __init__(self, model: Optional[str] = None, host: Optional[str] = None):
        """
        Initialize the synthesizer.

        Args:
            model: Model name (overrides config)
            host: API host URL (Ollama only)
        """
        config = get_config()

        # Allow model/host override for backwards compatibility
        if model or host:
            self.client = OllamaClient(
                model=model or config.ollama_model,
                host=host or config.ollama_host
            )
        else:
            self.client = get_llm_client()

    def synthesize(self, lyrics: str, max_lyrics_length: int = 3000) -> SynthesisResult:
        """
        Extract themes, moods, and narrative from lyrics.

        Args:
            lyrics: Song lyrics text
            max_lyrics_length: Maximum characters of lyrics to send

        Returns:
            SynthesisResult with extracted semantic metadata
        """
        # If LLM is disabled, return placeholder
        if self.client is None:
            return SynthesisResult(
                themes=["[llm-disabled]"],
                moods=["[llm-disabled]"],
                narrative="LLM analysis disabled. Run 'vectrola setup' to configure.",
                imagery=[],
                raw_response="",
            )

        # Truncate lyrics if too long
        truncated_lyrics = lyrics[:max_lyrics_length]
        prompt = SYNTHESIS_PROMPT.format(lyrics=truncated_lyrics)

        try:
            raw_response = self.client.generate(prompt)

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
            # If JSON parsing fails, return empty result
            return SynthesisResult(
                themes=[],
                moods=[],
                narrative="",
                imagery=[],
                raw_response=raw_response if 'raw_response' in dir() else "",
            )

        except Exception as e:
            error_msg = str(e)

            # Handle model not found
            if "not found" in error_msg.lower() or "404" in error_msg:
                config = get_config()
                return SynthesisResult(
                    themes=["[model-not-found]"],
                    moods=["[model-not-found]"],
                    narrative=f"Model '{config.llm_model}' not found. Run 'ollama pull {config.llm_model}' or 'vectrola setup' to fix.",
                    imagery=[],
                    raw_response=error_msg,
                )

            # Handle connection errors
            if "Connection" in error_msg or "refused" in error_msg.lower():
                config = get_config()
                provider = config.llm_provider or "ollama"
                return SynthesisResult(
                    themes=[f"[{provider}-unavailable]"],
                    moods=[f"[{provider}-unavailable]"],
                    narrative=f"{provider.title()} LLM not available. Check your configuration.",
                    imagery=[],
                    raw_response=error_msg,
                )

            return SynthesisResult(
                themes=["[llm-error]"],
                moods=["[llm-error]"],
                narrative=f"LLM Error: {error_msg}",
                imagery=[],
                raw_response=error_msg,
            )


# Convenience function
def synthesize_lyrics(lyrics: str) -> SynthesisResult:
    """Synthesize semantic metadata from lyrics using configured LLM."""
    synthesizer = Synthesizer()
    return synthesizer.synthesize(lyrics)
