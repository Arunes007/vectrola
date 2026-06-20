"""Load CLI messages from YAML file."""

import yaml
from pathlib import Path
from functools import lru_cache
from typing import Any


MESSAGES_FILE = Path(__file__).parent / "messages.yml"


@lru_cache(maxsize=1)
def load_messages() -> dict:
    """Load and cache messages from YAML file."""
    with open(MESSAGES_FILE, "r") as f:
        return yaml.safe_load(f)


def get(key: str, default: str = "") -> Any:
    """
    Get a message by dot-notation key.

    Examples:
        get("welcome.title") -> "🎧 Welcome to Vectrola"
        get("welcome.sections.core.header") -> "Core Commands:"
    """
    messages = load_messages()
    keys = key.split(".")
    value = messages
    for k in keys:
        if isinstance(value, dict) and k in value:
            value = value[k]
        else:
            return default
    return value
