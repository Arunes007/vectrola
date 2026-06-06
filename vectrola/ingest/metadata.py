"""Fetch song metadata from various sources (MusicBrainz, Genius, etc.)."""

from dataclasses import dataclass, field
from typing import Optional
import re


@dataclass
class SongMetadata:
    """Rich metadata for a song."""

    # Basic info
    title: str = ""
    artists: list[str] = field(default_factory=list)  # Singers
    album: str = ""
    year: Optional[int] = None

    # Bollywood specific
    movie: str = ""  # Film name (often same as album for soundtracks)
    actors: list[str] = field(default_factory=list)  # Film actors
    composer: str = ""  # Music director
    lyricist: str = ""  # Songwriter

    # Additional
    language: str = ""
    genres: list[str] = field(default_factory=list)
    duration_ms: Optional[int] = None

    # Source tracking
    source: str = ""  # "musicbrainz", "genius", "file_tags"
    musicbrainz_id: str = ""

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "artists": self.artists,
            "album": self.album,
            "year": self.year,
            "movie": self.movie,
            "actors": self.actors,
            "composer": self.composer,
            "lyricist": self.lyricist,
            "language": self.language,
            "genres": self.genres,
            "source": self.source,
        }


class MetadataFetcher:
    """
    Fetch rich metadata from multiple sources.

    Priority:
    1. MusicBrainz (free, comprehensive, good for Bollywood)
    2. Genius (needs API key, has actors/movie info sometimes)
    3. File tags (fallback)
    """

    def __init__(self, genius_token: Optional[str] = None):
        self.genius_token = genius_token
        self._mb_initialized = False

    def _init_musicbrainz(self):
        """Initialize MusicBrainz client."""
        if not self._mb_initialized:
            import musicbrainzngs
            musicbrainzngs.set_useragent("Vectrola", "0.1.0", "https://github.com/vectrola")
            self._mb_initialized = True

    def fetch(self, title: str, artist: str = "") -> Optional[SongMetadata]:
        """
        Fetch metadata for a song.

        Args:
            title: Song title
            artist: Artist name (optional but helps accuracy)

        Returns:
            SongMetadata or None if not found
        """
        # Try MusicBrainz first
        result = self._fetch_musicbrainz(title, artist)
        if result:
            return result

        # Try Genius if we have a token
        if self.genius_token:
            result = self._fetch_genius(title, artist)
            if result:
                return result

        return None

    def _fetch_musicbrainz(self, title: str, artist: str = "") -> Optional[SongMetadata]:
        """Fetch from MusicBrainz."""
        self._init_musicbrainz()
        import musicbrainzngs

        try:
            # Search for recordings
            query = f'recording:"{title}"'
            if artist:
                query += f' AND artist:"{artist}"'

            result = musicbrainzngs.search_recordings(query=query, limit=5)

            if not result.get("recording-list"):
                # Try without quotes for fuzzy match
                query = title
                if artist:
                    query += f" {artist}"
                result = musicbrainzngs.search_recordings(query=query, limit=5)

            if not result.get("recording-list"):
                return None

            # Get the best match
            recording = result["recording-list"][0]

            # Extract metadata
            metadata = SongMetadata(source="musicbrainz")
            metadata.title = recording.get("title", title)
            metadata.musicbrainz_id = recording.get("id", "")

            # Get artists
            if "artist-credit" in recording:
                for credit in recording["artist-credit"]:
                    if isinstance(credit, dict) and "artist" in credit:
                        metadata.artists.append(credit["artist"].get("name", ""))

            # Get album/movie info from release
            if "release-list" in recording:
                release = recording["release-list"][0]
                metadata.album = release.get("title", "")

                # For Bollywood, album is often the movie name
                if metadata.album:
                    metadata.movie = metadata.album

                # Get year from release date
                date_str = release.get("date", "")
                if date_str:
                    year_match = re.match(r"(\d{4})", date_str)
                    if year_match:
                        metadata.year = int(year_match.group(1))

            # Get more details from full recording lookup
            try:
                full_recording = musicbrainzngs.get_recording_by_id(
                    recording["id"],
                    includes=["artists", "releases", "tags", "work-rels"]
                )
                rec = full_recording.get("recording", {})

                # Get composer/lyricist from work relations
                if "work-relation-list" in rec:
                    for work_rel in rec["work-relation-list"]:
                        if "work" in work_rel:
                            work_id = work_rel["work"]["id"]
                            work_details = musicbrainzngs.get_work_by_id(
                                work_id,
                                includes=["artist-rels"]
                            )
                            work = work_details.get("work", {})
                            if "artist-relation-list" in work:
                                for rel in work["artist-relation-list"]:
                                    rel_type = rel.get("type", "")
                                    artist_name = rel.get("artist", {}).get("name", "")
                                    if rel_type == "composer":
                                        metadata.composer = artist_name
                                    elif rel_type in ["lyricist", "writer"]:
                                        metadata.lyricist = artist_name

                # Get tags/genres
                if "tag-list" in rec:
                    metadata.genres = [tag["name"] for tag in rec["tag-list"][:5]]

            except Exception:
                pass  # Full lookup failed, use basic info

            return metadata

        except Exception as e:
            print(f"MusicBrainz error: {e}")
            return None

    def _fetch_genius(self, title: str, artist: str = "") -> Optional[SongMetadata]:
        """Fetch from Genius (has rich metadata for popular songs)."""
        if not self.genius_token:
            return None

        try:
            import lyricsgenius
            genius = lyricsgenius.Genius(self.genius_token, verbose=False)

            song = genius.search_song(title, artist)
            if not song:
                return None

            metadata = SongMetadata(source="genius")
            metadata.title = song.title
            metadata.artists = [song.artist]
            metadata.album = song.album or ""

            # Genius sometimes has year in the song object
            if hasattr(song, 'year') and song.year:
                metadata.year = int(song.year)

            return metadata

        except Exception as e:
            print(f"Genius error: {e}")
            return None


def fetch_metadata(title: str, artist: str = "") -> Optional[SongMetadata]:
    """Convenience function to fetch metadata."""
    fetcher = MetadataFetcher()
    return fetcher.fetch(title, artist)
