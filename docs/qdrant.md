# Qdrant Vector Database

Vectrola uses Qdrant as its vector database for semantic search. Qdrant stores track embeddings and enables fast similarity search.

## Setup

### Start Qdrant with Docker

```bash
# Start Qdrant (data persists in Docker volume)
docker run -d --name qdrant -p 6333:6333 -p 6334:6334 \
  -v qdrant_storage:/qdrant/storage \
  qdrant/qdrant

# Check if running
curl http://localhost:6333/collections
```

### Verify Connection

```bash
vectrola status
# Should show: Qdrant ✓ connected
```

## Collection Structure

Vectrola uses a single collection `vectrola_library` with **named vectors**:

| Vector Name | Dimensions | Purpose |
|-------------|------------|---------|
| `lyrics_dense` | 384 | Multilingual text embeddings |
| `acoustic_clap` | 512 | Audio embeddings (Day 3) |

### Payload Schema

See **[schema.md](schema.md)** for the complete payload schema reference.

Key fields include:
- `title`, `artists`, `album`, `movie`, `year`
- `moods`, `themes`, `narrative` (AI analysis)
- `track_id`, `spotify_track_id`, `checksum` (deduplication)
- `sources` (multi-device local/cloud paths)

**Note:** User ownership is tracked in a separate `user_library` collection (not in track payloads). See [multitenancy.md](multitenancy.md) for details on the inverted index architecture.

## Python API

```python
from vectrola.storage.qdrant import get_db

db = get_db()

# Check connection
db.is_connected()  # True

# Count tracks
db.count()  # 120

# Search by lyrics
results = db.search_by_lyrics(query_vector, limit=10)

# Get a specific track
track = db.get_track("/path/to/song.mp3")

# List all tracks
tracks = db.list_all(limit=100)

# Delete a track
db.delete_track("/path/to/song.mp3")
```

## Named Vectors (Multimodal)

The collection supports multiple vector types for hybrid search:

```python
# Day 2: Lyrics only
db.search_by_lyrics(lyrics_vector, limit=10)

# Day 3: Audio only
db.search_by_audio(audio_vector, limit=10)

# Day 3: Hybrid (RRF fusion)
db.hybrid_search(lyrics_vector, audio_vector, limit=10)
```

## Backup & Restore

```bash
# Backup (copy Docker volume)
docker run --rm -v qdrant_storage:/data -v $(pwd):/backup \
  alpine tar czf /backup/qdrant_backup.tar.gz /data

# Restore
docker run --rm -v qdrant_storage:/data -v $(pwd):/backup \
  alpine tar xzf /backup/qdrant_backup.tar.gz -C /
```

## Troubleshooting

### "Cannot connect to Qdrant"
```bash
# Check if container is running
docker ps | grep qdrant

# Start if stopped
docker start qdrant

# Or create new container
docker run -d --name qdrant -p 6333:6333 qdrant/qdrant
```

### "Collection not found"
The collection is created automatically on first use. Run any ingest command:
```bash
vectrola ingest /path/to/song.mp3
```

### Reset database
```bash
# Delete and recreate container
docker rm -f qdrant
docker run -d --name qdrant -p 6333:6333 qdrant/qdrant
```
