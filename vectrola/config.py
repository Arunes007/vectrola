"""Configuration settings for Vectrola."""

from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
import os
import uuid

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
    qdrant_url: str = field(
        default_factory=lambda: os.getenv("QDRANT_URL", "http://localhost:6333")
    )
    qdrant_collection: str = "vectrola_library"
    qdrant_api_key: Optional[str] = field(
        default_factory=lambda: os.getenv("QDRANT_API_KEY")
    )

    # Audio processing
    audio_sample_rate: int = 48000
    audio_segment_duration: int = 10  # seconds
    audio_segment_offset: int = 30  # seconds from start

    # Optional features
    use_demucs: bool = False  # Stem separation (slow)

    # Google Drive settings
    gdrive_token_path: Path = field(
        default_factory=lambda: Path.home() / ".config" / "vectrola" / "gdrive_token.json"
    )
    gdrive_cache_dir: Path = field(
        default_factory=lambda: Path("./.vectrola_cache/gdrive")
    )

    # Multi-tenant settings (Day 7)
    user_id: Optional[str] = field(
        default_factory=lambda: os.getenv("VECTROLA_USER_ID")
    )
    multi_tenant: bool = field(
        default_factory=lambda: os.getenv("VECTROLA_MULTI_TENANT", "").lower() == "true"
    )


# Global config instance
config = VectrolaConfig()


def get_config() -> VectrolaConfig:
    """Get the global configuration."""
    return config


def get_or_create_user_id() -> str:
    """
    Get user ID from config/env, or auto-generate and persist.

    Priority:
    1. VECTROLA_USER_ID environment variable
    2. Stored user_id file (~/.config/vectrola/user_id)
    3. Auto-generate and persist new user_id

    Returns:
        User ID string (e.g., "user_abc123def456")
    """
    cfg = get_config()

    # 1. Check env/config
    if cfg.user_id:
        return cfg.user_id

    # 2. Check stored user_id file
    user_id_path = Path.home() / ".config" / "vectrola" / "user_id"
    if user_id_path.exists():
        stored_id = user_id_path.read_text().strip()
        if stored_id:
            return stored_id

    # 3. Generate new user_id and persist
    new_user_id = f"user_{uuid.uuid4().hex[:12]}"
    user_id_path.parent.mkdir(parents=True, exist_ok=True)
    user_id_path.write_text(new_user_id)

    return new_user_id
