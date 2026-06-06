"""Fetch song metadata from Spotify using SpotAPI (no credentials needed)."""

from dataclasses import dataclass, field
from typing import Optional
import re


@dataclass
class SpotifyTrack:
    """Track metadata from Spotify."""

    title: str = ""
    artists: list[str] = field(default_factory=list)
    album: str = ""
    year: Optional[int] = None
    duration_ms: Optional[int] = None
    spotify_id: str = ""

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "artists": self.artists,
            "album": self.album,
            "year": self.year,
            "duration_ms": self.duration_ms,
            "spotify_id": self.spotify_id,
        }


class SpotifyFetcher:
    """
    Fetch metadata from Spotify using SpotAPI.

    No API credentials needed - uses public Spotify web API.
    """

    def __init__(self):
        self._song_client = None

    @property
    def client(self):
        """Lazy load SpotAPI client."""
        if self._song_client is None:
            from spotapi import Song
            self._song_client = Song()
        return self._song_client

    def search(self, title: str, artist: str = "", limit: int = 5) -> list[SpotifyTrack]:
        """
        Search for tracks on Spotify.

        Args:
            title: Song title
            artist: Optional artist name to improve matching
            limit: Max results to return

        Returns:
            List of SpotifyTrack matches
        """
        try:
            # Build search query
            query = title
            if artist:
                query = f"{title} {artist}"

            results = self.client.query_songs(query, limit=limit)

            items = (results.get('data', {})
                     .get('searchV2', {})
                     .get('tracksV2', {})
                     .get('items', []))

            tracks = []
            for item in items:
                track_data = item.get('item', {}).get('data', {})

                # Extract artists
                artists = []
                for a in track_data.get('artists', {}).get('items', []):
                    name = a.get('profile', {}).get('name', '')
                    if name:
                        artists.append(name)

                # Extract album info
                album_data = track_data.get('albumOfTrack', {})
                album_name = album_data.get('name', '')

                # Try to extract year from release date
                year = None
                release_date = album_data.get('date', {}).get('isoString', '')
                if release_date:
                    year_match = re.match(r'(\d{4})', release_date)
                    if year_match:
                        year = int(year_match.group(1))

                # Get duration
                duration_ms = track_data.get('duration', {}).get('totalMilliseconds')

                # Get Spotify ID
                uri = track_data.get('uri', '')
                spotify_id = uri.split(':')[-1] if uri else ''

                tracks.append(SpotifyTrack(
                    title=track_data.get('name', ''),
                    artists=artists,
                    album=album_name,
                    year=year,
                    duration_ms=duration_ms,
                    spotify_id=spotify_id,
                ))

            return tracks

        except Exception as e:
            print(f"Spotify search error: {e}")
            return []

    def get_best_match(self, title: str, artist: str = "") -> Optional[SpotifyTrack]:
        """
        Get the best matching track for a title.

        Args:
            title: Song title
            artist: Optional artist name

        Returns:
            Best matching SpotifyTrack or None
        """
        tracks = self.search(title, artist, limit=5)

        if not tracks:
            return None

        # If we have an artist hint, try to find exact match
        if artist:
            artist_lower = artist.lower()
            for track in tracks:
                for track_artist in track.artists:
                    if artist_lower in track_artist.lower():
                        return track

        # Otherwise return first result (usually most popular)
        return tracks[0]


# Convenience function
def fetch_spotify_metadata(title: str, artist: str = "") -> Optional[SpotifyTrack]:
    """Fetch metadata from Spotify for a song."""
    fetcher = SpotifyFetcher()
    return fetcher.get_best_match(title, artist)
