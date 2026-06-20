# Track Deduplication

Vectrola uses a 2-tier deduplication strategy to avoid re-analyzing tracks that already exist in the database. This significantly speeds up ingestion when re-importing the same music library or syncing across devices.

## Deduplication Flow

```
┌─────────────────────────────────────────────────────────────────┐
│  1. Calculate checksum (MD5 hash of file content)               │
│  2. Read file tags → get title, artists                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  DEDUP CHECK                                                    │
│                                                                 │
│  Tier 1: Checksum                                               │
│  ─────────────────                                              │
│  Search Qdrant for matching checksum.                           │
│  → If found: update file_path & return (skip analysis)          │
│                                                                 │
│  Tier 2: Title + Artist (only if BOTH exist)                    │
│  ──────────────────────────────────────────                     │
│  Search Qdrant for matching title + artist (case-insensitive).  │
│  → If found: update file_path & return (skip analysis)          │
│  → If artist missing: skip tier 2 (avoid false matches)         │
└─────────────────────────────────────────────────────────────────┘
                              │ no match
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  NEW SONG - FULL ANALYSIS                                       │
│  • Spotify lookup (metadata, album art)                         │
│  • Fetch lyrics (LRClib → Genius → Whisper)                     │
│  • LLM synthesis (themes, moods, narrative)                     │
│  • Generate embeddings                                          │
│  • Store in Qdrant                                              │
└─────────────────────────────────────────────────────────────────┘
```

## Tier Descriptions

### Tier 1: Checksum (Exact File Match)

- **What it checks:** MD5 hash of the entire audio file
- **When it matches:** Same exact file (byte-for-byte identical)
- **Speed:** Fastest - indexed lookup in Qdrant
- **Use case:** Re-ingesting the same file from a different location

```python
# Checksum is calculated once at ingest start
checksum = calculate_checksum(file_path)  # MD5 hex digest (32 chars)
```

### Tier 2: Title + Artist (Logical Match)

- **What it checks:** Normalized title + first artist name
- **When it matches:** Same song, possibly different file (e.g., different bitrate)
- **Requirements:** BOTH title AND artist must be present in file tags
- **Normalization:** Lowercase, stripped whitespace
- **Use case:** Different rip/download of the same song

```python
# Matching is case-insensitive
"Tum Hi Ho" by "Arijit Singh"  ==  "tum hi ho" by "arijit singh"
```

**Why require both fields?**

If only title is provided (no artist), the match could be ambiguous:
- "Tera Chehra" by Artist A ≠ "Tera Chehra" by Artist B

To avoid false positives, we skip tier 2 if artist is missing and proceed to full analysis.

## What Happens on Match

When a duplicate is found:

1. **Merge `sources`** in Qdrant → add new device path to existing sources
2. **Update `checksum`** in Qdrant → for future tier 1 matching
3. **Add user to `user_ids`** → multi-tenant support
4. **Return existing analysis** → skip Spotify/lyrics/LLM/embeddings

```python
# From pipeline.py
if existing:
    point_id, track_id, payload = existing
    
    # Merge sources - add new device path
    existing_sources = payload.get("sources", {"local": {}, "cloud": {}})
    existing_sources["local"][device_id] = str(file_path)
    
    # Update sources and checksum in Qdrant
    db.client.set_payload(
        collection_name=db.COLLECTION,
        payload={"sources": existing_sources, "checksum": checksum},
        points=[point_id]
    )
    
    # Add user to track
    db.add_user_to_track(track_id, user_id)
    
    # Return existing TrackAnalysis (skip full pipeline)
    return TrackAnalysis(...)
```

## Schema

The following fields are used for deduplication:

| Field | Type | Description |
|-------|------|-------------|
| `checksum` | string | MD5 hex digest of file content (32 chars) |
| `track_id` | string | Canonical ID: `spotify:xxx` or `hash:xxx` |
| `title` | string | Track title (from file tags or Spotify) |
| `artists` | list[string] | Artist names |
| `sources` | object | Multi-device/cloud paths (see below) |

### Sources Schema

```json
{
  "sources": {
    "local": {
      "LYFVFXPHVW": "/Users/I575797/Music/song.mp3",
      "iPhone-Arun": "/var/mobile/Media/Music/song.mp3"
    },
    "cloud": {
      "gdrive": {
        "file_id": "1abc123",
        "path": "Music/song.mp3"
      }
    }
  }
}
```

- `sources.local.<hostname>` - Local file path per device (uses `platform.node()`)
- `sources.cloud.<provider>` - Cloud storage with file_id and path

On dedup match, the pipeline **merges** sources (adds new device path without overwriting existing).

Qdrant indexes:
- `checksum` - KEYWORD index for tier 1 lookup
- `track_id` - KEYWORD index for track existence checks

## Performance

| Scenario | Time |
|----------|------|
| Tier 1 match (checksum) | ~50ms |
| Tier 2 match (title+artist) | ~100ms |
| No match (full analysis) | 5-30s (depends on LLM, network) |

Deduplication can speed up re-ingestion by **100x** for existing tracks.

## CLI Usage

```bash
# Ingest local music - dedup happens automatically
vectrola ingest "/path/to/music"

# Output shows dedup in action:
# [1/100] Song.mp3
#    → Reading file tags...
#    → ✓ Found existing track (skipping analysis): Song Name
#    ✓ Done: melancholic, romantic
```

### Force Re-Analysis

Use the `--force` / `-F` flag to bypass deduplication and re-analyze existing tracks:

```bash
# Re-analyze all tracks (refreshes metadata, lyrics, moods, embeddings)
vectrola ingest "/path/to/music" --force

# Short form
vectrola ingest "/path/to/music" -F
```

**When to use `--force`:**
- Refresh metadata after LLM model upgrade
- Re-fetch lyrics that were previously unavailable  
- Fix tracks with incorrect moods/themes
- Update embeddings after model changes

**What `--force` does:**
- ❌ Skips checksum match
- ❌ Skips title+artist match
- ✅ Full Spotify lookup
- ✅ Re-fetch lyrics
- ✅ Re-run LLM synthesis
- ✅ Regenerate embeddings
- ✅ Overwrite existing track in Qdrant

## Testing

Run dedup-specific tests:

```bash
pytest tests/test_dedup.py -v
```

Tests cover:
- `calculate_checksum()` - determinism, MD5 correctness
- `generate_track_id()` - Spotify priority, hash fallback
- `find_existing_track()` - tier 1, tier 2, case normalization
