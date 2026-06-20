# Multi-Tenant Architecture

Vectrola supports a multi-tenant architecture where multiple users share a single Qdrant instance while each seeing only their own library. This enables:

- **Track deduplication**: Same song uploaded by different users → single embedding stored
- **Cross-device sync**: Access your library from any device
- **Shared infrastructure**: One Qdrant server serves all users

## Quick Start

```bash
# 1. Set up remote Qdrant (or use local)
export QDRANT_URL=https://your-qdrant.railway.app
export QDRANT_API_KEY=your-api-key

# 2. Enable multi-tenant mode
export VECTROLA_MULTI_TENANT=true

# 3. Ingest music (your user ID is auto-generated)
vectrola ingest /path/to/music
# or
vectrola gdrive ingest "/Music"

# 4. Search - returns only YOUR tracks
vectrola search "sad romantic songs"

# 5. Manage your library
vectrola library list
vectrola library stats
```

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│              SHARED TRACK CATALOG (vectrola_library)            │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ track_id: "fc0e05124b666d58"         (16-char hash)        ││
│  │ spotify_track_id: "4PTG3Z6ehGkBFwjybzWkR8"                  ││
│  │ embeddings: {lyrics_dense, acoustic_clap}                   ││
│  │ metadata: {title, artists, moods, themes, lyrics...}        ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
                              ▲
┌─────────────────────────────┴───────────────────────────────────┐
│            USER LIBRARY (user_library collection)               │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ user_id: "arunes007"                                        ││
│  │ track_id: "fc0e05124b666d58"  ← Links to track             ││
│  │ source: "gdrive"                                            ││
│  │ gdrive_file_id: "1abc123..."                                ││
│  │ added_at: "2026-06-20T10:00:00Z"                            ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
                              ▲
                              │ HTTPS + API Key
┌─────────────────────────────┴───────────────────────────────────┐
│                         USER'S DEVICE                           │
│                                                                 │
│  ~/.config/vectrola/user_id          (auto-generated)           │
└─────────────────────────────────────────────────────────────────┘
```

### How It Works (Inverted Index Pattern)

1. **Ingest**: When you ingest a track, Vectrola:
   - Generates a canonical `track_id` (16-char MD5 hash of artist + title)
   - Generates `spotify_track_id` if Spotify match found (stored separately)
   - Checks if the track already exists in Qdrant (`vectrola_library` collection)
   - If exists: skips embedding generation (reuses existing)
   - If new: generates embeddings and stores in `vectrola_library`
   - Creates entry in `user_library` collection linking you to the track
   - Stores source info (GDrive ID / local path) in the `user_library` entry

2. **Search**: Two-step query using inverted index:
   - Step 1: Fetch your track IDs from `user_library` (indexed by `user_id`)
   - Step 2: Query `vectrola_library` for those tracks (indexed by `track_id`)
   - Result: Only YOUR tracks, with O(1) indexed lookup (50x+ faster at scale)

3. **Playback**: The Obsidian wiki uses source info from `user_library` to find playable sources

## Track Identification

Tracks are identified by a canonical `track_id`:

| Format | Example | Description |
|--------|---------|-------------|
| **16-char hash** | `fc0e05124b666d58` | MD5 hash of normalized artist + title (always used) |
| `spotify_track_id` | `4PTG3Z6ehGkBFwjybzWkR8` | Separate field for Spotify ID (nullable) |

The 16-char hash ensures the same song from different sources (local file, Google Drive, different users) maps to the same catalog entry. Normalization rules:
- Strip featuring artists (`ft.`, `feat.`, `featuring`)
- Remove special characters
- Lowercase everything

This ensures "Arijit Singh ft. Shreya" + "Tum Hi Ho!" produces the same hash as "Arijit Singh" + "Tum Hi Ho".

## User Identification

Your user ID is determined in this priority:

1. `VECTROLA_USER_ID` environment variable
2. Stored in `~/.config/vectrola/user_id` (persisted)
3. Auto-generated as `user_XXXXXXXXXXXX` (12 random hex chars)

Once generated, your user ID persists across sessions.

```bash
# Check your user ID
cat ~/.config/vectrola/user_id

