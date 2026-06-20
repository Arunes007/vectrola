"""Main ingestion pipeline orchestrating transcription, synthesis, and storage."""

from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
import json
import hashlib

from vectrola.config import get_config, get_or_create_user_id, get_device_id
from vectrola.ingest.transcribe import Transcriber, TranscriptionResult
from vectrola.ingest.synthesis import Synthesizer, SynthesisResult
from vectrola.ingest.lyrics import LyricsFetcher, LyricsResult
from vectrola.ingest.spotify import SpotifyFetcher, SpotifyTrack
from vectrola.storage.tags import write_tags, read_file_tags, FileTags


def generate_track_id(
    artist: str,
    title: str,
) -> str:
    """
    Generate compact 16-char track ID from artist+title hash.

    Uses MD5 hash of normalized artist+title for universal deduplication
    across all music sources (Spotify, YouTube, SoundCloud, local files).

    Normalization:
    - Lowercase everything
    - Strip whitespace
    - Remove featuring artists (ft., feat., featuring)
    - Remove special characters except letters/numbers

    Args:
        artist: Primary artist name
        title: Track title

    Returns:
        16-character hex hash (e.g., "a1b2c3d4e5f6g7h8")
    """
    import re

    # Normalize artist: remove featuring artists
    artist_clean = re.sub(r'\s+(ft\.|feat\.|featuring)\s+.*', '', artist, flags=re.IGNORECASE)
    artist_clean = re.sub(r'[^a-z0-9\s]', '', artist_clean.lower()).strip()

    # Normalize title: remove special chars
    title_clean = re.sub(r'[^a-z0-9\s]', '', title.lower()).strip()

    # Generate hash
    normalized = f"{artist_clean}:{title_clean}"
    return hashlib.md5(normalized.encode()).hexdigest()[:16]


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


