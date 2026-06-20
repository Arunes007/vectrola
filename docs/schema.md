# Qdrant Payload Schema

Complete reference for the track payload schema stored in Qdrant.

## Collections

### vectrola_library (Tracks Catalog)
- **Name:** `vectrola_library`
- **Vectors:** Named vectors (see [Embedding Vectors](#embedding-vectors))
- **Purpose:** Shared track catalog with metadata and embeddings

### user_library (User-Track Mapping)
- **Name:** `user_library`
- **Vectors:** None (payload-only collection)
- **Purpose:** Many-to-many mapping between users and tracks (inverted index)

## Recent Changes (June 2026)

**Multi-Tenant Architecture Migration:**
- `track_id` format changed from `spotify:xxx` / `hash:xxx` to always 16-char hash
- `user_ids` array removed from track payloads
- New `user_library` collection for user-track mappings (inverted index)
- Added `spotify_track_id` field (separate from `track_id`)
- `spotify_id` field deprecated (use `spotify_track_id` instead)

See [multitenancy.md](multitenancy.md) for architecture details.

## Full Schema (vectrola_library)

```json
{
  // Core Metadata
  "title": "Tum Hi Ho",
  "artists": ["Arijit Singh"],
  "album": "Aashiqui 2",
  "movie": "Aashiqui 2",
  "year": 2013,
  "era": "2010s Rewind",
  "composer": "Mithoon",
  "lyricist": "Irshad Kamil",
  "language": "hi",
  "duration_seconds": 262.5,

  // Lyrics & AI Analysis
  "lyrics": "Hum tere bin ab reh nahi sakte...",
  "lyrics_source": "lrclib",
  "moods": ["melancholic", "romantic", "devotional"],
  "themes": ["love", "longing", "separation"],
  "narrative": "A deeply romantic song about being incomplete without one's beloved...",
  "imagery": ["rain", "empty streets", "moonlight"],

  // Track Identification (NEW FORMAT)
  "track_id": "fc0e05124b666d58",               // 16-char hash (NEW)
  "spotify_track_id": "4PTG3Z6ehGkBFwjybzWkR8",  // Separate field (NEW)
  "spotify_id": "4PTG3Z6ehGkBFwjybzWkR8",        // DEPRECATED
  "checksum": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",

  // Multi-Device Sources
  "sources": {
    "local": {
      "LYFVFXPHVW": "/Users/I575797/Music/Tum Hi Ho.mp3",
      "iPhone-Arun": "/var/mobile/Media/Music/Tum Hi Ho.mp3"
    },
    "cloud": {
      "gdrive": {
        "file_id": "1abc123def456",
        "path": "Music/Tum Hi Ho.mp3"
      }
    }
  },

  // NOTE: user_ids field REMOVED - now tracked in user_library collection

  // Album Art
  "album_art_url": "https://i.scdn.co/image/ab67616d0000b273..."
}
```

## Field Reference

### Core Metadata

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title` | string | ✓ | Track title |
| `artists` | list[string] | ✓ | Singer/performer names |
| `album` | string | | Album name |
| `movie` | string | | Film name (for Bollywood soundtracks) |
| `year` | int | | Release year |
| `era` | string | | Calculated era label (see below) |
| `composer` | string | | Music director |
| `lyricist` | string | | Lyricist name |
| `language` | string | | "hi" (Hindi) or "en" (English) |
| `duration_seconds` | float | | Track length in seconds |

**Era Values:**
- `"Old Melodies"` — before 1990
- `"90s Nostalgia"` — 1990-1999
- `"Y2K Vibes"` — 2000-2009
- `"2010s Rewind"` — 2010-2019
- `"Fresh Hits"` — 2020+
- `"Timeless"` — year unknown

### Lyrics & AI Analysis

| Field | Type | Description |
|-------|------|-------------|
| `lyrics` | string | Full lyrics text |
| `lyrics_source` | string | Source: `"lrclib"`, `"genius"`, `"whisper"`, `"file_tags"` |
| `moods` | list[string] | AI-detected moods (e.g., "melancholic", "upbeat") |
| `themes` | list[string] | AI-detected themes (e.g., "love", "friendship") |
| `narrative` | string | AI-generated summary of the song's story |
| `imagery` | list[string] | AI-detected visual imagery |
| `metadata_source` | string | Primary metadata source: `"spotify"`, `"musicbrainz"`, `"file_tags"` |

### Track Identification

| Field | Type | Description |
|-------|------|-------------|
| `track_id` | string | **Always** 16-char MD5 hash of normalized `artist:title` |
| `spotify_track_id` | string | Spotify track ID (nullable, for backward compatibility) |
| `spotify_id` | string | **DEPRECATED** - Use `spotify_track_id` instead |
| `checksum` | string | MD5 hash of audio file content (32 hex chars) |

**track_id Format:**
- **Always** a 16-char hex hash: `a1b2c3d4e5f6g7h8`
- Generated from normalized artist + title (lowercase, no special chars, no featuring artists)
- Example: `"Arijit Singh ft. Shreya"` + `"Tum Hi Ho!"` → `"fc0e05124b666d58"`

**Normalization Rules:**
- Strip featuring artists (`ft.`, `feat.`, `featuring`)
- Remove special characters (keep only letters/numbers)
- Convert to lowercase
- MD5 hash the result, take first 16 chars

**spotify_track_id:**
- Separate field for Spotify ID (no prefix)
- Example: `"4PTG3Z6ehGkBFwjybzWkR8"`
- Used for fetching metadata, artwork, etc.

### Multi-Device Sources

```json
"sources": {
  "local": {
    "<hostname>": "/absolute/path/to/file.mp3"
  },
  "cloud": {
    "<provider>": {
      "file_id": "cloud-file-id",
      "path": "relative/path/in/cloud"
    }
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `sources` | object | Container for all playback sources |
| `sources.local` | object | Map of hostname → local file path |
| `sources.cloud` | object | Map of provider → cloud file info |

**Supported Cloud Providers:**
- `gdrive` — Google Drive (file_id + path)
- `onedrive` — OneDrive (planned)
- `icloud` — iCloud (planned)

**Playback Priority:**
1. `sources.local[current_hostname]` — Local file on this device
2. Any `sources.local.*` — Local file on any device
3. `sources.cloud.gdrive` — Google Drive
4. Any `sources.cloud.*` — Other cloud providers

### Multi-Tenant: User Library Collection

User ownership is tracked in a **separate collection** (`user_library`) using an inverted index pattern:

**Collection:** `user_library` (payload-only, no vectors)

**Schema:**
```json
{
  "user_id": "arunes007",                  // Indexed (KEYWORD)
  "track_id": "fc0e05124b666d58",          // Indexed (KEYWORD), 16-char hash
  "source": "local" | "gdrive",
  "file_path": "/path/to/file.mp3",        // If source=local
  "gdrive_file_id": "1abc...",             // If source=gdrive
  "added_at": "2026-06-20T10:00:00Z"
}
```

**Why Separate Collection?**
- Scales to billions of users per track (vs 100K limit with arrays)
- O(1) indexed lookup (vs O(n) array scan)
- 50x+ faster search performance at scale
- No update contention (append-only)

**Query Pattern:**
1. Fetch user's track IDs from `user_library` (indexed by `user_id`)
2. Query `vectrola_library` tracks (indexed by `track_id`)

### Album Art

| Field | Type | Description |
|-------|------|-------------|
| `album_art_url` | string | Spotify album cover URL (nullable) |

Fetched from Spotify oEmbed API. Skipped if file has embedded artwork.

## Embedding Vectors

The collection uses **named vectors** for multimodal search:

| Vector Name | Dimensions | Model | Purpose |
|-------------|------------|-------|---------|
| `lyrics_dense` | 384 | `paraphrase-multilingual-MiniLM-L12-v2` | Text/lyrics similarity |
| `acoustic_clap` | 512 | `laion/clap-htsat-unfused` | Audio similarity |

## Indexes

### vectrola_library Collection

| Field | Index Type | Purpose |
|-------|-----------|---------|
| `track_id` | KEYWORD | Fast track lookup (16-char hash) |
| `checksum` | KEYWORD | Deduplication tier 1 (exact file match) |

### user_library Collection

| Field | Index Type | Purpose |
|-------|-----------|---------|
| `user_id` | KEYWORD | Fast user library lookup |
| `track_id` | KEYWORD | Join key for track details |

## Example: Minimal Payload

```json
{
  "title": "Unknown Track",
  "artists": [],
  "track_id": "a1b2c3d4e5f6g7h8",
  "checksum": "md5hashoffile...",
  "sources": {
    "local": {"LYFVFXPHVW": "/path/to/file.mp3"},
    "cloud": {}
  },
  "moods": [],
  "themes": []
}
```

## Example: Full Payload

```json
{
  "title": "Tum Hi Ho",
  "artists": ["Arijit Singh"],
  "album": "Aashiqui 2",
  "movie": "Aashiqui 2",
  "year": 2013,
  "era": "2010s Rewind",
  "composer": "Mithoon",
  "lyricist": "Irshad Kamil",
  "language": "hi",
  "duration_seconds": 262.5,
  "lyrics": "Hum tere bin ab reh nahi sakte\nTere bina kya wajood mera...",
  "lyrics_source": "lrclib",
  "moods": ["melancholic", "romantic", "devotional"],
  "themes": ["love", "longing", "separation", "devotion"],
  "narrative": "A deeply romantic song expressing how the singer feels incomplete without their beloved. The lyrics convey intense emotional dependency and devotion.",
  "imagery": ["empty room", "tears", "moonlight"],
  "metadata_source": "spotify",
  "track_id": "fc0e05124b666d58",
  "spotify_track_id": "4PTG3Z6ehGkBFwjybzWkR8",
  "spotify_id": "4PTG3Z6ehGkBFwjybzWkR8",
  "checksum": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",
  "sources": {
    "local": {
      "LYFVFXPHVW": "/Users/I575797/Music/Tum Hi Ho.mp3"
    },
    "cloud": {
      "gdrive": {
        "file_id": "1abc123def456ghi789",
        "path": "Music/Tum Hi Ho.mp3"
      }
    }
  },
  "album_art_url": "https://i.scdn.co/image/ab67616d0000b273..."
}
```

## Related Docs

- [Deduplication](dedup.md) — How tracks are deduplicated
- [Multi-tenancy](multitenancy.md) — User library management
- [Qdrant Setup](qdrant.md) — Database setup and API
