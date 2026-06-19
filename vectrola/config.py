"""Configuration settings for Vectrola."""

from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Tuple
import os
import uuid
import json
import platform


def get_device_id() -> str:
    """
    Get unique device identifier (hostname).

    Used for multi-device source tracking in the sources schema.

    Returns:
        Device hostname (e.g., "My-Macbook", "iPhone-Arun")
    """
    return platform.node()

# Load environment variables from .env file if it exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # python-dotenv not installed, environment variables can still be set manually
    pass


# Config file path
CONFIG_PATH = Path.home() / ".config" / "vectrola" / "config.json"


@dataclass
class VectrolaConfig:
    """Global configuration for Vectrola."""

    # Paths
    wiki_dir: Path = field(default_factory=lambda: Path("./wiki"))
    cache_dir: Path = field(default_factory=lambda: Path("./.vectrola_cache"))

    # Storage settings
    storage_mode: str = "local"  # "local" | "remote"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: Optional[str] = None
    qdrant_collection: str = "vectrola_library"

    # LLM settings
    llm_provider: str = "ollama"  # "ollama" | "openai" | "anthropic" | "none"
    llm_model: str = "llama3.2:1b"
    llm_api_key: Optional[str] = None

    # Legacy Ollama settings (for backwards compatibility)
    ollama_model: str = "qwen2.5:3b"
    ollama_host: str = "http://localhost:11434"

    # Whisper settings
    whisper_model: str = "base"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"

    # Audio processing
    audio_sample_rate: int = 48000
    audio_segment_duration: int = 10  # seconds
    audio_segment_offset: int = 30  # seconds from start

    # Optional features
    use_demucs: bool = False  # Stem separation (slow)

    # Google Drive settings
    gdrive_enabled: bool = False
    gdrive_token_path: Path = field(
        default_factory=lambda: Path.home() / ".config" / "vectrola" / "gdrive_token.json"
    )
    gdrive_cache_dir: Path = field(
        default_factory=lambda: Path("./.vectrola_cache/gdrive")
    )

    # User settings
    user_mode: str = "anonymous"  # "anonymous" | "login"
    user_id: Optional[str] = None
    multi_tenant: bool = False


def load_config() -> VectrolaConfig:
    """
    Load config with priority: env > config.json > defaults.

    Returns:
        VectrolaConfig with merged settings
    """
    config = VectrolaConfig()

    # 1. Load from config.json if exists
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text())

            # Storage settings
            if "storage" in data:
                config.storage_mode = data["storage"].get("mode", "local")
                config.qdrant_url = data["storage"].get("qdrant_url", config.qdrant_url)
                config.qdrant_api_key = data["storage"].get("qdrant_api_key")

            # LLM settings
            if "llm" in data:
                config.llm_provider = data["llm"].get("provider", "ollama")
                config.llm_model = data["llm"].get("model", "llama3.2:1b")
                config.llm_api_key = data["llm"].get("api_key")
                # Keep ollama_model in sync for backwards compatibility
                if config.llm_provider == "ollama":
                    config.ollama_model = config.llm_model

            # GDrive settings
            if "gdrive" in data:
                config.gdrive_enabled = data["gdrive"].get("enabled", False)

            # User settings
            if "user" in data:
                config.user_mode = data["user"].get("mode", "anonymous")
                config.multi_tenant = data["user"].get("multi_tenant", False)

        except (json.JSONDecodeError, KeyError):
            pass

    # 2. Override with environment variables (highest priority)
    if os.getenv("QDRANT_URL"):
        config.qdrant_url = os.getenv("QDRANT_URL")
        # If URL is not localhost, assume remote mode
        if "localhost" not in config.qdrant_url and "127.0.0.1" not in config.qdrant_url:
            config.storage_mode = "remote"
    if os.getenv("QDRANT_API_KEY"):
        config.qdrant_api_key = os.getenv("QDRANT_API_KEY")
    if os.getenv("VECTROLA_USER_ID"):
        config.user_id = os.getenv("VECTROLA_USER_ID")
    if os.getenv("VECTROLA_MULTI_TENANT", "").lower() == "true":
        config.multi_tenant = True
    if os.getenv("OPENAI_API_KEY"):
        config.llm_provider = "openai"
        config.llm_api_key = os.getenv("OPENAI_API_KEY")
    if os.getenv("ANTHROPIC_API_KEY"):
        config.llm_provider = "anthropic"
        config.llm_api_key = os.getenv("ANTHROPIC_API_KEY")

    return config


def save_config(config: VectrolaConfig) -> None:
    """
    Save config to ~/.config/vectrola/config.json.

    Args:
        config: VectrolaConfig to save
    """
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "version": 1,
        "storage": {
            "mode": config.storage_mode,
            "qdrant_url": config.qdrant_url,
            "qdrant_api_key": config.qdrant_api_key,
        },
        "llm": {
            "provider": config.llm_provider,
            "model": config.llm_model,
            "api_key": config.llm_api_key,
        },
        "gdrive": {
            "enabled": config.gdrive_enabled,
        },
        "user": {
            "mode": config.user_mode,
            "multi_tenant": config.multi_tenant,
        },
    }

    CONFIG_PATH.write_text(json.dumps(data, indent=2))


# Global config instance (lazy loaded)
_config: Optional[VectrolaConfig] = None


def get_config() -> VectrolaConfig:
    """Get the global configuration (lazy loaded)."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reset_config() -> None:
    """Reset the cached config (useful after save_config)."""
    global _config
    _config = None


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
