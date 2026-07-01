"""Semantic search over the music library."""

from dataclasses import dataclass
from typing import Optional

from vectrola.storage.qdrant import get_db, VectrolaDB
from vectrola.ingest.embeddings import get_text_embedder, get_audio_embedder, TextEmbedder, AudioEmbedder
from vectrola.config import get_or_create_user_id, get_config


@dataclass
class SearchResult:
    """A single search result."""

    file_path: str
    title: str
    artists: list[str]
    album: str
    movie: str
    score: float
    moods: list[str]
    themes: list[str]
    narrative: str
    lyrics_preview: str  # First 200 chars of lyrics
    track_id: str = ""  # Canonical track ID

    def __str__(self) -> str:
        artist_str = ", ".join(self.artists) if self.artists else "Unknown"
        return f"{artist_str} - {self.title} (score: {self.score:.2f})"


class SemanticSearch:
    """
    Semantic search over the music library.

    Supports:
    - Lyrics-only search (Day 2)
    - Audio-only search (acoustic similarity, Day 3)
    - Hybrid RRF search (lyrics + audio, Day 3)
    - User-filtered search (Day 7) - only returns tracks in user's library
    """

    def __init__(self, user_id: Optional[str] = None):
        """
        Initialize semantic search.

        Args:
            user_id: User ID for filtering results to user's library.
                     If None and multi_tenant is enabled, uses auto-generated ID.
        """
        self._db: Optional[VectrolaDB] = None
        self._text_embedder: Optional[TextEmbedder] = None
        self._audio_embedder: Optional[AudioEmbedder] = None

        # User filtering (Day 7)
        config = get_config()
        if user_id:
            self.user_id = user_id
        elif config.multi_tenant:
            self.user_id = get_or_create_user_id()
        else:
            self.user_id = None  # No filtering in single-user mode

    @property
    def db(self) -> VectrolaDB:
        """Lazy load database connection."""
        if self._db is None:
            self._db = get_db()
        return self._db

    @property
    def text_embedder(self) -> TextEmbedder:
        """Lazy load text embedder."""
        if self._text_embedder is None:
            self._text_embedder = get_text_embedder()
        return self._text_embedder

    @property
    def audio_embedder(self) -> AudioEmbedder:
        """Lazy load audio embedder."""
        if self._audio_embedder is None:
            self._audio_embedder = get_audio_embedder()
        return self._audio_embedder

    def search(
        self,
        query: str,
        limit: int = 10,
        score_threshold: float = 0.3,
        mode: str = "hybrid",
    ) -> list[SearchResult]:
        """
        Search tracks by natural language query.

        In multi-tenant mode, results are filtered to user's library.

        Examples:
            - "melancholic songs about time passing"
            - "upbeat Hindi songs for a party"
            - "songs about rain and loneliness"
            - "romantic Bollywood duets"

        Args:
            query: Natural language search query
            limit: Maximum number of results
            score_threshold: Minimum similarity score (0-1)
            mode: Search mode - "hybrid" (default), "lyrics", or "audio"

        Returns:
            List of SearchResult ordered by relevance
        """
        if mode == "hybrid":
            # Hybrid RRF search (lyrics + audio)
            lyrics_vector = self.text_embedder.embed(query)
            audio_vector = self.audio_embedder.embed_text(query)  # CLAP text embedding

            results = self.db.hybrid_search(
                lyrics_vector=lyrics_vector,
                audio_vector=audio_vector,
                limit=limit,
                user_id=self.user_id,  # User filtering (Day 7)
            )

        elif mode == "audio":
            # Audio-only search
            audio_vector = self.audio_embedder.embed_text(query)
            results = self.db.search_by_audio(
                query_vector=audio_vector,
                limit=limit,
                score_threshold=score_threshold,
                user_id=self.user_id,  # User filtering (Day 7)
            )

        else:
            # Lyrics-only search (default for Day 2 compat)
            query_vector = self.text_embedder.embed(query)
            results = self.db.search_by_lyrics(
                query_vector=query_vector,
                limit=limit,
                score_threshold=score_threshold,
                user_id=self.user_id,  # User filtering (Day 7)
            )

        # Convert to SearchResult objects
        return self._results_to_search_results(results)

    def find_similar(
        self,
        file_path: str,
        limit: int = 10,
        mode: str = "audio",
    ) -> list[SearchResult]:
        """
        Find tracks similar to a given track.

        In multi-tenant mode, results are filtered to user's library.

        Args:
            file_path: Path to the reference track
            limit: Maximum number of results
            mode: Similarity mode - "audio" (acoustic, default) or "lyrics"

        Returns:
            List of similar tracks (excluding the reference)
        """
        # Get the track's embedding
        track = self.db.get_track(file_path)
        if not track or not track.vector:
            return []

        if mode == "audio":
            # Acoustic similarity (Day 3)
            if "acoustic_clap" not in track.vector:
                return []
            vector = track.vector["acoustic_clap"]
            results = self.db.search_by_audio(
                query_vector=vector,
                limit=limit + 1,
                user_id=self.user_id,  # User filtering (Day 7)
            )
        else:
            # Lyrics similarity (Day 2)
            if "lyrics_dense" not in track.vector:
                return []
            vector = track.vector["lyrics_dense"]
            results = self.db.search_by_lyrics(
                query_vector=vector,
                limit=limit + 1,
                user_id=self.user_id,  # User filtering (Day 7)
            )

        # Convert and filter out self
        search_results = []
        for r in self._results_to_search_results(results):
            if r.file_path != file_path:
                search_results.append(r)
                if len(search_results) >= limit:
                    break

        return search_results

    def _results_to_search_results(self, results) -> list[SearchResult]:
        """Convert Qdrant results to SearchResult objects."""
        search_results = []
        for r in results:
            payload = r.payload or {}

            lyrics = payload.get("lyrics", "")
            lyrics_preview = lyrics[:200] + "..." if len(lyrics) > 200 else lyrics

            search_results.append(
                SearchResult(
                    file_path=payload.get("file_path", ""),
                    title=payload.get("title", "Unknown"),
                    artists=payload.get("artists", []),
                    album=payload.get("album", ""),
                    movie=payload.get("movie", ""),
                    score=r.score,
                    moods=payload.get("moods", []),
                    themes=payload.get("themes", []),
                    narrative=payload.get("narrative", ""),
                    lyrics_preview=lyrics_preview,
                    track_id=payload.get("track_id", ""),  # Day 7
                )
            )
        return search_results


# Convenience functions
def search_by_vibe(query: str, limit: int = 10, user_id: Optional[str] = None) -> list[SearchResult]:
    """
    Search the music library by vibe/description.

    Args:
        query: Natural language description (e.g., "sad songs about heartbreak")
        limit: Number of results
        user_id: Optional user ID for filtering (multi-tenant mode)

    Returns:
        List of matching tracks
    """
    searcher = SemanticSearch(user_id=user_id)
    return searcher.search(query, limit=limit)


def find_similar_tracks(file_path: str, limit: int = 10, user_id: Optional[str] = None) -> list[SearchResult]:
    """
    Find tracks similar to a given track.

    Args:
        file_path: Path to the reference track
        limit: Number of results
        user_id: Optional user ID for filtering (multi-tenant mode)

    Returns:
        List of similar tracks
    """
    searcher = SemanticSearch(user_id=user_id)
    return searcher.find_similar(file_path, limit=limit)
