"""Fetch lyrics from online sources."""

from pathlib import Path
from dataclasses import dataclass
from typing import Optional
import os
import re

# Get Genius API token from environment
# Get your own at: https://genius.com/api-clients
DEFAULT_GENIUS_TOKEN = os.getenv("GENIUS_API_TOKEN", "")


@dataclass
class LyricsResult:
    """Result of lyrics fetching."""

    text: str
    source: str  # "genius", "lrclib", "synced", "whisper"
    synced: bool  # True if timestamped lyrics available
    segments: Optional[list[dict]] = None  # [{start, end, text}, ...] if synced
    artist: Optional[str] = None
    title: Optional[str] = None
    album: Optional[str] = None  # For Bollywood, this is often the movie name
    duration_seconds: Optional[float] = None


class LyricsFetcher:
    """
    Fetch lyrics from multiple sources with fallback.

    Priority:
    1. LRClib (free, has synced lyrics)
    2. Genius (using direct API, no lyricsgenius package)
    3. Whisper transcription (fallback)
    """

    def __init__(self, genius_token: Optional[str] = None):
        """
        Initialize the fetcher.

        Args:
            genius_token: Genius API token (optional, uses default if not provided)
        """
        self.genius_token = genius_token or DEFAULT_GENIUS_TOKEN

    def fetch(
        self,
        artist: str,
        title: str,
        audio_path: Optional[Path] = None,
        use_whisper_fallback: bool = True,
    ) -> Optional[LyricsResult]:
        """
        Fetch lyrics for a song.

        Args:
            artist: Artist name
            title: Song title
            audio_path: Path to audio file (for Whisper fallback)
            use_whisper_fallback: If True, transcribe with Whisper if no lyrics found

        Returns:
            LyricsResult or None if not found
        """
        # Clean up title (remove file extensions, extra info)
        title = self._clean_title(title)
        artist = self._clean_artist(artist)

        # Try LRClib first (free, has synced lyrics)
        result = self._fetch_lrclib(artist, title)
        if result:
            return result

        # Try Genius as fallback (direct API, no lyricsgenius package)
        result = self._fetch_genius_direct(artist, title)
        if result:
            return result

        # Fallback to Whisper transcription
        if use_whisper_fallback and audio_path:
            return self._transcribe_whisper(audio_path, artist, title)

        return None

    def _fetch_lrclib(self, artist: str, title: str) -> Optional[LyricsResult]:
        """Fetch from LRClib (free, synced lyrics)."""
        import requests

        try:
            # Try synced lyrics first
            url = "https://lrclib.net/api/get"
            params = {"track_name": title}

            # Only add artist if we have one
            if artist:
                params["artist_name"] = artist

            response = requests.get(url, params=params, timeout=30)

            if response.status_code == 200:
                data = response.json()

                # Prefer synced lyrics
                if data.get("syncedLyrics"):
                    segments = self._parse_lrc(data["syncedLyrics"])
                    plain_text = "\n".join(seg["text"] for seg in segments)
                    return LyricsResult(
                        text=plain_text,
                        source="lrclib",
                        synced=True,
                        segments=segments,
                        artist=data.get("artistName", artist),
                        title=data.get("trackName", title),
                        album=data.get("albumName", ""),
                        duration_seconds=data.get("duration"),
                    )

                # Fall back to plain lyrics
                if data.get("plainLyrics"):
                    return LyricsResult(
                        text=data["plainLyrics"],
                        source="lrclib",
                        synced=False,
                        artist=data.get("artistName", artist),
                        title=data.get("trackName", title),
                        album=data.get("albumName", ""),
                        duration_seconds=data.get("duration"),
                    )

            # Try search endpoint if direct get fails
            if not artist:
                search_url = "https://lrclib.net/api/search"
                search_response = requests.get(search_url, params={"q": title}, timeout=10)

                if search_response.status_code == 200:
                    results = search_response.json()
                    if results and len(results) > 0:
                        # Take first result
                        first = results[0]
                        if first.get("syncedLyrics"):
                            segments = self._parse_lrc(first["syncedLyrics"])
                            plain_text = "\n".join(seg["text"] for seg in segments)
                            return LyricsResult(
                                text=plain_text,
                                source="lrclib",
                                synced=True,
                                segments=segments,
                                artist=first.get("artistName", ""),
                                title=first.get("trackName", title),
                                album=first.get("albumName", ""),
                                duration_seconds=first.get("duration"),
                            )
                        elif first.get("plainLyrics"):
                            return LyricsResult(
                                text=first["plainLyrics"],
                                source="lrclib",
                                synced=False,
                                artist=first.get("artistName", ""),
                                title=first.get("trackName", title),
                                album=first.get("albumName", ""),
                                duration_seconds=first.get("duration"),
                            )

            return None

        except Exception as e:
            print(f"LRClib error: {e}")
            return None

    def _fetch_genius_direct(self, artist: str, title: str) -> Optional[LyricsResult]:
        """Fetch from Genius using direct API (no lyricsgenius package)."""
        import requests
        from bs4 import BeautifulSoup

        try:
            # Search for the song
            headers = {'Authorization': f'Bearer {self.genius_token}'}
            query = f"{title} {artist}" if artist else title

            search_response = requests.get(
                'https://api.genius.com/search',
                params={'q': query},
                headers=headers,
                timeout=15
            )

            if search_response.status_code != 200:
                return None

            hits = search_response.json().get('response', {}).get('hits', [])
            if not hits:
                return None

            # Get the first result
            song_info = hits[0].get('result', {})
            song_url = song_info.get('url')
            song_title = song_info.get('title', title)
            song_artist = song_info.get('primary_artist', {}).get('name', artist)

            if not song_url:
                return None

            # Fetch lyrics from the song page
            page_response = requests.get(song_url, timeout=15)
            if page_response.status_code != 200:
                return None

            soup = BeautifulSoup(page_response.text, 'html.parser')

            # Find lyrics container (Genius uses data-lyrics-container)
            lyrics_divs = soup.find_all('div', {'data-lyrics-container': 'true'})
            if not lyrics_divs:
                # Try older format
                lyrics_divs = soup.find_all('div', class_='lyrics')

            if not lyrics_divs:
                return None

            # Extract text from lyrics divs
            lyrics_parts = []
            for div in lyrics_divs:
                # Get text, preserving line breaks
                for br in div.find_all('br'):
                    br.replace_with('\n')
                lyrics_parts.append(div.get_text())

            lyrics = '\n'.join(lyrics_parts).strip()

            # Clean up lyrics
            lyrics = self._clean_genius_lyrics(lyrics)

            if not lyrics:
                return None

            return LyricsResult(
                text=lyrics,
                source="genius",
                synced=False,
                artist=song_artist,
                title=song_title,
            )

        except Exception as e:
            print(f"Genius error: {e}")
            return None

    def _fetch_genius(self, artist: str, title: str) -> Optional[LyricsResult]:
        """Fetch from Genius (needs API token)."""
        try:
            if self._genius is None:
                import lyricsgenius
                self._genius = lyricsgenius.Genius(
                    self.genius_token,
                    verbose=False,
                    remove_section_headers=True,
                )

            song = self._genius.search_song(title, artist)

            if song and song.lyrics:
                # Clean up Genius lyrics (remove embed text, etc.)
                lyrics = self._clean_genius_lyrics(song.lyrics)
                return LyricsResult(
                    text=lyrics,
                    source="genius",
                    synced=False,
                    artist=song.artist,
                    title=song.title,
                )

            return None

        except Exception as e:
            print(f"Genius error: {e}")
            return None

    def _transcribe_whisper(
        self,
        audio_path: Path,
        artist: str,
        title: str
    ) -> Optional[LyricsResult]:
        """Fallback: transcribe with Whisper."""
        try:
            from vectrola.ingest.transcribe import Transcriber

            transcriber = Transcriber()
            result = transcriber.transcribe(audio_path)

            return LyricsResult(
                text=result.text,
                source="whisper",
                synced=True,
                segments=result.segments,
                artist=artist,
                title=title,
            )

        except Exception as e:
            print(f"Whisper error: {e}")
            return None

    def _parse_lrc(self, lrc_text: str) -> list[dict]:
        """Parse LRC format to segments."""
        segments = []
        pattern = r'\[(\d+):(\d+)\.(\d+)\](.*)'

        for line in lrc_text.split('\n'):
            match = re.match(pattern, line)
            if match:
                minutes, seconds, centiseconds, text = match.groups()
                start_time = int(minutes) * 60 + int(seconds) + int(centiseconds) / 100

                if text.strip():
                    segments.append({
                        "start": start_time,
                        "end": start_time + 5.0,  # Approximate, will be refined
                        "text": text.strip(),
                    })

        # Refine end times based on next segment
        for i in range(len(segments) - 1):
            segments[i]["end"] = segments[i + 1]["start"]

        return segments

    def _clean_title(self, title: str) -> str:
        """Clean song title for search."""
        # Remove file extension
        title = re.sub(r'\.(mp3|flac|wav|m4a|ogg)$', '', title, flags=re.IGNORECASE)
        # Remove common suffixes
        title = re.sub(r'\s*[\(\[]*(official|audio|video|lyrics|hd|hq|remaster).*$', '', title, flags=re.IGNORECASE)
        # Remove track numbers
        title = re.sub(r'^\d+[\.\-\s]+', '', title)
        return title.strip()

    def _clean_artist(self, artist: str) -> str:
        """Clean artist name for search."""
        # Handle "Unknown Artist"
        if artist.lower() in ['unknown artist', 'unknown', 'various']:
            return ''
        return artist.strip()

    def _clean_genius_lyrics(self, lyrics: str) -> str:
        """Clean Genius lyrics output."""
        # Remove "Embed" text at end
        lyrics = re.sub(r'\d*Embed$', '', lyrics)
        # Remove "You might also like" sections
        lyrics = re.sub(r'You might also like.*?(?=\n\n|\Z)', '', lyrics, flags=re.DOTALL)
        return lyrics.strip()


# Convenience function
def fetch_lyrics(artist: str, title: str, audio_path: Optional[Path] = None) -> Optional[LyricsResult]:
    """Fetch lyrics using default settings."""
    fetcher = LyricsFetcher()
    return fetcher.fetch(artist, title, audio_path)