def calculate_checksum(file_path: Path) -> str:
    """
    Calculate MD5 checksum of audio file.

    Args:
        file_path: Path to audio file

    Returns:
        MD5 hex digest (32 characters)
    """
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def find_existing_track(
    db,
    checksum: str,
    title: str,
    artist: Optional[str],
    user_id: str,
) -> Optional[tuple]:
    """
    Find existing track in USER's library using 2-tier deduplication.

    Priority:
    1. Checksum in user's sources (exact file match for THIS user)
    2. track_id (artist+title hash) - global catalog match

    Args:
        db: VectrolaDB instance
        checksum: MD5 hash of audio file
        title: Track title
        artist: Artist name (required for tier 2)
        user_id: User ID (required for tier 1 user-specific checksum matching)

    Returns:
        (point_id, track_id, payload) or None
    """
    from qdrant_client import models

    # 1. Check user's library for checksum match (user-specific)
    try:
        user_entries = db.get_user_library_entries(user_id, limit=10000)
        for entry in user_entries:
            sources = entry.payload.get("sources", {"local": {}, "cloud": {}})

            # Check all local sources
            for device, source_info in sources.get("local", {}).items():
                if isinstance(source_info, dict) and source_info.get("checksum") == checksum:
                    # Found same file in user's library!
                    track_id = entry.payload["track_id"]
                    # Get track details from vectrola_library
                    track_results = db.client.scroll(
                        collection_name=db.COLLECTION,
                        scroll_filter=models.Filter(
                            must=[models.FieldCondition(
                                key="track_id",
                                match=models.MatchValue(value=track_id)
                            )]
                        ),
                        limit=1,
                        with_payload=True
                    )
                    if track_results[0]:
                        track = track_results[0][0]
                        return (track.id, track_id, track.payload)

            # Check cloud sources
            for provider, source_info in sources.get("cloud", {}).items():
                if isinstance(source_info, dict) and source_info.get("checksum") == checksum:
                    track_id = entry.payload["track_id"]
                    # Get track details
                    track_results = db.client.scroll(
                        collection_name=db.COLLECTION,
                        scroll_filter=models.Filter(
                            must=[models.FieldCondition(
                                key="track_id",
                                match=models.MatchValue(value=track_id)
                            )]
                        ),
                        limit=1,
                        with_payload=True
                    )
                    if track_results[0]:
                        track = track_results[0][0]
                        return (track.id, track_id, track.payload)
    except Exception:
        pass

    # 2. Check by track_id (artist+title hash) - global catalog
    if artist and title:
        candidate_track_id = generate_track_id(artist, title)

        try:
            result = db.client.scroll(
                collection_name=db.COLLECTION,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="track_id",
                            match=models.MatchValue(value=candidate_track_id),
                        )
                    ]
                ),
                limit=1,
                with_payload=True,
            )
            if result[0]:
                point = result[0][0]
                return (point.id, point.payload.get("track_id"), point.payload)
        except Exception:
            pass

    return None


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
    track_id: str = ""  # 16-char MD5 hash
    spotify_track_id: Optional[str] = None  # Spotify track ID (separate from track_id)
    spotify_id: Optional[str] = None  # DEPRECATED: use spotify_track_id

    # Multi-device/multi-cloud sources (Day 7+)
    # Structure: {"local": {"hostname": "/path/to/file"}, "cloud": {"gdrive": {"file_id": "...", "path": "..."}}}
    sources: dict = field(default_factory=lambda: {"local": {}, "cloud": {}})

    # Album art
    album_art_url: Optional[str] = None  # Spotify album cover art URL

    # Deduplication
    checksum: str = ""  # MD5 hash of audio file content

    # Internal flag for CLI stats (not stored in DB)
    _was_deduplicated: bool = field(default=False, repr=False)

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
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
            "spotify_track_id": self.spotify_track_id,  # NEW: Separate field
            "spotify_id": self.spotify_id,  # DEPRECATED
            # Album art
            "album_art_url": self.album_art_url,
            # NOTE: sources and checksum NOT included - stored per-user in user_library
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
        force: bool = False,
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

        Args:
            file_path: Path to the audio file
            write_file_tags: Whether to write analysis back to file tags
            verbose: Print progress messages
            gdrive_file_id: Optional Google Drive file ID for cloud playback
            gdrive_path: Optional original path in Google Drive
            force: Skip dedup check and re-analyze even if track exists

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
        # 0. Calculate checksum for deduplication
        # ===========================================
        checksum = calculate_checksum(file_path)

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
        # 1.5. EARLY DEDUP CHECK - Checksum or Title+Artist
        # ===========================================
        db = None
        user_id = None
        device_id = get_device_id()
        if not force:
            try:
                from vectrola.storage.qdrant import get_db
                db = get_db()
                user_id = get_or_create_user_id()
                artist_str = artists[0] if artists else None

                existing = find_existing_track(
                    db=db,
                    checksum=checksum,
                    title=title,
                    artist=artist_str,
                    user_id=user_id,
                )

                if existing:
                    point_id, track_id, payload = existing
                    log(f"✓ Found existing track (skipping analysis): {title}")

                    # Get user's library entry
                    user_entries = db.get_user_library_entries(user_id, limit=10000)
                    user_entry = next((e for e in user_entries if e.payload["track_id"] == track_id), None)

                    if user_entry:
                        # User already has this track, update sources
                        user_sources = user_entry.payload.get("sources", {"local": {}, "cloud": {}})

                        # Add/update local device path with checksum
                        if "local" not in user_sources:
                            user_sources["local"] = {}
                        user_sources["local"][device_id] = {
                            "file_path": str(file_path),
                            "checksum": checksum
                        }

                        # Add/update GDrive if provided
                        if gdrive_file_id:
                            if "cloud" not in user_sources:
                                user_sources["cloud"] = {}
                            user_sources["cloud"]["gdrive"] = {
                                "file_id": gdrive_file_id,
                                "path": gdrive_path or "",
                                "checksum": checksum
                            }

                        # Update user_library entry with new sources
                        db.client.set_payload(
                            collection_name=db.USER_LIBRARY_COLLECTION,
                            payload={"sources": user_sources},
                            points=[user_entry.id]
                        )
                    else:
                        # User doesn't have this track yet, add to library
                        sources = {
                            "local": {
                                device_id: {
                                    "file_path": str(file_path),
                                    "checksum": checksum
                                }
                            },
                            "cloud": {}
                        }
                        if gdrive_file_id:
                            sources["cloud"]["gdrive"] = {
                                "file_id": gdrive_file_id,
                                "path": gdrive_path or "",
                                "checksum": checksum
                            }

                        db.add_track_to_user_library(
                            user_id=user_id,
                            track_id=track_id,
                            sources=sources
                        )

                    # Fetch thumbnail if missing
                    existing_album_art = payload.get("album_art_url")
                    if not existing_album_art:
                        spotify_track_id = payload.get("spotify_track_id") or payload.get("spotify_id")
                        if spotify_track_id:
                            from vectrola.ingest.spotify import fetch_spotify_thumbnail
                            thumbnail = fetch_spotify_thumbnail(spotify_track_id)
                            if thumbnail:
                                db.client.set_payload(
                                    collection_name=db.COLLECTION,
                                    payload={"album_art_url": thumbnail},
                                    points=[point_id]
                                )
                                existing_album_art = thumbnail
                                log(f"✓ Fetched missing thumbnail")

                    # Return TrackAnalysis from existing payload
                    return TrackAnalysis(
                        file_path=file_path,
                        title=payload.get("title", title),
                        artists=payload.get("artists", artists),
                        album=payload.get("album", album),
                        year=payload.get("year"),
                        era=payload.get("era", ""),
                        movie=payload.get("movie", ""),
                        composer=payload.get("composer", ""),
                        lyricist=payload.get("lyricist", ""),
                        lyrics=payload.get("lyrics", ""),
                        lyrics_source=payload.get("lyrics_source", ""),
                        language=payload.get("language", ""),
                        duration_seconds=payload.get("duration_seconds"),
                        themes=payload.get("themes", []),
                        moods=payload.get("moods", []),
                        narrative=payload.get("narrative", ""),
                        imagery=payload.get("imagery", []),
                        metadata_source=payload.get("metadata_source", ""),
                        track_id=track_id,
                        spotify_track_id=payload.get("spotify_track_id") or payload.get("spotify_id"),
                        spotify_id=payload.get("spotify_id"),  # DEPRECATED
                        sources={},  # Not used anymore
                        album_art_url=existing_album_art,
                        checksum=checksum,
                        _was_deduplicated=True,  # ← Mark as existing
                    )
            except Exception as e:
                log(f"Dedup check skipped: {e}")
        else:
            log("Force mode: skipping dedup check")

        # ===========================================
        # 2. Fetch metadata from Spotify FIRST (to get artist)
        # ===========================================
        log("Fetching metadata from Spotify...")
        artist_str = artists[0] if artists else ""

        # Check if file has embedded album art (skip thumbnail fetch if so)
        from vectrola.storage.tags import has_embedded_artwork
        file_has_artwork = has_embedded_artwork(file_path)

        spotify_track = self.spotify_fetcher.get_best_match(title, artist_str)
        spotify_duration_seconds = None  # Track Spotify's duration
        album_art_url = None  # Track album art from Spotify
        if spotify_track:
            # Capture spotify_id for track identification
            spotify_id = spotify_track.spotify_id

            # Capture album art URL (skip if file already has embedded art)
            if not file_has_artwork:
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

        # Generate canonical track_id for deduplication (16-char hash)
        track_id = generate_track_id(
            artist=artists[0] if artists else "",
            title=title,
        )

        # Calculate era from year
        era = calculate_era(year)

        # Build sources structure for this device
        sources = {"local": {}, "cloud": {}}
        sources["local"][device_id] = str(file_path)
        if gdrive_file_id:
            sources["cloud"]["gdrive"] = {
                "file_id": gdrive_file_id,
                "path": gdrive_path or ""
            }

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
            spotify_track_id=spotify_id,  # NEW: Store Spotify ID separately
            spotify_id=spotify_id,  # DEPRECATED: Keep for backward compat during migration
            # Multi-device sources
            sources=sources,
            # Album art
            album_art_url=album_art_url,
            # Deduplication
            checksum=checksum,
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

                    # Store in Qdrant (track catalog)
                    db.upsert_track(
                        track_id=track_id,
                        lyrics_vector=lyrics_vector,
                        payload=analysis.to_dict(),
                        audio_vector=None,  # TODO: Add CLAP support
                    )

                    # NEW: Add to user_library collection with sources
                    sources = {
                        "local": {
                            device_id: {
                                "file_path": str(file_path),
                                "checksum": checksum
                            }
                        },
                        "cloud": {}
                    }
                    if gdrive_file_id:
                        sources["cloud"]["gdrive"] = {
                            "file_id": gdrive_file_id,
                            "path": gdrive_path or "",
                            "checksum": checksum
                        }

                    db.add_track_to_user_library(
                        user_id=user_id,
                        track_id=track_id,
                        sources=sources
                    )

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
