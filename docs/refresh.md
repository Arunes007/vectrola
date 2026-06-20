# Track Metadata Refresh

The `refresh` command fills missing metadata for tracks already in your Qdrant library. It selectively re-runs pipeline stages to fetch only the missing fields without re-processing the entire track.

## When to Use

Use `refresh` when tracks in your library have incomplete metadata due to:
- API timeouts during initial ingestion (LRClib, Spotify, Genius)
- Missing lyrics/composers at the time of ingestion  
- LLM synthesis that returned empty results
- Album art that wasn't available
- Upgrading to a better LLM model and wanting to re-generate themes/moods

**Don't use for failed ingestions** - Just re-run `vectrola ingest` instead. Deduplication will automatically skip already-processed tracks and retry failed ones.

## Quick Start

```bash
# Check which tracks have missing metadata
vectrola refresh --list

# Refresh all tracks in your library
vectrola refresh

# Refresh a specific track
vectrola refresh --track "Maula Mere Maula"

# Refresh tracks from a folder
vectrola refresh /path/to/music
```

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│  1. Query Qdrant for user's tracks                              │
│  2. Detect missing fields (lyrics, moods, album art, etc.)      │
│  3. Selectively re-run only the needed pipeline stages:         │
│     • Spotify → album, year, spotify_id, album_art              │
│     • LRClib/Genius/Whisper → lyrics                            │
│     • MusicBrainz → composer, lyricist                          │
│     • LLM synthesis → themes, moods, narrative                  │
│  4. Update Qdrant payload (preserves embeddings, no re-index)   │
└─────────────────────────────────────────────────────────────────┘
```

**Key difference from full ingest:**
- ✅ Skips checksum calculation
- ✅ Skips file tag reading
- ✅ Skips embedding generation (preserves existing vectors)
- ✅ Only fetches missing fields
- ✅ No file path required (uses cached metadata)

## Missing Field Detection

The refresh command checks for these gaps:

| Field Category | What's Checked | Pipeline Stage |
|---------------|----------------|----------------|
| `spotify_metadata` | spotify_id, album (year is optional) | Spotify API |
| `lyrics` | lyrics field empty | LRClib → Genius → Whisper |
| `themes_moods` | themes or moods empty | LLM synthesis |
| `album_art` | album_art_url missing | Spotify oEmbed |

**Note:** `composer`, `lyricist`, and `year` are considered optional and not checked by refresh.

## Command Reference

### Default: Refresh All Tracks

```bash
vectrola refresh
```

Scans all tracks owned by the current user, detects missing fields, and fills them.

**Example output:**
```
🔄 Found 23 tracks with missing metadata (out of 119 total)

  Refreshing metadata ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 23/23

✅ Updated: 21/23 tracks
❌ Errors: 2 tracks
```

**Verbose mode** (`--verbose` or `-v`):
```bash
vectrola refresh --verbose
```

Shows detailed per-track progress:
```
🔄 Found 23 tracks with missing metadata (out of 119 total)

[1/23] Maula Mere Maula
   → Filling: lyrics, themes_moods
   ✓ Updated: 5 fields

[2/23] Tum Hi Ho
   → Filling: album_art
   ✓ Updated: 1 fields

[3/23] Tera Chehra
   → Filling: spotify_metadata
   ⚠ No updates available

✅ Updated: 21/23 tracks
❌ Errors: 2 tracks
```

### List Mode: Show Gaps

```bash
vectrola refresh --list
```

Shows which tracks have missing metadata without actually refreshing them.

**Example output:**
```
Tracks with missing metadata:

• Maula Mere Maula - Roop Kumar Rathod
  Missing: lyrics, themes_moods

• Tera Chehra - Adnan Sami
  Missing: album_art

10 tracks need refreshing.
```

### Refresh Specific Track

```bash
vectrola refresh --track "Song Name"
```

Searches by track title and refreshes the first match.

**Example:**
```bash
vectrola refresh --track "Maula Mere Maula"
```

If multiple tracks match, it shows the list and refreshes the first one:
```
Found 3 matches for 'Maula Mere Maula', refreshing first:
  • Maula Mere Maula - Roop Kumar Rathod
  • Maula Mere Maula (Remix) - Various Artists
  • Maula Mere Maula - Cover Version

[1/1] Maula Mere Maula
   → Filling: lyrics
   ✓ Updated: 2 fields