# Or set explicitly
export VECTROLA_USER_ID=user_mydevice123
```

## User Library Service

**Note:** As of June 2026, user library data is stored in the `user_library` Qdrant collection (not a local JSON file). The examples below show the conceptual structure.

User ownership maps track IDs to playable sources:

```json
{
  "user_id": "arunes007",
  "track_id": "fc0e05124b666d58",       // 16-char hash
  "source": "gdrive",
  "gdrive_file_id": "1abc123XYZ...",
  "file_path": "/Users/me/Music/song.mp3",
  "added_at": "2026-06-20T10:30:00Z"
}
```

### Playback Priority

When playing a track, Vectrola checks sources in this order:

1. **Google Drive** (if `gdrive_file_id` exists) - Works on any device
2. **Local file** (if `local_path` exists) - Faster, works offline

This allows cross-device playback via GDrive while preferring local files when available.

## CLI Commands

### Library Management

```bash
# List all tracks in your library
vectrola library list

# Show library statistics
vectrola library stats

# Manual library management (if needed)
# Note: Use 16-char hash track IDs, not spotify: format
vectrola library add "fc0e05124b666d58" \
  --gdrive-id "1abc123..." \
  --local-path "/path/to/song.mp3"

# Remove a track from your library
# (Only removes from YOUR library, not the global catalog)
vectrola library remove "fc0e05124b666d58"
```

### Example Output

```bash
$ vectrola library stats

📚 Library Statistics

Total Tracks     42
├── GDrive only  28
├── Local only    8
└── Both          6

User ID          user_abc123def456
```

```bash
$ vectrola library list
```
📚 Your Library (42 tracks)

┌──────────────────┬────────┬───────┐
│ Track ID         │ GDrive │ Local │
├──────────────────┼────────┼───────┤
│ fc0e05124b666d58 │   ✓    │   ✓   │
│ a1b2c3d4e5f6g7h8 │   ✓    │       │
│ 9876543210fedcba │        │   ✓   │
└──────────────────┴────────┴───────┘
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `QDRANT_URL` | No | `http://localhost:6333` | Qdrant server URL |
| `QDRANT_API_KEY` | For remote | - | API key for remote Qdrant |
| `VECTROLA_USER_ID` | No | Auto-generated | Your user identifier |
| `VECTROLA_MULTI_TENANT` | No | `false` | Enable user-scoped search filtering |

### Example `.env`

```bash
# Remote Qdrant (e.g., Railway, Qdrant Cloud)
QDRANT_URL=https://your-qdrant.railway.app
QDRANT_API_KEY=your-secret-api-key

# Multi-tenant mode
VECTROLA_MULTI_TENANT=true

# Optional: explicit user ID (otherwise auto-generated)
VECTROLA_USER_ID=user_macbook_home
```

## Setting Up Remote Qdrant

### Option 1: Railway (Recommended)

