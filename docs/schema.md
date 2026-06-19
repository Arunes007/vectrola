# Qdrant Payload Schema

Complete reference for the track payload schema stored in Qdrant.

## Collection

- **Name:** `vectrola_library`
- **Vectors:** Named vectors (see [Embedding Vectors](#embedding-vectors))

## Full Schema

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

  // Track Identification
  "track_id": "spotify:4PTG3Z6ehGkBFwjybzWkR8",
  "spotify_id": "4PTG3Z6ehGkBFwjybzWkR8",
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

  // Multi-Tenant
  "user_ids": ["arunes007", "user_xyz"],

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
| `track_id` | string | Canonical ID: `"spotify:<id>"` or `"hash:<md5[:16]>"` |
| `spotify_id` | string | Spotify track ID (nullable) |
| `checksum` | string | MD5 hash of audio file content (32 hex chars) |

**track_id Format:**
- If Spotify match found: `spotify:4PTG3Z6ehGkBFwjybzWkR8`
- Otherwise: `hash:a1b2c3d4e5f6g7h8` (MD5 of normalized `artist:title`)

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

### Multi-Tenant

| Field | Type | Description |
|-------|------|-------------|
| `user_ids` | list[string] | Users who have this track in their library |

When a user ingests a track that already exists (by checksum or title+artist), their user_id is added to `user_ids` without re-running analysis.

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

| Field | Index Type | Purpose |
|-------|-----------|---------|
| `track_id` | KEYWORD | Fast track existence check |
| `checksum` | KEYWORD | Deduplication tier 1 |
| `user_ids` | KEYWORD | Multi-tenant filtering |

## Example: Minimal Payload

```json
{
  "title": "Unknown Track",
  "artists": [],
  "track_id": "hash:a1b2c3d4e5f6g7h8",
  "checksum": "md5hashoffile...",
  "sources": {
    "local": {"LYFVFXPHVW": "/path/to/file.mp3"},
    "cloud": {}
  },
  "user_ids": ["anon_abc123"],
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
  "track_id": "spotify:4PTG3Z6ehGkBFwjybzWkR8",
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
  "user_ids": ["arunes007"],
  "album_art_url": "https://i.scdn.co/image/ab67616d0000b273..."
}
```

## Related Docs

- [Deduplication](dedup.md) — How tracks are deduplicated
- [Multi-tenancy](multitenancy.md) — User library management
- [Qdrant Setup](qdrant.md) — Database setup and API
