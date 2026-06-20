"""Selectively refresh missing metadata fields for existing tracks."""

from pathlib import Path
from typing import Optional
from qdrant_client import models


class MetadataRefresher:
    """
    Selectively re-runs pipeline stages to fill missing metadata.

    Uses the existing IngestPipeline components (spotify_fetcher, lyrics_fetcher,
    synthesis, etc.) to fetch only the missing fields without re-processing the
    entire track.
    """

    def __init__(self):
        """Initialize with a reusable IngestPipeline."""
        from vectrola.ingest.pipeline import IngestPipeline

        self.pipeline = IngestPipeline()

    def refresh_track(
        self,
        track_id: str,
        missing_fields: list[str],
        file_path: Optional[Path] = None,
    ) -> dict:
        """
        Refresh specific metadata fields for a track.

        Args:
            track_id: Track ID in Qdrant
            missing_fields: List from detect_missing_fields()
            file_path: Local file path (for Whisper fallback if lyrics still missing)

        Returns:
            Updated payload dict with filled fields

        Raises:
            ValueError: If track_id not found in Qdrant

        Example:
            >>> refresher = MetadataRefresher()
            >>> updates = refresher.refresh_track(
            ...     "spotify:4PTG3Z6ehGkBFwjybzWkR8",
            ...     ["lyrics", "themes_moods"],
            ...     Path("/path/to/song.mp3")
            ... )
            >>> updates.keys()
            dict_keys(['lyrics', 'lyrics_source', 'themes', 'moods', 'narrative', 'imagery'])
        """
        from vectrola.storage.qdrant import get_db

        db = get_db()

        # Get existing track
        points, _ = db.client.scroll(
            collection_name=db.COLLECTION,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="track_id", match=models.MatchValue(value=track_id)
                    )
                ]
            ),
            limit=1,
            with_payload=True,
        )

        if not points:
            raise ValueError(f"Track {track_id} not found")

        point = points[0]
        payload = point.payload
        updates = {}

        # Refresh Spotify metadata
        if "spotify_metadata" in missing_fields:
            updates.update(self._refresh_spotify(payload))

        # Refresh lyrics
        if "lyrics" in missing_fields:
            updates.update(self._refresh_lyrics(payload, updates, file_path))

        # Refresh LLM synthesis (themes, moods, narrative)
        if "themes_moods" in missing_fields:
            updates.update(self._refresh_themes_moods(payload, updates))

        # Refresh album art (if still missing after Spotify)
        if "album_art" in missing_fields and "album_art_url" not in updates:
            updates.update(self._refresh_album_art(payload, updates))

        return updates

    def _refresh_spotify(self, payload: dict) -> dict:
        """Fetch Spotify metadata (album, year, spotify_id, album_art)."""
        updates = {}

        title = payload.get("title", "")
        artist = payload.get("artists", [""])[0] if payload.get("artists") else ""

        spotify_track = self.pipeline.spotify_fetcher.get_best_match(title, artist)
        if spotify_track:
            updates["spotify_id"] = spotify_track.spotify_id
            updates["album"] = spotify_track.album
            updates["year"] = spotify_track.year
            updates["album_art_url"] = spotify_track.album_art_url
            updates["movie"] = spotify_track.album  # For Bollywood

        return updates

    def _refresh_lyrics(
        self, payload: dict, updates: dict, file_path: Optional[Path]
    ) -> dict:
        """Fetch lyrics (LRClib → Genius → Whisper)."""
        lyrics_updates = {}

        title = payload.get("title", "")
        artist = payload.get("artists", [""])[0] if payload.get("artists") else ""
        album = updates.get("album", payload.get("album", ""))

        # Try LRClib first
        lyrics_result = self.pipeline.lyrics_fetcher.fetch(title, artist, album)
        if lyrics_result:
            lyrics_updates["lyrics"] = lyrics_result.lyrics
            lyrics_updates["lyrics_source"] = lyrics_result.source
            if lyrics_result.segments:
                lyrics_updates["segments"] = lyrics_result.segments
        else:
            # Fallback to Genius
            from vectrola.ingest.lyrics import fetch_genius_lyrics

            genius_lyrics = fetch_genius_lyrics(
                title, artist, self.pipeline.genius_token
            )
            if genius_lyrics:
                lyrics_updates["lyrics"] = genius_lyrics
                lyrics_updates["lyrics_source"] = "genius"
            elif file_path and file_path.exists():
                # Whisper fallback (requires local file)
                transcription = self.pipeline.transcriber.transcribe(file_path)
                lyrics_updates["lyrics"] = transcription["text"]
                lyrics_updates["lyrics_source"] = "whisper"
                if transcription.get("segments"):
                    lyrics_updates["segments"] = transcription["segments"]

        return lyrics_updates

    def _refresh_themes_moods(self, payload: dict, updates: dict) -> dict:
        """Fetch themes/moods from LLM synthesis."""
        synthesis_updates = {}

        lyrics = updates.get("lyrics", payload.get("lyrics", ""))
        title = payload.get("title", "")

        if lyrics:
            synthesis = self.pipeline.synthesis.synthesize_from_lyrics(lyrics, title)
            synthesis_updates["themes"] = synthesis.themes
            synthesis_updates["moods"] = synthesis.moods
            synthesis_updates["narrative"] = synthesis.narrative
            synthesis_updates["imagery"] = synthesis.imagery

        return synthesis_updates

    def _refresh_album_art(self, payload: dict, updates: dict) -> dict:
        """Fetch album art from Spotify (if still missing)."""
        art_updates = {}

        spotify_id = updates.get("spotify_id", payload.get("spotify_id"))
        if spotify_id:
            from vectrola.ingest.spotify import fetch_spotify_thumbnail

            thumbnail = fetch_spotify_thumbnail(spotify_id)
            if thumbnail:
                art_updates["album_art_url"] = thumbnail

        return art_updates
