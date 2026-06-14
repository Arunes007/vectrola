"""Main ingestion pipeline orchestrating transcription, synthesis, and storage."""

from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
import json
import hashlib

from vectrola.config import get_config, get_or_create_user_id
from vectrola.ingest.transcribe import Transcriber, TranscriptionResult
from vectrola.ingest.synthesis import Synthesizer, SynthesisResult
from vectrola.ingest.lyrics import LyricsFetcher, LyricsResult
from vectrola.ingest.spotify import SpotifyFetcher, SpotifyTrack
from vectrola.storage.tags import write_tags, read_file_tags, FileTags


def generate_track_id(
    spotify_id: Optional[str],
    artist: str,
    title: str,
) -> str:
    """
    Generate canonical track ID for deduplication.

    Uses Spotify ID if available (most reliable), otherwise falls back to
    an MD5 hash of normalized artist + title.

    Args:
        spotify_id: Spotify track ID (e.g., "4PTG3Z6ehGkBFwjybzWkR8")
        artist: Artist name
        title: Track title

    Returns:
        Canonical track ID (e.g., "spotify:4PTG3Z6ehGkBFwjybzWkR8" or "hash:a1b2c3d4e5f6g7h8")
    """
    if spotify_id:
        return f"spotify:{spotify_id}"

    # Normalize and hash artist+title
    normalized = f"{artist.lower().strip()}:{title.lower().strip()}"
    hash_digest = hashlib.md5(normalized.encode()).hexdigest()[:16]
    return f"hash:{hash_digest}"


def calculate_era(year: Optional[int]) -> str:
    """
    Calculate era label from release year.

    Args:
        year: Release year (e.g., 1995, 2003)

    Returns:
        Era label (e.g., "90s Nostalgia", "Y2K Vibes")
    """
    if not year:
        return "Timeless"
    if year < 1990:
        return "Old Melodies"
    elif year < 2000:
        return "90s Nostalgia"
    elif year < 2010:
        return "Y2K Vibes"
    elif year < 2020:
        return "2010s Rewind"
    else:
        return "Fresh Hits"


@dataclass
class TrackAnalysis:
    """Complete analysis result for a track."""

    file_path: Path

    # Basic metadata
    title: str
    artists: list[str] = field(default_factory=list)  # Singers
    album: str = ""
    year: Optional[int] = None
    era: str = ""  # Calculated from year (e.g., "90s Nostalgia", "Y2K Vibes")

    # Bollywood specific
    movie: str = ""  # Film name (often = album for soundtracks)
    composer: str = ""  # Music director
    lyricist: str = ""

    # Lyrics
    lyrics: str = ""
    lyrics_source: str = ""  # "lrclib", "genius", "whisper", "file_tags"
    segments: list[dict] = field(default_factory=list)
    language: str = ""
    duration_seconds: Optional[float] = None

    # Semantic analysis (from Ollama)
    themes: list[str] = field(default_factory=list)
    moods: list[str] = field(default_factory=list)
    narrative: str = ""
    imagery: list[str] = field(default_factory=list)

    # Acoustic features (populated in Day 2-3)
    tempo: Optional[float] = None
    key: Optional[str] = None
    energy: Optional[float] = None

    # Embeddings (populated in Day 2-3)
    lyrics_vector: Optional[list[float]] = None
    audio_vector: Optional[list[float]] = None

    # Source tracking
    metadata_source: str = ""  # "file_tags", "lrclib", "musicbrainz"

    # Track identification (Day 7 - Multi-tenant)
    track_id: str = ""  # "spotify:xxx" or "hash:xxx"
    spotify_id: Optional[str] = None

    # Cloud storage (Day 7)
    gdrive_file_id: Optional[str] = None  # Google Drive file ID for playback
    gdrive_path: Optional[str] = None  # Original path in Google Drive

    # Album art
    album_art_url: Optional[str] = None  # Spotify album cover art URL

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            "file_path": str(self.file_path),
            "title": self.title,
            "artists": self.artists,
            "album": self.album,
            "year": self.year,
            "era": self.era,
            "movie": self.movie,
            "composer": self.composer,
            "lyricist": self.lyricist,
            "lyrics": self.lyrics,
            "lyrics_source": self.lyrics_source,
            "segments": self.segments,
            "language": self.language,
            "duration_seconds": self.duration_seconds,
            "themes": self.themes,
            "moods": self.moods,
            "narrative": self.narrative,
            "imagery": self.imagery,
            "tempo": self.tempo,
            "key": self.key,
            "energy": self.energy,
            "metadata_source": self.metadata_source,
            # Track identification (Day 7)
            "track_id": self.track_id,
            "spotify_id": self.spotify_id,
            # Cloud storage (Day 7)
            "gdrive_file_id": self.gdrive_file_id,
            "gdrive_path": self.gdrive_path,
            # Album art
            "album_art_url": self.album_art_url,
        }


