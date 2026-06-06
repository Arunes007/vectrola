"""Qdrant vector database storage for multimodal music search."""

from pathlib import Path
from typing import Optional
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

    This enables hybrid search with Reciprocal Rank Fusion (RRF).
    """

    COLLECTION = "vectrola_library"
    LYRICS_VECTOR_SIZE = 384  # all-MiniLM-L6-v2
    ACOUSTIC_VECTOR_SIZE = 512  # CLAP (Day 3)

    def __init__(self, url: str = "http://localhost:6333"):
        """
        Initialize connection to Qdrant.

        Args:
            url: Qdrant server URL
        """
        self.url = url
        self._client: Optional[QdrantClient] = None

    @property
    def client(self) -> QdrantClient:
        """Lazy connect to Qdrant."""
        if self._client is None:
            self._client = QdrantClient(url=self.url)
            self._ensure_collection()
        return self._client

    def _ensure_collection(self):
        """Create collection with named vectors if not exists."""
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
        except Exception as e:
            print(f"Error ensuring collection: {e}")
            raise
        except Exception as e:
            print(f"Error ensuring collection: {e}")
            raise

    def _generate_id(self, file_path: str) -> str:
        """Generate deterministic UUID from file path."""
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, file_path))

    def upsert_track(
        self,
        file_path: str,
        lyrics_vector: list[float],
        payload: dict,
        audio_vector: Optional[list[float]] = None,
    ) -> str:
        """
        Insert or update a track with its vectors.

        Args:
            file_path: Path to the audio file (used as unique ID)
            lyrics_vector: 384-dim lyrics embedding
            payload: Metadata (title, artist, moods, themes, etc.)
            audio_vector: Optional 512-dim CLAP embedding (Day 3)

        Returns:
            The point ID
        """
        point_id = self._generate_id(file_path)

        vectors = {"lyrics_dense": lyrics_vector}

        # Add acoustic vector if provided (Day 3)
        if audio_vector is not None:
            vectors["acoustic_clap"] = audio_vector

        # Ensure payload includes file_path for retrieval
        payload["file_path"] = file_path

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
    ) -> list[models.ScoredPoint]:
        """
        Search tracks by lyrics embedding.

        Args:
            query_vector: 384-dim query embedding
            limit: Max results to return
            score_threshold: Min similarity score (0-1)

        Returns:
            List of ScoredPoint with payload and score
        """
        return self.client.query_points(
            collection_name=self.COLLECTION,
            query=query_vector,
            using="lyrics_dense",
            limit=limit,
            score_threshold=score_threshold,
        ).points

    def search_by_audio(
        self,
        query_vector: list[float],
        limit: int = 10,
        score_threshold: Optional[float] = None,
    ) -> list[models.ScoredPoint]:
        """
        Search tracks by acoustic embedding (Day 3).

        Args:
            query_vector: 512-dim CLAP embedding
            limit: Max results to return
            score_threshold: Min similarity score (0-1)

        Returns:
            List of ScoredPoint with payload and score
        """
        return self.client.query_points(
            collection_name=self.COLLECTION,
            query=query_vector,
            using="acoustic_clap",
            limit=limit,
            score_threshold=score_threshold,
        ).points

    def hybrid_search(
        self,
        lyrics_vector: list[float],
        audio_vector: list[float],
        limit: int = 10,
    ) -> list[models.ScoredPoint]:
        """
        True multimodal search using Reciprocal Rank Fusion (Day 3).

        Combines lyrics semantics + acoustic texture in a SINGLE query.

        Args:
            lyrics_vector: 384-dim lyrics embedding
            audio_vector: 512-dim CLAP embedding
            limit: Max results to return

        Returns:
            RRF-fused results from both vector spaces
        """
        return self.client.query_points(
            collection_name=self.COLLECTION,
            prefetch=[
                models.Prefetch(
                    query=lyrics_vector,
                    using="lyrics_dense",
                    limit=20,
                ),
                models.Prefetch(
                    query=audio_vector,
                    using="acoustic_clap",
                    limit=20,
                ),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=limit,
        ).points

    def get_track(self, file_path: str) -> Optional[models.Record]:
        """
        Get a track by file path.

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

    def is_connected(self) -> bool:
        """Check if Qdrant is reachable."""
        try:
            self.client.get_collections()
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
        _db = VectrolaDB(url=config.qdrant_url)
    return _db
