"""Detect missing metadata fields in tracks for gap-filling."""


def detect_missing_fields(payload: dict) -> list[str]:
    """
    Detect which metadata fields are missing or empty in a track.

    Args:
        payload: Track payload from Qdrant

    Returns:
        List of missing field categories:
        - "spotify_metadata" - no spotify_id or missing album (year is optional)
        - "lyrics" - empty lyrics field
        - "themes_moods" - empty themes or moods
        - "album_art" - no album_art_url

    Example:
        >>> payload = {"title": "Song", "lyrics": "", "moods": []}
        >>> detect_missing_fields(payload)
        ['spotify_metadata', 'lyrics', 'themes_moods', 'album_art']
    """
    missing = []

    # Check Spotify metadata (year is optional)
    if not payload.get("spotify_id") or not payload.get("album"):
        missing.append("spotify_metadata")

    # Check lyrics
    if not payload.get("lyrics") or payload.get("lyrics", "").strip() == "":
        missing.append("lyrics")

    # Check LLM synthesis
    if not payload.get("themes") or not payload.get("moods"):
        missing.append("themes_moods")

    # Check album art
    if not payload.get("album_art_url"):
        missing.append("album_art")

    # Note: composer/lyricist are optional - not checked in refresh
    # They're often unavailable in APIs and not critical for search

    return missing
