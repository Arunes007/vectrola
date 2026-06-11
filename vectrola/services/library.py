"""User library service for managing track ownership and source mappings."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from vectrola.config import get_or_create_user_id


class UserLibrary:
    """
    Manages user's track ownership + GDrive file ID mappings.

    Stores a local JSON file mapping track_id -> source info:
    - gdrive_file_id: For Google Drive playback
    - local_path: For local file playback
    - added_at: When track was added to library

    Storage location: ~/.config/vectrola/library.json
    """

    LIBRARY_PATH = Path.home() / ".config" / "vectrola" / "library.json"

    def __init__(self, user_id: Optional[str] = None):
        """
        Initialize user library.

        Args:
            user_id: User ID (auto-generated if not provided)
        """
        self.user_id = user_id or get_or_create_user_id()
        self._data: Optional[dict] = None

    def _load(self) -> dict:
        """Load library from disk."""
        if self._data is not None:
            return self._data

        if self.LIBRARY_PATH.exists():
            try:
                with open(self.LIBRARY_PATH, 'r', encoding='utf-8') as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._data = self._empty_library()
        else:
            self._data = self._empty_library()

        return self._data

    def _empty_library(self) -> dict:
        """Create empty library structure."""
        return {
            "user_id": self.user_id,
            "tracks": {},
        }

    def _save(self):
        """Save library to disk."""
        if self._data is None:
            return

        self.LIBRARY_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(self.LIBRARY_PATH, 'w', encoding='utf-8') as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    @property
    def data(self) -> dict:
        """Get library data, loading from disk if needed."""
        return self._load()

    def add_track(
        self,
        track_id: str,
        gdrive_file_id: Optional[str] = None,
        local_path: Optional[str] = None,
    ):
        """
        Add track to user's library with source mapping.

        Args:
            track_id: Canonical track ID (e.g., "spotify:xxx" or "hash:xxx")
            gdrive_file_id: Optional Google Drive file ID for cloud playback
            local_path: Optional local file path for offline playback
        """
        tracks = self.data.get("tracks", {})

        # Update or create track entry
        if track_id in tracks:
            # Update existing entry - merge new sources
            entry = tracks[track_id]
            if gdrive_file_id:
                entry["gdrive_file_id"] = gdrive_file_id
            if local_path:
                entry["local_path"] = local_path
        else:
            # Create new entry
            tracks[track_id] = {
                "gdrive_file_id": gdrive_file_id,
                "local_path": local_path,
                "added_at": datetime.utcnow().isoformat() + "Z",
            }

        self._data["tracks"] = tracks
        self._save()

    def remove_track(self, track_id: str) -> bool:
        """
        Remove track from user's library.

        Note: This only removes from the user's library, not from
        the global Qdrant catalog.

        Args:
            track_id: Canonical track ID

        Returns:
            True if removed, False if not found
        """
        tracks = self.data.get("tracks", {})
        if track_id in tracks:
            del tracks[track_id]
            self._data["tracks"] = tracks
            self._save()
            return True
        return False

    def get_tracks(self) -> dict[str, dict]:
        """
        Get all tracks user owns with their sources.

        Returns:
            Dict mapping track_id -> source info
        """
        return self.data.get("tracks", {})

    def has_track(self, track_id: str) -> bool:
        """
        Check if user owns this track.

        Args:
            track_id: Canonical track ID

        Returns:
            True if user has this track
        """
        return track_id in self.data.get("tracks", {})

    def get_gdrive_id(self, track_id: str) -> Optional[str]:
        """
        Get Google Drive file ID for a track.

        Args:
            track_id: Canonical track ID

        Returns:
            GDrive file ID or None
        """
        track = self.data.get("tracks", {}).get(track_id, {})
        return track.get("gdrive_file_id")

    def get_local_path(self, track_id: str) -> Optional[str]:
        """
        Get local file path for a track.

        Args:
            track_id: Canonical track ID

        Returns:
            Local file path or None
        """
        track = self.data.get("tracks", {}).get(track_id, {})
        return track.get("local_path")

    def get_track_info(self, track_id: str) -> Optional[dict]:
        """
        Get full source info for a track.

        Args:
            track_id: Canonical track ID

        Returns:
            Dict with gdrive_file_id, local_path, added_at - or None
        """
        return self.data.get("tracks", {}).get(track_id)

    def count(self) -> int:
        """Get total number of tracks in library."""
        return len(self.data.get("tracks", {}))

    def stats(self) -> dict:
        """
        Get library statistics.

        Returns:
            Dict with counts: total, gdrive, local, both
        """
        tracks = self.data.get("tracks", {})

        total = len(tracks)
        gdrive_count = 0
        local_count = 0
        both_count = 0

        for track in tracks.values():
            has_gdrive = bool(track.get("gdrive_file_id"))
            has_local = bool(track.get("local_path"))

            if has_gdrive and has_local:
                both_count += 1
            elif has_gdrive:
                gdrive_count += 1
            elif has_local:
                local_count += 1

        return {
            "total": total,
            "gdrive_only": gdrive_count,
            "local_only": local_count,
            "both": both_count,
        }

    def clear(self) -> int:
        """
        Clear all tracks from library.

        Returns:
            Number of tracks removed
        """
        count = self.count()
        self._data = self._empty_library()
        self._save()
        return count