class IngestPipeline:
    """
    Main ingestion pipeline for processing audio tracks.

    Pipeline priority:
    1. Read existing file tags (if complete, use them)
    2. Fetch lyrics from LRClib/Genius (fast, accurate, includes album/movie)
    3. Optionally fetch composer/lyricist from MusicBrainz
    4. Fallback to Whisper transcription (for obscure songs)
    5. LLM synthesis for themes/moods
    """

    def __init__(self, use_stems: bool = False, genius_token: Optional[str] = None):
        """
        Initialize the ingestion pipeline.

        Args:
            use_stems: If True, use Demucs for vocal separation when using Whisper fallback.
            genius_token: Optional Genius API token for lyrics fetching.
        """
        self.use_stems = use_stems
        self.genius_token = genius_token
        config = get_config()

        # Lazy-loaded components
        self._transcriber: Optional[Transcriber] = None
        self._synthesizer: Optional[Synthesizer] = None
        self._lyrics_fetcher: Optional[LyricsFetcher] = None
        self._spotify_fetcher: Optional[SpotifyFetcher] = None

    @property
    def transcriber(self) -> Transcriber:
        """Lazy load transcriber."""
        if self._transcriber is None:
            self._transcriber = Transcriber()
        return self._transcriber

    @property
    def synthesizer(self) -> Synthesizer:
        """Lazy load synthesizer."""
        if self._synthesizer is None:
            self._synthesizer = Synthesizer()
        return self._synthesizer

    @property
    def lyrics_fetcher(self) -> LyricsFetcher:
        """Lazy load lyrics fetcher."""
        if self._lyrics_fetcher is None:
            self._lyrics_fetcher = LyricsFetcher(genius_token=self.genius_token)
        return self._lyrics_fetcher

    @property
    def spotify_fetcher(self) -> SpotifyFetcher:
        """Lazy load Spotify fetcher."""
        if self._spotify_fetcher is None:
            self._spotify_fetcher = SpotifyFetcher()
        return self._spotify_fetcher

    @property
    def metadata_fetcher(self):
        """Lazy load MusicBrainz fetcher (fallback for composer/lyricist)."""
        if not hasattr(self, '_metadata_fetcher') or self._metadata_fetcher is None:
            from vectrola.ingest.metadata import MetadataFetcher
            self._metadata_fetcher = MetadataFetcher(genius_token=self.genius_token)
        return self._metadata_fetcher

    def process_track(
        self,
        file_path: Path,
        write_file_tags: bool = True,
        verbose: bool = True,
        gdrive_file_id: Optional[str] = None,
        gdrive_path: Optional[str] = None,
    ) -> TrackAnalysis:
        """
        Process a single audio track through the full pipeline.

        Pipeline:
        1. Read file tags first - if complete, use them
        2. Fetch metadata from Spotify (artist, album, year, spotify_id)
        3. Fetch lyrics from LRClib (with artist from Spotify)
        4. Fetch composer/lyricist from MusicBrainz (fallback)
        5. Fallback to Whisper if no lyrics found
        6. LLM synthesis for themes/moods/narrative
        7. Generate track_id for deduplication
        8. Store in Qdrant (with deduplication check)
        9. Add to user's library

        Args:
            file_path: Path to the audio file
            write_file_tags: Whether to write analysis back to file tags
            verbose: Print progress messages
            gdrive_file_id: Optional Google Drive file ID for cloud playback
            gdrive_path: Optional original path in Google Drive

        Returns:
            TrackAnalysis with all extracted metadata
        """
        import sys

        def log(msg: str):
            if verbose:
                print(f"\n   → {msg}", end="", flush=True)

        file_path = Path(file_path)
        spotify_id = None  # Will be captured from Spotify lookup

        # ===========================================
        # 1. Read existing file tags
        # ===========================================
        log("Reading file tags...")
        file_tags = read_file_tags(file_path)

        title = file_tags.title or file_path.stem
        artists = file_tags.artists or []
        album = file_tags.album or ""
        year = file_tags.year
        composer = file_tags.composer or ""
        movie = ""  # File tags typically don't have movie
        lyricist = ""
        metadata_source = "file_tags" if file_tags.has_metadata else ""

        # ===========================================
        # 2. Fetch metadata from Spotify FIRST (to get artist)
        # ===========================================
        log("Fetching metadata from Spotify...")
        artist_str = artists[0] if artists else ""

        spotify_track = self.spotify_fetcher.get_best_match(title, artist_str)
        spotify_duration_seconds = None  # Track Spotify's duration
        album_art_url = None  # Track album art from Spotify
        if spotify_track:
            # Capture spotify_id for track identification
            spotify_id = spotify_track.spotify_id

            # Capture album art URL
            album_art_url = spotify_track.album_art_url

            # Get artist from Spotify if we don't have one
            if not artists and spotify_track.artists:
                artists = spotify_track.artists
                artist_str = artists[0]
                log(f"Found: {spotify_track.title} by {artist_str}")
            if not year and spotify_track.year:
                year = spotify_track.year
            if not album and spotify_track.album:
                album = spotify_track.album
                # For Bollywood, album is often the movie name
                movie = spotify_track.album
            # Convert duration from ms to seconds
            if spotify_track.duration_ms:
                spotify_duration_seconds = spotify_track.duration_ms / 1000.0
            metadata_source = "spotify"
        else:
            log("Not found on Spotify, trying MusicBrainz...")
            # Fallback to MusicBrainz for basic metadata
            try:
                mb_metadata = self.metadata_fetcher.fetch(title, artist_str)
                if mb_metadata:
                    if not artists and mb_metadata.artists:
                        artists = mb_metadata.artists
                        artist_str = artists[0]
                        log(f"Found: {mb_metadata.title} by {artist_str}")
                    if not year and mb_metadata.year:
                        year = mb_metadata.year
                    if not album and mb_metadata.album:
                        album = mb_metadata.album
                        movie = mb_metadata.album
                    if not composer and mb_metadata.composer:
                        composer = mb_metadata.composer
                    if not lyricist and mb_metadata.lyricist:
                        lyricist = mb_metadata.lyricist
                    metadata_source = "musicbrainz"
                else:
                    log("Not found on MusicBrainz either")
            except Exception as e:
                log(f"MusicBrainz error: {e}")

        # ===========================================
        # 3. Fetch lyrics (Genius → LRClib → Whisper)
        # ===========================================
        log("Fetching lyrics...")
        lyrics_result: Optional[LyricsResult] = None

        # Try with artist + title (artist from file tags OR Spotify)
        if artist_str and artist_str.lower() not in ['unknown artist', 'unknown', 'various']:
            lyrics_result = self.lyrics_fetcher.fetch(
                artist=artist_str,
                title=title,
                audio_path=file_path,
                use_whisper_fallback=False,
            )

        # If no artist or not found, try just title
        if lyrics_result is None:
            lyrics_result = self.lyrics_fetcher.fetch(
                artist="",
                title=title,
                audio_path=file_path,
                use_whisper_fallback=False,
            )

        # ===========================================
        # 4. Use LRClib data to fill missing fields
        # ===========================================
        if lyrics_result:
            lyrics = lyrics_result.text
            lyrics_source = lyrics_result.source
            segments = lyrics_result.segments or []
            # Use LRClib duration if available, otherwise Spotify duration
            duration_seconds = lyrics_result.duration_seconds or spotify_duration_seconds

            # LRClib album is often the movie name for Bollywood
            if not album and lyrics_result.album:
                album = lyrics_result.album

            # For Bollywood, album = movie
            if lyrics_result.album:
                movie = lyrics_result.album

            # Update artists if we got better info from LRClib
            if lyrics_result.artist and not artists:
                artists = [lyrics_result.artist]

            log(f"Found lyrics ({len(lyrics)} chars)")
        else:
            lyrics = ""
            lyrics_source = ""
            segments = []
            duration_seconds = spotify_duration_seconds  # Use Spotify duration if no lyrics
            log("No lyrics found online")

        # ===========================================
        # 5. Fallback to Whisper transcription if no lyrics
        # ===========================================
        if not lyrics:
            log("Transcribing with Whisper (fallback)...")
            transcription = self.transcriber.transcribe(file_path)
            lyrics = transcription.text
            lyrics_source = "whisper"
            segments = transcription.segments

        # Detect language
        if lyrics:
            language = self._detect_language(lyrics)
        else:
            language = ""

        # ===========================================
        # 6. LLM synthesis (themes, mood, narrative)
        # ===========================================
        if lyrics:
            log("Running LLM synthesis...")
            synthesis = self.synthesizer.synthesize(lyrics)
            themes = synthesis.themes
            moods = synthesis.moods
            narrative = synthesis.narrative
            imagery = synthesis.imagery

            # Check for LLM errors
            if moods and moods[0].startswith("["):
                # Error indicator in moods
                log(f"⚠ LLM Error: {narrative}")
            else:
                log(f"Got {len(moods)} moods, {len(themes)} themes")
        else:
            log("Skipping synthesis (no lyrics)")
            themes = []
            moods = []
            narrative = ""
            imagery = []

        # ===========================================
        # 7. Build analysis result
        # ===========================================
        log("Building analysis...")

        # Generate canonical track_id for deduplication
        track_id = generate_track_id(
            spotify_id=spotify_id,
            artist=artists[0] if artists else "",
            title=title,
        )

        # Calculate era from year
        era = calculate_era(year)

        analysis = TrackAnalysis(
            file_path=file_path,
            title=title,
            artists=artists,
            album=album,
            year=year,
            era=era,
            movie=movie,
            composer=composer,
            lyricist=lyricist,
            lyrics=lyrics,
            lyrics_source=lyrics_source,
            segments=segments,
            language=language,
            duration_seconds=duration_seconds,
            themes=themes,
            moods=moods,
            narrative=narrative,
            imagery=imagery,
            metadata_source=metadata_source,
            # Track identification (Day 7)
            track_id=track_id,
            spotify_id=spotify_id,
            # Cloud storage (Day 7)
            gdrive_file_id=gdrive_file_id,
            gdrive_path=gdrive_path,
            # Album art
            album_art_url=album_art_url,
        )

        # ===========================================
        # 8. Generate embeddings and store in Qdrant (with deduplication)
        # ===========================================
        log("Generating embeddings & storing in Qdrant...")
        try:
            from vectrola.ingest.embeddings import get_text_embedder, build_searchable_text
            from vectrola.storage.qdrant import get_db

            db = get_db()
            user_id = get_or_create_user_id()

            # Check if track already exists (deduplication)
            if db.track_exists(track_id):
                log("Track exists in catalog, adding to your library...")
                db.add_user_to_track(track_id, user_id)
            else:
                # New track - generate embeddings
                log("New track, generating embeddings...")

                # Build searchable text with weighted moods + synonyms
                searchable_text = build_searchable_text(lyrics, moods, themes, narrative)

                # Generate embedding from combined text
                embedder = get_text_embedder()
                lyrics_vector = embedder.embed(searchable_text) if searchable_text else None

                if lyrics_vector:
                    analysis.lyrics_vector = lyrics_vector

                    # Store in Qdrant with track_id and user_id
                    db.upsert_track(
                        track_id=track_id,
                        lyrics_vector=lyrics_vector,
                        payload=analysis.to_dict(),
                        user_id=user_id,
                    )

            # ===========================================
            # 9. Add to user's library (always)
            # ===========================================
            log("Adding to user library...")
            try:
                from vectrola.services.library import UserLibrary
                library = UserLibrary(user_id)
                library.add_track(
                    track_id=track_id,
                    gdrive_file_id=gdrive_file_id,
                    local_path=str(file_path),
                )
            except ImportError:
                # Library service not available yet - that's OK
                pass

        except Exception as e:
            # Don't fail the whole pipeline if Qdrant is unavailable
            log(f"Warning: Qdrant error: {e}")

        # ===========================================
        # 10. Write tags to file
        # ===========================================
        if write_file_tags:
            log("Writing tags to file...")
            write_tags(file_path, analysis.to_dict())

        if verbose:
            print()  # Newline after all the → logs

        return analysis

    def _detect_language(self, text: str) -> str:
        """Detect language from text sample."""
        sample = text[:200]
        # Check for Devanagari script (Hindi)
        if any(0x0900 <= ord(c) <= 0x097F for c in sample):
            return "hi"
        # Default to English
        return "en"


# Convenience function for simple usage
def ingest_track(file_path: Path, fast: bool = True) -> TrackAnalysis:
    """
    Ingest a single track with default settings.

    Args:
        file_path: Path to the audio file
        fast: If True, skip Demucs stem separation

    Returns:
        TrackAnalysis with extracted metadata
    """
    pipeline = IngestPipeline(use_stems=not fast)
    return pipeline.process_track(file_path)
