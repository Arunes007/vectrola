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
│                    SHARED TRACK CATALOG (Qdrant)                │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ track_id: "spotify:4PTG3Z6ehGkBFwjybzWkR8"                  ││
│  │ embeddings: {lyrics_dense, acoustic_clap}                   ││
│  │ metadata: {title, artists, moods, themes, lyrics...}        ││
│  │ user_ids: ["user_abc", "user_def"]  ← Multi-tenant array    ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
                              ▲
                              │ HTTPS + API Key
┌─────────────────────────────┴───────────────────────────────────┐
│                         USER'S DEVICE                           │
│                                                                 │
│  ~/.config/vectrola/user_id          (auto-generated)           │
│  ~/.config/vectrola/library.json     (local source mappings)    │
│                                                                 │
│  {                                                              │
│    "spotify:xyz": {                                             │
│      "gdrive_file_id": "1abc123...",                            │
│      "local_path": "/Music/song.mp3"                            │
│    }                                                            │
│  }                                                              │
└─────────────────────────────────────────────────────────────────┘
```

### How It Works

1. **Ingest**: When you ingest a track, Vectrola:
   - Generates a canonical `track_id` (e.g., `spotify:xxx` or `hash:xxx`)
   - Checks if the track already exists in Qdrant
   - If exists: adds your `user_id` to the `user_ids` array (no duplicate embeddings)
   - If new: generates embeddings and stores with your `user_id`
   - Saves source mapping (GDrive ID / local path) to your local `library.json`

2. **Search**: Queries filter by `user_ids` containing your ID, so you only see your tracks

3. **Playback**: The Obsidian wiki uses your `library.json` to find playable sources

## Track Identification

Tracks are identified by a canonical `track_id`:

| Format | Example | When Used |
|--------|---------|-----------|
| `spotify:XXX` | `spotify:4PTG3Z6ehGkBFwjybzWkR8` | Track matched on Spotify |
| `hash:XXX` | `hash:a1b2c3d4e5f6...` | No Spotify match (content hash) |

This ensures the same song from different sources (local file, Google Drive, different users) maps to the same catalog entry.

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

The `UserLibrary` service (`~/.config/vectrola/library.json`) maps track IDs to playable sources:

```json
{
  "user_id": "user_abc123def456",
  "tracks": {
    "spotify:4PTG3Z6ehGkBFwjybzWkR8": {
      "gdrive_file_id": "1abc123XYZ...",
      "local_path": "/Users/me/Music/song.mp3",
      "added_at": "2024-06-11T10:30:00Z"
    }
  }
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

# Add a track manually
vectrola library add "spotify:4PTG3Z6ehGkBFwjybzWkR8" \
  --gdrive-id "1abc123..." \
  --local-path "/path/to/song.mp3"

# Remove a track from your library
# (Only removes from YOUR library, not the global catalog)
vectrola library remove "spotify:4PTG3Z6ehGkBFwjybzWkR8"
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

📚 Your Library (42 tracks)

┌─────────────────────────────────────┬────────┬───────┐
│ Track ID                            │ GDrive │ Local │
├─────────────────────────────────────┼────────┼───────┤
│ spotify:4PTG3Z6ehGkBFwjybzWkR8      │   ✓    │   ✓   │
│ spotify:1234567890abcdef            │   ✓    │       │
│ hash:a1b2c3d4e5f6...                │        │   ✓   │
└─────────────────────────────────────┴────────┴───────┘
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
├── Spotify lookup → track_id: "spotify:4uLU6hMCjMI75M1A2tKUQC"
├── Track doesn't exist in Qdrant
├── Generate embeddings (lyrics + audio)
├── Store in Qdrant with user_ids: ["user_a"]
└── Save to user_a's library.json

User B ingests "Tum Hi Ho.flac" (same song, different file)
├── Spotify lookup → track_id: "spotify:4uLU6hMCjMI75M1A2tKUQC"
├── Track EXISTS in Qdrant! ✓
├── Skip embedding generation (reuse existing)
├── Add user_b to user_ids: ["user_a", "user_b"]
└── Save to user_b's library.json
```

Result: One embedding, two users can search it, each has their own playback source.

## Qdrant Schema

Tracks are stored with named vectors and a payload containing metadata plus the `user_ids` array:

```python
{
    "id": "uuid-xxx",
    "vectors": {
        "lyrics_dense": [0.1, 0.2, ...],   # 384-dim text embedding
        "acoustic_clap": [0.3, 0.4, ...]   # 512-dim CLAP audio embedding
    },
    "payload": {
        "track_id": "spotify:4uLU6hMCjMI75M1A2tKUQC",
        "title": "Tum Hi Ho",
        "artists": ["Arijit Singh"],
        "album": "Aashiqui 2",
        "moods": ["romantic", "melancholic"],
        "themes": ["love", "longing"],
        "lyrics": "...",
        "user_ids": ["user_abc", "user_def"]  # Multi-tenant
    }
}
```

Payload indexes:
- `track_id` (keyword) - for deduplication lookups
- `user_ids` (keyword) - for user-scoped filtering

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

The track exists in the global catalog but isn't in YOUR library. Either:
1. Re-ingest the file (your user_id will be added)
2. Manually add: `vectrola library add "track_id" --gdrive-id "xxx"`