```

### Refresh from Path

```bash
vectrola refresh /path/to/music
vectrola refresh /path/to/song.mp3
```

Refreshes tracks from a specific folder or file.

**How it works:**
1. Scans the path for audio files (`.mp3`, `.flac`, `.wav`, `.m4a`, `.ogg`)
2. Queries Qdrant by file path (matches against `sources.local.<device_id>`)
3. Refreshes only tracks found in both filesystem and Qdrant

**Use case:** You moved files to a new location and want to refresh metadata without re-ingesting.

## Pipeline Stages

Each missing field triggers specific API calls:

### 1. Spotify Metadata
**Triggered when:** `spotify_id` or `album` is missing (year is optional)  
**Fetches:**
- `spotify_id` - Canonical track ID
- `album` - Album name (also used as `movie` for Bollywood)
- `year` - Release year (optional)
- `album_art_url` - Album artwork URL

### 2. Lyrics
**Triggered when:** `lyrics` field is empty  
**Fetches:**
- `lyrics` - Full lyrics text
- `lyrics_source` - Source: "lrclib", "genius", "whisper", "file_tags"
- `segments` - Timestamped segments (if available)

**Fallback chain:**
1. LRClib (synced lyrics)
2. Genius (plain text lyrics)
3. Whisper (transcription, requires local file)

### 3. LLM Synthesis
**Triggered when:** `themes` or `moods` is empty  
**Fetches:**
- `themes` - Thematic tags (e.g., "love", "separation", "nostalgia")
- `moods` - Mood tags (e.g., "melancholic", "romantic", "uplifting")
- `narrative` - Song story/narrative summary
- `imagery` - Visual imagery descriptions

**Requires:** Lyrics must be available (from field or previous refresh stage)

### 4. Album Art
**Triggered when:** `album_art_url` is missing (and Spotify stage didn't fill it)  
**Fetches:**
- `album_art_url` - Spotify oEmbed thumbnail URL

## Performance

| Scenario | Time |
|----------|------|
| Track with complete metadata | ~10ms (just gap detection) |
| Spotify metadata only | ~200ms |
| Lyrics only (LRClib) | ~500ms |
| Lyrics + LLM synthesis | 3-10s (depends on LLM) |
| All fields missing | 5-15s |

**Batch refresh:**
- 100 tracks with 50% gaps: ~5-10 minutes
- Uses existing pipeline instances (no repeated model loading)

## Error Handling

If a stage fails (network timeout, API error), the refresh command:
1. Logs the error for that track
2. Continues to the next field/track
3. Shows error count in summary

**Example:**
```
[50/100] Broken Song
   → Filling: lyrics, themes_moods
   ✗ Error: Spotify API timeout

❌ Errors: 1 tracks
```

You can re-run `vectrola refresh` to retry failed tracks.

## Limitations

- **No local file = No Whisper:** If a track only has GDrive source (no local path), Whisper transcription fallback won't work
- **No re-embedding:** Refresh doesn't regenerate text/audio embeddings (preserves existing vectors)
- **No file tag updates:** Refresh only updates Qdrant, not audio file tags (use `vectrola ingest --force` for that)

## vs. Other Commands

| Command | Purpose | When to Use |
|---------|---------|-------------|
| `vectrola ingest` | Full pipeline (file → Qdrant) | Initial ingestion, failed tracks |
| `vectrola ingest --force` | Re-run full pipeline, bypass dedup | Refresh embeddings, fix bad data |
| `vectrola refresh` | Fill missing fields in Qdrant | Fix gaps without re-processing |

## Common Scenarios

### After LLM Upgrade
Upgraded from `llama3.2:1b` to `llama3.2:3b` and want better moods/themes:

```bash
# Check which tracks will be updated
vectrola refresh --list

# Refresh all (only re-runs LLM synthesis for tracks with empty moods/themes)
vectrola refresh
```

### After Lyrics Service Outage
LRClib was down during initial ingest, now it's back:

```bash
# Refresh all tracks (only fetches lyrics for tracks with empty lyrics)
vectrola refresh
```

### Spot-Check Specific Track
Want to verify one track has complete metadata:

```bash
vectrola refresh --track "Song Name"
```

If output shows "Complete (no gaps)", you're good.

## Testing

Run refresh-specific tests:

```bash
pytest tests/test_metadata_refresher.py -v
```

Tests cover:
- `detect_missing_fields()` - gap detection logic
- `MetadataRefresher.refresh_track()` - selective stage execution
- CLI `refresh` command - all scope options
