# Failed Ingestion Tracking & Retry

When ingesting music files (local or from Google Drive), some tracks may fail due to network timeouts, LLM errors, or storage issues. Vectrola tracks these failures and provides a `retry` command to re-process only the failed tracks.

## Quick Start

```bash
# After an ingestion with failures
vectrola ingest ~/Music/NewAlbum
# Output shows: ❌ Errors: 3 tracks
#               Failed tracks saved. Run 'vectrola retry' to retry.

# View failed tracks
vectrola retry --list

# Retry all failed tracks
vectrola retry

# Clear the failed list
vectrola retry --clear
```

## Commands

### List Failed Tracks

```bash
vectrola retry --list
# or
vectrola retry -l
```

Shows all tracks that failed during previous ingestion:

```
Failed tracks (2):

  1. Song1.mp3 (local)
     Error: Model 'llama3.2:1b' not found
     Stage: llm | Attempts: 2 | 2026-06-12T10:30:00Z

  2. Song2.mp3 (gdrive)
     Error: LRClib timeout
     Stage: lyrics | Attempts: 1 | 2026-06-12T10:31:00Z
```

### Retry Failed Tracks

```bash
vectrola retry
```

Re-processes all failed tracks:

```
🔄 Retrying 2 failed track(s)...

[1/2] Song1.mp3
   ✓ Done: melancholic, romantic
[2/2] Song2.mp3
   ✗ Error: LRClib timeout

✅ Recovered: 1 track(s)
❌ Still failing: 1 track(s)
```

Successfully recovered tracks are automatically removed from the failed list.

### Clear Failed List

```bash
vectrola retry --clear
```

Removes all entries from the failed list (useful for starting fresh).

## How It Works

### Failure Tracking

When a track fails during `vectrola ingest` or `vectrola gdrive ingest`:

1. The error is logged to console
2. The track is saved to `~/.config/vectrola/failed_ingests.json`
3. A message prompts the user to run `vectrola retry`

### Automatic Cleanup

When you successfully re-ingest a previously failed track (via `retry` or running `ingest` again), it's automatically removed from the failed list.

### Error Stages

Failed tracks are categorized by error stage for easier debugging:

| Stage | Common Errors |
|-------|---------------|
| `download` | Google Drive download failed, file not found |
| `metadata` | Spotify API timeout, rate limiting |
| `lyrics` | LRClib/Genius timeout, no lyrics found |
| `llm` | Ollama not running, model not found |
| `storage` | Qdrant connection failed, embedding error |
| `unknown` | Uncategorized errors |

## Storage Format

Failed ingestions are stored in `~/.config/vectrola/failed_ingests.json`:

```json
{
  "version": 1,
  "failed": [
    {
      "id": "gdrive:1abc123",
      "name": "Song.mp3",
      "source": "gdrive",
      "source_path": "/Music/Song.mp3",
      "gdrive_file_id": "1abc123",
      "error": "Model 'llama3.2:1b' not found",
      "error_stage": "llm",
      "failed_at": "2026-06-12T10:30:00Z",
      "attempts": 1
    }
  ]
}
```

### Fields

| Field | Description |
|-------|-------------|
| `id` | Unique identifier (`gdrive:<file_id>` or `local:<path>`) |
| `name` | Display name (filename) |
| `source` | `"local"` or `"gdrive"` |
| `source_path` | Original file path |
| `gdrive_file_id` | Google Drive file ID (for gdrive source) |
| `error` | Error message |
| `error_stage` | Which pipeline stage failed |
| `failed_at` | ISO timestamp of last failure |
| `attempts` | Number of retry attempts |

## Troubleshooting

### Common Issues and Fixes

**LLM Errors (model not found)**
```bash
# Check if Ollama is running
ollama list

# Pull the model if missing
ollama pull llama3.2:1b

# Retry
vectrola retry
```

**Network Timeouts (lyrics, metadata)**
```bash
# Just retry - often transient
vectrola retry

# If persistent, check your network connection
```

**Qdrant Connection Failed**
```bash
# Check Qdrant status
vectrola status

# For local Qdrant
docker start qdrant

# Retry
vectrola retry
```

**File Not Found (local ingestion)**
```bash
# View the path
vectrola retry --list

# If file was moved/deleted, clear it
vectrola retry --clear
```

### Viewing Detailed Errors

The `--list` flag shows the full error message for each failed track. Use this to diagnose issues before retrying.

## Integration with Setup

The `vectrola setup` wizard helps prevent common failure causes:

1. **LLM Setup** - Ensures Ollama is running with a valid model
2. **Storage Setup** - Configures Qdrant connection
3. **Google Drive Setup** - Authenticates for cloud ingestion

Run `vectrola setup` after installation to minimize ingestion failures.
