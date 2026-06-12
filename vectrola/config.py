"""Configuration settings for Vectrola."""

from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Tuple
import os
import uuid
import json

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


def get_current_user() -> Tuple[str, bool]:
    """
    Get current user ID and login status.

    Returns:
        (user_id, is_logged_in) tuple

    Priority:
    1. VECTROLA_USER_ID env var (for testing/CI)
    2. session.json (logged-in user)
    3. anon_id file (anonymous, generated if missing)
    """
    # 1. Env var override
    env_user = os.getenv("VECTROLA_USER_ID")
    if env_user:
        return (env_user, True)

    config_dir = Path.home() / ".config" / "vectrola"

    # 2. Check for logged-in session
    session_path = config_dir / "session.json"
    if session_path.exists():
        try:
            session = json.loads(session_path.read_text())
            if session.get("user_id"):
                return (session["user_id"], True)
        except (json.JSONDecodeError, KeyError):
            pass

    # 3. Anonymous user
    anon_path = config_dir / "anon_id"
    if anon_path.exists():
        anon_id = anon_path.read_text().strip()
        if anon_id:
            return (anon_id, False)

    # Generate new anonymous ID
    anon_id = f"anon_{uuid.uuid4().hex[:12]}"
    config_dir.mkdir(parents=True, exist_ok=True)
    anon_path.write_text(anon_id)

    return (anon_id, False)


def get_or_create_user_id() -> str:
    """
    Get user ID from config/env, or auto-generate and persist.

    DEPRECATED: Use get_current_user() instead which also returns login status.

    Priority:
    1. VECTROLA_USER_ID environment variable
    2. Stored user_id file (~/.config/vectrola/user_id)
    3. Auto-generate and persist new user_id

    Returns:
        User ID string (e.g., "user_abc123def456")
    """
    # Use new function but return just the user_id for backwards compatibility
    user_id, _ = get_current_user()
    return user_id