1. Create a new project on [Railway](https://railway.app)
2. Add the Qdrant template
3. Copy the public URL and API key
4. Add to your `.env`:
   ```bash
   QDRANT_URL=https://your-project.railway.app
   QDRANT_API_KEY=your-api-key
   ```

### Option 2: Qdrant Cloud

1. Sign up at [Qdrant Cloud](https://cloud.qdrant.io)
2. Create a cluster
3. Copy the URL and API key
4. Add to your `.env`

### Option 3: Self-Hosted

```bash
# Run Qdrant with authentication
docker run -d --name qdrant \
  -p 6333:6333 \
  -e QDRANT__SERVICE__API_KEY=your-secret-key \
  qdrant/qdrant
```

## Multi-Device Workflow

### Device 1 (Primary - has local files)

```bash
# .env
QDRANT_URL=https://shared-qdrant.railway.app
QDRANT_API_KEY=xxx
VECTROLA_MULTI_TENANT=true
VECTROLA_USER_ID=user_alice

# Ingest local files
vectrola ingest ~/Music/Library

# Ingest from Google Drive
vectrola gdrive auth
vectrola gdrive ingest "/Music"
```

### Device 2 (Secondary - no local files)

```bash
# .env (same remote Qdrant, same user ID)
QDRANT_URL=https://shared-qdrant.railway.app
QDRANT_API_KEY=xxx
VECTROLA_MULTI_TENANT=true
VECTROLA_USER_ID=user_alice  # Same user!

# Search works - filters to your tracks
vectrola search "romantic songs"

# Sync library.json from Device 1 (or re-ingest from GDrive)
vectrola gdrive ingest "/Music"

# Generate wiki - plays via GDrive
vectrola wiki
```

### Obsidian Sync

For cross-device wiki access:

```bash
# Generate wiki to a synced folder
vectrola wiki --output ~/iCloud/Obsidian/Vectrola
# or
vectrola wiki --output ~/Dropbox/Obsidian/Vectrola
```

The wiki's audio player automatically uses GDrive for playback when local files aren't available.

## How Deduplication Works

When two users ingest the same song:

```
User A ingests "Tum Hi Ho.mp3"
├── Spotify lookup → spotify_track_id: "4uLU6hMCjMI75M1A2tKUQC"
├── Generate track_id: "fc0e05124b666d58" (hash of "arijit singh:tum hi ho")
├── Track doesn't exist in vectrola_library
├── Generate embeddings (lyrics + audio)
├── Store in vectrola_library collection
└── Create user_library entry: user_a → fc0e05124b666d58

User B ingests "Tum Hi Ho.flac" (same song, different file)
├── Spotify lookup → spotify_track_id: "4uLU6hMCjMI75M1A2tKUQC"
├── Generate track_id: "fc0e05124b666d58" (same hash!)
├── Track EXISTS in vectrola_library! ✓
├── Skip embedding generation (reuse existing)
└── Create user_library entry: user_b → fc0e05124b666d58
```

Result: One embedding, two users can search it, each has their own source info in `user_library`.

## Qdrant Schema

### vectrola_library Collection (Tracks Catalog)

Tracks are stored with named vectors and metadata:

```python
{
    "id": "uuid-xxx",
    "vectors": {
        "lyrics_dense": [0.1, 0.2, ...],   # 384-dim text embedding
        "acoustic_clap": [0.3, 0.4, ...]   # 512-dim CLAP audio embedding
    },
    "payload": {
        "track_id": "fc0e05124b666d58",        # 16-char hash
        "spotify_track_id": "4uLU6hMCjMI75M1A2tKUQC",  # Separate field
        "title": "Tum Hi Ho",
        "artists": ["Arijit Singh"],
        "album": "Aashiqui 2",
        "moods": ["romantic", "melancholic"],
        "themes": ["love", "longing"],
        "lyrics": "...",
        "sources": {...}  # Multi-device source info
    }
}
```

Payload indexes:
- `track_id` (keyword) - for fast track lookup
- `checksum` (keyword) - for deduplication by file content

### user_library Collection (User-Track Mapping)

User ownership tracked separately using inverted index:

```python
{
    "id": "uuid-yyy",
    "payload": {
        "user_id": "arunes007",               # Indexed (KEYWORD)
        "track_id": "fc0e05124b666d58",       # Indexed (KEYWORD)
        "source": "gdrive",
        "gdrive_file_id": "1abc123...",
        "file_path": "/path/to/file.mp3",     # If source=local
        "added_at": "2026-06-20T10:00:00Z"
    }
}
```

Payload indexes:
- `user_id` (keyword) - for fast user library lookup
- `track_id` (keyword) - join key for track details

**Why Separate Collection?**
- Scales to billions of users per track (vs 100K limit with arrays)
- O(1) indexed lookup (vs O(n) array scan)
- 50x+ faster search performance at scale
- No update contention (append-only)

See [schema.md](schema.md) for complete schema reference.

## Troubleshooting

### "Connection refused" to Qdrant

Check your `QDRANT_URL`:
```bash
# Local
curl http://localhost:6333/collections

# Remote
curl -H "api-key: $QDRANT_API_KEY" https://your-qdrant.railway.app/collections
```

### Search returns all tracks (not just mine)

Ensure multi-tenant mode is enabled:
```bash
export VECTROLA_MULTI_TENANT=true
```

### Different user IDs on different devices

If you want the same library across devices, use the same user ID:
```bash
# Check current user ID
cat ~/.config/vectrola/user_id

# Set explicitly in .env
VECTROLA_USER_ID=user_your_shared_id
```

### Track not playing in wiki

Check that the track has a playable source:
```bash
vectrola library list | grep "track_id"
```

If missing GDrive ID, re-ingest from Google Drive. If missing local path, the file may have moved.

### "Track already exists" but I can't search it

The track exists in the global catalog but isn't in YOUR library. Re-ingest the file and a new `user_library` entry will be created linking you to the track (no duplicate embeddings generated).

## Architecture Migration (June 2026)

**Previous Architecture:** User ownership tracked via `user_ids` arrays in track payloads
- Issue: O(n) array scans during filtering, broke at ~100K users per track
- Payload bloat: Popular tracks with 1M users = 20MB payload

**New Architecture:** Separate `user_library` collection with inverted index
- Performance: 50x+ faster search at scale (O(1) indexed lookup)
- Scalability: Handles billions of users per track
- Storage: 47% smaller track IDs (16-char hash vs 30-char `spotify:` format)

All new installs use the new architecture automatically. Existing installations can migrate with:
```bash
python scripts/migrate_to_user_library.py
```
