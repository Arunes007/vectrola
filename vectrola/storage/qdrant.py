"""Qdrant vector database storage for multimodal music search."""

from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
import uuid

from qdrant_client import QdrantClient, models
from qdrant_client.http.exceptions import UnexpectedResponse

from vectrola.config import get_config


class VectrolaDB:
    """
    Qdrant storage with named vectors for multimodal fusion.

    Uses a single collection with named vectors:
    - lyrics_dense: 384-dim sentence-transformers embeddings
    - acoustic_clap: 512-dim CLAP audio embeddings (Day 3)

    Day 7 additions:
    - Support for remote Qdrant with API key
    - Track ID based indexing for deduplication
    - User filtering for multi-tenant search
    """

    COLLECTION = "vectrola_library"
    USER_LIBRARY_COLLECTION = "user_library"  # NEW: User-track mapping
    LYRICS_VECTOR_SIZE = 384  # all-MiniLM-L6-v2
    ACOUSTIC_VECTOR_SIZE = 512  # CLAP (Day 3)

    def __init__(self, url: str = "http://localhost:6333", api_key: Optional[str] = None):
        """
        Initialize connection to Qdrant.

        Args:
            url: Qdrant server URL
            api_key: Optional API key for remote Qdrant (Railway, etc.)
        """
        self.url = url
        self.api_key = api_key
        self._client: Optional[QdrantClient] = None

    @property
    def client(self) -> QdrantClient:
        """Lazy connect to Qdrant with optional API key."""
        if self._client is None:
            # Parse URL to handle remote Qdrant (Railway, etc.) correctly
            # qdrant-client's url parameter adds :6333 by default, which breaks Railway
            parsed = urlparse(self.url)
            is_https = parsed.scheme == "https"
            is_remote = is_https or (parsed.port and parsed.port != 6333)

            if is_remote:
                # Use host/port/https for remote Qdrant
                host = parsed.hostname
                port = parsed.port or (443 if is_https else 6333)
                self._client = QdrantClient(
                    host=host,
                    port=port,
                    https=is_https,
                    api_key=self.api_key,
                    timeout=30,
                )
            else:
                # Local Qdrant - use url directly
                self._client = QdrantClient(url=self.url, api_key=self.api_key, timeout=30)

            self._ensure_collection()
        return self._client

    def _ensure_collection(self):
        """Create collections if not exists."""
        try:
            collections = [c.name for c in self._client.get_collections().collections]

            if self.COLLECTION not in collections:
                self._client.create_collection(
                    collection_name=self.COLLECTION,
                    vectors_config={
                        "lyrics_dense": models.VectorParams(
                            size=self.LYRICS_VECTOR_SIZE,
                            distance=models.Distance.COSINE,
                        ),
                        "acoustic_clap": models.VectorParams(
                            size=self.ACOUSTIC_VECTOR_SIZE,
                            distance=models.Distance.COSINE,
                        ),
                    },
                )
                print(f"✓ Created collection '{self.COLLECTION}' with both vectors")

            # Create payload indexes for efficient filtering (Day 7)
            self._ensure_indexes()

            # NEW: Create user_library collection
            self._ensure_user_library_collection()

        except Exception as e:
            print(f"Error ensuring collection: {e}")
            raise

    def _ensure_indexes(self):
        """Create payload indexes for track_id filtering."""
        try:
            # Index for track_id (deduplication lookups)
            self._client.create_payload_index(
                collection_name=self.COLLECTION,
                field_name="track_id",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
        except Exception:
            pass  # Index may already exist

        try:
            # Index for checksum (deduplication by file hash)
            self._client.create_payload_index(
                collection_name=self.COLLECTION,
                field_name="checksum",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
        except Exception:
            pass  # Index may already exist

    def _ensure_user_library_collection(self):
        """Create user_library collection for many-to-many user-track mapping."""
        try:
            collections = [c.name for c in self._client.get_collections().collections]

            if self.USER_LIBRARY_COLLECTION not in collections:
                # No vectors needed - this is pure payload storage
                self._client.create_collection(
                    collection_name=self.USER_LIBRARY_COLLECTION,
                    vectors_config={}  # Empty = payload-only collection
                )
                print(f"✓ Created collection '{self.USER_LIBRARY_COLLECTION}'")

            # Create indexes for fast filtering
            self._ensure_user_library_indexes()

        except Exception as e:
            print(f"Error ensuring user_library collection: {e}")
            raise

    def _ensure_user_library_indexes(self):
        """Create indexes for user_id and track_id filtering."""
        try:
            # Index for user_id (primary filter)
            self._client.create_payload_index(
                collection_name=self.USER_LIBRARY_COLLECTION,
                field_name="user_id",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
        except Exception:
            pass  # May already exist

        try:
            # Index for track_id (join key)
            self._client.create_payload_index(
                collection_name=self.USER_LIBRARY_COLLECTION,
                field_name="track_id",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
        except Exception:
            pass

    def _generate_id(self, identifier: str) -> str:
        """Generate deterministic UUID from identifier (track_id or file_path)."""
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, identifier))

    def track_exists(self, track_id: str) -> bool:
        """
        Check if a track with this ID already has embeddings.

        Args:
            track_id: Canonical track ID (e.g., "spotify:xxx" or "hash:xxx")

        Returns:
            True if track exists in the catalog
        """
        try:
            results = self.client.scroll(
                collection_name=self.COLLECTION,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="track_id",
                            match=models.MatchValue(value=track_id),
                        )
                    ]
                ),
                limit=1,
            )
            return len(results[0]) > 0
        except Exception:
            return False

    def get_track_by_id(self, track_id: str) -> Optional[models.Record]:
        """
        Get a track by its canonical track_id.

        Args:
            track_id: Canonical track ID (e.g., "spotify:xxx" or "hash:xxx")

        Returns:
            Record with vectors and payload, or None
        """
        try:
            results = self.client.scroll(
                collection_name=self.COLLECTION,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="track_id",
                            match=models.MatchValue(value=track_id),
                        )
                    ]
                ),
                limit=1,
                with_payload=True,
                with_vectors=True,
            )
            return results[0][0] if results[0] else None
        except Exception:
            return None

    def add_track_to_user_library(
        self,
        user_id: str,
        track_id: str,
        sources: dict,
    ) -> str:
        """
        Add a track to user's library (user_library collection).

        Args:
            user_id: User ID
            track_id: 16-char track hash
            sources: Full sources object with device-level checksums
                     Format: {"local": {"device": {"file_path": "...", "checksum": "..."}},
                              "cloud": {"gdrive": {"file_id": "...", "path": "...", "checksum": "..."}}}

        Returns:
            Library entry UUID
        """
        from datetime import datetime

        # Generate unique ID for this library entry
        entry_id = str(uuid.uuid4())

        payload = {
            "user_id": user_id,
            "track_id": track_id,
            "sources": sources,
            "added_at": datetime.utcnow().isoformat(),
        }

        self.client.upsert(
            collection_name=self.USER_LIBRARY_COLLECTION,
            points=[
                models.PointStruct(
                    id=entry_id,
                    vector={},  # No vectors in this collection
                    payload=payload,
                )
            ],
        )

        return entry_id

    def get_user_track_ids(self, user_id: str, limit: int = 10000) -> list[str]:
        """
        Get all track IDs in user's library.

        Args:
            user_id: User ID
            limit: Max tracks to return (use pagination for >10K)

        Returns:
            List of 16-char track hashes
        """
        results = self.client.scroll(
            collection_name=self.USER_LIBRARY_COLLECTION,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="user_id",
                        match=models.MatchValue(value=user_id),
                    )
                ]
            ),
            limit=limit,
            with_vectors=False,
        )

        return [r.payload["track_id"] for r in results[0]]

    def get_user_library_entries(
        self,
        user_id: str,
        limit: int = 10000
    ) -> list[models.Record]:
        """
        Get all library entries for a user (with file paths, GDrive IDs, etc.).

        Args:
            user_id: User ID
            limit: Max entries to return

        Returns:
            List of Records with full payload
        """
        results = self.client.scroll(
            collection_name=self.USER_LIBRARY_COLLECTION,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="user_id",
                        match=models.MatchValue(value=user_id),
                    )
                ]
            ),
            limit=limit,
            with_vectors=False,
        )

        return results[0]

    def remove_track_from_user_library(
        self,
        user_id: str,
        track_id: str
    ) -> bool:
        """
        Remove a track from user's library.

        Args:
            user_id: User ID
            track_id: 16-char track hash

        Returns:
            True if removed, False if not found
        """
        # Find the library entry
        results = self.client.scroll(
            collection_name=self.USER_LIBRARY_COLLECTION,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(key="user_id", match=models.MatchValue(value=user_id)),
                    models.FieldCondition(key="track_id", match=models.MatchValue(value=track_id)),
                ]
            ),
            limit=1,
            with_vectors=False,
        )

        if not results[0]:
            return False

        entry_id = results[0][0].id
        self.client.delete(
            collection_name=self.USER_LIBRARY_COLLECTION,
            points_selector=models.PointIdsList(points=[entry_id]),
        )

        return True

    def add_user_to_track(self, track_id: str, user_id: str) -> bool:
        """
        DEPRECATED: Add a user to an existing track's user_ids array.

        Use add_track_to_user_library() instead.

        Used when a track already exists in the catalog and a new user
        wants to add it to their library.

        Args:
            track_id: Canonical track ID
            user_id: User ID to add

        Returns:
            True if successful, False if track not found
        """
        try:
            # Find the point by track_id
            results = self.client.scroll(
                collection_name=self.COLLECTION,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="track_id",
                            match=models.MatchValue(value=track_id),
                        )
                    ]
                ),
                limit=1,
                with_payload=True,
            )

            if not results[0]:
                return False

            point = results[0][0]
            user_ids = point.payload.get("user_ids", [])

            if user_id not in user_ids:
                user_ids.append(user_id)
                self.client.set_payload(
                    collection_name=self.COLLECTION,
                    payload={"user_ids": user_ids},
                    points=[point.id],
                )

            return True
        except Exception as e:
            print(f"Error adding user to track: {e}")
            return False

    def upsert_track(
        self,
        track_id: str,
        lyrics_vector: list[float],
        payload: dict,
        audio_vector: Optional[list[float]] = None,
    ) -> str:
        """
        Insert or update a track with its vectors.

        Args:
            track_id: 16-char track hash
            lyrics_vector: 384-dim lyrics embedding
            payload: Metadata (title, artist, moods, themes, etc.)
            audio_vector: Optional 512-dim CLAP embedding (Day 3)

        Returns:
            The point ID
        """
        # Use track_id for deterministic point ID
        point_id = self._generate_id(track_id)

        vectors = {"lyrics_dense": lyrics_vector}

        # Add acoustic vector if provided (Day 3)
        if audio_vector is not None:
            vectors["acoustic_clap"] = audio_vector

        # Ensure track_id is in payload
        payload["track_id"] = track_id

        self.client.upsert(
            collection_name=self.COLLECTION,
            points=[
                models.PointStruct(
                    id=point_id,
                    vector=vectors,
                    payload=payload,
                )
            ],
        )

        return point_id

    def search_by_lyrics(
        self,
        query_vector: list[float],
        limit: int = 10,
        score_threshold: Optional[float] = None,
        user_id: Optional[str] = None,
    ) -> list[models.ScoredPoint]:
        """
        Search tracks by lyrics embedding.

        Args:
            query_vector: 384-dim query embedding
            limit: Max results to return
            score_threshold: Min similarity score (0-1)
            user_id: Optional user ID to filter results to user's library

        Returns:
            List of ScoredPoint with payload and score
        """
        query_filter = None
        if user_id:
            # NEW: Get user's track IDs from user_library collection
            track_ids = self.get_user_track_ids(user_id, limit=10000)

            if not track_ids:
                return []  # User has no tracks

            # Filter by track_id (not user_ids array anymore)
            query_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="track_id",
                        match=models.MatchAny(any=track_ids[:1000]),  # Qdrant limit
                    )
                ]
            )

        return self.client.query_points(
            collection_name=self.COLLECTION,
            query=query_vector,
            using="lyrics_dense",
            limit=limit,
            score_threshold=score_threshold,
            query_filter=query_filter,
        ).points

    def search_by_audio(
        self,
        query_vector: list[float],
        limit: int = 10,
        score_threshold: Optional[float] = None,
        user_id: Optional[str] = None,
    ) -> list[models.ScoredPoint]:
        """
        Search tracks by acoustic embedding (Day 3).

        Args:
            query_vector: 512-dim CLAP embedding
            limit: Max results to return
            score_threshold: Min similarity score (0-1)
            user_id: Optional user ID to filter results to user's library

        Returns:
            List of ScoredPoint with payload and score
        """
        query_filter = None
        if user_id:
            # NEW: Get user's track IDs from user_library collection
            track_ids = self.get_user_track_ids(user_id, limit=10000)

            if not track_ids:
                return []  # User has no tracks

            # Filter by track_id
            query_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="track_id",
                        match=models.MatchAny(any=track_ids[:1000]),  # Qdrant limit
                    )
                ]
            )

        return self.client.query_points(
            collection_name=self.COLLECTION,
            query=query_vector,
            using="acoustic_clap",
            limit=limit,
            score_threshold=score_threshold,
            query_filter=query_filter,
        ).points

    def hybrid_search(
        self,
        lyrics_vector: list[float],
        audio_vector: list[float],
        limit: int = 10,
        user_id: Optional[str] = None,
    ) -> list[models.ScoredPoint]:
        """
        True multimodal search using Reciprocal Rank Fusion (Day 3).

        Combines lyrics semantics + acoustic texture in a SINGLE query.

        Args:
            lyrics_vector: 384-dim lyrics embedding
            audio_vector: 512-dim CLAP embedding
            limit: Max results to return
            user_id: Optional user ID to filter results to user's library

        Returns:
            RRF-fused results from both vector spaces
        """
        query_filter = None
        if user_id:
            # NEW: Get user's track IDs from user_library collection
            track_ids = self.get_user_track_ids(user_id, limit=10000)

            if not track_ids:
                return []  # User has no tracks

            # Filter by track_id
            query_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="track_id",
                        match=models.MatchAny(any=track_ids[:1000]),  # Qdrant limit
                    )
                ]
            )

        return self.client.query_points(
            collection_name=self.COLLECTION,
            prefetch=[
                models.Prefetch(
                    query=lyrics_vector,
                    using="lyrics_dense",
                    limit=20,
                    filter=query_filter,
                ),
                models.Prefetch(
                    query=audio_vector,
                    using="acoustic_clap",
                    limit=20,
                    filter=query_filter,
                ),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=limit,
        ).points

    def get_track(self, file_path: str) -> Optional[models.Record]:
        """
        Get a track by file path (legacy method for backward compatibility).

        Args:
            file_path: Path to the audio file

        Returns:
            Record with vectors and payload, or None
        """
        point_id = self._generate_id(file_path)
        try:
            results = self.client.retrieve(
                collection_name=self.COLLECTION,
                ids=[point_id],
                with_vectors=True,
            )
            return results[0] if results else None
        except Exception:
            return None

    def delete_track(self, file_path: str) -> bool:
        """
        Delete a track by file path.

        Args:
            file_path: Path to the audio file

        Returns:
            True if deleted, False if not found
        """
        point_id = self._generate_id(file_path)
        try:
            self.client.delete(
                collection_name=self.COLLECTION,
                points_selector=models.PointIdsList(points=[point_id]),
            )
            return True
        except Exception:
            return False

    def update_payload(self, file_path: str, payload_updates: dict) -> bool:
        """
        Update specific fields in a track's payload without changing vectors.

        Args:
            file_path: Path to the audio file
            payload_updates: Dictionary of fields to update (merged with existing)

        Returns:
            True if updated, False if track not found
        """
        point_id = self._generate_id(file_path)
        try:
            self.client.set_payload(
                collection_name=self.COLLECTION,
                payload=payload_updates,
                points=[point_id],
            )
            return True
        except Exception as e:
            print(f"Error updating payload: {e}")
            return False

    def count(self) -> int:
        """Get total number of tracks in the collection."""
        try:
            info = self.client.get_collection(self.COLLECTION)
            return info.points_count
        except Exception:
            return 0

    def list_all(self, limit: int = 100) -> list[models.Record]:
        """
        List all tracks in the collection.

        Args:
            limit: Max tracks to return

        Returns:
            List of Records with payload
        """
        results = self.client.scroll(
            collection_name=self.COLLECTION,
            limit=limit,
            with_vectors=False,
        )
        return results[0]  # (records, next_offset)

    def list_user_tracks(self, user_id: str, limit: int = 100) -> list[models.Record]:
        """
        List tracks in a specific user's library.

        Args:
            user_id: User ID to filter by
            limit: Max tracks to return

        Returns:
            List of Records owned by the user
        """
        # Get user's track IDs from user_library collection
        track_ids = self.get_user_track_ids(user_id, limit=limit)

        if not track_ids:
            return []

        # Fetch track details from vectrola_library collection
        results = self.client.scroll(
            collection_name=self.COLLECTION,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="track_id",
                        match=models.MatchAny(any=track_ids[:1000]),  # Qdrant limit
                    )
                ]
            ),
            limit=limit,
            with_vectors=False,
        )
        return results[0]

    def is_connected(self) -> bool:
        """Check if Qdrant is reachable."""
        try:
            self.client.get_collections()
            return True
        except Exception:
            return False

    def get_all_tracks(self, limit: int = 10000) -> list[dict]:
        """
        Get all tracks from the database as plain dicts.

        Args:
            limit: Max tracks to return

        Returns:
            List of track metadata dicts
        """
        results = self.client.scroll(
            collection_name=self.COLLECTION,
            limit=limit,
            with_vectors=False,
            with_payload=True,
        )

        tracks = []
        for record in results[0]:
            payload = record.payload
            payload["id"] = record.id
            tracks.append(payload)

        return tracks

    def update_track_metadata(self, track_id: str, updates: dict) -> bool:
        """
        Update metadata for a track.

        Args:
            track_id: Track ID (spotify:xxx or hash:xxx)
            updates: Dict of fields to update

        Returns:
            True if successful
        """
        point_id = self._generate_id(track_id)

        try:
            self.client.set_payload(
                collection_name=self.COLLECTION,
                payload=updates,
                points=[point_id],
            )
            return True
        except Exception:
            return False


# Singleton instance
_db: Optional[VectrolaDB] = None


def get_db() -> VectrolaDB:
    """Get the singleton VectrolaDB instance."""
    global _db
    if _db is None:
        config = get_config()
        _db = VectrolaDB(url=config.qdrant_url, api_key=config.qdrant_api_key)
    return _db
