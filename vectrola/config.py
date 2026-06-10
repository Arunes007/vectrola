"""Configuration settings for Vectrola."""

from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
import os

# Load environment variables from .env file if it exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # python-dotenv not installed, environment variables can still be set manually
    pass


@dataclass
class VectrolaConfig:
    """Global configuration for Vectrola."""

    # Paths
    wiki_dir: Path = field(default_factory=lambda: Path("./wiki"))
    cache_dir: Path = field(default_factory=lambda: Path("./.vectrola_cache"))

    # Whisper settings
    whisper_model: str = "base"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"

    # Ollama settings
    ollama_model: str = "qwen2.5:3b"
    ollama_host: str = "http://localhost:11434"

    # Qdrant settings
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "vectrola_library"

    # Audio processing
    audio_sample_rate: int = 48000
    audio_segment_duration: int = 10  # seconds
    audio_segment_offset: int = 30  # seconds from start

    # Optional features
    use_demucs: bool = False  # Stem separation (slow)


# Global config instance
config = VectrolaConfig()


def get_config() -> VectrolaConfig:
    """Get the global configuration."""
    return config
