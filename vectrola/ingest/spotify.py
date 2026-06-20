"""Fetch song metadata from Spotify using SpotAPI (no credentials needed)."""

from dataclasses import dataclass, field
from typing import Optional
import re


def fetch_spotify_thumbnail(spotify_id: str) -> Optional[str]:
    """
    Fetch album art URL from Spotify oEmbed API.

    This is a fallback when the SpotAPI search doesn't return cover art.

    Args:
        spotify_id: Spotify track ID (e.g., "4PTG3Z6ehGkBFwjybzWkR8")

    Returns:
        Thumbnail URL (i.scdn.co) or None
    """
    import requests

    if not spotify_id:
        return None

    track_url = f"https://open.spotify.com/track/{spotify_id}"
    oembed_url = f"https://open.spotify.com/oembed?url={track_url}"

    try:
        response = requests.get(oembed_url, timeout=5)
        if response.ok:
            data = response.json()
            return data.get("thumbnail_url")
    except Exception:
        pass

    return None


@dataclass
class SpotifyTrack:
    """Track metadata from Spotify."""

    title: str = ""
    artists: list[str] = field(default_factory=list)
    album: str = ""
    album_id: str = ""  # Album ID for fetching release year
    year: Optional[int] = None
    duration_ms: Optional[int] = None
    spotify_id: str = ""
    album_art_url: Optional[str] = None  # Album cover art URL

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "artists": self.artists,
            "album": self.album,
            "album_id": self.album_id,
            "year": self.year,
            "duration_ms": self.duration_ms,
            "spotify_id": self.spotify_id,
            "album_art_url": self.album_art_url,
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

    def _fetch_album_year(self, album_id: str) -> Optional[int]:
        """
        Fetch release year from album info.

        The search API doesn't return release date, so we need a separate call.
        """
        if not album_id:
            return None

        from threading import Thread

        try:
            from spotapi import PublicAlbum

            # Use threading for timeout (signal doesn't work with curl_cffi)
            result_container = {'info': None, 'error': None}

            def fetch_thread():
                try:
                    album = PublicAlbum(album_id)
                    result_container['info'] = album.get_album_info()
                except Exception as e:
                    result_container['error'] = e

            thread = Thread(target=fetch_thread, daemon=True)
            thread.start()
            thread.join(timeout=5)  # 5 second timeout

            if thread.is_alive():
                # Timeout - year is optional so just return None
                return None

            if result_container['error']:
                raise result_container['error']

            info = result_container['info']
            if not info:
                return None

            # Extract year from album data
            album_data = info.get('data', {}).get('albumUnion', {})
            date_info = album_data.get('date', {})
            iso_string = date_info.get('isoString', '')

            if iso_string:
                year_match = re.match(r'(\d{4})', iso_string)
                if year_match:
                    return int(year_match.group(1))

            return None
        except Exception as e:
            # Don't fail if album fetch fails - year is optional
            return None

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
        from threading import Thread
        import time

        try:
            # Build search query
            query = title
            if artist:
                query = f"{title} {artist}"

            # Use threading for timeout (signal doesn't work with curl_cffi)
            result_container = {'results': None, 'error': None}

            def search_thread():
                try:
                    result_container['results'] = self.client.query_songs(query, limit=limit)
                except Exception as e:
                    result_container['error'] = e

            thread = Thread(target=search_thread, daemon=True)
            thread.start()
            thread.join(timeout=10)  # 10 second timeout

            if thread.is_alive():
                print(f"Spotify search timeout for: {query}")
                return []

            if result_container['error']:
                raise result_container['error']

            results = result_container['results']
            if not results:
                return []

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

                # Extract album ID for fetching release year later
                album_uri = album_data.get('uri', '')
                album_id = album_uri.split(':')[-1] if album_uri else ''

                # Extract album cover art URL
                cover_art_sources = album_data.get('coverArt', {}).get('sources', [])
                album_art_url = cover_art_sources[0].get('url') if cover_art_sources else None

                # Get duration
                duration_ms = track_data.get('duration', {}).get('totalMilliseconds')

                # Get Spotify ID
                uri = track_data.get('uri', '')
                spotify_id = uri.split(':')[-1] if uri else ''

                # Fallback to oEmbed if no album art from search
                if not album_art_url and spotify_id:
                    album_art_url = fetch_spotify_thumbnail(spotify_id)

                tracks.append(SpotifyTrack(
                    title=track_data.get('name', ''),
                    artists=artists,
                    album=album_name,
                    album_id=album_id,
                    year=None,  # Will be fetched separately if needed
                    duration_ms=duration_ms,
                    spotify_id=spotify_id,
                    album_art_url=album_art_url,
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

        best_track = None

        # If we have an artist hint, try to find exact match
        if artist:
            artist_lower = artist.lower()
            for track in tracks:
                for track_artist in track.artists:
                    if artist_lower in track_artist.lower():
                        best_track = track
                        break
                if best_track:
                    break

        # Otherwise return first result (usually most popular)
        if not best_track:
            best_track = tracks[0]

        # Fetch year from album (separate API call)
        if best_track and best_track.album_id:
            best_track.year = self._fetch_album_year(best_track.album_id)

        return best_track


# Convenience function
def fetch_spotify_metadata(title: str, artist: str = "") -> Optional[SpotifyTrack]:
    """Fetch metadata from Spotify for a song."""
    fetcher = SpotifyFetcher()
    return fetcher.get_best_match(title, artist)
