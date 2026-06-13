"""Track and retry failed ingestions."""

from datetime import datetime
from pathlib import Path
from typing import Optional
import json


FAILED_INGESTS_PATH = Path.home() / ".config" / "vectrola" / "failed_ingests.json"


class FailedIngestsManager:
    """
    Manage failed ingestion tracking and retry.

    Stores failed tracks in ~/.config/vectrola/failed_ingests.json
    so users can retry them later without re-ingesting everything.
    """

    def __init__(self):
        self._data = self._load()

    def _load(self) -> dict:
        """Load failed ingests from disk."""
        if FAILED_INGESTS_PATH.exists():
            try:
                return json.loads(FAILED_INGESTS_PATH.read_text())
            except (json.JSONDecodeError, IOError):
                pass
        return {"version": 1, "failed": []}

    def _save(self):
        """Save failed ingests to disk."""
        FAILED_INGESTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        FAILED_INGESTS_PATH.write_text(json.dumps(self._data, indent=2))

    def add_failed(
        self,
        name: str,
        source: str,
        source_path: str,
        error: str,
        error_stage: str,
        gdrive_file_id: Optional[str] = None,
    ):
        """
        Add or update a failed ingestion.

        Args:
            name: Display name (filename)
            source: "local" or "gdrive"
            source_path: Original path
            error: Error message
            error_stage: "download", "metadata", "lyrics", "llm", "storage", "unknown"
            gdrive_file_id: Google Drive file ID (for gdrive source)
        """
        # Generate unique ID
        if source == "gdrive" and gdrive_file_id:
            item_id = f"gdrive:{gdrive_file_id}"
        else:
            item_id = f"local:{source_path}"

        # Check if already exists (update attempts)
        for item in self._data["failed"]:
            if item["id"] == item_id:
                item["error"] = error
                item["error_stage"] = error_stage
                item["failed_at"] = datetime.utcnow().isoformat() + "Z"
                item["attempts"] += 1
                self._save()
                return

        # Add new entry
        self._data["failed"].append({
            "id": item_id,
            "name": name,
            "source": source,
            "source_path": source_path,
            "gdrive_file_id": gdrive_file_id,
            "error": error,
            "error_stage": error_stage,
            "failed_at": datetime.utcnow().isoformat() + "Z",
            "attempts": 1,
        })
        self._save()

    def remove_failed(self, item_id: str):
        """
        Remove a track from failed list (on successful retry or re-ingest).

        Args:
            item_id: Unique ID (e.g., "gdrive:abc123" or "local:/path/to/file")
        """
        self._data["failed"] = [
            f for f in self._data["failed"] if f["id"] != item_id
        ]
        self._save()

    def get_failed(self) -> list[dict]:
        """Get all failed ingestions."""
        return self._data["failed"]

    def clear(self) -> int:
        """
        Clear all failed ingestions.

        Returns:
            Number of items cleared
        """
        count = len(self._data["failed"])
        self._data["failed"] = []
        self._save()
        return count

    def count(self) -> int:
        """Get number of failed ingestions."""
        return len(self._data["failed"])


def detect_error_stage(error_msg: str) -> str:
    """
    Detect which stage failed based on error message.

    Args:
        error_msg: The error message string

    Returns:
        Stage name: "download", "metadata", "lyrics", "llm", "storage", or "unknown"
    """
    error_lower = error_msg.lower()

    if "download" in error_lower or "drive" in error_lower:
        return "download"
    if "spotify" in error_lower:
        return "metadata"
    if "lyrics" in error_lower or "lrclib" in error_lower or "genius" in error_lower:
        return "lyrics"
    if "ollama" in error_lower or "llm" in error_lower or "model" in error_lower or "anthropic" in error_lower or "openai" in error_lower:
        return "llm"
    if "qdrant" in error_lower or "storage" in error_lower or "vector" in error_lower or "embedding" in error_lower:
        return "storage"

    return "unknown"
